"""THE ONE MERMAID LABEL PATH (design §7.12b, R2-S7; slice 3 spec §7 3c).

Every label in every Mermaid export — step, lane, condition, store, external party, entity,
field, relationship — goes through `escape_mermaid()`. There is no second label path.
Node ids are generated from database ids (s12, d7, x2, e40, E7, l1, a_3), never from user
text. `_guard()` is the last step of every exporter: an output line that begins with a
directive Mermaid would act on is a renderer bug, so it is logged and refused with a 500
rather than handed to a consultant to paste into a client's deck.

The exporters render exactly the dicts `generate_process_flow`, `generate_dfd` and
`generate_erd` return; they read nothing else."""
import logging
import re
import unicodedata

from fastapi import HTTPException

log = logging.getLogger("vb")

# Design §7.12b, copied exactly — '#' first by construction, since the map runs in one pass.
MERMAID_ENTITY = {'#': '#35;', '"': '#quot;', '<': '#lt;', '>': '#gt;', '`': '#96;',
                  '[': '#91;', ']': '#93;', '(': '#40;', ')': '#41;', '{': '#123;',
                  '}': '#125;', '|': '#124;', ';': '#59;'}

LABEL_CAP = 200
_BREAKING = {"Cc", "Zl", "Zp"}      # CR, LF, tab, \v, \f, U+0085, U+2028, U+2029 …
BANNED_FIRST_TOKENS = ("click", "call", "href", "%%{init", "style", "classDef", "linkStyle", "class")
_TYPE_CODE = re.compile(r"[A-Z_]+")

UNASSIGNED_LANE = "Unassigned"
OUTSIDE_LANE = "Outside this flow"
EVENT_LABEL = '(" ")'                # e{flow_id}((" ")) — the spec's `(("")` fails Mermaid 11's parser


def check_format(fmt: str) -> None:
    """The export routes speak Mermaid only. The flow JSON file (D-25) belongs to the import slice."""
    if fmt == "json":
        raise HTTPException(422, "format=json (the flow JSON file) comes with the flow import slice; "
                                 "use format=mermaid")
    if fmt != "mermaid":
        raise HTTPException(422, "format must be mermaid")


def escape_mermaid(text) -> str:
    """Spec §7 3c, in this order: cap the RAW text (never cut an entity), break-like characters
    to a space, drop `%%`, the entity map in ONE pass, then wrap in quotes."""
    s = str(text or "")
    s = s[:LABEL_CAP]
    s = "".join(" " if unicodedata.category(c) in _BREAKING else c for c in s)
    s = s.replace("%%", "")
    s = "".join(MERMAID_ENTITY.get(c, c) for c in s)
    return '"' + s + '"'


def _guard(text: str) -> str:
    """The last step of every exporter (§7.12b): any line whose first token is a directive → 500."""
    for n, line in enumerate(text.splitlines(), 1):
        token = (line.split() or [""])[0]
        if any(token.startswith(word) for word in BANNED_FIRST_TOKENS):
            log.error("mermaid guard: line %d begins with a banned directive (%r)", n, token[:20])
            raise HTTPException(500, "The diagram export produced an unsafe line and was stopped")
    return text


def _join(lines: list[str]) -> str:
    return _guard("\n".join(lines) + "\n")


def _ref(n: dict) -> str:
    return f"{n['hier_code']} {n['node_name']}"


# ---- the process flow (§7.2a export_process_flow, criterion 19) ------------------------------

def export_process_flow(g: dict) -> str:
    """flowchart LR; one subgraph per lane (l1…, unassigned last), steps and their start/end
    events inside their lane, handoff targets in an `outside` subgraph, stores and parties at
    the top level. SEQUENCE/PARALLEL `-->`, HANDOFF `-.->`, a condition as `|"label"|`. A step's
    data (store or party) is a dotted association `-.-`, written from the source side."""
    lines = ["flowchart LR"]
    lane_order = [lane["org_role_id"] for lane in g["lanes"]]
    lane_label = {lane["org_role_id"]: lane["org_role_name"] + (f" · {lane['org_unit_name']}"
                                                                if lane["org_unit_name"] else "")
                  for lane in g["lanes"]}
    lane_of = {n["bfc_node_id"]: n["lane_org_role_id"] for n in g["nodes"]}
    events: dict[object, list[str]] = {}
    for e in g["edges"]:
        if e["from_bfc_node_id"] is None or e["to_bfc_node_id"] is None:
            anchor = e["to_bfc_node_id"] if e["from_bfc_node_id"] is None else e["from_bfc_node_id"]
            events.setdefault(lane_of.get(anchor), []).append(f"e{e['bfc_node_flow_id']}")

    bands = [(rid, lane_label[rid]) for rid in lane_order]
    if any(n["lane_org_role_id"] is None for n in g["nodes"]):
        bands.append((None, UNASSIGNED_LANE))
    for i, (rid, label) in enumerate(bands, 1):
        lines.append(f"    subgraph l{i}[{escape_mermaid(label)}]")
        lines += [f"        s{n['bfc_node_id']}[{escape_mermaid(_ref(n))}]"
                  for n in g["nodes"] if n["lane_org_role_id"] == rid]
        # an event is an unlabelled circle; Mermaid refuses an empty "" label, so one space
        lines += [f'        {ev}({EVENT_LABEL})' for ev in events.get(rid, [])]
        lines.append("    end")
    if g["outside"]:
        lines.append(f"    subgraph outside[{escape_mermaid(OUTSIDE_LANE)}]")
        lines += [f"        s{n['bfc_node_id']}[{escape_mermaid(_ref(n))}]" for n in g["outside"]]
        lines.append("    end")
    lines += [f"    d{s['data_entity_id']}[({escape_mermaid(s['de_number'] + ' ' + s['de_name'])})]"
              for s in g["stores"]]
    lines += [f"    x{x['external_entity_id']}[{escape_mermaid(x['ext_number'] + ' ' + x['ext_name'])}]"
              for x in g["externals"]]

    for e in g["edges"]:
        fid = e["bfc_node_flow_id"]
        src = f"e{fid}" if e["from_bfc_node_id"] is None else f"s{e['from_bfc_node_id']}"
        dst = f"e{fid}" if e["to_bfc_node_id"] is None else f"s{e['to_bfc_node_id']}"
        arrow = "-.->" if e["flow_type"] == "HANDOFF" else "-->"
        label = f"|{escape_mermaid(e['condition_label'])}|" if e["condition_label"] else ""
        lines.append(f"    {src} {arrow}{label} {dst}")
    for s in g["stores"]:
        d = f"d{s['data_entity_id']}"
        lines += [f"    {d} -.- s{step}" for step in s["reads"]]
        lines += [f"    s{step} -.- {d}" for step in s["writes"]]
    for x in g["externals"]:
        pid = f"x{x['external_entity_id']}"
        for f in x["flows"]:
            lines.append(f"    {pid} -.- s{f['bfc_node_id']}" if f["direction"] == "I"
                         else f"    s{f['bfc_node_id']} -.- {pid}")
    return _join(lines)


# ---- the DFD (§7.2a generate_dfd, D-31) -------------------------------------------------------

def export_dfd(g: dict) -> str:
    """flowchart LR; processes as stadiums, stores as cylinders, parties as squares; one edge per
    flow in its direction (I = into the step), labelled when the flow has a label."""
    lines = ["flowchart LR"]
    lines += [f"    s{p['bfc_node_id']}([{escape_mermaid(_ref(p))}])" for p in g["processes"]]
    lines += [f"    d{s['data_entity_id']}[({escape_mermaid(s['de_number'] + ' ' + s['de_name'])})]"
              for s in g["stores"]]
    lines += [f"    x{x['external_entity_id']}[{escape_mermaid(x['ext_number'] + ' ' + x['ext_name'])}]"
              for x in g["externals"]]
    for f in g["flows"]:
        other = f"d{f['data_entity_id']}" if f["kind"] == "STORE" else f"x{f['external_entity_id']}"
        step = f"s{f['bfc_node_id']}"
        src, dst = (other, step) if f["direction"] == "I" else (step, other)
        label = f"|{escape_mermaid(f['label'])}|" if f["label"] else ""
        lines.append(f"    {src} -->{label} {dst}")
    return _join(lines)


# ---- the ERD (§7.4 generate_erd, D-29; glyph table spec §7 3b) -------------------------------

PARENT_GLYPH = {"1": "||", "0..1": "|o"}
CHILD_GLYPH = {"1": "o|", "many": "o{"}          # the child end never claims a minimum (A-S3-8)


def _type(code: str | None) -> str:
    return code if code and _TYPE_CODE.fullmatch(code) else "unknown"


def _keys(f: dict) -> str:
    keys = [k for k, on in (("PK", f["is_primary_key"]), ("FK", f["is_foreign_key"])) if on]
    return (" " + ", ".join(keys)) if keys else ""      # R2-NEW-3: both → `PK, FK`


def _rel(r: dict) -> str:
    glyph = PARENT_GLYPH[r["parent_cardinality"]] + ("--" if r["identifying"] else "..") \
        + CHILD_GLYPH[r["child_cardinality"]]
    return f"    E{r['parent_data_entity_id']} {glyph} E{r['child_data_entity_id']} : {escape_mermaid(r['label'])}"


def export_erd(g: dict) -> str:
    """erDiagram; each entity E{id} with the alias "DE-0007 name"; its fields as
    `<type> a_<n> [PK|FK|PK, FK] "<real name>"` (erDiagram takes no quoted attribute names, so a
    Japanese or spaced name lives in the comment and never collides); one line per relationship,
    parent first; each out-of-area parent a declared stub entity with its relationships."""
    lines = ["erDiagram"]
    for e in g["entities"]:
        alias = f"    E{e['data_entity_id']}[{escape_mermaid(e['de_number'] + ' ' + e['de_name'])}]"
        if not e["fields"]:
            lines.append(alias)
            continue
        lines.append(alias + " {")
        lines += [f"        {_type(f['data_type_code'])} a_{n}{_keys(f)} {escape_mermaid(f['field_name'])}"
                  for n, f in enumerate(e["fields"], 1)]
        lines.append("    }")
    drawn = {e["data_entity_id"] for e in g["entities"]}
    stubs: dict[int, str] = {}
    for r in g["outside_refs"]:
        if r["parent_data_entity_id"] not in drawn:
            stubs.setdefault(r["parent_data_entity_id"], r["parent_de_number"] + " " + r["parent_de_name"])
    lines += [f"    E{pid}[{escape_mermaid(label)}]" for pid, label in stubs.items()]
    lines += [_rel(r) for r in g["relationships"]]
    lines += [_rel(r) for r in g["outside_refs"]]
    return _join(lines)
