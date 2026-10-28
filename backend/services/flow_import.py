"""Process flow as a file — `vb-process-flow/2.0` (design §7.2b, D-25; slice 1e-b spec). Piece (a1): the published
format (schema, worked example and the AI conversion prompt pack) and the export of one anchor's flow. The import
(validate / commit on the bulk pipeline) is piece (a2).

The file carries what the DFD is drawn from — steps, performers, inputs, outputs, triggers and external flows — and
no edges and no lanes (D-38). Export writes every list, empty as `[]`, so an export re-imported changes nothing
(spec §7, §10.1)."""
from functools import cache
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow, BfcNodeTrigger, BusinessRequirement, CodeMaster,
                    DataEntity, ExternalEntity, ProcessTrigger)
from schemas.flow_file import FORMAT, json_schema
from services import bfc, components

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
