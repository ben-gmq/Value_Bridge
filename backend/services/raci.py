"""RACI links for process steps and business requirements (§5.4.5, Q7). Rules key on the code's
behaviour, never its letter (VB law 5): the behaviour is copied from the code here, and the
database refuses a copy that disagrees."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BfcNode, BfcNodeOrgRole, BrOrgRole, BusinessRequirement, OrgRole
from services.code_master import validate_required_code
from services import lifecycle

SINGLE = {BfcNodeOrgRole: ("ACCOUNTABLE", "RESPONSIBLE"), BrOrgRole: ("ACCOUNTABLE",)}


def _owner(model):
    return ("bfc_node_id", BfcNode) if model is BfcNodeOrgRole else ("br_id", BusinessRequirement)


def list_links(db: Session, model, owner_id: int) -> list:
    col, _ = _owner(model)
    return list(db.scalars(select(model).where(getattr(model, col) == owner_id, model.is_active)))


def link(db: Session, actor_id: int, model, owner, org_role_id: int, raci_code: str):
    col, _ = _owner(model)
    owner_id = getattr(owner, col)
    if model is BfcNodeOrgRole:                               # SR-5: the step, FOR SHARE, first
        lifecycle.lock_for_share(db, owner)
    else:
        lifecycle.lock_for_share(db, db.get(BfcNode, owner.bfc_node_id))
        lifecycle.lock_for_share(db, owner)                   # the BR too, after the step (sara M2)
    if not owner.is_active:
        raise HTTPException(409, "Restore it first")
    if model is BfcNodeOrgRole and not owner.is_process:
        raise HTTPException(422, "Roles are assigned to a process step")
    role = db.get(OrgRole, org_role_id)
    if role is None or role.project_id != owner.project_id or not role.is_active:
        raise HTTPException(422, "Choose an active org role in this project")
    code = validate_required_code(db, owner.project_id, "RACI_TYPE", raci_code, "raci_code")
    if code.behaviour_code in SINGLE[model]:
        taken = db.scalars(select(model).where(getattr(model, col) == owner_id, model.is_active,
                                               model.raci_behaviour == code.behaviour_code)).first()
        if taken is not None and taken.org_role_id != org_role_id:
            holder = db.get(OrgRole, taken.org_role_id).org_role_code
            raise HTTPException(409, f"{holder} is already {code.behaviour_code.title()}. "
                                     "Remove that first.")
    row = db.scalars(select(model).where(getattr(model, col) == owner_id,
                                         model.org_role_id == org_role_id,
                                         model.raci_code_id == code.code_id)).one_or_none()
    if row is None:
        row = model(project_id=owner.project_id, org_role_id=org_role_id, raci_code_id=code.code_id,
                    raci_behaviour=code.behaviour_code, created_by=actor_id, **{col: owner_id})
        db.add(row)
    elif row.is_active:
        raise HTTPException(409, f"{role.org_role_code} already has {raci_code} here")
    else:                                                     # re-link restores (S1-7)
        lifecycle.relink(db, actor_id, row)
        row.raci_behaviour = code.behaviour_code
    db.commit()
    db.refresh(row)
    return row


def unlink(db: Session, actor_id: int, row, row_version: int) -> None:
    lifecycle.unlink(db, actor_id, row, row_version)
