"""Slice 2 routes (§9): process flow edges and the flow completeness report. Collections use
project_ctx; /process-flows/{id} uses object_guard, so an edge you cannot see is a 404."""
from fastapi import Depends
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser, BfcNodeFlow
from routers.guards import GuardedRouter, object_guard, project_ctx
from schemas.process_flow import FlowCompletenessOut, ProcessFlowIn, ProcessFlowOut, ProcessFlowPatch
from services import process_flow

router = GuardedRouter(tags=["process-flow"])
_read = project_ctx("REVIEWER")
_edit = project_ctx("EDITOR")
_flow_w = object_guard(BfcNodeFlow, "EDITOR")


@router.get("/projects/{project_id}/process-flows", response_model=list[ProcessFlowOut], **_read.route)
def list_flows(project_id: int, bfc_node_id: int | None = None, db: Session = Depends(get_db)):
    return process_flow.list_flows(db, project_id, bfc_node_id)


@router.post("/projects/{project_id}/process-flows", response_model=ProcessFlowOut, status_code=201,
             **_edit.route)
def link_flow(project_id: int, body: ProcessFlowIn, user: AppUser = Depends(current_user),
              db: Session = Depends(get_db)):
    return process_flow.link_process_flow(db, user.app_user_id, project_id, body.from_bfc_node_id,
                                          body.to_bfc_node_id, body.flow_type, body.condition_label,
                                          body.seq_no, body.note)


@router.patch("/process-flows/{id}", response_model=ProcessFlowOut, **_flow_w.route)
def update_flow(id: int, body: ProcessFlowPatch, row: BfcNodeFlow = Depends(_flow_w.dep),
                user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    fields = body.model_dump(exclude_unset=True, exclude={"row_version"})
    if fields.get("flow_type", ...) is None:
        fields.pop("flow_type")                      # omit to leave; a type is never null
    return process_flow.update_process_flow(db, user.app_user_id, row, body.row_version, fields)


@router.delete("/process-flows/{id}", status_code=204, **_flow_w.route)
def remove_flow(id: int, row_version: int, row: BfcNodeFlow = Depends(_flow_w.dep),
                user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    process_flow.remove_process_flow(db, user.app_user_id, row, row_version)


@router.get("/projects/{project_id}/flow-completeness", response_model=FlowCompletenessOut, **_read.route)
def flow_completeness(project_id: int, db: Session = Depends(get_db)):
    return process_flow.flow_completeness_report(db, project_id)
