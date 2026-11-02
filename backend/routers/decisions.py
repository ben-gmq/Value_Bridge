"""Slice Decisions routes (§4.11; docs/slice_decisions_spec.md §7). Reads at VIEW, the one write at EDIT; no component
(DC-1). No PATCH, DELETE or retire route — a decision is never changed (A-41); a correction is a new POST naming the
decision it supersedes. A decision of a project you cannot see is a 404."""
from fastapi import Depends
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser, Decision
from routers.guards import GuardedRouter, object_guard, project_ctx
from schemas.decision import DecisionIn, DecisionOut
from services import decision as decision_service

router = GuardedRouter(tags=["decisions"])
_read = project_ctx("VIEW")
_edit = project_ctx("EDIT")
_r = object_guard(Decision, "VIEW")


@router.get("/projects/{project_id}/decisions", response_model=list[DecisionOut], **_read.route)
def list_decisions(project_id: int, dimension: str | None = None, include_superseded: bool = True,
                   db: Session = Depends(get_db)):
    return decision_service.list_decisions(db, project_id, dimension, include_superseded)


@router.post("/projects/{project_id}/decisions", response_model=DecisionOut, status_code=201, **_edit.route)
def record_decision(project_id: int, body: DecisionIn, user: AppUser = Depends(current_user),
                    db: Session = Depends(get_db)):
    return decision_service.record_decision(db, user.app_user_id, project_id, body.model_dump())


@router.get("/decisions/{id}", response_model=DecisionOut, **_r.route)
def read_decision(id: int, row: Decision = Depends(_r.dep), db: Session = Depends(get_db)):
    return decision_service.read_decision(db, row)
