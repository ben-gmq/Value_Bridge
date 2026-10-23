"""The weekly archive check (slice16 spec §1a maintenance loop, §17 R11/R14, §18 S5, §19 U1/U5; history Q-84, AR-23;
BUGLOG VB-012). Run by Fortience IS from scripts/weekly_check.py, as the application role — it needs nothing more:
the app may mark a check failure (`baseline_archive.check_failed_at`), owe a replacement file, and record a held
project file's check (`project_purge.archive_checked_*`). Every run, even one with nothing to report, records one
WEEKLY_CHECK_RAN audit row (U5), which the Removals tab reads as "last run" and warns about after 8 days.

What it checks:
1. **Every current written baseline file** (the highest `file_seq` of each part, not already check-failed): the stored
   object exists with the recorded size and sha256 — no decryption (R14). A mismatch marks the row check-failed and owes
   `file_seq + 1` in the same transaction (S5); the writer (scripts.write_archives) writes the replacement.
2. **Every held project archive** (an executed ARCHIVE with no executed DELETE_ARCHIVE of it, U1): the object exists
   with the recorded size and sha256, and its key still unwraps the file's data key. The result is recorded on the
   request; a failure is in the report and on the Removals tab.
What it reports: projects due for archiving, projects reopened since the last run, owed and failing files, unfinished
removals, every held archive's result, and the platform-admin lines (slice 17, VB-012).

No client content: ids, codes, dates and fixed messages only (R19)."""
import base64
import hashlib
import json
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import AuditEvent, BaselineArchive, Project, ProjectPurge, ProjectPurgeKey
from services import admin_grant, audit, purge

EVENT = "WEEKLY_CHECK_RAN"
STALE_AFTER = timedelta(days=8)                         # U5
MISSING = "the stored file is missing"
DIFFERS = "the stored file's size or sha256 differs from the record"
KEY_GONE = "the project key no longer unwraps the file"
UNREADABLE = "the stored file is not a readable archive envelope"


def _stored(store, name: str, size: int, sha: str) -> tuple[bytes | None, str | None]:
    try:
        blob = store.get(name)
    except (FileNotFoundError, OSError, ValueError):
        return None, MISSING
    if len(blob) != size or hashlib.sha256(blob).hexdigest() != sha:
        return blob, DIFFERS
    return blob, None


def _current_written(db: Session) -> list[BaselineArchive]:
    """The newest file of each part that is written and not already marked failed."""
    newest = (select(BaselineArchive.baseline_id, BaselineArchive.archive_part,
                     func.max(BaselineArchive.file_seq).label("seq"))
              .group_by(BaselineArchive.baseline_id, BaselineArchive.archive_part).subquery())
    return list(db.scalars(select(BaselineArchive).join(newest, (newest.c.baseline_id == BaselineArchive.baseline_id)
                                                        & (newest.c.archive_part == BaselineArchive.archive_part)
                                                        & (newest.c.seq == BaselineArchive.file_seq))
                           .where(BaselineArchive.written_at.is_not(None), BaselineArchive.check_failed_at.is_(None))
                           .order_by(BaselineArchive.baseline_id, BaselineArchive.archive_part)))


def check_files(db: Session, store, actor_id: int) -> list[dict]:
    """1. Each failure is marked and its replacement owed in one transaction (the guard allows exactly this, S5)."""
    failed = []
    for row in _current_written(db):
        _, why = _stored(store, row.object_name, row.byte_size, row.file_sha256)
        if why is None:
            continue
        row.check_failed_at, row.last_check_error = func.now(), why
        row.updated_by, row.row_version = actor_id, row.row_version + 1
        db.flush()
        db.add(BaselineArchive(baseline_id=row.baseline_id, archive_part=row.archive_part, file_seq=row.file_seq + 1,
                               project_id=row.project_id, format_version=row.format_version, created_by=actor_id))
        audit.record(db, "ARCHIVE_CHECK_FAILED", actor_id=actor_id, project_id=row.project_id,
                     target_table="baseline_archive", target_id=row.baseline_id,
                     detail={"archive_part": row.archive_part, "file_seq": row.file_seq, "error": why})
        db.commit()
        failed.append({"project_id": row.project_id, "baseline_id": row.baseline_id, "archive_part": row.archive_part,
                       "file_seq": row.file_seq, "error": why, "replacement_file_seq": row.file_seq + 1})
    return failed


def _held(db: Session) -> list[ProjectPurge]:
    deleted = select(ProjectPurge.archive_purge_id).where(ProjectPurge.purge_kind == "DELETE_ARCHIVE",
                                                         ProjectPurge.executed_at.is_not(None))
    return list(db.scalars(select(ProjectPurge).where(
        ProjectPurge.purge_kind == "ARCHIVE", ProjectPurge.executed_at.is_not(None),
        ProjectPurge.project_purge_id.not_in(deleted)).order_by(ProjectPurge.project_purge_id)))


def _unwraps(blob: bytes, keys) -> bool:
    try:
        env = json.loads(blob)
        keys.unwrap(env["key_ref"], base64.b64decode(env["wrapped_data_key"]))
        return True
    except Exception:                                                          # noqa: BLE001 — any failure: not readable
        return False


def check_held(db: Session, store, keys) -> list[dict]:
    """2. U1: the only copy of an archived project — its object, its size and sha256, and its key."""
    out = []
    for p in _held(db):
        blob, why = _stored(store, p.archive_object_name, p.archive_byte_size, p.archive_sha256)
        if why is None and not _unwraps(blob, keys):
            why = KEY_GONE
        p.archive_checked_at, p.archive_check_error = func.now(), why          # the guard sets the clock
        p.row_version += 1
        db.commit()
        out.append({"project_purge_id": p.project_purge_id, "project_code": p.project_code, "ok": why is None,
                    "error": why})
    return out


def last_run(db: Session) -> dict:
    """U5: the newest run's line, and whether it is stale (never run, or over 8 days ago)."""
    ev = db.scalar(select(AuditEvent).where(AuditEvent.event_type == EVENT)
                   .order_by(AuditEvent.occurred_at.desc(), AuditEvent.audit_event_id.desc()).limit(1))
    now = db.scalar(select(func.now()))
    if ev is None:
        return {"ran_at": None, "summary": None, "stale": True}
    return {"ran_at": ev.occurred_at, "summary": ev.detail.get("summary"), "stale": now - ev.occurred_at > STALE_AFTER}


def card(db: Session) -> dict:
    """The Removals tab's card: the last run, any held archive whose last check failed, and the admin lines (live)."""
    failing = [{"project_purge_id": p.project_purge_id, "project_code": p.project_code,
                "checked_at": p.archive_checked_at, "error": p.archive_check_error}
               for p in _held(db) if p.archive_check_error]
    return {"last_run": last_run(db), "held_failing": failing, "admin": admin_grant.weekly_admin_lines(db)}


def _reopened_since(db: Session, since) -> list[dict]:
    q = select(AuditEvent).where(AuditEvent.event_type == "PROJECT_REOPENED")
    if since is not None:
        q = q.where(AuditEvent.occurred_at > since)
    events = db.scalars(q.order_by(AuditEvent.occurred_at)).all()
    codes = dict(db.execute(select(Project.project_id, Project.project_code).where(
        Project.project_id.in_([e.project_id for e in events] or [-1]))).all())
    return [{"project_id": e.project_id, "project_code": codes.get(e.project_id), "reopened_at": e.occurred_at,
             "was_closed_on": (e.detail or {}).get("was_closed_on")} for e in events]


def _unfinished_removals(db: Session) -> list[dict]:
    rows = []
    for p in db.scalars(select(ProjectPurge).where(ProjectPurge.cancelled_at.is_(None)).order_by(
            ProjectPurge.project_purge_id)):
        keys_left = 0
        if p.executed_at is not None and p.purge_kind == "DELETE":
            keys_left = db.scalar(select(func.count()).select_from(ProjectPurgeKey).where(
                ProjectPurgeKey.project_purge_id == p.project_purge_id, ProjectPurgeKey.destroyed_at.is_(None)))
        state = purge.state(p)
        if state in ("OPEN", "APPROVED") or keys_left:
            rows.append({"project_purge_id": p.project_purge_id, "purge_kind": p.purge_kind,
                         "project_code": p.project_code, "state": state, "keys_outstanding": keys_left})
    return rows


def report(db: Session, since) -> dict:
    ov = purge.overview(db)
    return {"due_for_archiving": ov["due_for_archiving"], "reopened_since_last_run": _reopened_since(db, since),
            "owed_files": ov["archive_backlog"], "unfinished_removals": _unfinished_removals(db),
            "live_platform_admins": ov["live_platform_admins"], "admin": admin_grant.weekly_admin_lines(db)}


def run(db: Session, store, keys, actor_id: int, operator: str) -> dict:
    """One weekly run: the checks, the report, and its line — recorded even when there is nothing to say (U5)."""
    since = last_run(db)["ran_at"]
    failed = check_files(db, store, actor_id)
    held = check_held(db, store, keys)
    rep = report(db, since) | {"failed_files": failed, "held_archives": held}
    summary = {"due": len(rep["due_for_archiving"]), "reopened": len(rep["reopened_since_last_run"]),
               "owed_files": sum(o["owed_files"] for o in rep["owed_files"]), "failed_files": len(failed),
               "held_archives": len(held), "held_failing": sum(1 for h in held if not h["ok"]),
               "unfinished_removals": len(rep["unfinished_removals"]),
               "admins_without_a_grant": len(rep["admin"]["admins_without_a_grant"]),
               "open_admin_requests_over_7_days": len(rep["admin"]["open_over_7_days"])}
    audit.record(db, EVENT, actor_id=actor_id, target_table="weekly_check",
                 detail={"summary": summary, "operator": operator})
    db.commit()
    return rep | {"summary": summary}
