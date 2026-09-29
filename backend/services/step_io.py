"""Step I/O — the ONE writer of BFC_NODE_DATA_ENTITY (R2-D13, §7.3 `bfc.ensure_step_io`).

Kept in its own module so business_requirement, bfc and (later) flow_import can all call it
without importing each other. Nothing else writes step I/O.
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow, BrDataEntity, DataEntity
from services import lifecycle

DIRECTIONS = ("I", "O")


def live_entity(db: Session, project_id: int, data_entity_id: int) -> DataEntity:
    de = db.get(DataEntity, data_entity_id)
    if de is None or de.project_id != project_id or not de.is_active:
        raise HTTPException(422, "Choose an active data entity in this project")
    return de


def ensure_step_io(db: Session, actor_id: int, node: BfcNode, data_entity_id: int,
                   direction: str) -> BfcNodeDataEntity:
    """Create, or re-activate, the step I/O row. Never commits — the caller's transaction owns it."""
    if direction not in DIRECTIONS:
        raise HTTPException(422, "direction must be I (input) or O (output)")
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


def unlink(db: Session, actor_id: int, row: BfcNodeDataEntity, row_version: int) -> None:
    """Refused while a BR CRUD or an external flow still depends on the row (D-24, R2-D13)."""
    lifecycle.check_version(row, row_version)
    crud = db.scalars(select(BrDataEntity).where(
        BrDataEntity.bfc_node_id == row.bfc_node_id, BrDataEntity.data_entity_id == row.data_entity_id,
        BrDataEntity.direction == row.direction, BrDataEntity.is_active)).all()
    ext = db.scalars(select(BfcNodeExternalFlow).where(
        BfcNodeExternalFlow.bfc_node_id == row.bfc_node_id,
        BfcNodeExternalFlow.data_entity_id == row.data_entity_id,
        BfcNodeExternalFlow.direction == row.direction, BfcNodeExternalFlow.is_active)).all()
    if crud or ext:
        from models import BusinessRequirement, ExternalEntity
        names = [f"{db.get(BusinessRequirement, c.br_id).br_number} {c.crud_code}" for c in crud]
        names += [f"{db.get(ExternalEntity, x.external_entity_id).ext_number} {x.direction}" for x in ext]
        raise HTTPException(409, f"Still needed by {', '.join(names)}")
    lifecycle.unlink(db, actor_id, row, row_version)
