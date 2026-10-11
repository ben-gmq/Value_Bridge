"""Baselines (§4.6, §9; slice8_schema §5.4). Read-only apart from freeze and approve: no PATCH, PUT or DELETE
exists on a baseline or a shadow, and the database refuses them anyway. Baselines are always on (no
component gate, [Q-18])."""
from typing import Literal

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import AppUser, Baseline
from routers.guards import GuardedRouter, authenticated, object_guard, project_ctx
from schemas.baseline import ApproveIn, BaselineDetailOut, BaselineOut, FreezeIn, FreezeOut
from services import baseline as svc
from services import project as project_service

router = GuardedRouter(tags=["baselines"])
_auth = authenticated()
_reader = project_ctx("VIEW")
_editor = project_ctx("EDIT")
_b_reader = object_guard(Baseline, "VIEW")
_b_editor = object_guard(Baseline, "EDIT")


@router.get("/projects/{project_id}/baselines", response_model=list[BaselineOut], **_reader.route)
def list_baselines(project_id: int, db: Session = Depends(get_db)):
    rows = svc.list_baselines(db, project_id)
    agreed = svc.agreed_id(rows)
    return [{**svc.header(db, b), "is_agreed": b.baseline_id == agreed} for b in rows]


@router.get("/projects/{project_id}/baselines/next", **_reader.route)
def next_baseline(project_id: int, bump: Literal["MINOR", "MAJOR"] = "MINOR", db: Session = Depends(get_db)):
    return svc.preview(db, project_service.get_project(db, project_id), bump)


@router.post("/projects/{project_id}/baselines/freeze", response_model=FreezeOut, status_code=201,
             **_editor.route)
def freeze(project_id: int, body: FreezeIn, user: AppUser = Depends(_auth.dep)):
    return svc.freeze(user, project_id, body.note, body.bump, body.confirm_text, body.preview_digest)


@router.get("/projects/{project_id}/baselines/diff", **_reader.route)
def diff(project_id: int, from_: str = Query(alias="from", max_length=18),
         to: str = Query(max_length=18), priced: bool = False):
    return svc.diff_for_api(project_id, from_, to, priced)


@router.get("/baselines/{id}", response_model=BaselineDetailOut, **_b_reader.route)
def read_baseline(id: int, b: Baseline = Depends(_b_reader.dep), db: Session = Depends(get_db)):
    agreed = svc.agreed_id(svc.list_baselines(db, b.project_id))
    return {**svc.detail(db, b), "is_agreed": b.baseline_id == agreed}


@router.get("/baselines/{id}/rows/{entity}", **_b_reader.route)
def baseline_rows(id: int, entity: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                  b: Baseline = Depends(_b_reader.dep), db: Session = Depends(get_db)):
    svc.require_intact(db, b)
    return svc.rows(db, b, entity, offset, limit)


@router.post("/baselines/{id}/approve", response_model=BaselineOut, **_b_editor.route)
def approve(id: int, body: ApproveIn, b: Baseline = Depends(_b_editor.dep), user: AppUser = Depends(_auth.dep),
            db: Session = Depends(get_db)):
    out = svc.approve(db, user, b, body.client_approver_name, body.client_approved_on, body.approval_note,
                      body.approval_reference, body.row_version)
    return {**out, "is_agreed": svc.agreed_id(svc.list_baselines(db, b.project_id)) == b.baseline_id}   # sara L3
