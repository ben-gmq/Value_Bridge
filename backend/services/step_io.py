"""Step I/O — the ONE writer of BFC_NODE_DATA_ENTITY (R2-D13, §7.3 `bfc.ensure_step_io`).

Kept in its own module so business_requirement, bfc and (later) flow_import can all call it
without importing each other. Nothing else writes step I/O.
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow, BrDataEntity, DataEntity
from services import lifecycle
from services.access import NOT_FOUND

DIRECTIONS = ("I", "O")


def live_entity(db: Session, project_id: int, data_entity_id: int) -> DataEntity:
    de = db.get(DataEntity, data_entity_id)
    if de is not None and de.project_id == project_id:
        lifecycle.lock_for_share(db, de)                      # VB-009 (SR-5): an entity retire waits for this link
    if de is None or de.project_id != project_id or not de.is_active:
        raise HTTPException(422, "Choose an active data entity in this project")
    return de


def ensure_step_io(db: Session, actor_id: int, node: BfcNode, data_entity_id: int,
                   direction: str) -> BfcNodeDataEntity:
    """Create, or re-activate, the step I/O row. Never commits — the caller's transaction owns it."""
    if direction not in DIRECTIONS:
        raise HTTPException(422, "direction must be I (input) or O (output)")
    lifecycle.lock_for_share(db, node)                        # SR-5: serialised with a step retire
    if not (node.is_active and node.is_process):
        raise HTTPException(422, "Data flows in and out of a process step only")
    live_entity(db, node.project_id, data_entity_id)
    row = db.scalars(select(BfcNodeDataEntity).where(
        BfcNodeDataEntity.bfc_node_id == node.bfc_node_id,
        BfcNodeDataEntity.data_entity_id == data_entity_id,
        BfcNodeDataEntity.direction == direction)).one_or_none()
    if row is None:
        row = BfcNodeDataEntity(project_id=node.project_id, bfc_node_id=node.bfc_node_id,
                                data_entity_id=data_entity_id, direction=direction,
                                created_by=actor_id)
        db.add(row)
    elif not row.is_active:                                  # restore, never re-insert (S1-7)
        lifecycle.relink(db, actor_id, row)
    db.flush()
    return row


def list_links(db: Session, node: BfcNode) -> list[BfcNodeDataEntity]:
    return list(db.scalars(select(BfcNodeDataEntity).where(
        BfcNodeDataEntity.bfc_node_id == node.bfc_node_id, BfcNodeDataEntity.is_active)))


def link(db: Session, actor_id: int, node: BfcNode, data_entity_id: int, direction: str) -> BfcNodeDataEntity:
    """The step I/O editor. 409 on a live duplicate, like every other link route."""
    live = db.scalars(select(BfcNodeDataEntity).where(
        BfcNodeDataEntity.bfc_node_id == node.bfc_node_id,
        BfcNodeDataEntity.data_entity_id == data_entity_id,
        BfcNodeDataEntity.direction == direction, BfcNodeDataEntity.is_active)).first()
    if live is not None:
        raise HTTPException(409, "That step already has this data in that direction")
    row = ensure_step_io(db, actor_id, node, data_entity_id, direction)
    db.commit()
    return row


def dependents(db: Session, row: BfcNodeDataEntity) -> list[str]:
    """What still needs this step I/O row — each live BR CRUD and external flow, named (D-24, R2-D13). Shared by
    unlink and the flow import's replace mode, which keeps such a row instead of retiring it (§7.2b rule 8)."""
    from models import BusinessRequirement, ExternalEntity
    crud = db.scalars(select(BrDataEntity).where(
        BrDataEntity.bfc_node_id == row.bfc_node_id, BrDataEntity.data_entity_id == row.data_entity_id,
        BrDataEntity.direction == row.direction, BrDataEntity.is_active)).all()
    ext = db.scalars(select(BfcNodeExternalFlow).where(
        BfcNodeExternalFlow.bfc_node_id == row.bfc_node_id,
        BfcNodeExternalFlow.data_entity_id == row.data_entity_id,
        BfcNodeExternalFlow.direction == row.direction, BfcNodeExternalFlow.is_active)).all()
    names = [f"{db.get(BusinessRequirement, c.br_id).br_number} {c.crud_code}" for c in crud]
    names += [f"{db.get(ExternalEntity, x.external_entity_id).ext_number} {x.direction}" for x in ext]
    return names


def unlink(db: Session, actor_id: int, row: BfcNodeDataEntity, row_version: int, commit: bool = True) -> None:
    """Refused while a BR CRUD or an external flow still depends on the row (D-24, R2-D13). `commit=False` (slice
    1e-b piece b): the flow import's replace mode — the check runs again inside its transaction."""
    lifecycle.check_version(row, row_version)
    if names := dependents(db, row):
        raise HTTPException(409, f"Still needed by {', '.join(names)}")
    lifecycle.unlink(db, actor_id, row, row_version, commit=commit)


def hand_off(db: Session, actor_id: int, a: BfcNode, to_bfc_node_id: int, data_entity_id: int) -> dict:
    """D-65 (slice13 §4.4, §7.4): process A hands a data entity to process B — A's output and B's input,
    written through ensure_step_io in ONE transaction, so the derived order A → B appears by itself
    (D-38: order is never stored). B outside A's project is 404 (never named); B in the other chart is
    422 (a diagram never crosses charts). Both rows already live → nothing written, `already` true."""
    b = db.get(BfcNode, to_bfc_node_id)
    if b is None or b.project_id != a.project_id:
        raise HTTPException(404, NOT_FOUND)
    if b.bfc_set_code != a.bfc_set_code:
        raise HTTPException(422, "Diagrams never cross charts: both steps must be in the same chart")
    if b.bfc_node_id == a.bfc_node_id:
        raise HTTPException(422, "A hand-off joins two different process steps")
    lifecycle.lock_for_share(db, a)                           # A then B, as ensure_step_io will (sara L1):
    lifecycle.lock_for_share(db, b)                           # `already` is read under the same locks
    live = set(db.execute(select(BfcNodeDataEntity.bfc_node_id, BfcNodeDataEntity.direction).where(
        BfcNodeDataEntity.data_entity_id == data_entity_id, BfcNodeDataEntity.is_active,
        BfcNodeDataEntity.bfc_node_id.in_((a.bfc_node_id, b.bfc_node_id)))).all())
    already = (a.bfc_node_id, "O") in live and (b.bfc_node_id, "I") in live
    try:
        out_row = ensure_step_io(db, actor_id, a, data_entity_id, "O")
        in_row = ensure_step_io(db, actor_id, b, data_entity_id, "I")
        db.commit()
    except Exception:
        db.rollback()                                         # D2: never A's output without B's input
        raise
    return {"output": out_row, "input": in_row, "already": already}
