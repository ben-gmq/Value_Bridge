"""Removal requests and archive status (slice16 spec §9). There is no route that deletes: execution is the owner-run
job's (design §6.6). Requesting is a PLATFORM project setting; approving, cancelling, deleting an archive and the lists
are platform-admin routes that carry only the request id."""
from fastapi import Depends
from sqlalchemy.orm import Session

from database import get_db
from models import AppUser, Baseline
from routers.guards import GuardedRouter, authenticated, object_guard, platform_admin, project_ctx
from schemas.purge import ArchiveDeletionIn, PurgeApproveIn, PurgeCancelIn, PurgeRequestIn
from services import purge, weekly_check

router = GuardedRouter(tags=["purge"])
_admin = platform_admin()
_auth = authenticated()
_platform = project_ctx("PLATFORM")
_b_reader = object_guard(Baseline, "VIEW")


@router.post("/projects/{project_id}/purge-requests", status_code=201, **_platform.route)
def request_purge(project_id: int, body: PurgeRequestIn, actor: AppUser = Depends(_auth.dep),
                  db: Session = Depends(get_db)):
    return purge.request_row(db, purge.request(db, actor, project_id, body.kind, body.reason, body.confirm_text))


@router.post("/purge-requests/{id}/delete-archive", status_code=201, **_admin.route)
def request_archive_deletion(id: int, body: ArchiveDeletionIn, actor: AppUser = Depends(_admin.dep),
                             db: Session = Depends(get_db)):
    """AR-9: the project is gone; the request names the executed ARCHIVE whose keys and files go."""
    return purge.request_row(db, purge.request(db, actor, None, "DELETE_ARCHIVE", body.reason, body.confirm_text, id))


@router.post("/purge-requests/{id}/approve", **_admin.route)
def approve_purge(id: int, body: PurgeApproveIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return purge.request_row(db, purge.approve(db, actor, id, body.confirm_text, body.row_version))


@router.post("/purge-requests/{id}/cancel", **_admin.route)
def cancel_purge(id: int, body: PurgeCancelIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return purge.request_row(db, purge.cancel(db, actor, id, body.row_version))


@router.get("/purge-requests", **_admin.route)
def list_purge_requests(db: Session = Depends(get_db)):
    return purge.list_requests(db)


@router.get("/admin/archive-overview", **_admin.route)
def archive_overview(db: Session = Depends(get_db)):
    return purge.overview(db)


@router.get("/admin/weekly-check", **_admin.route)
def weekly_check_card(db: Session = Depends(get_db)):
    """U5, AR-23, VB-012: the last weekly run's line (stale after 8 days), held archives whose last check failed, and
    the platform-admin lines, read live."""
    return weekly_check.card(db)


@router.get("/baselines/{id}/archive", **_b_reader.route)
def baseline_archive(id: int, b: Baseline = Depends(_b_reader.dep), db: Session = Depends(get_db)):
    return purge.archive_status(db, b.baseline_id)
