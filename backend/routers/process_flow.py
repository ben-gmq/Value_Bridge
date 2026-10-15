"""The DFD and what it is drawn from (D-38, D-46, D-47, D-49; slice7_schema §9): the diagram and its
Mermaid export, the completeness report, saved positions, the performer, time/event triggers and their
links, and copying one chart into the other. The process-flow arrows and their routes were retired by
D-38 (0045). Collections use project_ctx; object routes use object_guard, so an object you cannot see is
a 404. A write names the component it needs: the chart's DFD component for trigger links and external flows
(DR7-D1); the performer only its chart, whatever the DFD setting (S10c-2, Ben 2026-10-14)."""
from typing import Annotated

from fastapi import Depends
from fastapi.responses import PlainTextResponse
from pydantic import Field
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser, BfcNode, BfcNodeTrigger, ProcessTrigger
from routers.guards import GuardedRouter, object_guard, project_ctx
from schemas.process_flow import (DfdGraphOut, LayoutItem, PerformerIn, ProcessCompletenessOut, SetCopyIn,
                                  SetCopyOut, StepTriggerIn, StepTriggerOut, TriggerIn, TriggerOut, TriggerPatch)
from schemas.scope import BfcNodeOut
from services import bfc, bfc_set, components, diagram_layout, lifecycle, process_flow, render
from services import trigger as trigger_service

router = GuardedRouter(tags=["dfd"])
_read = project_ctx("VIEW")
_edit = project_ctx("EDIT")
_edit_asis = project_ctx("EDIT", "AS_IS")              # copying a chart needs the as-is chart on


node_dfd_component = components.node_dfd_component      # one resolver (sara 7c L4)
node_set_component = components.node_set_component      # the performer: the chart's own component (S10c-2)


_node_r = object_guard(BfcNode, "VIEW")
_node_dfd_w = object_guard(BfcNode, "EDIT", component=node_dfd_component)
_node_set_w = object_guard(BfcNode, "EDIT", component=node_set_component)
_trig_w = object_guard(ProcessTrigger, "EDIT")       # the catalogue's any-of check is in the service


def _uid(user: AppUser) -> int:
    return user.app_user_id


# ---- the DFD ------------------------------------------------------------------------------------
@router.get("/projects/{project_id}/process-completeness", response_model=ProcessCompletenessOut, **_read.route)
def process_completeness(project_id: int, bfc_set: str = "TO_BE", db: Session = Depends(get_db)):
    return process_flow.process_completeness(db, project_id, bfc.check_set(bfc_set))


@router.get("/bfc-nodes/{id}/dfd", response_model=DfdGraphOut, **_node_r.route)
def dfd_graph(id: int, node: BfcNode = Depends(_node_r.dep), db: Session = Depends(get_db)):
    return process_flow.generate_dfd(db, node)


@router.get("/bfc-nodes/{id}/dfd/export", response_class=PlainTextResponse, **_node_r.route)
def export_dfd(id: int, format: str = "mermaid", order: bool = False, node: BfcNode = Depends(_node_r.dep),
               db: Session = Depends(get_db)):
    """The DFD as Mermaid text (§9.8, R2-S7); `order=true` adds the derived order, dashed."""
    render.check_format(format)
    return PlainTextResponse(render.export_dfd(process_flow.generate_dfd(db, node), with_order=order))


_LAYOUT = "/projects/{project_id}/diagram-layouts/{diagram_type}/{scope_key}"


@router.get(_LAYOUT, response_model=list[LayoutItem], **_read.route)
def get_layout(project_id: int, diagram_type: str, scope_key: str, db: Session = Depends(get_db)):
    return diagram_layout.get(db, project_id, diagram_type, scope_key)


@router.put(_LAYOUT, response_model=list[LayoutItem], **_edit.route)
def save_layout(project_id: int, diagram_type: str, scope_key: str,
                body: Annotated[list[LayoutItem], Field(max_length=2000)],      # A-35: 2,000 steps
                user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return diagram_layout.save(db, _uid(user), project_id, diagram_type, scope_key,
                               [i.model_dump() for i in body])


@router.delete(_LAYOUT, status_code=204, **_edit.route)
def reset_layout(project_id: int, diagram_type: str, scope_key: str,
                 user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    diagram_layout.reset(db, _uid(user), project_id, diagram_type, scope_key)


# ---- the performer (D-46) -------------------------------------------------------------------------
@router.put("/bfc-nodes/{id}/performer", response_model=BfcNodeOut, **_node_set_w.route)
def set_performer(id: int, body: PerformerIn, node: BfcNode = Depends(_node_set_w.dep),
                  user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    node, warnings = bfc.set_performer(db, _uid(user), node, body.row_version, body.performer_kind,
                                       body.code, body.performer_label)
    return BfcNodeOut.model_validate(node).model_copy(update={"warnings": warnings})


# ---- triggers (D-49): the catalogue and the steps they start ----------------------------------------
@router.get("/projects/{project_id}/process-triggers", response_model=list[TriggerOut], **_read.route)
def list_triggers(project_id: int, include_retired: bool = False, db: Session = Depends(get_db)):
    return trigger_service.list_triggers(db, project_id, include_retired)


@router.post("/projects/{project_id}/process-triggers", response_model=TriggerOut, status_code=201, **_edit.route)
def create_trigger(project_id: int, body: TriggerIn, user: AppUser = Depends(current_user),
                   db: Session = Depends(get_db)):
    return trigger_service.create_trigger(db, _uid(user), project_id, body.trigger_name, body.trigger_kind,
                                          body.schedule_note, body.description)


@router.patch("/process-triggers/{id}", response_model=TriggerOut, **_trig_w.route)
def update_trigger(id: int, body: TriggerPatch, row: ProcessTrigger = Depends(_trig_w.dep),
                   user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    sent = body.model_dump(exclude_unset=True, exclude={"row_version"})
    return trigger_service.update_trigger(db, _uid(user), row, body.row_version, sent)


@router.delete("/process-triggers/{id}", status_code=204, **_trig_w.route)
def retire_trigger(id: int, row_version: int, row: ProcessTrigger = Depends(_trig_w.dep),
                   user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    trigger_service.retire_trigger(db, _uid(user), row, row_version)


@router.patch("/process-triggers/{id}/restore", response_model=TriggerOut, **_trig_w.route)
def restore_trigger(id: int, row: ProcessTrigger = Depends(_trig_w.dep), user: AppUser = Depends(current_user),
                    db: Session = Depends(get_db)):
    return trigger_service.restore_trigger(db, _uid(user), row)


@router.get("/bfc-nodes/{id}/triggers", response_model=list[StepTriggerOut], **_node_r.route)
def list_step_triggers(id: int, node: BfcNode = Depends(_node_r.dep), db: Session = Depends(get_db)):
    return trigger_service.list_links(db, node)


@router.post("/bfc-nodes/{id}/triggers", response_model=StepTriggerOut, status_code=201, **_node_dfd_w.route)
def link_step_trigger(id: int, body: StepTriggerIn, node: BfcNode = Depends(_node_dfd_w.dep),
                      user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return trigger_service.link(db, _uid(user), node, body.process_trigger_id, body.note)


@router.delete("/bfc-nodes/{id}/triggers/{link_id}", status_code=204, **_node_dfd_w.route)
def unlink_step_trigger(id: int, link_id: int, row_version: int, node: BfcNode = Depends(_node_dfd_w.dep),
                        user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    trigger_service.unlink(db, _uid(user), lifecycle.child_of(db, BfcNodeTrigger, link_id, "bfc_node_id",
                                                              node.bfc_node_id), row_version)


# ---- the two charts (D-47) -------------------------------------------------------------------------
@router.get("/projects/{project_id}/bfc-sets", **_read.route)
def chart_counts(project_id: int, db: Session = Depends(get_db)):
    return bfc_set.counts(db, project_id)


@router.post("/projects/{project_id}/bfc-sets/{to_set}/copy-from/{from_set}", response_model=SetCopyOut,
             **_edit_asis.route)
def copy_chart(project_id: int, to_set: str, from_set: str, body: SetCopyIn, user: AppUser = Depends(current_user),
               db: Session = Depends(get_db)):
    """Preview without confirm_hash; with it, the whole tree is copied into the empty chart (Q-24)."""
    return bfc_set.copy_set(db, _uid(user), project_id, to_set, from_set, body.confirm_hash)
