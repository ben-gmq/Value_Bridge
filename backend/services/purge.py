"""Requests to take a project out of VB, or to delete its archive (slice16 spec §7, §9, §15a, §17 R2/R3, §19, §20;
schema §3.2, §12.5). The app requests, approves, cancels and lists; executing a removal is the owner-run job's alone
(design §6.6) and is not here.

The database guard on `project_purge` (0072) is the control: two live platform admins, four eyes, the approver's
independence (AR-13, AR-15), the approval time and every order of steps. This service adds what needs the request's
words — the reason, the typed `<client code>/<project code>` (R3), "an ARCHIVE only when due" (AR-11) — and turns the
guard's refusals into plain 409s. Audit rows carry ids and codes, never project content, and no project_id (Q-69 b:
the purge removes the project's own audit rows; these must outlive it)."""
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from models import AppUser, BaselineArchive, Client, Project, ProjectPurge
from services import access, audit
from services.baseline import local_today

KINDS = ProjectPurge.KINDS
ARCHIVE_AFTER_YEARS = 2                                     # AR-1
_DAY = timedelta(hours=24)                                  # Q-72: the wait between approval and execution


def due_on(closed_on: date | None) -> date | None:
    """The day a closed project comes due for archiving: two years after it closed (AR-1, AR-8)."""
    if closed_on is None:
        return None
    try:
        return closed_on.replace(year=closed_on.year + ARCHIVE_AFTER_YEARS)
    except ValueError:                                      # 29 February → 1 March
        return date(closed_on.year + ARCHIVE_AFTER_YEARS, 3, 1)


def _guarded(db: Session, step) -> None:
    """Run a write the database guard decides; its refusal (fixed text, no data) becomes a 409."""
    try:
        step()
        db.flush()
    except DBAPIError as exc:                               # IntegrityError included: restrict_violation is class 23
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23001":                    # the guard's refusal, fixed text
            raise HTTPException(409, exc.orig.diag.message_primary) from exc
        if "uq_pp_open" in str(exc.orig):
            raise HTTPException(409, "A removal request for this project is already open") from exc
        raise


def _confirm(client_code: str, project_code: str, typed: str | None) -> None:
    expected = f"{client_code}/{project_code}"
    if (typed or "").strip() != expected:
        raise HTTPException(422, f"Type the client and project codes to confirm: {expected}")


def _event(db: Session, kind: str, actor: AppUser, p: ProjectPurge, **more) -> None:
    audit.record(db, kind, actor_id=actor.app_user_id, target_table="project_purge", target_id=p.project_purge_id,
                 detail={"purge_kind": p.purge_kind, "project_id": p.project_id, "project_code": p.project_code,
                         "client_id": p.client_id, **more})


def request(db: Session, actor: AppUser, project_id: int | None, kind: str, reason: str | None,
            confirm_text: str | None, archive_purge_id: int | None = None) -> ProjectPurge:
    """ARCHIVE / DELETE name a live project; DELETE_ARCHIVE names the executed ARCHIVE (the project is gone, AR-9) and
    is requested only from that ARCHIVE (`archive_purge_id`)."""
    if kind not in KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(KINDS)}")
    if (kind == "DELETE_ARCHIVE") != (archive_purge_id is not None):
        raise HTTPException(422, "An archive is deleted from its executed ARCHIVE request, not from the project")
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(422, "Give the reason: the contract clause or Ben's instruction")
    if kind == "DELETE_ARCHIVE":
        src = db.get(ProjectPurge, archive_purge_id) if archive_purge_id else None
        if src is None or src.purge_kind != "ARCHIVE" or src.executed_at is None:
            raise HTTPException(404, "Not found")
        project_id = src.project_id
        client, code = db.get(Client, src.client_id), src.project_code
    else:
        # sara L1: FOR UPDATE waits for every in-flight write (they hold FOR KEY SHARE), so none lands after the request
        project = db.scalar(select(Project).where(Project.project_id == project_id).with_for_update())
        if project is None:
            raise HTTPException(404, "Not found")
        client, code = db.get(Client, project.client_id), project.project_code
        if kind == "ARCHIVE":
            due = due_on(project.closed_on)
            if due is None or due > local_today():          # AR-11: earlier removal is a contract DELETE
                raise HTTPException(409, "This project is not due for archiving yet"
                                    + (f" (due {due.isoformat()})" if due else ": it is not closed"))
    _confirm(client.client_code, code, confirm_text)
    p = ProjectPurge(purge_kind=kind, project_id=project_id, client_id=client.client_id, project_code=code,
                     reason=reason, requested_by_user_id=actor.app_user_id,
                     archive_purge_id=archive_purge_id if kind == "DELETE_ARCHIVE" else None)
    _guarded(db, lambda: db.add(p))
    _event(db, "PURGE_REQUESTED", actor, p, reason=reason)
    db.commit()
    db.refresh(p)
    return p


def _open(db: Session, purge_id: int, row_version: int) -> ProjectPurge:
    p = db.scalar(select(ProjectPurge).where(ProjectPurge.project_purge_id == purge_id).with_for_update())
    if p is None:
        raise HTTPException(404, "Not found")
    if p.row_version != row_version:
        raise HTTPException(409, "Updated by another user. Please refresh.")
    return p


def approve(db: Session, actor: AppUser, purge_id: int, confirm_text: str | None, row_version: int) -> ProjectPurge:
    p = _open(db, purge_id, row_version)
    _confirm(db.get(Client, p.client_id).client_code, p.project_code, confirm_text)

    def step():
        p.approved_by_user_id, p.approved_at = actor.app_user_id, func.now()     # the guard sets the time
        p.updated_by, p.row_version = actor.app_user_id, p.row_version + 1
    _guarded(db, step)
    _event(db, "PURGE_APPROVED", actor, p)
    db.commit()
    db.refresh(p)
    return p


def cancel(db: Session, actor: AppUser, purge_id: int, row_version: int) -> ProjectPurge:
    p = _open(db, purge_id, row_version)

    def step():
        p.cancelled_by_user_id, p.cancelled_at = actor.app_user_id, func.now()   # the guard sets the time
        p.updated_by, p.row_version = actor.app_user_id, p.row_version + 1
    _guarded(db, step)
    _event(db, "PURGE_CANCELLED", actor, p)
    db.commit()
    db.refresh(p)
    return p


def state(p: ProjectPurge) -> str:
    """Derived, never stored (Q-67): OPEN → APPROVED → EXECUTED, or CANCELLED."""
    if p.cancelled_at is not None:
        return "CANCELLED"
    if p.executed_at is not None:
        return "EXECUTED"
    return "APPROVED" if p.approved_at is not None else "OPEN"


def _names(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    return {u.app_user_id: u.display_name for u in db.scalars(select(AppUser).where(AppUser.app_user_id.in_(ids)))}


def list_requests(db: Session) -> list[dict]:
    return _rows(db, list(db.scalars(select(ProjectPurge).order_by(ProjectPurge.project_purge_id.desc()))))


def request_row(db: Session, p: ProjectPurge) -> dict:
    """One request as the list shows it (sara L7: a write returns its own row, not the whole list)."""
    return _rows(db, [p])[0]


def _rows(db: Session, rows: list[ProjectPurge]) -> list[dict]:
    names = _names(db, [x for p in rows for x in (p.requested_by_user_id, p.approved_by_user_id,
                                                  p.cancelled_by_user_id, p.executed_by_user_id)])
    clients = {c.client_id: c for c in db.scalars(select(Client).where(Client.client_id.in_({p.client_id for p in rows})))}
    now = db.scalar(select(func.now()))
    return [{"project_purge_id": p.project_purge_id, "purge_kind": p.purge_kind, "state": state(p),
             "project_id": p.project_id, "project_code": p.project_code, "client_code": clients[p.client_id].client_code,
             "reason": p.reason, "archive_purge_id": p.archive_purge_id,
             "requested_at": p.requested_at, "requested_by": names.get(p.requested_by_user_id),
             "requested_by_user_id": p.requested_by_user_id,
             "approved_at": p.approved_at, "approved_by": names.get(p.approved_by_user_id),
             "runnable_from": p.approved_at and p.approved_at.replace(microsecond=0) + _DAY,
             "waiting": bool(p.approved_at and p.executed_at is None and p.cancelled_at is None
                             and p.approved_at + _DAY > now),
             "cancelled_at": p.cancelled_at, "cancelled_by": names.get(p.cancelled_by_user_id),
             "executed_at": p.executed_at, "executed_by": names.get(p.executed_by_user_id),
             "backups_age_out_on": p.backups_age_out_on, "row_version": p.row_version} for p in rows]


def overview(db: Session) -> dict:
    """The removals card: live platform admins (AR-5 warning below two), projects due for archiving (AR-1), and
    archive files still owed across projects (the backlog, R11)."""
    today = local_today()
    admins = db.scalar(select(func.count()).select_from(AppUser).where(AppUser.is_active, AppUser.is_platform_admin))
    removed = set(db.scalars(select(ProjectPurge.project_id).where(ProjectPurge.executed_at.is_not(None),
                                                                     ProjectPurge.purge_kind.in_(("ARCHIVE", "DELETE")))))
    removed |= access.pending_project_ids(db)              # sara L8: a project with an open request is not offered
    clients = {c.client_id: c.client_code for c in db.scalars(select(Client))}
    due = []
    for p in db.scalars(select(Project).where(Project.closed_on.is_not(None)).order_by(Project.closed_on)):
        d = due_on(p.closed_on)
        if d <= today and p.project_id not in removed:
            due.append({"project_id": p.project_id, "project_code": p.project_code,
                        "client_code": clients.get(p.client_id), "closed_on": p.closed_on, "due_on": d})
    owed = db.execute(select(BaselineArchive.project_id, func.count(), func.max(BaselineArchive.last_error))
                      .where(BaselineArchive.written_at.is_(None)).group_by(BaselineArchive.project_id)).all()
    codes = dict(db.execute(select(Project.project_id, Project.project_code)
                            .where(Project.project_id.in_([o[0] for o in owed] or [-1]))).all())
    return {"live_platform_admins": admins, "due_for_archiving": due,
            "archive_backlog": [{"project_id": pid, "project_code": codes.get(pid), "owed_files": n,
                                 "last_error": err} for pid, n, err in owed]}


def archive_status(db: Session, baseline_id: int) -> list[dict]:
    """One baseline's archive files, the current one per part (highest file_seq) — never the file itself."""
    rows = db.scalars(select(BaselineArchive).where(BaselineArchive.baseline_id == baseline_id)
                      .order_by(BaselineArchive.archive_part, BaselineArchive.file_seq.desc()))
    seen, out = set(), []
    for r in rows:
        if r.archive_part in seen:
            continue
        seen.add(r.archive_part)
        status = ("CHECK_FAILED" if r.check_failed_at else "WRITTEN" if r.written_at
                  else "FAILING" if r.last_error else "OWED")
        out.append({"archive_part": r.archive_part, "file_seq": r.file_seq, "status": status,
                    "written_at": r.written_at, "byte_size": r.byte_size, "last_error": r.last_error})
    return out
