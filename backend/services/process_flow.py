"""Process flow edges (§7.2a, D-20, D-23, Q2, S2-1…S2-5). The one writer of BFC_NODE_FLOW.

An edge joins two process steps of one project; a missing end is a start or end event. Two
live edges join the same two steps only under different conditions (Q2) — compared with
bfc.normalise_name, which is stricter than the index. Re-adding a removed edge restores the
same row, so its baseline source_id stays stable. There is NO cycle check: a rework loop is
ordinary process behaviour (§5.3), the opposite of the solution-dependency rule.
"""
from fastapi import HTTPException
from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session

from models import (BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow, BfcNodeFlow, BfcNodeOrgRole,
                    BrDataEntity)
from services import lifecycle
from services.bfc import normalise_name

FLOW_TYPES = ("SEQUENCE", "CONDITIONAL", "PARALLEL", "HANDOFF")      # S2-1, = ck_bnf_flow_type


def _clean(text: str | None) -> str | None:
    text = (text or "").strip()
    return text or None


def _same_condition(a: str | None, b: str | None) -> bool:
    return normalise_name(a or "") == normalise_name(b or "")


def _end(db: Session, project_id: int, node_id: int | None, which: str) -> BfcNode | None:
    if node_id is None:
        return None
    node = db.get(BfcNode, node_id)
    if node is None or node.project_id != project_id or not node.is_active:
        raise HTTPException(422, f"The {which} step must be an active step in this project")
    if not node.is_process:
        raise HTTPException(422, f"The {which} node is not a process step. Flows join process steps only")
    return node


def _check_label(flow_type: str, label: str | None) -> None:
    if flow_type == "CONDITIONAL" and label is None:
        raise HTTPException(422, "A conditional branch needs a condition label")


def _between(db: Session, from_id: int | None, to_id: int | None) -> list[BfcNodeFlow]:
    def _eq(col, v):
        return col.is_(None) if v is None else col == v
    return list(db.scalars(select(BfcNodeFlow).where(
        _eq(BfcNodeFlow.from_bfc_node_id, from_id), _eq(BfcNodeFlow.to_bfc_node_id, to_id))))


def _refuse_duplicate(rows: list[BfcNodeFlow], label: str | None, except_id: int | None = None) -> None:
    if any(r.is_active and r.bfc_node_flow_id != except_id and _same_condition(r.condition_label, label)
           for r in rows):
        raise HTTPException(409, "These two steps are already joined under that condition. "
                                 "Give the second edge a different condition, or edit the first")


def link_process_flow(db: Session, actor_id: int, project_id: int, from_id: int | None,
                      to_id: int | None, flow_type: str, condition_label: str | None,
                      seq_no: int | None, note: str | None) -> BfcNodeFlow:
    if from_id is None and to_id is None:
        raise HTTPException(422, "An edge needs a from step, a to step, or both")
    _end(db, project_id, from_id, "from")
    _end(db, project_id, to_id, "to")
    label = _clean(condition_label)
    _check_label(flow_type, label)
    rows = _between(db, from_id, to_id)
    _refuse_duplicate(rows, label)
    twins = sorted((r for r in rows if not r.is_active and _same_condition(r.condition_label, label)),
                   key=lambda r: r.deleted_at, reverse=True)
    if twins:                                     # restore the latest twin, never re-insert (S2-5)
        row = twins[0]
        lifecycle.relink(db, actor_id, row)
    else:
        row = BfcNodeFlow(project_id=project_id, from_bfc_node_id=from_id, to_bfc_node_id=to_id,
                          created_by=actor_id)
        db.add(row)
    row.flow_type, row.condition_label, row.seq_no, row.note = flow_type, label, seq_no, _clean(note)
    db.commit()
    db.refresh(row)
    return row


def update_process_flow(db: Session, actor_id: int, row: BfcNodeFlow, row_version: int,
                        fields: dict) -> BfcNodeFlow:
    """S2-2: the ends are fixed; re-pointing an edge is remove + add."""
    lifecycle.check_version(row, row_version)
    if not row.is_active:                        # edges have no restore route (sara LOW-2)
        raise HTTPException(409, "This flow was removed. Add it again to bring it back")
    flow_type = fields.get("flow_type", row.flow_type)
    label = _clean(fields["condition_label"]) if "condition_label" in fields else row.condition_label
    _check_label(flow_type, label)
    if not _same_condition(label, row.condition_label):
        _refuse_duplicate(_between(db, row.from_bfc_node_id, row.to_bfc_node_id), label,
                          except_id=row.bfc_node_flow_id)
    row.flow_type, row.condition_label = flow_type, label
    if "seq_no" in fields:
        row.seq_no = fields["seq_no"]
    if "note" in fields:
        row.note = _clean(fields["note"])
    row.updated_by = actor_id
    db.commit()
    db.refresh(row)
    return row


def remove_process_flow(db: Session, actor_id: int, row: BfcNodeFlow, row_version: int) -> None:
    lifecycle.unlink(db, actor_id, row, row_version)


def list_flows(db: Session, project_id: int, bfc_node_id: int | None = None) -> list[BfcNodeFlow]:
    """Live edges of a project, or those touching one step, in render order (S2-3)."""
    q = select(BfcNodeFlow).where(BfcNodeFlow.project_id == project_id, BfcNodeFlow.is_active)
    if bfc_node_id is not None:
        q = q.where((BfcNodeFlow.from_bfc_node_id == bfc_node_id)
                    | (BfcNodeFlow.to_bfc_node_id == bfc_node_id))
    return list(db.scalars(q.order_by(BfcNodeFlow.seq_no.asc().nulls_last(), BfcNodeFlow.bfc_node_flow_id)))


def flow_completeness_report(db: Session, project_id: int) -> dict:
    """§7.2a — the gaps that make a flow unreadable. `unlabelled_branch` is gone: the table
    CHECK makes it always empty (S2-1). `dangling_handoff` is empty by construction: a node
    with a live edge cannot be retired (lifecycle.retire), so no key is returned for it.
    `crud_without_io` and `ext_without_io` must be 0 — the licence FKs hold them; these prove it
    (criterion 148)."""
    steps = list(db.scalars(select(BfcNode).where(
        BfcNode.project_id == project_id, BfcNode.is_active, BfcNode.is_process)
        .order_by(BfcNode.hier_code)))
    edges = list_flows(db, project_id)
    touched = {e.from_bfc_node_id for e in edges} | {e.to_bfc_node_id for e in edges}
    starts = {e.to_bfc_node_id for e in edges if e.from_bfc_node_id is None}
    ends = {e.from_bfc_node_id for e in edges if e.to_bfc_node_id is None}

    def _ref(n: BfcNode) -> dict:
        return {"bfc_node_id": n.bfc_node_id, "hier_code": n.hier_code, "node_name": n.node_name}

    by_parent: dict[int, list[BfcNode]] = {}
    for s in steps:
        by_parent.setdefault(s.parent_bfc_node_id, []).append(s)
    parents = {p.bfc_node_id: p for p in db.scalars(select(BfcNode).where(
        BfcNode.bfc_node_id.in_(list(by_parent))))} if by_parent else {}
    flowed = {pid: kids for pid, kids in by_parent.items()
              if any(k.bfc_node_id in touched for k in kids)}

    with_output = set(db.scalars(select(BfcNodeDataEntity.bfc_node_id).where(
        BfcNodeDataEntity.project_id == project_id, BfcNodeDataEntity.is_active,
        BfcNodeDataEntity.direction == "O")))
    with_lane = set(db.scalars(select(BfcNodeOrgRole.bfc_node_id).where(
        BfcNodeOrgRole.project_id == project_id, BfcNodeOrgRole.is_active,
        BfcNodeOrgRole.raci_behaviour == "RESPONSIBLE")))           # the lane (R2-D9)
    return {
        "orphan_steps": [_ref(s) for s in steps if s.bfc_node_id not in touched],
        "no_start": [_ref(parents[pid]) for pid, kids in flowed.items()
                     if not any(k.bfc_node_id in starts for k in kids)],
        "no_end": [_ref(parents[pid]) for pid, kids in flowed.items()
                   if not any(k.bfc_node_id in ends for k in kids)],
        "no_output": [_ref(s) for s in steps if s.bfc_node_id not in with_output],
        "no_lane": [_ref(s) for s in steps if s.bfc_node_id not in with_lane],
        "crud_without_io": _unlicensed(db, project_id, BrDataEntity, BrDataEntity.br_data_entity_id),
        "ext_without_io": _unlicensed(db, project_id, BfcNodeExternalFlow,
                                      BfcNodeExternalFlow.bfc_node_external_flow_id),
        "edge_count": len(edges),
    }


def _unlicensed(db: Session, project_id: int, model, pk) -> list[int]:
    """Live rows naming a data entity with no matching live step I/O row (D-24, R2-D13)."""
    io = exists().where(and_(BfcNodeDataEntity.bfc_node_id == model.bfc_node_id,
                             BfcNodeDataEntity.data_entity_id == model.data_entity_id,
                             BfcNodeDataEntity.direction == model.direction,
                             BfcNodeDataEntity.is_active))
    return list(db.scalars(select(pk).where(model.project_id == project_id, model.is_active,
                                            model.data_entity_id.is_not(None), ~io)))

