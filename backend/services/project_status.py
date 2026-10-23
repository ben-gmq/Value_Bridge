"""A project's status, the two-year archive clock and retiring a project (slice16 spec §15a, §19 U2; history AR-8, AR-10,
Q-90). The status is a company code list (PROJECT_STATUS, company-only) whose every code carries an OPEN or CLOSED
behaviour (0070); the database holds `closed_on` to it (`ck_project_closed_on`) — branch on the behaviour, never the
code (law 5).

- Entering a closed status records today (ICT) as `closed_on`: the two years start (AR-8). A closed status to another
  closed one keeps the date. Leaving a closed status clears it; closing again restarts the clock.
- Leaving a closed status is a platform admin's act (U2, D-71 (6)) — it is the archive reminder's only off-switch.
  Closing, and moving between open statuses, stays an editor's.
- Retiring a project first moves it to a closed status (closed_on set) in the same transaction, so a retired project
  comes due like any other; refused when no live closed status exists (AR-10, Q-90).
Every change is audited; the weekly check (not built) reads PROJECT_REOPENED for "reopened since the last run"."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import AppUser, CodeMaster, Project, ProjectMember, UserAccessGrant
from services import access, audit
from services.baseline import local_today
from services.code_master import resolve, validate_required_code
from services.lifecycle import lock, soft_delete

CATEGORY = "PROJECT_STATUS"


def _fresh(project: Project, row_version: int) -> None:
    if project.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")


def _live(db: Session, project: Project) -> None:
    """sara MEDIUM-1, LOW-2: a retired project takes no status change (reopening it would stop its clock for good, and
    it would never come due); and the row is locked, then re-checked for an open removal request (Q-73), so a request
    opened while this runs cannot slip past the guard's earlier check."""
    lock(db, project)
    if not project.is_active:
        raise HTTPException(409, "The project is retired")
    access.require_not_pending(db, project.project_id)


def _move(project: Project, new: CodeMaster) -> None:
    """The one place the status and its clock change together."""
    if new.behaviour_code == "CLOSED" and project.status_behaviour != "CLOSED":
        project.closed_on = local_today()                  # AR-8: the two years start today (ICT)
    elif new.behaviour_code != "CLOSED":
        project.closed_on = None                           # reopened: the clock stops; closing again restarts it
    project.status_code_id, project.status_behaviour = new.code_id, new.behaviour_code


def _event(db: Session, kind: str, actor: AppUser, project: Project, before: CodeMaster | None,
           after: CodeMaster | None, **more) -> None:
    audit.record(db, kind, actor_id=actor.app_user_id, project_id=project.project_id, target_table="project",
                 target_id=project.project_id,
                 detail={"from": before.code if before else None, "to": after.code if after else None,
                         "closed_on": project.closed_on.isoformat() if project.closed_on else None, **more})


def _current(db: Session, project: Project) -> CodeMaster:
    return db.get(CodeMaster, project.status_code_id)


def set_status(db: Session, actor: AppUser, project: Project, code: str | None, row_version: int) -> Project:
    """An editor's status change. Leaving a closed status is refused here (403): that is `reopen`, a platform admin's."""
    _live(db, project)
    new = validate_required_code(db, None, CATEGORY, code, "status_code")
    if project.status_behaviour == "CLOSED" and new.behaviour_code != "CLOSED":       # sara LOW-1: 403 before 409
        raise HTTPException(403, "Reopening a closed project is for a platform admin: it stops the archive clock")
    _fresh(project, row_version)
    if new.code_id == project.status_code_id:
        raise HTTPException(409, f"The project is already {new.label}")
    before = _current(db, project)
    _move(project, new)
    project.updated_by = actor.app_user_id
    _event(db, "PROJECT_STATUS_CHANGED", actor, project, before, new)
    db.commit()
    return project


def reopen(db: Session, actor: AppUser, project: Project, code: str | None, row_version: int) -> Project:
    """U2: a platform admin moves a closed project back to an open status; `closed_on` is cleared."""
    _live(db, project)
    _fresh(project, row_version)
    new = validate_required_code(db, None, CATEGORY, code, "status_code")
    if project.status_behaviour != "CLOSED":
        raise HTTPException(409, "The project is not closed")
    if new.behaviour_code == "CLOSED":
        raise HTTPException(422, "Reopen to an open status")
    before = _current(db, project)
    closed_on = project.closed_on
    _move(project, new)
    project.updated_by = actor.app_user_id
    _event(db, "PROJECT_REOPENED", actor, project, before, new, was_closed_on=closed_on.isoformat())
    db.commit()
    return project


def retire(db: Session, actor: AppUser, project: Project, confirm_text: str | None, row_version: int) -> Project:
    """AR-10 / Q-90: closed first (the clock starts), then retired, in one transaction. sara HIGH-1: refused, by name,
    while the project still has live members or legacy access grants — the database holds those to a live project
    (fk_pm_live_project, fk_grant_live_project), and ending them with the retire would be a design change (Ben's)."""
    _live(db, project)
    _fresh(project, row_version)
    if (confirm_text or "").strip() != project.project_code:
        raise HTTPException(422, f"Type the project code to confirm: {project.project_code}")
    holders = db.scalars(select(AppUser.display_name).join(ProjectMember, ProjectMember.app_user_id == AppUser.app_user_id)
                         .where(ProjectMember.project_id == project.project_id, ProjectMember.is_active)
                         .order_by(AppUser.display_name)).all()
    grants = db.scalar(select(func.count()).select_from(UserAccessGrant).where(
        UserAccessGrant.project_id == project.project_id, UserAccessGrant.is_active))
    if holders or grants:
        who = ", ".join(holders) + (f" and {grants} legacy access grant(s)" if grants else "")
        raise HTTPException(409, f"Remove the project's members first ({who}): a retired project keeps none")
    before = _current(db, project)
    after = before
    if project.status_behaviour != "CLOSED":
        closed = [c for c in resolve(db, None, CATEGORY) if c.behaviour_code == "CLOSED"]
        if not closed:
            raise HTTPException(409, "No live closed project status exists, so the project cannot be retired")
        after = closed[0]
        _move(project, after)
    soft_delete(project, actor.app_user_id)
    project.updated_by = actor.app_user_id
    _event(db, "PROJECT_RETIRED", actor, project, before, after)
    db.commit()
    return project
