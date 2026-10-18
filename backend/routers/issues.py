"""Slice 14 routes (§4.5, docs/slice14_issue_spec.md §8): stakeholders and issues.

Reads are project_ctx / object_guard at VIEW; every write needs EDIT and component ISSUE (I-9), so a project with the
component off answers 409 COMPONENT_OFF. A row of a project you cannot see is a 404."""
from fastapi import Depends
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser, Stakeholder
from routers.guards import GuardedRouter, object_guard, project_ctx
from schemas.issue import StakeholderIn, StakeholderOut, StakeholderPatch
from services import issue as issue_service, lifecycle

router = GuardedRouter(tags=["issues"])
_read = project_ctx("VIEW")
_edit = project_ctx("EDIT", "ISSUE")
_stk_r, _stk_w = object_guard(Stakeholder, "VIEW"), object_guard(Stakeholder, "EDIT", component="ISSUE")


def _uid(user: AppUser) -> int:
    return user.app_user_id


# ---- stakeholders (§4.5 create_stakeholder) -------------------------------------------------------------------------
@router.get("/projects/{project_id}/stakeholders", response_model=list[StakeholderOut], **_read.route)
def list_stakeholders(project_id: int, include_retired: bool = False, db: Session = Depends(get_db)):
    return issue_service.list_stakeholders(db, project_id, include_retired)


@router.post("/projects/{project_id}/stakeholders", response_model=StakeholderOut, status_code=201, **_edit.route)
def create_stakeholder(project_id: int, body: StakeholderIn, user: AppUser = Depends(current_user),
                       db: Session = Depends(get_db)):
    return issue_service.create_stakeholder(db, _uid(user), project_id, body.model_dump())


@router.get("/stakeholders/{id}", response_model=StakeholderOut, **_stk_r.route)
def read_stakeholder(id: int, stk: Stakeholder = Depends(_stk_r.dep)):
    return stk


@router.patch("/stakeholders/{id}", response_model=StakeholderOut, **_stk_w.route)
def update_stakeholder(id: int, body: StakeholderPatch, stk: Stakeholder = Depends(_stk_w.dep),
                       user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return issue_service.update_stakeholder(db, _uid(user), stk, body.row_version,
                                            body.model_dump(exclude_unset=True, exclude={"row_version"}))


@router.delete("/stakeholders/{id}", status_code=204, **_stk_w.route)
def retire_stakeholder(id: int, row_version: int, stk: Stakeholder = Depends(_stk_w.dep),
                       user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    """I-7: refused while a live issue names them as raiser (lifecycle finds it through the FK)."""
    lifecycle.retire(db, _uid(user), stk, row_version)


@router.patch("/stakeholders/{id}/restore", response_model=StakeholderOut, **_stk_w.route)
def restore_stakeholder(id: int, stk: Stakeholder = Depends(_stk_w.dep), user: AppUser = Depends(current_user),
                        db: Session = Depends(get_db)):
    return issue_service.restore_stakeholder(db, _uid(user), stk)
