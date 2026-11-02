"""Slice Risks routes (§4.10; docs/slice_risks_spec.md §7). Reads are project_ctx / object_guard at VIEW; every write
needs EDIT and component RISK, so a project with it off answers 409 COMPONENT_OFF; promote also needs ISSUE (the
service checks it). A risk of a project you cannot see is a 404."""
from fastapi import Depends
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser, Risk
from routers.guards import GuardedRouter, object_guard, project_ctx
from schemas.risk import MaterialisedOut, MaterialiseIn, RiskIn, RiskOut, RiskPatch
from services import risk as risk_service

router = GuardedRouter(tags=["risks"])
_read = project_ctx("VIEW")
_edit = project_ctx("EDIT", "RISK")
_r, _w = object_guard(Risk, "VIEW"), object_guard(Risk, "EDIT", component="RISK")


def _out(db: Session, risk: Risk) -> Risk:
    risk.materialised_issue_number = risk_service.issue_number_of(db, risk)
    return risk


@router.get("/projects/{project_id}/risks", response_model=list[RiskOut], **_read.route)
def list_risks(project_id: int, include_retired: bool = False, status: str | None = None,
               owner_org_role_id: int | None = None, phase_id: int | None = None, issue_id: int | None = None,
               db: Session = Depends(get_db)):
    """`issue_id`: the risk an issue materialised from (the issue page's back-link)."""
    rows = risk_service.list_risks(db, project_id, include_retired, status=status,
                                   owner_org_role_id=owner_org_role_id, phase_id=phase_id, issue_id=issue_id)
    return [_out(db, r) for r in rows]


@router.post("/projects/{project_id}/risks", response_model=RiskOut, status_code=201, **_edit.route)
def raise_risk(project_id: int, body: RiskIn, user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return _out(db, risk_service.raise_risk(db, user.app_user_id, project_id, body.model_dump()))


@router.get("/risks/{id}", response_model=RiskOut, **_r.route)
def read_risk(id: int, risk: Risk = Depends(_r.dep), db: Session = Depends(get_db)):
    return _out(db, risk)


@router.patch("/risks/{id}", response_model=RiskOut, **_w.route)
def update_risk(id: int, body: RiskPatch, risk: Risk = Depends(_w.dep), user: AppUser = Depends(current_user),
                db: Session = Depends(get_db)):
    return _out(db, risk_service.update_risk(db, user.app_user_id, risk, body.row_version,
                                             body.model_dump(exclude_unset=True, exclude={"row_version"})))


@router.post("/risks/{id}/materialise", response_model=MaterialisedOut, **_w.route)
def materialise_risk(id: int, body: MaterialiseIn, risk: Risk = Depends(_w.dep),
                     user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    risk, issue = risk_service.materialise(db, user.app_user_id, risk, body.row_version,
                                           body.model_dump(exclude={"row_version"}))
    return {"risk": _out(db, risk), "issue": issue}


@router.delete("/risks/{id}", status_code=204, **_w.route)
def retire_risk(id: int, row_version: int, risk: Risk = Depends(_w.dep), user: AppUser = Depends(current_user),
                db: Session = Depends(get_db)):
    """R1-2: refused on a materialised risk; otherwise refused while nothing points at it (nothing does today)."""
    risk_service.retire_risk(db, user.app_user_id, risk, row_version)


@router.patch("/risks/{id}/restore", response_model=RiskOut, **_w.route)
def restore_risk(id: int, risk: Risk = Depends(_w.dep), user: AppUser = Depends(current_user),
                 db: Session = Depends(get_db)):
    return _out(db, risk_service.restore_risk(db, user.app_user_id, risk))
