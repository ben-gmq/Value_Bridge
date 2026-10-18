"""Slice 14 routes (§4.5, docs/slice14_issue_spec.md §8): stakeholders and issues.

Reads are project_ctx / object_guard at VIEW; every write needs EDIT and component ISSUE (I-9), so a project with the
component off answers 409 COMPONENT_OFF. A row of a project you cannot see is a 404."""
from fastapi import Depends
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser, Issue, IssueBr, Stakeholder
from routers.guards import GuardedRouter, object_guard, project_ctx
from schemas.issue import (DashboardOut, IssueBrIn, IssueBrOut, IssueIn, IssueOut, IssuePatch, ReopenIn, ResolveIn,
                           StakeholderIn, StakeholderOut, StakeholderPatch)
from services import issue as issue_service, lifecycle

router = GuardedRouter(tags=["issues"])
_read = project_ctx("VIEW")
_edit = project_ctx("EDIT", "ISSUE")
_stk_r, _stk_w = object_guard(Stakeholder, "VIEW"), object_guard(Stakeholder, "EDIT", component="ISSUE")
_iss_r, _iss_w = object_guard(Issue, "VIEW"), object_guard(Issue, "EDIT", component="ISSUE")


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


# ---- issues (§4.5 raise_issue / resolve_issue; spec §8, §14 R2) -------------------------------------------------
@router.get("/projects/{project_id}/issues", response_model=list[IssueOut], **_read.route)
def list_issues(project_id: int, include_retired: bool = False, open_only: bool = False, status: str | None = None,
                severity: str | None = None, issue_type: str | None = None, raiser: int | None = None,
                area: str | None = None, db: Session = Depends(get_db)):
    return issue_service.list_issues(db, project_id, include_retired, open_only=open_only, status=status,
                                     severity=severity, issue_type=issue_type, raiser=raiser, area=area)


@router.get("/projects/{project_id}/issue-dashboard", response_model=DashboardOut, **_read.route)
def issue_dashboard(project_id: int, db: Session = Depends(get_db)):
    return issue_service.dashboard(db, project_id)


@router.post("/projects/{project_id}/issues", response_model=IssueOut, status_code=201, **_edit.route)
def raise_issue(project_id: int, body: IssueIn, user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return issue_service.raise_issue(db, _uid(user), project_id, body.model_dump())


@router.get("/issues/{id}", response_model=IssueOut, **_iss_r.route)
def read_issue(id: int, issue: Issue = Depends(_iss_r.dep)):
    return issue


@router.patch("/issues/{id}", response_model=IssueOut, **_iss_w.route)
def update_issue(id: int, body: IssuePatch, issue: Issue = Depends(_iss_w.dep), user: AppUser = Depends(current_user),
                 db: Session = Depends(get_db)):
    return issue_service.update_issue(db, _uid(user), issue, body.row_version,
                                      body.model_dump(exclude_unset=True, exclude={"row_version"}))


@router.post("/issues/{id}/resolve", response_model=IssueOut, **_iss_w.route)
def resolve_issue(id: int, body: ResolveIn, issue: Issue = Depends(_iss_w.dep), user: AppUser = Depends(current_user),
                  db: Session = Depends(get_db)):
    return issue_service.resolve_issue(db, _uid(user), issue, body.row_version, body.status_code, body.resolution)


@router.post("/issues/{id}/reopen", response_model=IssueOut, **_iss_w.route)
def reopen_issue(id: int, body: ReopenIn, issue: Issue = Depends(_iss_w.dep), user: AppUser = Depends(current_user),
                 db: Session = Depends(get_db)):
    return issue_service.reopen_issue(db, _uid(user), issue, body.row_version)


@router.delete("/issues/{id}", status_code=204, **_iss_w.route)
def retire_issue(id: int, row_version: int, issue: Issue = Depends(_iss_w.dep), user: AppUser = Depends(current_user),
                 db: Session = Depends(get_db)):
    """I-4: for an issue raised in error; refused while it has live BR links (lifecycle, through the FK)."""
    lifecycle.retire(db, _uid(user), issue, row_version)


@router.patch("/issues/{id}/restore", response_model=IssueOut, **_iss_w.route)
def restore_issue(id: int, issue: Issue = Depends(_iss_w.dep), user: AppUser = Depends(current_user),
                  db: Session = Depends(get_db)):
    return issue_service.restore_issue(db, _uid(user), issue)


# ---- links to BRs (§4.5 link_issue_br; R1: every link is addressed under its issue) ----------------------------
def _link_out(row: IssueBr) -> dict:
    br = row.br_row
    return {"issue_br_id": row.issue_br_id, "issue_id": row.issue_id, "br_id": row.br_id, "br_number": br.br_number,
            "br_statement": br.br_statement, "bfc_node_id": br.bfc_node_id, "is_active": row.is_active,
            "row_version": row.row_version}


@router.get("/issues/{id}/brs", response_model=list[IssueBrOut], **_iss_r.route)
def list_issue_brs(id: int, include_retired: bool = False, issue: Issue = Depends(_iss_r.dep),
                   db: Session = Depends(get_db)):
    return [_link_out(r) for r in issue_service.links_of(db, issue, include_retired)]


@router.post("/issues/{id}/brs", response_model=IssueBrOut, status_code=201, **_iss_w.route)
def link_issue_br(id: int, body: IssueBrIn, issue: Issue = Depends(_iss_w.dep), user: AppUser = Depends(current_user),
                  db: Session = Depends(get_db)):
    return _link_out(issue_service.link_br(db, _uid(user), issue, body.br_id))


@router.delete("/issues/{id}/brs/{link_id}", status_code=204, **_iss_w.route)
def unlink_issue_br(id: int, link_id: int, row_version: int, issue: Issue = Depends(_iss_w.dep),
                    user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    issue_service.unlink_br(db, _uid(user), lifecycle.child_of(db, IssueBr, link_id, "issue_id", issue.issue_id),
                            row_version)
