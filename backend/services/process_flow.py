"""Process flow edges (§7.2a, D-20, D-23, Q2, S2-1…S2-5). `_link_row` is the only path that creates or re-links an arrow; every path that makes an
arrow live (`_link_row`, `step_retire.restore`) locks a step at one of its ends (SG-1).

An edge joins two process steps of one project; a missing end is a start or end event. Two
live edges join the same two steps only under different conditions (Q2) — compared with
bfc.normalise_name, which is stricter than the index. Re-adding a removed edge restores the
same row, so its baseline source_id stays stable. There is NO cycle check: a rework loop is
ordinary process behaviour (§5.3), the opposite of the solution-dependency rule.
"""
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from models import (BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow, BfcNodeFlow, BfcNodeOrgRole,
                    BrDataEntity, BusinessRequirement, DataEntity, ExternalEntity, OrgRole, OrgUnit)
from services import audit, diagram_layout, lifecycle
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


def _link_row(db: Session, actor_id: int, project_id: int, from_id: int | None, to_id: int | None,
              flow_type: str, condition_label: str | None, seq_no: int | None,
              note: str | None) -> tuple[BfcNodeFlow, bool]:
    """The one per-arrow rule, with NO commit: (row, restored). SG-1: _link_row is the only path
    that creates or re-links an arrow; every path that makes an arrow live (_link_row,
    step_retire.restore) locks a step at one of its ends. link_process_flow and keep_arrows both
    write through here, and the future flow JSON import will too."""
    if from_id is None and to_id is None:
        raise HTTPException(422, "An edge needs a from step, a to step, or both")
    for end_id in sorted({from_id, to_id} - {None}):          # SR-5: both ends FOR SHARE, in id order
        end = db.get(BfcNode, end_id)
        if end is not None and end.project_id == project_id:
            lifecycle.lock_for_share(db, end)
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
        lifecycle.relink(db, actor_id, row, detail={"previous": {
            "flow_type": row.flow_type, "condition_label": row.condition_label,
            "seq_no": row.seq_no, "note": row.note}})
    else:
        row = BfcNodeFlow(project_id=project_id, from_bfc_node_id=from_id, to_bfc_node_id=to_id,
                          created_by=actor_id)
        db.add(row)
    row.flow_type, row.condition_label, row.seq_no, row.note = flow_type, label, seq_no, _clean(note)
    return row, bool(twins)


def link_process_flow(db: Session, actor_id: int, project_id: int, from_id: int | None,
                      to_id: int | None, flow_type: str, condition_label: str | None,
                      seq_no: int | None, note: str | None) -> BfcNodeFlow:
    row, _ = _link_row(db, actor_id, project_id, from_id, to_id, flow_type, condition_label, seq_no, note)
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
    with a live edge cannot be retired on its own (lifecycle.retire), and a step retired with its
    dependents takes its edges with it (step_retire), so no key is returned for it.
    `crud_without_io` and `ext_without_io` must be 0 — the licence FKs hold them; these prove it
    (criterion 148). `step_without_br` is a WARNING: retiring a BR while its step is live is the
    designed first step of a demote (SR-3). `live_link_on_retired_step` must be 0."""
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
    with_br = set(db.scalars(select(BusinessRequirement.bfc_node_id).where(
        BusinessRequirement.project_id == project_id, BusinessRequirement.is_active)))
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
        "step_without_br": [_ref(s) for s in steps if s.bfc_node_id not in with_br],
        "live_link_on_retired_step": _live_on_retired(db, project_id),
    }


def _live_on_retired(db: Session, project_id: int) -> list[dict]:
    """Live rows hanging off a retired step — must be empty; the independent proof that a
    step retire never leaves a half state (docs/step_retire_spec.md §4)."""
    retired = select(BfcNode.bfc_node_id).where(BfcNode.project_id == project_id, ~BfcNode.is_active)
    out = []
    for model, cols in ((BusinessRequirement, ("bfc_node_id",)), (BfcNodeDataEntity, ("bfc_node_id",)),
                        (BfcNodeOrgRole, ("bfc_node_id",)), (BfcNodeExternalFlow, ("bfc_node_id",)),
                        (BfcNodeFlow, ("from_bfc_node_id", "to_bfc_node_id"))):
        pk = model.__mapper__.primary_key[0]
        on_retired = or_(*(getattr(model, c).in_(retired) for c in cols))
        out += [{"table": model.__table__.name, "id": i} for i in db.scalars(
            select(pk).where(model.project_id == project_id, model.is_active, on_retired).order_by(pk))]
    return out


def _unlicensed(db: Session, project_id: int, model, pk) -> list[int]:
    """Live rows naming a data entity with no matching live step I/O row (D-24, R2-D13)."""
    io = exists().where(and_(BfcNodeDataEntity.bfc_node_id == model.bfc_node_id,
                             BfcNodeDataEntity.data_entity_id == model.data_entity_id,
                             BfcNodeDataEntity.direction == model.direction,
                             BfcNodeDataEntity.is_active))
    return list(db.scalars(select(pk).where(model.project_id == project_id, model.is_active,
                                            model.data_entity_id.is_not(None), ~io)))



# ---- the graph (D-21: data, not a picture) -----------------------------------------------

VARIANTS = ("AS_IS", "TO_BE")                       # D-22; both read the same rows until APPLICATION lands


def steps_under(db: Session, node: BfcNode) -> list[BfcNode]:
    """The active process steps under a parent node — shared by the flow, the DFD and the ERD."""
    return list(db.scalars(select(BfcNode).where(
        BfcNode.project_id == node.project_id, BfcNode.is_active, BfcNode.is_process,
        BfcNode.hier_code.startswith(f"{node.hier_code}.")).order_by(BfcNode.hier_code)))


def generate_process_flow(db: Session, node: BfcNode, variant: str = "AS_IS") -> dict:
    """§7.2a. The process descendants of a parent node as boxes, the live edges touching them,
    one swimlane per RESPONSIBLE role (R2-D9; none → the unassigned lane), the data stores and
    external parties of their step I/O, and any saved positions (D-30). Cycles are legal, so
    nothing here walks the edges. `system` on a box waits for APPLICATION (D-8)."""
    if variant not in VARIANTS:
        raise HTTPException(422, "variant must be AS_IS or TO_BE")
    if not node.is_active:
        raise HTTPException(409, "This node is retired. Restore it first")
    if node.is_process:
        raise HTTPException(422, "A process flow is drawn for a parent node, not a step")
    steps = steps_under(db, node)
    ids = [s.bfc_node_id for s in steps]
    inside = set(ids)

    brs = {b.bfc_node_id: b for b in db.scalars(select(BusinessRequirement).where(
        BusinessRequirement.bfc_node_id.in_(ids), BusinessRequirement.is_active))} if ids else {}
    lane_of: dict[int, int] = dict(db.execute(select(BfcNodeOrgRole.bfc_node_id, BfcNodeOrgRole.org_role_id).where(
        BfcNodeOrgRole.bfc_node_id.in_(ids), BfcNodeOrgRole.is_active,
        BfcNodeOrgRole.raci_behaviour == "RESPONSIBLE")).all()) if ids else {}
    roles = {r.org_role_id: r for r in db.scalars(select(OrgRole).where(
        OrgRole.org_role_id.in_(set(lane_of.values()))))} if lane_of else {}
    units = {u.org_unit_id: u for u in db.scalars(select(OrgUnit).where(
        OrgUnit.org_unit_id.in_({r.org_unit_id for r in roles.values()})))} if roles else {}

    edges = [] if not ids else list(db.scalars(select(BfcNodeFlow).where(
        BfcNodeFlow.is_active, BfcNodeFlow.from_bfc_node_id.in_(ids) | BfcNodeFlow.to_bfc_node_id.in_(ids))
        .order_by(BfcNodeFlow.seq_no.asc().nulls_last(), BfcNodeFlow.bfc_node_flow_id)))
    far_ids = {e.from_bfc_node_id for e in edges} | {e.to_bfc_node_id for e in edges}
    far = {n.bfc_node_id: n for n in db.scalars(select(BfcNode).where(
        BfcNode.bfc_node_id.in_({i for i in far_ids if i is not None} - inside)))}

    io = [] if not ids else list(db.scalars(select(BfcNodeDataEntity).where(
        BfcNodeDataEntity.bfc_node_id.in_(ids), BfcNodeDataEntity.is_active)))
    des = {d.data_entity_id: d for d in db.scalars(select(DataEntity).where(
        DataEntity.data_entity_id.in_({r.data_entity_id for r in io})))} if io else {}
    ext_rows = [] if not ids else list(db.scalars(select(BfcNodeExternalFlow).where(
        BfcNodeExternalFlow.bfc_node_id.in_(ids), BfcNodeExternalFlow.is_active)))
    exts = {x.external_entity_id: x for x in db.scalars(select(ExternalEntity).where(
        ExternalEntity.external_entity_id.in_({r.external_entity_id for r in ext_rows})))} if ext_rows else {}

    def _lane_key(role_id):
        r = roles[role_id]
        u = units.get(r.org_unit_id)
        return (u.level_no if u else 99, u.seq_no if u else 0, r.org_role_code)

    lanes = [{"org_role_id": rid, "org_role_code": roles[rid].org_role_code,
              "org_role_name": roles[rid].org_role_name,
              "org_unit_name": units[roles[rid].org_unit_id].org_unit_name
              if roles[rid].org_unit_id in units else None}
             for rid in sorted(set(lane_of.values()), key=_lane_key)]
    return {
        "scope": {"bfc_node_id": node.bfc_node_id, "hier_code": node.hier_code, "node_name": node.node_name},
        "variant": variant,
        "nodes": [{"bfc_node_id": s.bfc_node_id, "hier_code": s.hier_code, "node_name": s.node_name,
                   "data_processing_desc": s.data_processing_desc,
                   "br_number": brs[s.bfc_node_id].br_number if s.bfc_node_id in brs else None,
                   "lane_org_role_id": lane_of.get(s.bfc_node_id)} for s in steps],
        "edges": [{"bfc_node_flow_id": e.bfc_node_flow_id, "from_bfc_node_id": e.from_bfc_node_id,
                   "to_bfc_node_id": e.to_bfc_node_id, "flow_type": e.flow_type,
                   "condition_label": e.condition_label, "seq_no": e.seq_no, "row_version": e.row_version,
                   "is_external": any(x is not None and x not in inside
                                      for x in (e.from_bfc_node_id, e.to_bfc_node_id))} for e in edges],
        "outside": [{"bfc_node_id": n.bfc_node_id, "hier_code": n.hier_code, "node_name": n.node_name}
                    for n in sorted(far.values(), key=lambda n: n.hier_code)],
        "lanes": lanes,
        "stores": [{"data_entity_id": d.data_entity_id, "de_number": d.de_number, "de_name": d.de_name,
                    "reads": sorted(r.bfc_node_id for r in io if r.data_entity_id == d.data_entity_id and r.direction == "I"),
                    "writes": sorted(r.bfc_node_id for r in io if r.data_entity_id == d.data_entity_id and r.direction == "O")}
                   for d in sorted(des.values(), key=lambda d: d.de_number)],
        "externals": [{"external_entity_id": x.external_entity_id, "ext_number": x.ext_number, "ext_name": x.ext_name,
                       "flows": [{"bfc_node_id": r.bfc_node_id, "direction": r.direction,
                                  "data_entity_id": r.data_entity_id, "flow_label": r.flow_label}
                                 for r in ext_rows if r.external_entity_id == x.external_entity_id]}
                      for x in sorted(exts.values(), key=lambda x: x.ext_number)],
        "layout": diagram_layout.positions(db, node.project_id, "PROCESS_FLOW", node.bfc_node_id),
        "can_suggest": can_suggest(db, node),
    }


# ---- suggest a flow's arrows from the chart order: preview, then keep (docs/draft_arrows_spec.md) ----

ARROWS_KEPT = "FLOW_ARROWS_KEPT"


def _frame(db: Session, node: BfcNode) -> list[BfcNode]:
    """A-SG-4: the node's active children, in chart order, when every one is a process step."""
    if not node.is_active:
        raise HTTPException(409, "This node is retired. Restore it first")
    if node.is_process:
        raise HTTPException(422, "A process flow is drawn for a parent node, not a step")
    kids = list(db.scalars(select(BfcNode).where(
        BfcNode.project_id == node.project_id, BfcNode.parent_bfc_node_id == node.bfc_node_id,
        BfcNode.is_active).order_by(BfcNode.seq_no, BfcNode.hier_code)))
    if any(not k.is_process for k in kids):
        raise HTTPException(422, "Suggest works on a function whose children are all steps")
    if not kids:
        raise HTTPException(422, "There are no process steps under this node")
    return kids


def _plan(db: Session, node: BfcNode) -> tuple[list[BfcNode], list[tuple[int | None, int | None]], str]:
    """The whole suggest rule, read only: (frame steps, proposed pairs, confirm hash). 409 when a
    live arrow joins two frame steps or a live start / end event sits on one (A-SG-2); a hand-off
    from or to a step outside the frame does not block."""
    steps = _frame(db, node)
    ids = [s.bfc_node_id for s in steps]
    inside = set(ids)
    touching = list(db.scalars(select(BfcNodeFlow).where(
        BfcNodeFlow.from_bfc_node_id.in_(ids) | BfcNodeFlow.to_bfc_node_id.in_(ids))))
    for e in touching:
        if e.is_active and all(end is None or end in inside for end in (e.from_bfc_node_id, e.to_bfc_node_id)):
            raise HTTPException(409, "This flow already has arrows between its steps. "
                                     "Suggest works only on a flow with none")
    pairs = list(zip([None, *ids], [*ids, None]))       # start → each step in chart order → end
    wanted = set(pairs)
    retired = sorted([e.bfc_node_flow_id, e.row_version] for e in touching
                     if not e.is_active and (e.from_bfc_node_id, e.to_bfc_node_id) in wanted)
    body = {"frame": node.bfc_node_id,
            "steps": sorted([s.bfc_node_id, s.row_version] for s in steps),
            "retired": retired}
    return steps, pairs, hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def can_suggest(db: Session, node: BfcNode) -> bool:
    """The same rule as suggest_arrows, so the button never disagrees with the server."""
    try:
        _plan(db, node)
    except HTTPException:
        return False
    return True


def suggest_arrows(db: Session, node: BfcNode) -> dict:
    """GET …/suggest. Nothing is written: every arrow is SEQUENCE with seq_no NULL (A-SG-1)."""
    _, pairs, h = _plan(db, node)
    return {"arrows": [{"from_bfc_node_id": a, "to_bfc_node_id": b, "flow_type": "SEQUENCE"} for a, b in pairs],
            "confirm_hash": h}


def keep_arrows(db: Session, actor_id: int, node: BfcNode, confirm_hash: str) -> dict:
    """POST …/suggest/keep. Lock the frame's steps FOR NO KEY UPDATE in id order (a colleague's
    link_process_flow holds an end FOR SHARE, so the two serialise), RE-RUN the whole suggest rule
    under the lock, compare the hash, then write every arrow through _link_row (SG-1), flush, and
    audit with the real ids. One commit: all the arrows, or none."""
    ids = sorted(k.bfc_node_id for k in _frame(db, node))
    db.scalars(select(BfcNode).where(BfcNode.bfc_node_id.in_(ids)).order_by(BfcNode.bfc_node_id)
               .with_for_update(key_share=True, of=BfcNode)
               .execution_options(populate_existing=True)).all()     # the locked versions, not stale copies
    _, pairs, h = _plan(db, node)
    if confirm_hash != h:
        raise HTTPException(409, "The chart changed since the suggestion. Suggest again")
    created, restored = [], []
    for a, b in pairs:
        row, was_restored = _link_row(db, actor_id, node.project_id, a, b, "SEQUENCE", None, None, None)
        (restored if was_restored else created).append(row)
    db.flush()
    out = {"created": [r.bfc_node_flow_id for r in created], "restored": [r.bfc_node_flow_id for r in restored]}
    audit.record(db, ARROWS_KEPT, actor_id=actor_id, project_id=node.project_id,
                 target_table="bfc_node", target_id=node.bfc_node_id,
                 detail={"frame_id": node.bfc_node_id, "confirm_hash": h,
                         "created_ids": out["created"], "restored_ids": out["restored"]})
    db.commit()
    return out


def _l1(hier_code: str) -> str:
    return hier_code.split(".", 1)[0]


def _cross_area(db: Session, project_id: int, de_ids: set[int]) -> list[int]:
    """A-S3-2: counted across the WHOLE project, not the frame (every step in one frame shares
    its L1). W = L1 areas writing the DE ('O'), R = L1 areas reading it ('I'); cross-area iff some
    writer area differs from some reader area (§4.1a). Only active rows on active steps count."""
    if not de_ids:
        return []
    rows = db.execute(select(BfcNodeDataEntity.data_entity_id, BfcNodeDataEntity.direction, BfcNode.hier_code)
                      .join(BfcNode, BfcNode.bfc_node_id == BfcNodeDataEntity.bfc_node_id)
                      .where(BfcNodeDataEntity.project_id == project_id, BfcNodeDataEntity.is_active,
                             BfcNodeDataEntity.data_entity_id.in_(de_ids),
                             BfcNode.is_active, BfcNode.is_process)).all()
    areas: dict[int, dict[str, set[str]]] = {}
    for de_id, direction, hier in rows:
        areas.setdefault(de_id, {"I": set(), "O": set()})[direction].add(_l1(hier))
    return sorted(de_id for de_id, a in areas.items()
                  if any(w != r for w in a["O"] for r in a["I"]))


def generate_dfd(db: Session, node: BfcNode) -> dict:
    """§7.2a generate_dfd (D-31): the same rows as the process flow, no sequence — no
    BFC_NODE_FLOW read at all. One flow per active step I/O row, EXCEPT an I/O row that an active
    external flow names on the same (step, DE, direction): that one is drawn from/to the party
    instead, and the store is still listed, because another step may read it (§5.3
    BFC_NODE_EXTERNAL_FLOW). An external flow is labelled with its DE name, else its flow_label."""
    if not node.is_active:
        raise HTTPException(409, "This node is retired. Restore it first")
    if node.is_process:
        raise HTTPException(422, "A data flow diagram is drawn for a parent node, not a step")
    steps = steps_under(db, node)
    ids = [s.bfc_node_id for s in steps]

    io = [] if not ids else list(db.scalars(select(BfcNodeDataEntity).where(
        BfcNodeDataEntity.bfc_node_id.in_(ids), BfcNodeDataEntity.is_active)
        .order_by(BfcNodeDataEntity.bfc_node_data_entity_id)))
    ext_rows = [] if not ids else list(db.scalars(select(BfcNodeExternalFlow).where(
        BfcNodeExternalFlow.bfc_node_id.in_(ids), BfcNodeExternalFlow.is_active)
        .order_by(BfcNodeExternalFlow.bfc_node_external_flow_id)))
    de_ids = {r.data_entity_id for r in io} | {x.data_entity_id for x in ext_rows if x.data_entity_id}
    des = {d.data_entity_id: d for d in db.scalars(select(DataEntity).where(
        DataEntity.data_entity_id.in_(de_ids)))} if de_ids else {}
    exts = {x.external_entity_id: x for x in db.scalars(select(ExternalEntity).where(
        ExternalEntity.external_entity_id.in_({r.external_entity_id for r in ext_rows})))} if ext_rows else {}

    covered = {(x.bfc_node_id, x.data_entity_id, x.direction) for x in ext_rows if x.data_entity_id}
    flows = [{"kind": "STORE", "bfc_node_id": r.bfc_node_id, "direction": r.direction,
              "data_entity_id": r.data_entity_id, "external_entity_id": None,
              "bfc_node_data_entity_id": r.bfc_node_data_entity_id, "bfc_node_external_flow_id": None,
              "label": des[r.data_entity_id].de_name}
             for r in io if (r.bfc_node_id, r.data_entity_id, r.direction) not in covered]
    flows += [{"kind": "EXTERNAL", "bfc_node_id": x.bfc_node_id, "direction": x.direction,
               "data_entity_id": x.data_entity_id, "external_entity_id": x.external_entity_id,
               "bfc_node_data_entity_id": None, "bfc_node_external_flow_id": x.bfc_node_external_flow_id,
               "label": des[x.data_entity_id].de_name if x.data_entity_id else x.flow_label}
              for x in ext_rows]
    return {
        "scope": {"bfc_node_id": node.bfc_node_id, "hier_code": node.hier_code, "node_name": node.node_name},
        "processes": [{"bfc_node_id": s.bfc_node_id, "hier_code": s.hier_code, "node_name": s.node_name}
                      for s in steps],
        "stores": [{"data_entity_id": d.data_entity_id, "de_number": d.de_number, "de_name": d.de_name}
                   for d in sorted(des.values(), key=lambda d: d.de_number)],
        "externals": [{"external_entity_id": x.external_entity_id, "ext_number": x.ext_number,
                       "ext_name": x.ext_name} for x in sorted(exts.values(), key=lambda x: x.ext_number)],
        "flows": flows,
        "cross_area": _cross_area(db, node.project_id, set(des)),
        "layout": diagram_layout.positions(db, node.project_id, "DFD", node.bfc_node_id),
    }
