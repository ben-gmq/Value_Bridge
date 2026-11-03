"""Slice Change requests routes (docs/slice_change_requests_spec.md §4). Reads are project_ctx / object_guard at VIEW;
every write needs EDIT and component CHANGE_REQUEST (409 COMPONENT_OFF when off; criterion 49b). Deciding is an
editor's (SC-7, criterion 192). A change request of a project you cannot see is a 404."""
from fastapi import Depends
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser, ChangeRequest
from routers.guards import GuardedRouter, object_guard, project_ctx
from schemas.change_request import AnalyseIn, CorrectionIn, CrIn, CrPatch, DecideIn, SeedsIn
from services import change_request as cr_service

router = GuardedRouter(tags=["change-requests"])
_read = project_ctx("VIEW")
_edit = project_ctx("EDIT", "CHANGE_REQUEST")
_r, _w = object_guard(ChangeRequest, "VIEW"), object_guard(ChangeRequest, "EDIT", component="CHANGE_REQUEST")


@router.get("/projects/{project_id}/change-requests", **_read.route)
def list_change_requests(project_id: int, status: str | None = None, origin: str | None = None,
                         against: int | None = None, include_retired: bool = False, db: Session = Depends(get_db)):
    return cr_service.list_change_requests(db, project_id, status=status, origin=origin, against=against,
                                           include_retired=include_retired)


@router.get("/projects/{project_id}/change-requests/unagreed-edits", **_read.route)
def unagreed_edits(project_id: int, db: Session = Depends(get_db)):
    """Seeds of undecided, rejected or retired changes still carrying their edit (CR-1)."""
    return cr_service.warning_lines(db, project_id)


@router.get("/projects/{project_id}/change-requests/summary", **_read.route)
def change_request_summary(project_id: int, db: Session = Depends(get_db)):
    return cr_service.summary(db, project_id)


@router.post("/projects/{project_id}/change-requests", status_code=201, **_edit.route)
def raise_change_request(project_id: int, body: CrIn, user: AppUser = Depends(current_user),
                         db: Session = Depends(get_db)):
    cr = cr_service.raise_change_request(db, user.app_user_id, project_id, body.model_dump())
    return cr_service.detail(db, cr)


@router.get("/change-requests/{id}", **_r.route)
def read_change_request(id: int, cr: ChangeRequest = Depends(_r.dep), db: Session = Depends(get_db)):
    return cr_service.detail(db, cr)


@router.patch("/change-requests/{id}", **_w.route)
def update_change_request(id: int, body: CrPatch, cr: ChangeRequest = Depends(_w.dep),
                          user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    cr = cr_service.update_change_request(db, user.app_user_id, cr, body.row_version,
                                          body.model_dump(exclude_unset=True, exclude={"row_version"}))
    return cr_service.detail(db, cr)


@router.put("/change-requests/{id}/seeds", **_w.route)
def set_seeds(id: int, body: SeedsIn, cr: ChangeRequest = Depends(_w.dep), user: AppUser = Depends(current_user),
              db: Session = Depends(get_db)):
    """The whole seed list in one PUT; clears the trace and price and returns the CR to draft."""
    cr = cr_service.set_seeds(db, user.app_user_id, cr, body.row_version, [s.model_dump() for s in body.seeds])
    return cr_service.detail(db, cr)


@router.post("/change-requests/{id}/analyse", **_w.route)
def analyse(id: int, body: AnalyseIn, cr: ChangeRequest = Depends(_w.dep), user: AppUser = Depends(current_user),
            db: Session = Depends(get_db)):
    """Trace and price."""
    return cr_service.detail(db, cr_service.analyse(db, user.app_user_id, cr, body.row_version))


@router.post("/change-requests/{id}/decide", **_w.route)
def decide(id: int, body: DecideIn, cr: ChangeRequest = Depends(_w.dep), user: AppUser = Depends(current_user),
           db: Session = Depends(get_db)):
    cr = cr_service.decide(db, user.app_user_id, cr, body.row_version, body.model_dump(exclude={"row_version"}))
    return cr_service.detail(db, cr)


@router.post("/change-requests/{id}/decision-correction", **_w.route)
def correct_decision(id: int, body: CorrectionIn, cr: ChangeRequest = Depends(_w.dep),
                     user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    cr = cr_service.correct_decision(db, user.app_user_id, cr, body.row_version,
                                     body.model_dump(exclude={"row_version"}))
    return cr_service.detail(db, cr)


@router.delete("/change-requests/{id}", status_code=204, **_w.route)
def retire_change_request(id: int, row_version: int, cr: ChangeRequest = Depends(_w.dep),
                          user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    cr_service.retire(db, user.app_user_id, cr, row_version)


@router.patch("/change-requests/{id}/restore", **_w.route)
def restore_change_request(id: int, cr: ChangeRequest = Depends(_w.dep), user: AppUser = Depends(current_user),
                           db: Session = Depends(get_db)):
    return cr_service.detail(db, cr_service.restore(db, user.app_user_id, cr))
