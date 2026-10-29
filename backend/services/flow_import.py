"""Process flow as a file — `vb-process-flow/2.0` (design §7.2b, D-25; slice 1e-b spec). Piece (a1): the published
format (schema, worked example and the AI conversion prompt pack) and the export of one anchor's flow. Piece (a2):
the re-import in merge mode — validate and commit on the one bulk pipeline (VB law 8), staged one `import_row` per
file object (spec §3). Piece (b): new outside parties and flows, and replace mode — the step I/O and trigger links a
file's own steps leave out of a list they state are retired, or kept when a BR CRUD or an external flow needs them.

The file carries what the DFD is drawn from — steps, performers, inputs, outputs, triggers and external flows — and
no edges and no lanes (D-38). Export writes every list, empty as `[]`, so an export re-imported changes nothing
(spec §7, §10.1)."""
import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from models import (BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow, BfcNodeTrigger, BusinessRequirement, CodeMaster,
                    DataEntity, ExternalEntity, ImportBatch, ImportRow, ProcessTrigger)
from schemas.flow_file import FORMAT, FlowFile, json_schema
from services import audit, bfc, bulk, components, data_entity, external_entity, lifecycle, step_io, trigger, xlsx
from services.bulk import msg

PACK_PATH = Path(__file__).resolve().parent.parent / "assets" / "flow_prompt_pack.md"
APPROVED_SERVICE = "Claude Enterprise (FTC account)"                 # FI-6, FI-10: the only one

# The worked example of design §7.2b; tests prove it validates against the published schema (criterion 95).
EXAMPLE = {
    "format": FORMAT,
    "parent": {"hier_code": "01.02.03", "name": "Order to cash — order capture"},
    "mode": "merge",
    "external_entities": [{"key": "X1", "ext_number": None, "name": "Customer", "kind": "CUSTOMER"}],
    "steps": [
        {"key": "S1", "br_number": "BR-0012", "hier_code": "01.02.03.01", "row_version": 4,
         "name": "Receive order", "description": "The order arrives by phone or e-mail and is keyed in.",
         "performer": {"kind": "ORG_ROLE", "code": "SALES-ADMIN"},
         "triggers": [{"name": "Customer calls", "kind": "EVENT"}],
         "inputs": ["DE-0007"], "outputs": ["Sales order"],
         "external_flows": [{"external": "X1", "direction": "I", "data_entity": "DE-0007"}],
         "source_ref": "slide 4, shape 12"},
        {"key": "S2", "br_number": None, "hier_code": None, "row_version": None,
         "name": "Check credit", "description": "The customer's credit limit is checked against the order.",
         "performer": {"kind": "AI", "label": "Credit-scoring agent"},
         "inputs": ["Sales order"], "outputs": ["Credit decision"],
         "source_ref": "slide 4, shape 15"},
    ],
}


@cache
def _pack() -> str:
    return PACK_PATH.read_text(encoding="utf-8")


def schema() -> dict:
    """GET /process-flow-json/schema: the format, its generated JSON Schema, the worked example and the prompt
    pack. The pack is for Claude Enterprise under FTC's account only (FI-6, FI-10); its first section tells the
    consultant so, and to remove personal data before pasting (VB-013)."""
    pack = _pack()
    rules = pack.split("## Before you start", 1)[1].split("\n---", 1)[0]
    return {"format": FORMAT, "approved_ai_service": APPROVED_SERVICE,
            "ai_rules": "Before you start" + rules.rstrip(),      # travels with a saved schema file (sara L3)
            "schema": json_schema(), "example": EXAMPLE, "prompt_pack": pack}


def check_anchor(db: Session, node: BfcNode, lock: bool = True) -> None:
    """Spec §4 rule 6: an anchor is a live parent node at level 2–4 (its children sit at a process level), and
    its chart's DFD component is on (P3). Shared by export (a read: lock=False) and import (locked)."""
    if not node.is_active:
        raise HTTPException(422, "This node is retired. Restore it first")
    if node.is_process:
        raise HTTPException(422, "A process step has no flow under it. Choose its parent node")
    if node.level_no + 1 not in bfc.PROCESS_LEVELS:
        raise HTTPException(422, "A flow sits under a node whose children can be processes "
                                 f"(levels {bfc.PROCESS_LEVELS[0] - 1} to {bfc.PROCESS_LEVELS[-1] - 1})")
    components.require_on(db, node.project_id, components.node_dfd_component(node), lock)    # 409 COMPONENT_OFF


def _children(db: Session, anchor: BfcNode) -> list[BfcNode]:
    """The anchor's live direct process children, in chart order (FI-9: only these are a file's steps)."""
    return list(db.scalars(select(BfcNode).where(
        BfcNode.project_id == anchor.project_id, BfcNode.parent_bfc_node_id == anchor.bfc_node_id,
        BfcNode.is_active, BfcNode.is_process).order_by(BfcNode.seq_no)))


def _performer(db: Session, node: BfcNode) -> dict | None:
    p = bfc.describe_performer(db, node)
    if p is None:
        return None
    return {"kind": "AI", "label": p["name"]} if p["kind"] == "AI" else {"kind": p["kind"], "code": p["code"]}


def export(db: Session, anchor: BfcNode) -> dict:
    """The anchor's direct process children as `vb-process-flow/2.0` (spec §7). Every list is written, empty as
    `[]`, so replace mode on an unchanged export retires nothing. A to-be step carries its BR number (its
    identity, R2-D1); an as-is step has none and is matched by name."""
    check_anchor(db, anchor, lock=False)
    steps = _children(db, anchor)
    if not steps:
        raise HTTPException(422, "There are no process steps under this node to export")
    ids = [s.bfc_node_id for s in steps]
    pid = anchor.project_id

    brs: dict[int, str] = {}
    if anchor.bfc_set_code == "TO_BE" and ids:
        for node_id, number in db.execute(select(BusinessRequirement.bfc_node_id, BusinessRequirement.br_number)
                                          .where(BusinessRequirement.project_id == pid,
                                                 BusinessRequirement.bfc_node_id.in_(ids),
                                                 BusinessRequirement.is_active)):
            brs[node_id] = number

    triggers: dict[int, list[dict]] = {i: [] for i in ids}
    for node_id, name, kind in db.execute(
            select(BfcNodeTrigger.bfc_node_id, ProcessTrigger.trigger_name, ProcessTrigger.trigger_kind)
            .join(ProcessTrigger, ProcessTrigger.process_trigger_id == BfcNodeTrigger.process_trigger_id)
            .where(BfcNodeTrigger.project_id == pid, BfcNodeTrigger.bfc_node_id.in_(ids),
                   BfcNodeTrigger.is_active, ProcessTrigger.is_active)
            .order_by(ProcessTrigger.trigger_name)):
        triggers[node_id].append({"name": name, "kind": kind})

    io: dict[tuple[int, str], list[str]] = {(i, d): [] for i in ids for d in ("I", "O")}
    for node_id, direction, number in db.execute(
            select(BfcNodeDataEntity.bfc_node_id, BfcNodeDataEntity.direction, DataEntity.de_number)
            .join(DataEntity, DataEntity.data_entity_id == BfcNodeDataEntity.data_entity_id)
            .where(BfcNodeDataEntity.project_id == pid, BfcNodeDataEntity.bfc_node_id.in_(ids),
                   BfcNodeDataEntity.is_active, DataEntity.is_active)
            .order_by(DataEntity.de_number)):
        io[(node_id, direction)].append(number)

    flows = db.execute(
        select(BfcNodeExternalFlow, ExternalEntity, DataEntity.de_number)
        .join(ExternalEntity, ExternalEntity.external_entity_id == BfcNodeExternalFlow.external_entity_id)
        .outerjoin(DataEntity, DataEntity.data_entity_id == BfcNodeExternalFlow.data_entity_id)
        .where(BfcNodeExternalFlow.project_id == pid, BfcNodeExternalFlow.bfc_node_id.in_(ids),
               BfcNodeExternalFlow.is_active, ExternalEntity.is_active)
        .order_by(ExternalEntity.ext_number, BfcNodeExternalFlow.direction, DataEntity.de_number)).all()
    parties: dict[int, dict] = {}
    step_flows: dict[int, list[dict]] = {i: [] for i in ids}
    for flow, party, number in flows:
        if party.external_entity_id not in parties:
            kind = db.get(CodeMaster, party.kind_code_id).code if party.kind_code_id else None
            parties[party.external_entity_id] = {"key": f"X{len(parties) + 1}", "ext_number": party.ext_number,
                                                 "name": party.ext_name, "kind": kind}
        step_flows[flow.bfc_node_id].append({"external": parties[party.external_entity_id]["key"],
                                             "direction": flow.direction, "data_entity": number})

    return {
        "format": FORMAT,
        "parent": {"hier_code": anchor.hier_code, "name": anchor.node_name},
        "mode": "merge",
        "external_entities": list(parties.values()),
        "steps": [{"key": f"S{n}", "br_number": brs.get(s.bfc_node_id), "hier_code": s.hier_code,
                   "row_version": s.row_version, "name": s.node_name, "description": s.data_processing_desc,
                   "performer": _performer(db, s), "triggers": triggers[s.bfc_node_id],
                   "inputs": io[(s.bfc_node_id, "I")], "outputs": io[(s.bfc_node_id, "O")],
                   "external_flows": step_flows[s.bfc_node_id]}
                  for n, s in enumerate(steps, 1)],
    }


def download_name(anchor: BfcNode) -> str:
    """Server-made, never from user text (§7.11): the chart and the anchor's code."""
    return f"vb-flow-{anchor.bfc_set_code.lower().replace('_', '')}-{anchor.hier_code}.json"


# ==== the import (piece a2) ==========================================================================================
TARGET = "PROCESS_FLOW"
SLUG = "process-flow"
MODES = ("merge", "replace")
DE_NUMBER = re.compile(r"^DE-\d+$")                  # spec §3: a DE number is always a number, never a name
KEY_CAP = 250                                        # import_row.business_key


def clean(value: str | None) -> str | None:
    """Rule 13 (D4): every name and reference is cleaned as 1e-a cleans a cell — Unicode whitespace and invisible
    edge characters stripped — and inner runs of space collapsed; empty → None. Matching then uses
    bfc.normalise_name, for steps, data entities, triggers and parties alike."""
    value = xlsx.clean_cell(value)
    return re.sub(r"\s+", " ", value) if isinstance(value, str) else value


def _norm(value: str) -> str:
    return bfc.normalise_name(value)


@dataclass
class Row:
    """One file object on its way through validate or commit (spec §3)."""
    kind: str
    path: str
    verdict: str = "MATCH"
    business_key: str | None = None
    local_key: str | None = None
    source_ref: str | None = None
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    obj: dict | None = None              # the file object itself (STEP, EXTERNAL_ENTITY): commit re-reads it
    pins: dict = field(default_factory=dict)   # what it resolved to; a different resolution at commit is an error
    plan: dict = field(default_factory=dict)   # what the apply needs and the preview shows
    target_id: int | None = None
    target: dict | None = None           # a RETIRE or KEPT row: what it acts on, {table, id, label} (S4-2)

    @property
    def pair(self) -> tuple[str, str]:
        """D5: a re-checked row meets its staged row by (row_kind, source_path); a RETIRE or KEPT row, which has no
        path, by what it acts on."""
        return (self.kind, self.path) if self.path is not None else (self.kind, _target_key(self.target))


def _target_key(target: dict) -> str:
    return f"{target['table']}:{target['id']}"


def _stored_pair(r: ImportRow) -> tuple[str, str]:
    return (r.row_kind, r.source_path) if r.source_path is not None else (r.row_kind, _target_key(r.payload["target"]))


# ---- reading the file (file-level: 422, nothing staged) ------------------------------------------------------------

def _reject_constant(name: str):
    raise ValueError(f"{name} is not a number JSON allows")


def _no_duplicate_keys(pairs: list[tuple]) -> dict:
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise ValueError(f"the key \"{k[:40]}\" appears twice in one object")
        seen[k] = v
    return seen


def read_file(body: bytes) -> dict:
    """§7.12a: valid UTF-8 JSON, no NaN / Infinity, no repeated key, not nested past what the stack allows; then the
    strict 2.0 model (unknown keys refused, so `edges` and `lanes` are, D-38). Returns the file as given — a key
    left out stays left out (rules 2, 3, 12)."""
    try:
        raw = json.loads(body.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_no_duplicate_keys)
    except RecursionError:
        raise HTTPException(422, "This file is nested too deeply to read. Nothing was staged.")
    except (UnicodeDecodeError, ValueError) as e:
        raise HTTPException(422, f"This is not a readable JSON file ({str(e)[:200]}). Nothing was staged.")
    if not isinstance(raw, dict):
        raise HTTPException(422, "This is not a vb-process-flow file. Nothing was staged.")
    fmt = raw.get("format")
    if fmt != FORMAT:
        if isinstance(fmt, str) and fmt.startswith("vb-process-flow/1"):
            raise HTTPException(422, "This is a vb-process-flow 1.0 file. Re-export the flow from VB and edit the new "
                                     "file. Nothing was staged.")
        raise HTTPException(422, f"This is not a {FORMAT} file. Nothing was staged.")
    try:
        doc = FlowFile.model_validate(raw)
    except ValidationError as e:
        where = "; ".join(f"/{'/'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()[:5])
        more = f" (and {e.error_count() - 5} more)" if e.error_count() > 5 else ""
        raise HTTPException(422, f"This file does not follow the {FORMAT} format — {where}{more}. Nothing was staged.")
    for what, items in (("step", doc.steps), ("external party", doc.external_entities)):
        keys = [i.key for i in items]
        if (dup := next((k for k in keys if keys.count(k) > 1), None)) is not None:
            raise HTTPException(422, f"Two {what} entries share the key \"{dup}\"; a key is unique in the file. "
                                     "Nothing was staged.")
    return doc.model_dump(exclude_unset=True)


def _anchor(db: Session, project_id: int, anchor_id: int, lock: bool) -> BfcNode:
    anchor = db.get(BfcNode, anchor_id)
    if anchor is None or anchor.project_id != project_id:
        raise HTTPException(404, "Not found")
    if lock:
        lifecycle.lock(db, anchor)                   # two imports into one anchor take turns
    check_anchor(db, anchor, lock=lock)              # rule 6 and P3: the anchor's chart's DFD component
    return anchor


# ---- resolving the file against the database (validate, and again at commit under lock) ----------------------------

def _performer_text(p: dict | None) -> str | None:
    if p is None:
        return None
    return f"{p['kind']} {p['code']}" if p["kind"] != "AI" else f"AI {p['name']}"


def _performer_key(p: dict | None):
    return None if p is None else (p["kind"], p["ref_id"] if p["kind"] != "AI" else p["name"])


class _Resolver:
    """Rules 1–17 of spec §4. Run at validate, and at commit under the batch's locks; both runs must agree row for
    row (rule 14, D5), RETIRE and KEPT rows included (§7.2b: the RETIRE set re-computed inside the lock)."""

    def __init__(self, db: Session, anchor: BfcNode, doc: dict, lock: bool, mode: str = "merge"):
        self.db, self.anchor, self.doc, self.lock, self.mode = db, anchor, doc, lock, mode
        self.pid = anchor.project_id
        self.to_be = anchor.bfc_set_code == "TO_BE"
        self.rows: list[Row] = []
        self.step_nodes: dict[int, BfcNode | None] = {}
        self.unmatched: list[BfcNode] = []

    def run(self) -> list[Row]:
        db = self.db
        q = select(BfcNode).where(BfcNode.project_id == self.pid,
                                  BfcNode.parent_bfc_node_id == self.anchor.bfc_node_id, BfcNode.is_active)
        if self.lock:                                # at commit: held, and read fresh (rule 14)
            q = q.order_by(BfcNode.bfc_node_id).with_for_update(of=BfcNode) \
                .execution_options(populate_existing=True)
        children = sorted(db.scalars(q), key=lambda n: n.seq_no)
        self.children = children
        self.processes = {c.bfc_node_id: c for c in children if c.is_process}
        self.by_name: dict[str, BfcNode] = {}
        for c in children:
            self.by_name.setdefault(_norm(c.node_name), c)
        steps = self.doc["steps"]
        self._steps(steps)
        self._parties()
        self._links(steps)
        if self.mode == "replace":
            self._replace(steps)
        taken = {n.bfc_node_id for n in self.step_nodes.values() if n is not None}
        self.unmatched = [p for p in self.processes.values() if p.bfc_node_id not in taken]
        self._near_duplicates()
        self._unique_keys()
        return self.rows

    # -- steps (rules 1, 4, 5, 11, 12, 14, 15) --
    def _steps(self, steps: list[dict]) -> None:
        db, anchor = self.db, self.anchor
        numbers = sorted({clean(s["br_number"]) for s in steps if s.get("br_number")})
        brs = dict(db.execute(select(BusinessRequirement.br_number, BusinessRequirement.bfc_node_id).where(
            BusinessRequirement.project_id == self.pid, BusinessRequirement.is_active,
            BusinessRequirement.br_number.in_(numbers))).all()) if numbers else {}
        taken: dict[int, str] = {}
        names: dict[str, str] = {}
        new = 0
        for i, s in enumerate(steps):
            key, name = s["key"], clean(s["name"])
            r = Row("STEP", f"/steps/{i}", local_key=key, source_ref=s.get("source_ref"), obj=s)
            self.rows.append(r)
            if not name:
                r.errors.append(msg("NAME_REQUIRED", "Name the step.", "name"))
                name = ""
            nkey = _norm(name)
            node = None
            number = clean(s.get("br_number"))
            if number:
                r.business_key = number
                if not self.to_be:
                    r.errors.append(msg("BR_ON_AS_IS", "An as-is step has no BR number; it is matched by its name. "
                                        "Remove br_number.", "br_number"))
                elif s.get("row_version") is None:                                      # rule 11 (D1)
                    r.errors.append(msg("BR_NEEDS_VERSION", "BR numbers come only from a VB export — remove it or "
                                        "re-export.", "br_number", br_number=number))
                elif number not in brs:
                    r.errors.append(msg("BR_UNKNOWN", f"There is no live {number} in this project.", "br_number",
                                        br_number=number))
                elif brs[number] not in self.processes:                                 # rule 5 (FI-9)
                    r.errors.append(msg("BR_OUT_OF_SCOPE", f"{number}'s step is not directly under {anchor.hier_code}; "
                                        "a file updates only the steps directly under the node you chose.",
                                        "br_number", br_number=number, anchor=anchor.hier_code))
                else:
                    node = self.processes[brs[number]]
            else:
                r.business_key = nkey[:KEY_CAP] or None
                live = self.by_name.get(nkey)
                if live is not None and live.is_process:                                # design rule 2 (R2-P1)
                    node = live
                    r.warnings.append(msg("MATCHED_BY_NAME", f"Matched existing step {live.hier_code} by name.",
                                          "name", hier_code=live.hier_code))
                if s.get("hier_code") and self.to_be:
                    r.errors.append(msg("HIER_WITHOUT_BR", "hier_code is a cross-check of br_number, not an "
                                        "identity. Remove it, or re-export.", "hier_code"))
                elif s.get("hier_code") and node is None:
                    r.errors.append(msg("AS_IS_NOT_FOUND", f"No live step named '{name}' sits under "
                                        f"{anchor.hier_code}; an as-is step is matched by its name. Re-export, or "
                                        "remove hier_code to add it as a new step.", "hier_code"))
            if node is not None:
                if clean(s.get("hier_code")) and clean(s["hier_code"]) != node.hier_code:      # sara L1
                    r.errors.append(msg("MOVED", f"{number or name} moved since export: now {node.hier_code}, file "
                                        f"says {s['hier_code']} — re-export.", "hier_code",
                                        now=node.hier_code, file=s["hier_code"]))
                if s.get("row_version") is not None and s["row_version"] != node.row_version:   # rule 4 (FI-3)
                    perf = _performer_text(bfc.describe_performer(db, node)) or "none"
                    desc = node.data_processing_desc or ""
                    r.errors.append(msg("STALE", f"This step changed in VB since the export. It is now named "
                                        f"'{node.node_name}', performer {perf}, description "
                                        f"'{desc[:120]}{'…' if len(desc) > 120 else ''}'. Re-export and edit again.",
                                        "row_version", name=node.node_name, performer=perf, description=desc[:120]))
                if node.bfc_node_id in taken:
                    r.errors.append(msg("TWO_STEPS_ONE_NODE", f"Step {taken[node.bfc_node_id]} already matches "
                                        f"{node.hier_code}.", None, hier_code=node.hier_code))
                    node = None
                else:
                    taken[node.bfc_node_id] = key
            if nkey and nkey in names:                                                  # Q1
                r.errors.append(msg("NAME_REPEATED", f"Step {names[nkey]} in this file has the same name.", "name"))
            names.setdefault(nkey, key)
            clash = self.by_name.get(nkey)
            if nkey and clash is not None and (node is None or clash.bfc_node_id != node.bfc_node_id) \
                    and not any(e["code"] in ("TWO_STEPS_ONE_NODE",) for e in r.errors):   # rule 5
                r.errors.append(msg("NAME_TAKEN", f"'{name}' already exists under {anchor.hier_code} "
                                    f"({clash.hier_code}).", "name", hier_code=clash.hier_code))
            if node is None and not r.errors:
                new += 1
                if len(self.children) + new > bfc.MAX_SIBLINGS:
                    r.errors.append(msg("TOO_MANY", f"A node holds at most {bfc.MAX_SIBLINGS} children.", None))
            self.step_nodes[i] = node
            self._step_values(r, s, name, node)

    def _step_values(self, r: Row, s: dict, name: str, node: BfcNode | None) -> None:
        """What the step would write (rules 3, 12), and its verdict: UPDATE when the name, description or performer
        changes, MATCH when nothing does, INSERT for a new step."""
        values = {"node_name": name}
        if "description" in s:
            # Rule 12: a description is text, not a name — kept exactly as given (line breaks and all, so an export
            # round-trips); only an empty or blank one clears it (sara H1).
            d = s["description"]
            values["description"] = d if d is not None and d.strip() else None
        perf = self._performer(r, s)
        if perf is not _KEEP:
            values["performer"] = perf
        r.plan["values"] = values
        if node is None:
            r.verdict = "INSERT"
            return
        r.target_id = node.bfc_node_id
        r.pins = {"node": node.bfc_node_id, "row_version": node.row_version}            # rule 14 (D2)
        if _step_changes(self.db, node, values):
            r.verdict = "UPDATE"

    def _performer(self, step: Row, s: dict):
        """Rule 3 (FI-2): absent → keep; null → clear; a known live code → that performer; an unknown or retired one
        → keep, with a warning. One PERFORMER row (MATCH only) per step that names one."""
        if "performer" not in s:
            return _KEEP
        p = s["performer"]
        if p is None:
            return None
        i = step.path.rsplit("/", 1)[1]
        r = Row("PERFORMER", f"/steps/{i}/performer")
        self.rows.append(r)
        if p["kind"] == "AI":
            label = clean(p["label"])
            r.business_key = f"{step.local_key}/AI"
            if not label:                              # sara M2: caught here, never at commit
                r.errors.append(msg("NAME_REQUIRED", "Name the AI that performs this step.", "performer"))
                return _KEEP
            found = {"kind": "AI", "code": None, "name": label, "ref_id": None}
        else:
            code = clean(p["code"]) or ""
            r.business_key = f"{step.local_key}/{p['kind']}:{code.upper()}"[:KEY_CAP]
            row = bfc.performer_row(self.db, self.pid, p["kind"], code) if code else None
            if row is None or not row.is_active:
                r.warnings.append(msg("UNKNOWN_PERFORMER", f"No live {p['kind'].replace('_', ' ').lower()} '{code}' "
                                      "in this project — the step keeps its current performer.", "performer",
                                      kind=p["kind"], value=code))
                r.pins = {"performer": None}
                return _KEEP
            found = {"kind": p["kind"], "code": code.upper(), "name": None, "ref_id": bfc.performer_ref(row, p["kind"])}
        r.target_id = found["ref_id"]
        r.pins = {"performer": list(_performer_key(found))}
        r.plan = {"performer": found}
        return found

    # -- external parties (rule 8; piece a: matched only) --
    def _parties(self) -> None:
        db = self.db
        live = list(db.scalars(select(ExternalEntity).where(ExternalEntity.project_id == self.pid,
                                                            ExternalEntity.is_active)))
        by_number = {p.ext_number: p for p in live}
        by_name: dict[str, list[ExternalEntity]] = {}
        for p in live:
            by_name.setdefault(_norm(p.ext_name), []).append(p)
        self.party_keys: dict[str, ExternalEntity | None] = {}
        self.party_rows: dict[str, Row] = {}
        new_names: dict[str, str] = {}
        for k, e in enumerate(self.doc.get("external_entities", [])):
            r = Row("EXTERNAL_ENTITY", f"/external_entities/{k}", local_key=e["key"], obj=e)
            self.rows.append(r)
            self.party_rows[e["key"]] = r
            name, number = clean(e["name"]) or "", clean(e.get("ext_number"))
            party = None
            if number:
                r.business_key = number
                party = by_number.get(number)
                if party is None:
                    r.errors.append(msg("PARTY_UNKNOWN", f"There is no live {number} in this project.", "ext_number",
                                        ext_number=number))
            else:
                r.business_key = _norm(name)[:KEY_CAP] or None
                found = by_name.get(_norm(name), [])
                if len(found) > 1:                                                       # N2
                    r.errors.append(msg("NAME_AMBIGUOUS", f"'{name}' matches {found[0].ext_number} and "
                                        f"{found[1].ext_number}. Name it by its number.", "name"))
                elif found:
                    party = found[0]
                else:
                    self._new_party(r, e, name, new_names)
            if party is not None:
                r.target_id = party.external_entity_id
                r.pins = {"party": party.external_entity_id}
                kind = db.get(CodeMaster, party.kind_code_id).code if party.kind_code_id else None
                if e.get("kind") and e["kind"] != kind:
                    r.warnings.append(msg("KIND_KEPT", f"{party.ext_number} keeps its kind {kind or '(none)'}; an "
                                          "import never changes a party.", "kind", kind=kind))
            self.party_keys[e["key"]] = party

    def _new_party(self, r: Row, e: dict, name: str, new_names: dict[str, str]) -> None:
        """Rule 8: a party named by no `ext_number` and no live name is created at commit, its EXT number minted
        then (§9.8). Its kind must be a live EXTERNAL_ENTITY_KIND code of this project; one new name given twice in
        the file is one party, so the second entry is an error."""
        r.verdict = "INSERT"
        if not name:
            r.errors.append(msg("NAME_REQUIRED", "Name the external party.", "name"))
            return
        if _norm(name) in new_names:
            r.errors.append(msg("NAME_REPEATED", f"Party {new_names[_norm(name)]} in this file has the same name.",
                                "name"))
            return
        new_names[_norm(name)] = e["key"]
        kind = clean(e.get("kind"))
        try:
            external_entity.kind_code_id(self.db, self.pid, kind)
        except HTTPException:
            r.errors.append(msg("KIND_UNKNOWN", f"'{kind}' is not an external party kind in this project.", "kind",
                                kind=kind))
            return
        r.plan = {"name": name, "kind": kind}
        r.warnings.append(msg("NEW_PARTY", f"'{name}' is not an external party yet; it will be created.", "name"))

    # -- triggers, inputs and outputs, external flows (rules 2, 7, 10, 13) --
    def _links(self, steps: list[dict]) -> None:
        db = self.db
        trigs: dict[str, list[ProcessTrigger]] = {}
        for t in db.scalars(select(ProcessTrigger).where(ProcessTrigger.project_id == self.pid,
                                                         ProcessTrigger.is_active)):
            trigs.setdefault(_norm(t.trigger_name), []).append(t)
        des = list(db.scalars(select(DataEntity).where(DataEntity.project_id == self.pid, DataEntity.is_active)))
        self.de_by_number = {d.de_number: d for d in des}
        self.de_by_name: dict[str, list[DataEntity]] = {}
        for d in des:
            self.de_by_name.setdefault(_norm(d.de_name), []).append(d)
        self.trigger_rows: dict[str, Row] = {}
        self.de_rows: dict[str, Row] = {}
        for i, s in enumerate(steps):
            node, key = self.step_nodes.get(i), s["key"]
            if s.get("triggers") is not None:
                seen: dict[str, Row] = {}
                for j, t in enumerate(s["triggers"]):
                    path = f"/steps/{i}/triggers/{j}"
                    tname = clean(t["name"]) or ""
                    tk = _norm(tname)
                    tr = self._trigger(tk, tname, t["kind"], path, trigs)
                    if tk in seen:
                        seen[tk].warnings.append(msg("REPEATED", f"'{tname}' is listed twice for this step; it is "
                                                     "one link.", None))
                        continue
                    lr = Row("STEP_TRIGGER", path, business_key=f"{key}/{tname}"[:KEY_CAP],
                             plan={"step": i, "trigger": tk})
                    seen[tk] = lr
                    self.rows.append(lr)
                    link = None
                    if node is not None and tr.target_id is not None:
                        link = db.scalars(select(BfcNodeTrigger).where(
                            BfcNodeTrigger.bfc_node_id == node.bfc_node_id,
                            BfcNodeTrigger.process_trigger_id == tr.target_id)).one_or_none()
                    self._link_verdict(lr, link)
            io_seen: dict[tuple, Row] = {}
            for direction, field_name in (("I", "inputs"), ("O", "outputs")):
                for j, ref in enumerate(s.get(field_name) or []):
                    self._io(i, key, node, direction, ref, f"/steps/{i}/{field_name}/{j}", io_seen)
            flow_seen: dict[tuple, Row] = {}
            for k, f in enumerate(s.get("external_flows") or []):
                path = f"/steps/{i}/external_flows/{k}"
                self._flow(i, key, node, f, path, io_seen, flow_seen)

    def _trigger(self, tk: str, tname: str, kind: str, path: str, trigs: dict) -> Row:
        tr = self.trigger_rows.get(tk)
        if tr is not None:
            if tr.verdict == "INSERT" and tr.plan["kind"] != kind and \
                    not any(e["code"] == "TWO_KINDS" for e in tr.errors):                # rule 7
                tr.errors.append(msg("TWO_KINDS", f"The new trigger '{tname}' is given two kinds in this file.",
                                     "kind"))
            return tr
        tr = Row("TRIGGER", path, business_key=tk[:KEY_CAP] or None)
        self.trigger_rows[tk] = tr
        self.rows.append(tr)
        live = trigs.get(tk, [])
        if not tname:
            tr.errors.append(msg("NAME_REQUIRED", "Name the trigger.", "name"))
        elif len(live) > 1:                                                              # N2
            tr.errors.append(msg("NAME_AMBIGUOUS", f"'{tname}' matches two live triggers: '{live[0].trigger_name}' "
                                 f"and '{live[1].trigger_name}'.", "name"))
        elif live:
            tr.target_id = live[0].process_trigger_id
            tr.pins = {"trigger": tr.target_id}
            if live[0].trigger_kind != kind:
                tr.warnings.append(msg("KIND_KEPT", f"'{live[0].trigger_name}' keeps its kind "
                                       f"{live[0].trigger_kind}.", "kind", kind=live[0].trigger_kind))
        else:
            tr.verdict = "INSERT"
            tr.plan = {"name": tname, "kind": kind}
            tr.warnings.append(msg("NEW_TRIGGER", f"'{tname}' is not in the trigger catalogue; it will be added.",
                                   "name"))
        return tr

    def _de(self, ref: str, path: str) -> Row:
        """A data entity reference, by `DE-nnnn` or by name: one DATA_ENTITY row per distinct reference (§3)."""
        ref = clean(ref) or ""
        by_number = bool(DE_NUMBER.match(ref))
        rk = ref if by_number else f"name:{_norm(ref)}"
        r = self.de_rows.get(rk)
        if r is not None:
            return r
        r = Row("DATA_ENTITY", path, business_key=(ref if by_number else _norm(ref))[:KEY_CAP] or None,
                plan={"ref": rk})
        self.de_rows[rk] = r
        self.rows.append(r)
        if by_number:
            de = self.de_by_number.get(ref)
            if de is None:
                r.errors.append(msg("DE_UNKNOWN", f"There is no live {ref} in this project.", None, de_number=ref))
            else:
                r.target_id = de.data_entity_id
        else:
            found = self.de_by_name.get(_norm(ref), [])
            if not ref:
                r.errors.append(msg("NAME_REQUIRED", "Name the data entity.", None))
            elif len(found) > 1:                                                         # N2
                r.errors.append(msg("NAME_AMBIGUOUS", f"'{ref}' matches {found[0].de_number} and "
                                    f"{found[1].de_number}. Name it by its number.", None))
            elif found:
                r.target_id = found[0].data_entity_id
            else:
                r.verdict = "INSERT"
                r.plan["name"] = ref
                r.warnings.append(msg("NEW_DATA_ENTITY", f"'{ref}' is not a data entity yet; it will be created.",
                                      None))
        if r.target_id is not None:
            r.pins = {"data_entity": r.target_id}
        return r

    def _io(self, i: int, key: str, node: BfcNode | None, direction: str, ref: str, path: str,
            seen: dict) -> Row | None:
        """One STEP_IO row per resolved (step, entity, direction); a repeat is a warning (rule 13)."""
        der = self._de(ref, path)
        grain = (direction, der.target_id if der.target_id is not None else der.plan["ref"])
        if grain in seen:
            seen[grain].warnings.append(msg("REPEATED", f"{clean(ref)} is named twice as this step's "
                                            f"{'input' if direction == 'I' else 'output'}; it is one link.", None))
            return seen[grain]
        r = Row("STEP_IO", path, business_key=f"{key}/{direction}/{clean(ref)}"[:KEY_CAP],
                plan={"step": i, "de": der.plan["ref"], "direction": direction})
        seen[grain] = r
        self.rows.append(r)
        link = None
        if node is not None and der.target_id is not None:
            link = self.db.scalars(select(BfcNodeDataEntity).where(
                BfcNodeDataEntity.bfc_node_id == node.bfc_node_id,
                BfcNodeDataEntity.data_entity_id == der.target_id,
                BfcNodeDataEntity.direction == direction)).one_or_none()
        self._link_verdict(r, link)
        return r

    def _flow(self, i: int, key: str, node: BfcNode | None, f: dict, path: str, io_seen: dict,
              seen: dict) -> None:
        """Rules 8 and 10 (FI-4): a flow implies its step I/O; a live flow is MATCH, a retired one is restored (it
        keeps its old label and note), and a new one — to a new or known party, from a new or known step — is
        created at commit by bfc.link_external_flow. One row per resolved (party, direction, entity) of a step."""
        ref = clean(f.get("data_entity"))
        bkey = f"{key}/{f['external']}/{f['direction']}/{ref or '-'}"[:KEY_CAP]
        der = self._io(i, key, node, f["direction"], f["data_entity"], path, io_seen) if ref else None
        de_row = self.de_rows[der.plan["de"]] if der is not None else None
        if f["external"] not in self.party_keys:
            r = Row("EXTERNAL_FLOW", path, verdict="INSERT", business_key=bkey)
            self.rows.append(r)
            r.errors.append(msg("FLOW_PARTY_UNKNOWN", f"No entry in external_entities has the key "
                                f"\"{f['external']}\".", "external"))
            return
        party = self.party_keys[f["external"]]
        de_id = de_row.target_id if de_row is not None else None
        grain = (party.external_entity_id if party is not None else f["external"], f["direction"],
                 (de_id if de_id is not None else de_row.plan["ref"]) if de_row is not None else None)
        if grain in seen:
            seen[grain].warnings.append(msg("REPEATED", "This flow is listed twice for this step; it is one flow.",
                                            None))
            return
        r = Row("EXTERNAL_FLOW", path, business_key=bkey,
                plan={"step": i, "party": f["external"], "direction": f["direction"],
                      "de": der.plan["de"] if der is not None else None})
        seen[grain] = r
        self.rows.append(r)
        flow = None
        if node is not None and party is not None and (ref is None or de_id is not None):
            de_match = (BfcNodeExternalFlow.data_entity_id == de_id) if de_id is not None \
                else BfcNodeExternalFlow.data_entity_id.is_(None)
            flow = self.db.scalars(select(BfcNodeExternalFlow).where(
                BfcNodeExternalFlow.bfc_node_id == node.bfc_node_id,
                BfcNodeExternalFlow.external_entity_id == party.external_entity_id,
                BfcNodeExternalFlow.direction == f["direction"], de_match)).one_or_none()
        self._link_verdict(r, flow)

    # -- replace mode (rule 9, FI-1, FI-4; design §7.2b rule 8) --
    def _replace(self, steps: list[dict]) -> None:
        """For each file step resolved to a live step, and only for the lists it states: every live input or output
        (of a live data entity) outside the file's I/O set — its `inputs`, `outputs` and what its own external flows
        imply — is staged RETIRE, or KEPT with a warning when a BR CRUD or an external flow needs it; every live
        trigger link (of a live catalogue trigger) the file does not list is staged RETIRE. Nothing else is ever
        staged for retirement: steps, BRs, performers, parties, external flows, data entities, catalogue triggers."""
        db = self.db
        for i, s in enumerate(steps):
            node = self.step_nodes.get(i)
            if node is None:
                continue
            key = s["key"]
            mine = [r for r in self.rows if r.plan.get("step") == i and r.path is not None]
            directions = [d for d, name in (("I", "inputs"), ("O", "outputs")) if s.get(name) is not None]
            if directions:
                keep = {(r.plan["direction"], self.de_rows[r.plan["de"]].target_id)
                        for r in mine if r.kind == "STEP_IO"}
                links = db.execute(select(BfcNodeDataEntity, DataEntity)
                                   .join(DataEntity, DataEntity.data_entity_id == BfcNodeDataEntity.data_entity_id)
                                   .where(BfcNodeDataEntity.bfc_node_id == node.bfc_node_id,
                                          BfcNodeDataEntity.direction.in_(directions),
                                          BfcNodeDataEntity.is_active, DataEntity.is_active)
                                   .order_by(BfcNodeDataEntity.direction, DataEntity.de_number)).all()
                for link, de in links:
                    if (link.direction, link.data_entity_id) in keep:
                        continue
                    what = "input" if link.direction == "I" else "output"
                    r = self._retire_row("STEP_IO", i, f"{key}/{link.direction}/{de.de_number}", link,
                                         "bfc_node_data_entity",
                                         f"{node.hier_code} {node.node_name} — {what} {de.de_number} {de.de_name}")
                    if needs := step_io.dependents(db, link):
                        r.verdict = "KEPT"
                        r.warnings.append(msg("KEPT_DEPENDENT", f"{de.de_number} {de.de_name} stays this step's "
                                              f"{what}: still needed by {', '.join(needs)}.", None,
                                              dependents=needs))
            if s.get("triggers") is not None:
                keep = {self.trigger_rows[r.plan["trigger"]].target_id for r in mine if r.kind == "STEP_TRIGGER"}
                links = db.execute(select(BfcNodeTrigger, ProcessTrigger)
                                   .join(ProcessTrigger,
                                         ProcessTrigger.process_trigger_id == BfcNodeTrigger.process_trigger_id)
                                   .where(BfcNodeTrigger.bfc_node_id == node.bfc_node_id, BfcNodeTrigger.is_active,
                                          ProcessTrigger.is_active)
                                   .order_by(ProcessTrigger.trigger_name)).all()
                for link, t in links:
                    if link.process_trigger_id not in keep:
                        self._retire_row("STEP_TRIGGER", i, f"{key}/{t.trigger_name}", link, "bfc_node_trigger",
                                         f"{node.hier_code} {node.node_name} — trigger {t.trigger_name}")

    def _retire_row(self, kind: str, i: int, business_key: str, link, table: str, label: str) -> Row:
        link_id = getattr(link, link.__mapper__.primary_key[0].name)
        r = Row(kind, None, verdict="RETIRE", business_key=business_key[:KEY_CAP], plan={"step": i},
                target={"table": table, "id": link_id, "label": label})
        r.target_id = link_id
        r.pins = {"link": link_id, "row_version": link.row_version}       # an edit after the preview → rejected
        self.rows.append(r)
        return r

    @staticmethod
    def _link_verdict(r: Row, link) -> None:
        """Rule 10: a live link is MATCH and its writer never called; a retired one is restored (INSERT)."""
        if link is not None and link.is_active:
            r.target_id = getattr(link, link.__mapper__.primary_key[0].name)
            r.pins = {"link": r.target_id}
        else:
            r.verdict = "INSERT"
            if link is not None:
                r.plan["restore"] = True
                r.pins = {"restore": getattr(link, link.__mapper__.primary_key[0].name)}

    # -- rule 16 (P2): what the file did not name, and near-duplicates of it --
    def _near_duplicates(self) -> None:
        for r in self.rows:
            if r.kind != "STEP" or r.verdict != "INSERT":
                continue
            for live in self.unmatched:
                if _close(_norm(r.plan["values"]["node_name"]), _norm(live.node_name)):
                    r.warnings.append(msg("POSSIBLE_DUPLICATE", f"This new step's name is close to "
                                          f"'{live.node_name}' ({live.hier_code}), which the file does not name. "
                                          "Is it the same step?", "name", hier_code=live.hier_code,
                                          name=live.node_name))

    def _unique_keys(self) -> None:
        """A business key is unique per kind in a batch (uq_ir_business_key): a repeat already carries its error or
        warning, so the later row keeps none."""
        seen = set()
        for r in self.rows:
            if r.business_key is None:
                continue
            if (r.kind, r.business_key) in seen:
                r.business_key = None
            else:
                seen.add((r.kind, r.business_key))


_KEEP = object()                    # a performer left out or unknown: the step keeps its own (rule 3)


def _close(a: str, b: str) -> bool:
    """Rule 16: the same words in another order, or one word added or dropped."""
    ta, tb = a.split(), b.split()
    sa, sb = set(ta), set(tb)
    if not sa or not sb or ta == tb:
        return False
    return sa == sb or (len(sa ^ sb) == 1 and (sa < sb or sb < sa))


def _step_changes(db: Session, node: BfcNode, values: dict) -> list[dict]:
    """Before/after of a matched step, computed now (S4-8): name, description, performer."""
    out = []
    if values["node_name"] != node.node_name:
        out.append({"column": "name", "before": node.node_name, "after": values["node_name"], "cleared": False})
    if "description" in values and values["description"] != node.data_processing_desc:
        out.append({"column": "description", "before": node.data_processing_desc, "after": values["description"],
                    "cleared": values["description"] is None})
    if "performer" in values:
        now = bfc.describe_performer(db, node)
        if _performer_key(now) != _performer_key(values["performer"]):
            out.append({"column": "performer", "before": _performer_text(now),
                        "after": _performer_text(values["performer"]), "cleared": values["performer"] is None})
    return out


# ---- validate ------------------------------------------------------------------------------------------------------

def validate(db: Session, actor_id: int, project_id: int, anchor_id: int, mode: str, body: bytes,
             file_name: str) -> ImportBatch:
    """POST /projects/{id}/bulk/process-flow/validate (design §7.2b). The anchor and mode come from the screen
    (R2-P3); the file's own `parent` and `mode` must agree. A file-level fault is 422 with nothing staged; a fault
    in one object is that row's error, and the rest still stages (FI-3)."""
    if mode not in MODES:
        raise HTTPException(422, "mode: choose merge or replace")
    anchor = _anchor(db, project_id, anchor_id, lock=False)
    doc = read_file(body)
    if doc["parent"]["hier_code"] != anchor.hier_code:
        raise HTTPException(422, f"This file is for {doc['parent']['hier_code'][:40]}; you chose "
                                 f"{anchor.hier_code}. Nothing was staged.")
    if doc.get("mode", "merge") != mode:
        raise HTTPException(422, f"The file says mode {doc['mode']}; you chose {mode}. Nothing was staged.")
    resolver = _Resolver(db, anchor, doc, lock=False, mode=mode)
    rows = resolver.run()
    status = bulk._statuses(db)
    warnings = [msg("NOT_IN_FILE", f"{n.hier_code} {n.node_name} is not in this file — kept as is.", None,
                    hier_code=n.hier_code, name=n.node_name) for n in resolver.unmatched]
    batch = ImportBatch(project_id=project_id, target_entity=TARGET, source_format=FORMAT, import_mode=mode.upper(),
                        anchor_bfc_node_id=anchor.bfc_node_id, file_name=file_name, uploaded_by_user_id=actor_id,
                        status_code_id=status["VALIDATING"], file_warning_detail=warnings)
    db.add(batch)
    db.flush()
    sha = hashlib.sha256(body).hexdigest()
    for r in rows:
        db.add(ImportRow(import_batch_id=batch.import_batch_id, target_entity=TARGET, row_kind=r.kind,
                         source_path=r.path, local_key=r.local_key, source_ref=r.source_ref,
                         business_key=r.business_key, payload=_payload(r, sha), verdict=r.verdict,
                         is_valid=not r.errors, error_detail=r.errors, warning_detail=r.warnings))
    _count(batch, rows)
    batch.status_code_id = status["VALIDATED"]
    db.commit()
    db.refresh(batch)
    return batch


def _payload(r: Row, sha: str) -> dict:
    p = {"v": 1, "file": {"sha256": sha}, "plan": r.plan}
    if r.obj is not None:
        p["obj"] = r.obj
    if r.target_id is not None:
        p["resolved"] = {"target_id": r.target_id}
    if r.pins:
        p["pins"] = r.pins
    if r.target is not None:
        p["target"] = r.target                       # ck_ir_db_staged_target: what a RETIRE or KEPT row acts on
    return p


def _count(batch: ImportBatch, rows: list[Row]) -> None:
    """A row with errors counts only as an error (UAT 2026-10-08); MATCH is not counted (S4-7)."""
    batch.row_count = len(rows)
    batch.error_count = sum(1 for r in rows if r.errors)
    batch.warning_count = sum(1 for r in rows if r.warnings)
    batch.insert_count = sum(1 for r in rows if r.verdict == "INSERT" and not r.errors)
    batch.update_count = sum(1 for r in rows if r.verdict == "UPDATE" and not r.errors)
    batch.retire_count = sum(1 for r in rows if r.verdict == "RETIRE" and not r.errors)    # KEPT is not counted


# ---- preview -------------------------------------------------------------------------------------------------------

def preview_rows(db: Session, batch: ImportBatch, stored: list[ImportRow]) -> list[dict]:
    """Each row with its pointer, `source_ref` and verdict; a STEP's before/after computed now against the live node
    (S4-8), or from the before-values it stored at commit."""
    out = []
    for r in stored:
        plan = r.payload.get("plan") or {}
        changes = []
        if r.row_kind == "STEP":
            values = plan.get("values") or {}
            if r.verdict == "INSERT":
                changes = [{"column": c, "before": None, "after": v if c != "performer" else _performer_text(v),
                            "cleared": False}
                           for c, v in (("name", values.get("node_name")), ("description", values.get("description")),
                                        ("performer", values.get("performer"))) if v is not None]
            elif r.verdict == "UPDATE":
                if "before" in r.payload:
                    changes = r.payload["before"]
                else:
                    node = db.get(BfcNode, (r.payload.get("resolved") or {}).get("target_id"))
                    changes = _step_changes(db, node, values) if node is not None else []
        out.append({"import_row_id": r.import_row_id, "sheet_row_no": None, "row_kind": r.row_kind,
                    "source_path": r.source_path, "local_key": r.local_key, "source_ref": r.source_ref,
                    "verdict": r.verdict, "business_key": r.business_key, "is_valid": r.is_valid,
                    "errors": r.error_detail, "warnings": r.warning_detail, "changes": changes,
                    "resolved": None, "br_number": r.payload.get("br_number"),
                    "ext_number": r.payload.get("ext_number"),
                    "target_label": (r.payload.get("target") or {}).get("label"),
                    "committed_target_id": r.committed_target_id})
    return out


# ---- commit --------------------------------------------------------------------------------------------------------

def _rebuild(stored: list[ImportRow]) -> dict:
    """The file again, from its staged objects (the file itself is never kept, R2-S8)."""
    def index(r):
        return int(r.source_path.split("/")[2])
    steps = sorted((r for r in stored if r.row_kind == "STEP"), key=index)
    parties = sorted((r for r in stored if r.row_kind == "EXTERNAL_ENTITY"), key=index)
    return {"steps": [r.payload["obj"] for r in steps], "external_entities": [r.payload["obj"] for r in parties]}


def commit_rows(db: Session, actor_id: int, batch: ImportBatch, status: dict[str, int], acknowledged_inserts,
                acknowledged_updates, source_ip: str | None, acknowledged_retires=None) -> ImportBatch:
    """§7.2b's commit inside bulk.commit's lock, status and error handling: every row resolved again under lock and
    compared with its staged row (rule 14, D5); the counts acknowledged (R2-P1, FI-7); then one transaction, in
    dependency order, with no writer committing on its own."""
    stored = bulk._rows_of(db, batch)
    anchor = _anchor(db, batch.project_id, batch.anchor_bfc_node_id, lock=True)
    resolver = _Resolver(db, anchor, _rebuild(stored), lock=True, mode=batch.import_mode.lower())
    try:
        fresh = {r.pair: r for r in resolver.run()}
    except HTTPException as e:
        raise bulk._RuleFailure(str(e.detail), {})
    # §7.2b: the RETIRE set re-computed inside the lock. Any difference from the preview — a row more or less, a
    # RETIRE now KEPT or the other way — and nothing is written.
    if {(r.pair, r.verdict) for r in fresh.values() if r.verdict in ("RETIRE", "KEPT")} != \
            {(_stored_pair(s), s.verdict) for s in stored if s.verdict in ("RETIRE", "KEPT")}:
        raise HTTPException(409, "The flow changed since the preview, so what this import would remove changed too. "
                                 "Nothing was written — validate the file again.")
    errors: dict[int, list[dict]] = {}
    for s in stored:
        r = fresh.pop(_stored_pair(s), None)
        errs = []
        if r is None:
            errs.append(msg("VERDICT_CHANGED", "This object no longer resolves as it did: the data changed since the "
                            "upload. Upload the file again.", None))
        else:
            errs = list(r.errors)
            if not errs and r.verdict != s.verdict:
                errs.append(msg("VERDICT_CHANGED", f"This object would now be {r.verdict}, not {s.verdict}: the data "
                                "changed since the upload. Upload the file again.", None, was=s.verdict, now=r.verdict))
            pinned = s.payload.get("pins") or {}
            if not errs and pinned != json.loads(json.dumps(r.pins)):                  # rule 14 (D2)
                errs.append(msg("RESOLVED_CHANGED", "What this object points at changed since the upload, so nothing "
                                "was written. Upload the file again.", None, was=pinned, now=r.pins))
        if errs:
            errors[s.import_row_id] = errs
    if errors or fresh:
        raise bulk._RuleFailure(f"{len(errors) + len(fresh)} objects changed since the upload, so nothing was applied "
                                "and the batch was rejected. Export again, re-apply your edits and upload.", errors)
    rows = {_stored_pair(s): s for s in stored}
    plan_rows = list(resolver.rows)
    inserts = sum(1 for r in plan_rows if r.verdict == "INSERT")
    updates = sum(1 for r in plan_rows if r.verdict == "UPDATE")
    retires = sum(1 for r in plan_rows if r.verdict == "RETIRE")
    if inserts and acknowledged_inserts != inserts:
        raise HTTPException(422, f"This will CREATE {inserts} new rows. Confirm the count.")
    if updates and acknowledged_updates != updates:                                    # rule 15 (FI-7)
        raise HTTPException(422, f"This will CHANGE {updates} existing steps. Confirm the count.")
    if retires and acknowledged_retires != retires:                                    # §7.11 property 6
        raise HTTPException(422, f"This will RETIRE {retires} rows. Confirm the count.")

    current: Row | None = None
    try:
        with bulk.no_commit(db):
            for current in _apply(db, actor_id, anchor, resolver):
                pass
            current = None
            db.flush()
    except (HTTPException, ValueError, StaleDataError) as e:                          # sara L2
        detail = e.detail if isinstance(e, HTTPException) else \
            "it changed while this import was being applied" if isinstance(e, StaleDataError) else str(e)
        rid = rows[current.pair].import_row_id if current is not None else None
        raise bulk._RuleFailure(f"{current.path if current else 'The file'} could not be applied: {detail}. Nothing "
                                "was applied and the batch was rejected.",
                                {rid: [msg("APPLY_FAILED", str(detail), None)]} if rid else {})

    with bulk.no_commit(db):
        updated = []
        for r in plan_rows:
            row = rows[r.pair]
            row.committed_target_id = None if r.kind == "PERFORMER" or r.verdict == "KEPT" else r.target_id
            extra = {}
            if r.kind == "STEP" and r.verdict == "UPDATE":
                extra["before"] = r.plan["changes"]
                updated.append({"bfc_node_id": r.target_id, "hier_code": r.plan["hier_code"],
                                "name_before": r.plan["before"]["node_name"],
                                "description_before": r.plan["before"]["description"]})
            if r.plan.get("br_number"):
                extra["br_number"] = r.plan["br_number"]
            if r.plan.get("ext_number"):                 # a new party's number, minted at commit (§9.8)
                extra["ext_number"] = r.plan["ext_number"]
            if extra:
                row.payload = {**row.payload, **extra}
        batch.status_code_id = status["COMMITTED"]
        batch.committed_at = func.now()
        batch.committed_by_user_id = actor_id
        audit.record(db, "IMPORT_COMMITTED", actor_id=actor_id, project_id=batch.project_id,
                     target_table="import_batch", target_id=batch.import_batch_id,
                     detail={"entity": TARGET, "anchor_bfc_node_id": anchor.bfc_node_id,
                             "anchor": anchor.hier_code, "mode": batch.import_mode,
                             "insert_count": inserts, "update_count": updates,
                             "match_count": sum(1 for r in plan_rows if r.verdict == "MATCH"),
                             "retire_count": retires, "file_sha256": stored[0].payload.get("file", {}).get("sha256"),
                             "updated_steps": updated},                               # FI-7: kept past the purge
                     source_ip=source_ip)
        db.flush()
    return batch


def _apply(db: Session, actor_id: int, anchor: BfcNode, res: _Resolver):
    """§7.2b's order: new parties, data entities and triggers; new steps (with their BR when to-be); changed steps —
    name and description, then performer, each call on the step's current row_version (rule 17); then the links and
    external flows; last the retirements, each re-checked for a dependent. A generator, so a failure names the object
    being written."""
    pid = anchor.project_id
    nodes = {}
    by_kind = {}
    for r in res.rows:
        by_kind.setdefault(r.kind, []).append(r)
    for r in res.party_rows.values():
        yield r
        if r.verdict == "INSERT":
            party = external_entity.create_party(db, actor_id, pid, r.plan["name"], r.plan["kind"], None,
                                                 commit=False)
            r.target_id = party.external_entity_id
            r.plan["ext_number"] = party.ext_number
            res.party_keys[r.local_key] = party
    for r in res.de_rows.values():
        yield r
        if r.verdict == "INSERT":
            r.target_id = data_entity.add_entity(db, actor_id, pid, r.plan["name"], None, None).data_entity_id
    for r in res.trigger_rows.values():
        yield r
        if r.verdict == "INSERT":
            r.target_id = trigger.create_trigger(db, actor_id, pid, r.plan["name"], r.plan["kind"], None, None,
                                                 commit=False).process_trigger_id
    for r in by_kind.get("STEP", []):
        yield r
        i = int(r.path.split("/")[2])
        values = r.plan["values"]
        if r.verdict == "INSERT":
            node = bfc.create_node(db, actor_id, pid, anchor.bfc_node_id, values["node_name"], is_process=True,
                                   commit=False)
            if values.get("description") is not None:
                node = bfc.update_node(db, actor_id, node, node.row_version,
                                       {"data_processing_desc": values["description"]}, commit=False)
            if values.get("performer") is not None:
                _set_performer(db, actor_id, node, values["performer"])
            r.target_id = node.bfc_node_id
            if anchor.bfc_set_code == "TO_BE":
                r.plan["br_number"] = db.scalar(select(BusinessRequirement.br_number).where(
                    BusinessRequirement.bfc_node_id == node.bfc_node_id, BusinessRequirement.is_active))
        else:
            node = res.step_nodes[i]
            if r.verdict == "UPDATE":
                r.plan["changes"] = _step_changes(db, node, values)
                r.plan["hier_code"] = node.hier_code
                r.plan["before"] = {"node_name": node.node_name, "description": node.data_processing_desc}
                fields = {}
                if values["node_name"] != node.node_name:
                    fields["node_name"] = values["node_name"]
                if "description" in values and values["description"] != node.data_processing_desc:
                    fields["data_processing_desc"] = values["description"]
                if fields:
                    node = bfc.update_node(db, actor_id, node, r.pins["row_version"], fields, commit=False)
                if "performer" in values and _performer_key(bfc.describe_performer(db, node)) != \
                        _performer_key(values["performer"]):
                    _set_performer(db, actor_id, node, values["performer"])
        nodes[i] = node
    for r in by_kind.get("STEP_IO", []):
        yield r
        if r.verdict == "INSERT":
            r.target_id = step_io.ensure_step_io(db, actor_id, nodes[r.plan["step"]],
                                                 res.de_rows[r.plan["de"]].target_id,
                                                 r.plan["direction"]).bfc_node_data_entity_id
    for r in by_kind.get("STEP_TRIGGER", []):
        yield r
        if r.verdict == "INSERT":
            r.target_id = trigger.link(db, actor_id, nodes[r.plan["step"]],
                                       res.trigger_rows[r.plan["trigger"]].target_id, None,
                                       commit=False).bfc_node_trigger_id
    for r in by_kind.get("EXTERNAL_FLOW", []):
        yield r
        if r.verdict == "INSERT":
            de = res.de_rows[r.plan["de"]].target_id if r.plan["de"] is not None else None
            r.target_id = bfc.link_external_flow(db, actor_id, nodes[r.plan["step"]],
                                                 res.party_keys[r.plan["party"]].external_entity_id,
                                                 r.plan["direction"], de, None, None, commit=False,
                                                 keep_text=True).bfc_node_external_flow_id
    for r in res.rows:
        if r.verdict != "RETIRE":
            continue
        yield r
        if r.kind == "STEP_IO":                      # its dependents checked again, inside this transaction
            step_io.unlink(db, actor_id, db.get(BfcNodeDataEntity, r.target_id), r.pins["row_version"], commit=False)
        else:
            trigger.unlink(db, actor_id, db.get(BfcNodeTrigger, r.target_id), r.pins["row_version"], commit=False)


def _set_performer(db: Session, actor_id: int, node: BfcNode, p: dict | None) -> None:
    """Rule 17 (D6): the step's current row_version, after any change made before it in this commit."""
    db.flush()
    if p is None:
        bfc.set_performer(db, actor_id, node, node.row_version, None, None, None, commit=False)
    elif p["kind"] == "AI":
        bfc.set_performer(db, actor_id, node, node.row_version, "AI", None, p["name"], commit=False)
    else:
        bfc.set_performer(db, actor_id, node, node.row_version, p["kind"], p["code"], None, commit=False)
