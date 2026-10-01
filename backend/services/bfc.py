"""The Business Function Chart (§7.2, D-23, S1-2). level_no, seq_no and hier_code are derived
here and nowhere else; is_process is the only process test (VB law 4)."""
import re
import unicodedata

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow, BfcNodeFlow, BfcNodeOrgRole,
                    BusinessRequirement, ExternalEntity)
from services import audit, business_requirement, step_io
from services import lifecycle
from services.lifecycle import restore

MAX_LEVEL = 5
MAX_SIBLINGS = 99                  # two-digit hier_code segments (S1-3)
PROCESS_LEVELS = (3, 4, 5)         # A-47


def normalise_name(s: str) -> str:
    """Q1 — one definition, shared with the flow import."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip().casefold()


def _children(db: Session, project_id: int, parent_id: int | None) -> list[BfcNode]:
    parent = (BfcNode.parent_bfc_node_id == parent_id) if parent_id is not None \
        else BfcNode.parent_bfc_node_id.is_(None)
    return list(db.scalars(select(BfcNode).where(BfcNode.project_id == project_id, parent,
                                                 BfcNode.is_active).order_by(BfcNode.seq_no)))


def assert_name_free(db: Session, project_id: int, parent_id: int | None, name: str,
                     except_id: int | None = None) -> None:
    want = normalise_name(name)
    for sib in _children(db, project_id, parent_id):
        if sib.bfc_node_id != except_id and normalise_name(sib.node_name) == want:
            raise HTTPException(409, f"'{name}' already exists under this parent ({sib.hier_code})")


def _code(parent: BfcNode | None, seq_no: int) -> str:
    seg = f"{seq_no:02d}"
    return seg if parent is None else f"{parent.hier_code}.{seg}"


def _live_node(db: Session, project_id: int, node_id: int) -> BfcNode:
    node = db.get(BfcNode, node_id)
    if node is None or node.project_id != project_id or not node.is_active:
        raise HTTPException(422, "Choose an active parent node in this project")
    return node


def tree(db: Session, project_id: int, include_retired: bool = False) -> list[dict]:
    q = select(BfcNode, BusinessRequirement.br_number).outerjoin(
        BusinessRequirement, (BusinessRequirement.bfc_node_id == BfcNode.bfc_node_id)
        & BusinessRequirement.is_active).where(BfcNode.project_id == project_id)
    if not include_retired:
        q = q.where(BfcNode.is_active)
    return [{"node": n, "br_number": br} for n, br in db.execute(q.order_by(BfcNode.hier_code))]


def create_node(db: Session, actor_id: int, project_id: int, parent_id: int | None, name: str,
                is_process: bool = False, purpose_desc: str | None = None) -> BfcNode:
    parent = _live_node(db, project_id, parent_id) if parent_id is not None else None
    level = 1 if parent is None else parent.level_no + 1
    if level > MAX_LEVEL:
        raise HTTPException(422, "The chart is fixed at 5 levels")
    if parent is not None and parent.is_process:
        raise HTTPException(422, "A process has no children. Split it into sub-steps first")
    if is_process and level not in PROCESS_LEVELS:
        raise HTTPException(422, "A process sits at level 3, 4 or 5")
    assert_name_free(db, project_id, parent_id, name)
    siblings = _children(db, project_id, parent_id)
    seq_no = (siblings[-1].seq_no if siblings else 0) + 1
    if seq_no > MAX_SIBLINGS:
        raise HTTPException(422, f"A node holds at most {MAX_SIBLINGS} children")
    node = BfcNode(project_id=project_id, parent_bfc_node_id=parent_id, level_no=level,
                   seq_no=seq_no, hier_code=_code(parent, seq_no), node_name=name,
                   # A-54 default, mirroring ck_bfc_l5_is_process; never a process TEST (law 4)
                   is_process=is_process or level == MAX_LEVEL,
                   purpose_desc=purpose_desc, created_by=actor_id)
    db.add(node)
    db.flush()
    if node.is_process:
        business_requirement.create_br(db, actor_id, node)            # D-2, same transaction
    db.commit()
    return node


def update_node(db: Session, actor_id: int, node: BfcNode, row_version: int, fields: dict) -> BfcNode:
    lifecycle.check_live(node, row_version)
    if "node_name" in fields:
        assert_name_free(db, node.project_id, node.parent_bfc_node_id, fields["node_name"],
                         except_id=node.bfc_node_id)
        node.node_name = fields["node_name"]
    if "purpose_desc" in fields:
        node.purpose_desc = fields["purpose_desc"]
    if "data_processing_desc" in fields:
        if fields["data_processing_desc"] is not None and not node.is_process:
            raise HTTPException(422, "Only a process step describes its data processing")
        node.data_processing_desc = fields["data_processing_desc"]
    node.updated_by = actor_id
    db.commit()
    return node


def _subtree(db: Session, root: BfcNode) -> list[BfcNode]:
    """root and every descendant, live or retired, parents before children."""
    out, frontier = [root], [root]
    while frontier:
        ids = [n.bfc_node_id for n in frontier]
        frontier = list(db.scalars(select(BfcNode).where(BfcNode.parent_bfc_node_id.in_(ids))))
        out.extend(frontier)
    return out


def reorder(db: Session, actor_id: int, node: BfcNode, row_version: int, new_seq_no: int) -> BfcNode:
    """S1-2: two phases for seq_no AND hier_code; every shifted sibling's subtree is re-coded."""
    lifecycle.check_live(node, row_version)
    siblings = _children(db, node.project_id, node.parent_bfc_node_id)
    if not 1 <= new_seq_no <= len(siblings):
        raise HTTPException(422, f"Position must be between 1 and {len(siblings)}")
    order = [s for s in siblings if s is not node]
    order.insert(new_seq_no - 1, node)
    moved = [(s, i) for i, s in enumerate(order, start=1) if s.seq_no != i]
    if not moved:
        return node
    old = node.seq_no
    live_subtrees = {s.bfc_node_id: [n for n in _subtree(db, s) if n.is_active] for s, _ in moved}
    for s, _ in moved:                                              # phase 1: out of the way
        s.seq_no = -s.seq_no
        for n in live_subtrees[s.bfc_node_id]:
            n.hier_code = f"~{n.bfc_node_id}"
    db.flush()
    parent = db.get(BfcNode, node.parent_bfc_node_id) if node.parent_bfc_node_id else None
    for s, target in moved:                                         # phase 2: into place
        s.seq_no = target
        s.hier_code = _code(parent, target)
        for n in live_subtrees[s.bfc_node_id][1:]:                  # parents precede children
            n.hier_code = _code(db.get(BfcNode, n.parent_bfc_node_id), n.seq_no)
        s.updated_by = actor_id
    db.flush()
    audit.record(db, "BFC_REORDERED", actor_id=actor_id, project_id=node.project_id,
                 target_table="bfc_node", target_id=node.bfc_node_id,
                 detail={"from": old, "to": new_seq_no,
                         "subtree_size": sum(len(v) for v in live_subtrees.values())})
    db.commit()
    return node


def _step_blockers(db: Session, node: BfcNode) -> list[str]:
    out = []
    br = db.scalars(select(BusinessRequirement).where(
        BusinessRequirement.bfc_node_id == node.bfc_node_id, BusinessRequirement.is_active)).first()
    if br:
        out.append(f"business requirement {br.br_number}")
    for model, what in ((BfcNodeDataEntity, "step data"), (BfcNodeOrgRole, "step roles"),
                        (BfcNodeExternalFlow, "external flows")):
        n = db.scalar(select(func.count()).select_from(model).where(
            model.bfc_node_id == node.bfc_node_id, model.is_active))
        if n:
            out.append(f"{n} {what}")
    edges = db.scalar(select(func.count()).select_from(BfcNodeFlow).where(
        (BfcNodeFlow.from_bfc_node_id == node.bfc_node_id)
        | (BfcNodeFlow.to_bfc_node_id == node.bfc_node_id), BfcNodeFlow.is_active))
    if edges:
        out.append(f"{edges} flow edges")
    if node.data_processing_desc:
        out.append("the data processing description")
    return out


def mark_process(db: Session, actor_id: int, node: BfcNode, row_version: int,
                 is_process: bool) -> BusinessRequirement | None:
    """D-23. Promote creates the BR; demote is refused, never cascaded, while step facts live."""
    lifecycle.check_live(node, row_version)
    if is_process == node.is_process:
        return None
    if is_process:
        if node.level_no not in PROCESS_LEVELS:
            raise HTTPException(422, "A process sits at level 3, 4 or 5")
        if _children(db, node.project_id, node.bfc_node_id):
            raise HTTPException(409, "This node has sub-steps; the lowest one is the process")
        node.is_process, node.updated_by = True, actor_id
        db.flush()
        br = business_requirement.create_br(db, actor_id, node)
        db.commit()
        return br
    if node.level_no == MAX_LEVEL:
        raise HTTPException(422, "A level-5 node is always a process")
    blockers = _step_blockers(db, node)
    if blockers:
        raise HTTPException(409, "Retire first: " + ", ".join(blockers))
    node.is_process, node.updated_by = False, actor_id
    db.commit()
    return None


def _free_slot(db: Session, n: BfcNode) -> None:
    """§7.12: the name must be free, and a node whose code a live node now holds is renumbered
    to the end of its parent (R2-D10)."""
    assert_name_free(db, n.project_id, n.parent_bfc_node_id, n.node_name, except_id=n.bfc_node_id)
    siblings = _children(db, n.project_id, n.parent_bfc_node_id)
    if any(s.seq_no == n.seq_no for s in siblings):
        n.seq_no = (siblings[-1].seq_no if siblings else 0) + 1
        if n.seq_no > MAX_SIBLINGS:
            raise HTTPException(422, f"A node holds at most {MAX_SIBLINGS} children")
    # sara H1: always re-derive — a retired node's code goes stale when its parent is
    # reordered or restored elsewhere, since a retired code is only history (R2-D10).
    parent = db.get(BfcNode, n.parent_bfc_node_id) if n.parent_bfc_node_id else None
    if parent is not None and parent.is_process:
        raise HTTPException(409, f"{parent.hier_code} {parent.node_name} is now a process step, "
                                 "so it cannot hold this node. Make it a summary node first")
    n.hier_code = _code(parent, n.seq_no)


def restore_node(db: Session, actor_id: int, node: BfcNode) -> BfcNode:
    """The plain restore (commits). A step retired with its dependents is restored through
    step_retire instead (SR-1), which the route checks first."""
    restore(db, actor_id, node, before_activate=lambda n: _free_slot(db, n))
    return node


def restore_node_row(db: Session, actor_id: int, node: BfcNode, detail: dict | None = None) -> None:
    """The same restore with NO commit, for step_retire's one transaction (SR-2)."""
    lifecycle.restore_row(db, actor_id, node, before_activate=lambda n: _free_slot(db, n), detail=detail)


# ---- external flows (D-24a, R2-D13) --------------------------------------------------------

def link_external_flow(db: Session, actor_id: int, node: BfcNode, external_entity_id: int,
                       direction: str, data_entity_id: int | None, flow_label: str | None,
                       note: str | None) -> BfcNodeExternalFlow:
    if direction not in step_io.DIRECTIONS:
        raise HTTPException(422, "direction must be I (from the party) or O (to the party)")
    lifecycle.lock_for_share(db, node)                        # SR-5: serialised with a step retire
    if not (node.is_active and node.is_process):
        raise HTTPException(422, "External parties exchange data with a process step only")
    ext = db.get(ExternalEntity, external_entity_id)
    if ext is None or ext.project_id != node.project_id or not ext.is_active:
        raise HTTPException(422, "Choose an active external party in this project")
    if data_entity_id is not None:
        step_io.ensure_step_io(db, actor_id, node, data_entity_id, direction)
    de_match = (BfcNodeExternalFlow.data_entity_id == data_entity_id) if data_entity_id is not None \
        else BfcNodeExternalFlow.data_entity_id.is_(None)
    row = db.scalars(select(BfcNodeExternalFlow).where(
        BfcNodeExternalFlow.bfc_node_id == node.bfc_node_id,
        BfcNodeExternalFlow.external_entity_id == external_entity_id,
        BfcNodeExternalFlow.direction == direction, de_match)).one_or_none()
    if row is None:
        row = BfcNodeExternalFlow(project_id=node.project_id, bfc_node_id=node.bfc_node_id,
                                  external_entity_id=external_entity_id, direction=direction,
                                  data_entity_id=data_entity_id, created_by=actor_id)
        db.add(row)
    elif row.is_active:
        raise HTTPException(409, f"That flow with {ext.ext_number} already exists")
    else:                                                     # re-link restores (S1-7)
        lifecycle.relink(db, actor_id, row)
    row.flow_label, row.note = flow_label, note
    db.commit()
    db.refresh(row)
    return row


def list_external_flows(db: Session, node: BfcNode) -> list[BfcNodeExternalFlow]:
    return list(db.scalars(select(BfcNodeExternalFlow).where(
        BfcNodeExternalFlow.bfc_node_id == node.bfc_node_id, BfcNodeExternalFlow.is_active)))


def unlink_external_flow(db: Session, actor_id: int, row: BfcNodeExternalFlow, row_version: int) -> None:
    lifecycle.unlink(db, actor_id, row, row_version)
