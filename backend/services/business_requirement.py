"""Business requirements (§7.3, D-2, D-24). A BR is never created from a route: it appears with
its process step (create_node / mark_process) and the consultant edits it."""
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BfcNode, BrDataEntity, BusinessRequirement
from services import numbering, step_io
from services.code_master import resolve, validate_required_code
from services import lifecycle

log = logging.getLogger("vb")

CRUD = ("C", "R", "U", "D")
EDITABLE = ("br_statement", "business_logic", "output_expectation")
# Set only by the baseline freeze, never chosen by a person (Ben, 2026-09-29, S1-8).
SYSTEM_SET_STATUSES = frozenset({"BASELINED", "SUPERSEDED"})


def create_br(db: Session, actor_id: int, node: BfcNode) -> BusinessRequirement:
    """Same transaction as the node change; never commits. Exactly one live BR per node (D-2)."""
    if not node.is_process:
        raise HTTPException(422, "A business requirement attaches to a process step")
    draft = next((c for c in resolve(db, node.project_id, "BR_STATUS") if c.code == "DRAFT"), None)
    if draft is None:                                          # L6: detail in the log only
        log.error("BR_STATUS/DRAFT missing for project %s", node.project_id)
        raise HTTPException(500, "Something went wrong.")
    br = BusinessRequirement(project_id=node.project_id, bfc_node_id=node.bfc_node_id,
                             br_number=numbering.next_number(db, node.project_id, "BR"),
                             status_code_id=draft.code_id, created_by=actor_id)
    db.add(br)
    db.flush()
    return br


def list_brs(db: Session, project_id: int, include_retired: bool = False) -> list[BusinessRequirement]:
    q = select(BusinessRequirement).where(BusinessRequirement.project_id == project_id)
    if not include_retired:
        q = q.where(BusinessRequirement.is_active)
    return list(db.scalars(q.order_by(BusinessRequirement.br_number)))


def update_br(db: Session, actor_id: int, br: BusinessRequirement, row_version: int,
              fields: dict, status_code: str | None) -> BusinessRequirement:
    lifecycle.check_live(br, row_version)
    for k in EDITABLE:
        if k in fields:
            setattr(br, k, fields[k])
    if status_code is not None:
        if status_code in SYSTEM_SET_STATUSES:
            raise HTTPException(422, f"{status_code.title()} is set by the baseline freeze, not by hand")
        br.status_code_id = validate_required_code(db, br.project_id, "BR_STATUS", status_code,
                                                   "status_code").code_id
    br.updated_by = actor_id
    db.commit()
    db.refresh(br)                 # reload the code relationship with the new id
    return br


def link_data_entity(db: Session, actor_id: int, br: BusinessRequirement, data_entity_id: int,
                     crud_code: str, usage_note: str | None) -> BrDataEntity:
    """D-24: the step I/O that licenses the CRUD is created in the same transaction."""
    if crud_code not in CRUD:
        raise HTTPException(422, "crud_code must be one of C, R, U, D")
    lifecycle.lock_for_share(db, db.get(BfcNode, br.bfc_node_id))    # SR-5: the step first
    db.refresh(br)
    if not br.is_active:
        raise HTTPException(409, f"{br.br_number} is retired. Restore it first.")
    node = db.get(BfcNode, br.bfc_node_id)
    step_io.ensure_step_io(db, actor_id, node, data_entity_id, "I" if crud_code == "R" else "O")
    row = db.scalars(select(BrDataEntity).where(
        BrDataEntity.br_id == br.br_id, BrDataEntity.data_entity_id == data_entity_id,
        BrDataEntity.crud_code == crud_code)).one_or_none()
    if row is None:
        row = BrDataEntity(project_id=br.project_id, br_id=br.br_id, bfc_node_id=br.bfc_node_id,
                           data_entity_id=data_entity_id, crud_code=crud_code,
                           usage_note=usage_note, created_by=actor_id)
        db.add(row)
    elif row.is_active:
        raise HTTPException(409, f"{br.br_number} already has {crud_code} on that entity")
    else:                                                     # re-link restores (S1-7)
        lifecycle.relink(db, actor_id, row)
        row.usage_note = usage_note
    db.commit()
    db.refresh(row)
    return row


def list_data_links(db: Session, br: BusinessRequirement) -> list[BrDataEntity]:
    return list(db.scalars(select(BrDataEntity).where(BrDataEntity.br_id == br.br_id,
                                                      BrDataEntity.is_active)))


def unlink_data_entity(db: Session, actor_id: int, row: BrDataEntity, row_version: int) -> None:
    """The step I/O stays: it is a fact about the step, removed on its own (§7.3)."""
    lifecycle.unlink(db, actor_id, row, row_version)
