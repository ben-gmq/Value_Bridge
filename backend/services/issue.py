"""Issue management (§4.5; docs/slice14_issue_spec.md; I-1…I-16). The one owner of stakeholder and issue writes.

Stakeholders: a named client-side person, no login (D-4); org unit optional (I-2); the live name is unique per org
unit (I-16). Retiring one is refused while a live issue names them (I-7) — lifecycle.retire finds that through the
FK. Audit labels carry ids and numbers only, never a name or title (R7)."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import OrgUnit, Stakeholder
from services import lifecycle


def _text(value: str | None, field: str, required: bool = False) -> str | None:
    v = (value or "").strip()
    if required and not v:
        raise HTTPException(422, f"{field} cannot be empty")
    if len(v) > 200:
        raise HTTPException(422, f"{field} is longer than 200 characters")
    return v or None


def _org_unit(db: Session, project_id: int, org_unit_id: int | None) -> int | None:
    """R11: the unit is read FOR SHARE, so a unit retire and a stakeholder save are serialised. Another project's
    unit is the same 422 as a missing one (a bad id in a body, as client_org.create_role; sara A M-3)."""
    if org_unit_id is None:
        return None
    unit = db.scalars(select(OrgUnit).where(OrgUnit.org_unit_id == org_unit_id,
                                            OrgUnit.project_id == project_id)).one_or_none()
    if unit is None:
        raise HTTPException(422, "Choose an org unit in this project")
    lifecycle.lock_for_share(db, unit)
    if not unit.is_active:
        raise HTTPException(409, f"{lifecycle.label(unit)} is retired. Restore it first.")
    return unit.org_unit_id


def _check_name_free(db: Session, project_id: int, org_unit_id: int | None, name: str,
                     stakeholder_id: int | None = None) -> None:
    """I-16: unique among live stakeholders of the same unit, as uq_stk_name_live normalises it. The index still
    decides a race; this names the clash in the ordinary case."""
    q = select(Stakeholder.stakeholder_id).where(
        Stakeholder.project_id == project_id, Stakeholder.is_active,
        func.coalesce(Stakeholder.org_unit_id, 0) == (org_unit_id or 0),
        func.lower(func.btrim(Stakeholder.stakeholder_name)) == name.strip().lower())
    if stakeholder_id is not None:
        q = q.where(Stakeholder.stakeholder_id != stakeholder_id)
    if db.scalar(q.limit(1)) is not None:
        raise HTTPException(409, "A stakeholder with this name already exists in this org unit")


def list_stakeholders(db: Session, project_id: int, include_retired: bool = False) -> list[Stakeholder]:
    q = select(Stakeholder).where(Stakeholder.project_id == project_id)
    if not include_retired:
        q = q.where(Stakeholder.is_active)
    return list(db.scalars(q.order_by(func.lower(Stakeholder.stakeholder_name), Stakeholder.stakeholder_id)))


def create_stakeholder(db: Session, actor_id: int, project_id: int, fields: dict) -> Stakeholder:
    name = _text(fields.get("stakeholder_name"), "stakeholder_name", required=True)
    unit_id = _org_unit(db, project_id, fields.get("org_unit_id"))
    _check_name_free(db, project_id, unit_id, name)
    stk = Stakeholder(project_id=project_id, org_unit_id=unit_id, stakeholder_name=name,
                      job_title=_text(fields.get("job_title"), "job_title"),
                      is_bpo=bool(fields.get("is_bpo", False)), created_by=actor_id)
    db.add(stk)
    db.commit()
    db.refresh(stk)
    return stk


def update_stakeholder(db: Session, actor_id: int, stk: Stakeholder, row_version: int, fields: dict) -> Stakeholder:
    lifecycle.check_live(stk, row_version)
    if "stakeholder_name" in fields:
        stk.stakeholder_name = _text(fields["stakeholder_name"], "stakeholder_name", required=True)
    if "job_title" in fields:
        stk.job_title = _text(fields["job_title"], "job_title")
    if "is_bpo" in fields:
        if fields["is_bpo"] is None:
            raise HTTPException(422, "is_bpo cannot be empty")
        stk.is_bpo = fields["is_bpo"]
    if "org_unit_id" in fields:
        stk.org_unit_id = _org_unit(db, stk.project_id, fields["org_unit_id"])
    _check_name_free(db, stk.project_id, stk.org_unit_id, stk.stakeholder_name, stk.stakeholder_id)
    stk.updated_by = actor_id
    db.commit()
    db.refresh(stk)
    return stk


def restore_stakeholder(db: Session, actor_id: int, stk: Stakeholder) -> Stakeholder:
    """A live namesake in the same unit may have been added meanwhile → 409. A retired unit refuses through
    lifecycle.restore (RESTORE_FIRST)."""
    lifecycle.lock(db, stk)
    if stk.is_active:
        raise HTTPException(409, f"{lifecycle.label(stk)} is not retired")
    _check_name_free(db, stk.project_id, stk.org_unit_id, stk.stakeholder_name, stk.stakeholder_id)
    lifecycle.restore(db, actor_id, stk)
    db.refresh(stk)
    return stk
