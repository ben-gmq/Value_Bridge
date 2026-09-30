"""Slice 2 routes (§9): process flow edges, the flow graph, the DFD (slice 3a), saved diagram positions and the
flow completeness report. Collections use project_ctx; /process-flows/{id} and
/bfc-nodes/{id}/process-flow use object_guard, so an object you cannot see is a 404."""
from typing import Annotated

from fastapi import Depends
from fastapi.responses import PlainTextResponse
from pydantic import Field
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser, BfcNode, BfcNodeFlow
from routers.guards import GuardedRouter, object_guard, project_ctx
from schemas.process_flow import (DfdGraphOut, FlowCompletenessOut, LayoutItem, ProcessFlowGraphOut, ProcessFlowIn,
                                  ProcessFlowOut, ProcessFlowPatch)
from services import diagram_layout, process_flow, render

router = GuardedRouter(tags=["process-flow"])
_read = project_ctx("REVIEWER")
_edit = project_ctx("EDITOR")
_flow_w = object_guard(BfcNodeFlow, "EDITOR")
_node_r = object_guard(BfcNode, "REVIEWER")


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


@router.get("/bfc-nodes/{id}/process-flow", response_model=ProcessFlowGraphOut, **_node_r.route)
def process_flow_graph(id: int, variant: str = "AS_IS", node: BfcNode = Depends(_node_r.dep),
                       db: Session = Depends(get_db)):
    return process_flow.generate_process_flow(db, node, variant)


@router.get("/bfc-nodes/{id}/dfd", response_model=DfdGraphOut, **_node_r.route)
def dfd_graph(id: int, node: BfcNode = Depends(_node_r.dep), db: Session = Depends(get_db)):
    return process_flow.generate_dfd(db, node)


@router.get("/bfc-nodes/{id}/process-flow/export", response_class=PlainTextResponse, **_node_r.route)
def export_process_flow(id: int, format: str = "mermaid", variant: str = "AS_IS",
                        node: BfcNode = Depends(_node_r.dep), db: Session = Depends(get_db)):
    """The process flow as Mermaid text (§7.2a export_process_flow, R2-S7)."""
    render.check_format(format)
    return PlainTextResponse(render.export_process_flow(process_flow.generate_process_flow(db, node, variant)))


@router.get("/bfc-nodes/{id}/dfd/export", response_class=PlainTextResponse, **_node_r.route)
def export_dfd(id: int, format: str = "mermaid", node: BfcNode = Depends(_node_r.dep),
               db: Session = Depends(get_db)):
    """The DFD as Mermaid text (§7.2a export_dfd, R2-S7)."""
    render.check_format(format)
    return PlainTextResponse(render.export_dfd(process_flow.generate_dfd(db, node)))


_LAYOUT = "/projects/{project_id}/diagram-layouts/{diagram_type}/{scope_key}"


@router.get(_LAYOUT, response_model=list[LayoutItem], **_read.route)
def get_layout(project_id: int, diagram_type: str, scope_key: str, db: Session = Depends(get_db)):
    return diagram_layout.get(db, project_id, diagram_type, scope_key)


@router.put(_LAYOUT, response_model=list[LayoutItem], **_edit.route)
def save_layout(project_id: int, diagram_type: str, scope_key: str,
                body: Annotated[list[LayoutItem], Field(max_length=2000)],      # A-35: 2,000 steps
                user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return diagram_layout.save(db, user.app_user_id, project_id, diagram_type, scope_key,
                               [i.model_dump() for i in body])


@router.delete(_LAYOUT, status_code=204, **_edit.route)
def reset_layout(project_id: int, diagram_type: str, scope_key: str,
                 user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    diagram_layout.reset(db, user.app_user_id, project_id, diagram_type, scope_key)
