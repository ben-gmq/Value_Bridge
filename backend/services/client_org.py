"""Client organisation (§5.3 ORG_UNIT / ORG_ROLE, S1-7). level_no and seq_no are derived here;
the level code defaults from the level and may be overridden per unit."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import OrgRole, OrgUnit
from services.code_master import resolve, validate_required_code
from services import lifecycle

MAX_LEVEL = 3


def list_units(db: Session, project_id: int) -> list[OrgUnit]:
    return list(db.scalars(select(OrgUnit).where(OrgUnit.project_id == project_id, OrgUnit.is_active)
                           .order_by(OrgUnit.level_no, OrgUnit.parent_org_unit_id, OrgUnit.seq_no)))


def _level_code(db: Session, project_id: int, level_no: int, code: str | None) -> int:
    if code:
        return validate_required_code(db, project_id, "ORG_UNIT_LEVEL", code, "level_code").code_id
    levels = resolve(db, project_id, "ORG_UNIT_LEVEL")
    if len(levels) < level_no:
        raise HTTPException(422, "level_code is required at this level")
    return levels[level_no - 1].code_id


def create_unit(db: Session, actor_id: int, project_id: int, parent_id: int | None, code: str,
                name: str, level_code: str | None, description: str | None) -> OrgUnit:
    parent = None
    if parent_id is not None:
        parent = db.get(OrgUnit, parent_id)
        if parent is None or parent.project_id != project_id or not parent.is_active:
            raise HTTPException(422, "Choose an active parent unit in this project")
    level = 1 if parent is None else parent.level_no + 1
    if level > MAX_LEVEL:
        raise HTTPException(422, "The client organisation is fixed at 3 levels")
    siblings = db.scalars(select(OrgUnit.seq_no).where(
        OrgUnit.project_id == project_id, OrgUnit.is_active,
        OrgUnit.parent_org_unit_id == parent_id if parent_id else OrgUnit.parent_org_unit_id.is_(None))
    ).all()
    seq_no = max(siblings, default=0) + 1
    if seq_no > 99:
        raise HTTPException(422, "A unit holds at most 99 children")
    unit = OrgUnit(project_id=project_id, parent_org_unit_id=parent_id, level_no=level,
                   level_code_id=_level_code(db, project_id, level, level_code),
                   org_unit_code=code, org_unit_name=name, seq_no=seq_no,
                   description=description, created_by=actor_id)
    db.add(unit)
    db.commit()
    return unit


def update_unit(db: Session, actor_id: int, unit: OrgUnit, row_version: int, fields: dict,
                level_code: str | None) -> OrgUnit:
    lifecycle.check_live(unit, row_version)
    for k in ("org_unit_code", "org_unit_name", "description"):
        if k in fields:
            setattr(unit, k, fields[k])
    if level_code is not None:
        unit.level_code_id = _level_code(db, unit.project_id, unit.level_no, level_code)
    unit.updated_by = actor_id
    db.commit()
    return unit


def list_roles(db: Session, project_id: int) -> list[OrgRole]:
    return list(db.scalars(select(OrgRole).where(OrgRole.project_id == project_id, OrgRole.is_active)
                           .order_by(OrgRole.org_role_code)))


def create_role(db: Session, actor_id: int, project_id: int, org_unit_id: int, code: str,
                name: str, responsibility_desc: str | None, headcount: int | None) -> OrgRole:
    unit = db.get(OrgUnit, org_unit_id)
    if unit is None or unit.project_id != project_id or not unit.is_active:
        raise HTTPException(422, "Choose an active org unit in this project")
    role = OrgRole(project_id=project_id, org_unit_id=org_unit_id, org_role_code=code,
                   org_role_name=name, responsibility_desc=responsibility_desc,
                   headcount=headcount, created_by=actor_id)
    db.add(role)
    db.commit()
    return role


def update_role(db: Session, actor_id: int, role: OrgRole, row_version: int, fields: dict) -> OrgRole:
    lifecycle.check_live(role, row_version)
    if "org_unit_id" in fields:
        unit = db.get(OrgUnit, fields["org_unit_id"])
        if unit is None or unit.project_id != role.project_id or not unit.is_active:
            raise HTTPException(422, "Choose an active org unit in this project")
    for k in ("org_unit_id", "org_role_code", "org_role_name", "responsibility_desc", "headcount"):
        if k in fields:
            setattr(role, k, fields[k])
    role.updated_by = actor_id
    db.commit()
    return role


def restore_unit(db: Session, actor_id: int, unit: OrgUnit) -> OrgUnit:
    """sara M3: a retired unit whose position was taken comes back at the end of its parent."""
    def _free(row: OrgUnit) -> None:
        parent = (OrgUnit.parent_org_unit_id == row.parent_org_unit_id) if row.parent_org_unit_id \
            else OrgUnit.parent_org_unit_id.is_(None)
        seqs = set(db.scalars(select(OrgUnit.seq_no).where(OrgUnit.project_id == row.project_id,
                                                           OrgUnit.is_active, parent)))
        if row.seq_no in seqs:
            row.seq_no = max(seqs) + 1
            if row.seq_no > 99:
                raise HTTPException(422, "A unit holds at most 99 children")
    lifecycle.restore(db, actor_id, unit, before_activate=_free)
    return unit
