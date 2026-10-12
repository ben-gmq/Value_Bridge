"""Slice 1 and 5 routes (§9): the function chart, business requirements, solutions, data entities and fields,
external parties, the client organisation, and the links between them.

Every route declares one guard. Project-scoped collections use project_ctx; everything under
/<things>/{id} uses object_guard, so a row in a project you cannot see is a 404. There is no
"create a requirement" route: a BR appears with its process step (D-2, §7.3).
"""
from fastapi import Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import (AppUser, Application, ApplicationBfcNode, ApplicationSolution, BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow, BfcNodeOrgRole,
                    BrDataEntity, BrOrgRole, BusinessRequirement, DataEntity, DataField,
                    ExternalEntity, OrgRole, OrgUnit, BrFunctionRequirement, BrSolution, FunctionRequirement,
                    Solution)
from routers.guards import GuardedRouter, object_guard, project_ctx
from schemas.erd import ErdGraphOut
from schemas.scope import (BfcNodeIn, BfcNodeOut, BfcNodePatch, BrDataEntityIn, BrDataEntityOut,
                           BrOut, BrPatch, BrRaciOut, DataEntityIn, DataEntityListOut, DataEntityOut,
                           DataEntityPatch, DataEntityUseOut,
                           DataFieldIn, DataFieldOut, DataFieldPatch, ExternalEntityIn,
                           ExternalEntityOut, ExternalEntityPatch, ExternalFlowIn, ExternalFlowOut,
                           OrgRoleIn, OrgRoleOut, OrgRolePatch, OrgUnitIn, OrgUnitOut, OrgUnitPatch,
                           ProcessIn, ProcessOut, RaciIn, ReorderIn, RestoreCountOut,
                           RetireConfirmIn, RetirePreviewOut, StepIoIn, StepIoOut,
                           StepRaciOut, TreeNodeOut)
from schemas.application import (AllocationIn, AllocationOut, ApplicationIn, ApplicationListOut,
                                 ApplicationOut, ApplicationPatch, LinkNotePatch, SupportIn, SupportOut)
from schemas.effort import ComplexityIn, EffortSummaryOut, RateCardChangeOut, RateCardIn, RateCardOut
from schemas.interface import InterfaceIn, InterfaceListOut, InterfaceOut
from schemas.function_requirement import (BrFrIn, BrFrOut, BrFrPatch, BrFrSolutionIn, FrBrOut, FrIn, FrOut, FrPatch,
                                         WarningsOut)
from schemas.solution import (BrSolutionIn, BrSolutionOut, BrSolutionPatch, SolutionBrOut, SolutionIn,
                             SolutionListOut, SolutionOut, SolutionPatch)
from services import bfc, business_requirement as br_service, client_org, data_entity as de_service
from services import components, external_entity as ext_service, lifecycle, raci, render, step_io, step_retire
from services import effort as effort_service, interface as iface_service
from services import application as app_service, function_requirement as fr_service, solution as sol_service

router = GuardedRouter(tags=["scope"])
_read = project_ctx("VIEW")
_edit = project_ctx("EDIT")


def _og(model, min_level, component=None):
    return object_guard(model, min_level, component=component)


# D-37: the project component each family of writes needs on (slice7_schema §5.2 table).
_edit_sol = project_ctx("EDIT", "SOLUTION")
_edit_fr = project_ctx("EDIT", "FUNCTION_REQUIREMENT")
_edit_app = project_ctx("EDIT", "APPLICATION")
_edit_effort = project_ctx("EDIT", "EFFORT")


def _uid(user: AppUser) -> int:
    return user.app_user_id


_child = lifecycle.child_of


def _retire_and_restore(prefix: str, model, out, on_restore=None, component=None):
    """DELETE (soft, refuse-with-dependents) and PATCH …/restore for one RESTORABLE entity."""
    g = _og(model, "EDIT", component)

    @router.delete(f"/{prefix}/{{id}}", status_code=204, name=f"retire_{model.__tablename__}", **g.route)
    def _delete(id: int, row_version: int, obj=Depends(g.dep), user: AppUser = Depends(current_user),
                db: Session = Depends(get_db)):
        lifecycle.retire(db, _uid(user), obj, row_version)

    @router.patch(f"/{prefix}/{{id}}/restore", response_model=out, name=f"restore_{model.__tablename__}",
                  **g.route)
    def _restore(id: int, obj=Depends(g.dep), user: AppUser = Depends(current_user),
                 db: Session = Depends(get_db)):
        if on_restore:
            return on_restore(db, _uid(user), obj)
        lifecycle.restore(db, _uid(user), obj)
        return obj


# ---- the function chart (§7.2) ------------------------------------------------------------
def node_set_component(node: BfcNode) -> str | None:
    """Resolver: a node of the as-is chart needs AS_IS on (D-47); the to-be chart is always on."""
    return "AS_IS" if node.bfc_set_code == "AS_IS" else None


node_dfd_component = components.node_dfd_component      # one resolver (sara 7c L4)


_node_r, _node_w = _og(BfcNode, "VIEW"), _og(BfcNode, "EDIT", node_set_component)
_node_dfd_w = _og(BfcNode, "EDIT", node_dfd_component)
_node_asis_w = _og(BfcNode, "EDIT", ("APPLICATION", "AS_IS"))


@router.get("/projects/{project_id}/bfc-tree", response_model=list[TreeNodeOut], **_read.route)
def bfc_tree(project_id: int, include_retired: bool = False, bfc_set: str = "TO_BE", db: Session = Depends(get_db)):
    return [{**BfcNodeOut.model_validate(r["node"]).model_dump(), "br_number": r["br_number"]}
            for r in bfc.tree(db, project_id, include_retired, bfc_set)]


@router.post("/projects/{project_id}/bfc-nodes", response_model=BfcNodeOut, status_code=201, **_edit.route)
def create_node(project_id: int, body: BfcNodeIn, user: AppUser = Depends(current_user),
                db: Session = Depends(get_db)):
    return bfc.create_node(db, _uid(user), project_id, body.parent_bfc_node_id, body.node_name,
                           body.is_process, body.purpose_desc, body.bfc_set)


@router.get("/bfc-nodes/{id}", response_model=BfcNodeOut, **_node_r.route)
def read_node(id: int, node: BfcNode = Depends(_node_r.dep)):
    return node


@router.patch("/bfc-nodes/{id}", response_model=BfcNodeOut, **_node_w.route)
def update_node(id: int, body: BfcNodePatch, node: BfcNode = Depends(_node_w.dep),
                user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return bfc.update_node(db, _uid(user), node, body.row_version,
                           body.model_dump(exclude_unset=True, exclude={"row_version"}))


@router.patch("/bfc-nodes/{id}/reorder", response_model=BfcNodeOut, **_node_w.route)
def reorder_node(id: int, body: ReorderIn, node: BfcNode = Depends(_node_w.dep),
                 user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return bfc.reorder(db, _uid(user), node, body.row_version, body.new_seq_no)


@router.patch("/bfc-nodes/{id}/process", response_model=ProcessOut, **_node_w.route)
def mark_process(id: int, body: ProcessIn, node: BfcNode = Depends(_node_w.dep),
                 user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    br = bfc.mark_process(db, _uid(user), node, body.row_version, body.is_process)
    return {"node": node, "business_requirement": br}


_retire_and_restore("bfc-nodes", BfcNode, BfcNodeOut, on_restore=step_retire.restore_plain,
                    component=node_set_component)


# retire a step with its requirement and flows (docs/step_retire_spec.md §9, design §1a S3-SR)
@router.get("/bfc-nodes/{id}/retire-preview", response_model=RetirePreviewOut, **_node_w.route)
def retire_preview(id: int, node: BfcNode = Depends(_node_w.dep), db: Session = Depends(get_db)):
    return step_retire.preview(db, node)


@router.post("/bfc-nodes/{id}/retire-with-dependents", status_code=204, **_node_w.route)
def retire_with_dependents(id: int, body: RetireConfirmIn, node: BfcNode = Depends(_node_w.dep),
                           user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    step_retire.retire(db, _uid(user), node, body.confirm_hash)


@router.post("/bfc-nodes/{id}/restore-with-dependents", response_model=RestoreCountOut, **_node_w.route)
def restore_with_dependents(id: int, node: BfcNode = Depends(_node_w.dep),
                            user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return step_retire.restore(db, _uid(user), node)


# step I/O — written only through step_io (R2-D13)
@router.get("/bfc-nodes/{id}/data-entities", response_model=list[StepIoOut], **_node_r.route)
def list_step_io(id: int, node: BfcNode = Depends(_node_r.dep), db: Session = Depends(get_db)):
    return step_io.list_links(db, node)


@router.post("/bfc-nodes/{id}/data-entities", response_model=StepIoOut, status_code=201, **_node_w.route)
def link_step_io(id: int, body: StepIoIn, node: BfcNode = Depends(_node_w.dep),
                 user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return step_io.link(db, _uid(user), node, body.data_entity_id, body.direction)


@router.delete("/bfc-nodes/{id}/data-entities/{link_id}", status_code=204, **_node_w.route)
def unlink_step_io(id: int, link_id: int, row_version: int, node: BfcNode = Depends(_node_w.dep),
                   user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    step_io.unlink(db, _uid(user), _child(db, BfcNodeDataEntity, link_id, "bfc_node_id", node.bfc_node_id),
                   row_version)


@router.get("/bfc-nodes/{id}/external-flows", response_model=list[ExternalFlowOut], **_node_r.route)
def list_external_flows(id: int, node: BfcNode = Depends(_node_r.dep), db: Session = Depends(get_db)):
    return bfc.list_external_flows(db, node)


@router.post("/bfc-nodes/{id}/external-flows", response_model=ExternalFlowOut, status_code=201,
             **_node_dfd_w.route)
def link_external_flow(id: int, body: ExternalFlowIn, node: BfcNode = Depends(_node_dfd_w.dep),
                       user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return bfc.link_external_flow(db, _uid(user), node, body.external_entity_id, body.direction,
                                  body.data_entity_id, body.flow_label, body.note)


@router.delete("/bfc-nodes/{id}/external-flows/{link_id}", status_code=204, **_node_dfd_w.route)
def unlink_external_flow(id: int, link_id: int, row_version: int, node: BfcNode = Depends(_node_dfd_w.dep),
                         user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    bfc.unlink_external_flow(db, _uid(user), _child(db, BfcNodeExternalFlow, link_id, "bfc_node_id",
                                                    node.bfc_node_id), row_version)


@router.get("/bfc-nodes/{id}/org-roles", response_model=list[StepRaciOut], **_node_r.route)
def list_step_roles(id: int, node: BfcNode = Depends(_node_r.dep), db: Session = Depends(get_db)):
    return raci.list_links(db, BfcNodeOrgRole, node.bfc_node_id)


@router.post("/bfc-nodes/{id}/org-roles", response_model=StepRaciOut, status_code=201, **_node_w.route)
def link_step_role(id: int, body: RaciIn, node: BfcNode = Depends(_node_w.dep),
                   user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return raci.link(db, _uid(user), BfcNodeOrgRole, node, body.org_role_id, body.raci_code)


@router.delete("/bfc-nodes/{id}/org-roles/{link_id}", status_code=204, **_node_w.route)
def unlink_step_role(id: int, link_id: int, row_version: int, node: BfcNode = Depends(_node_w.dep),
                     user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    raci.unlink(db, _uid(user), _child(db, BfcNodeOrgRole, link_id, "bfc_node_id", node.bfc_node_id),
                row_version)


# ---- business requirements (§7.3) ---------------------------------------------------------
_br_r, _br_w = _og(BusinessRequirement, "VIEW"), _og(BusinessRequirement, "EDIT")


@router.get("/projects/{project_id}/business-requirements", response_model=list[BrOut], **_read.route)
def list_brs(project_id: int, include_retired: bool = False, db: Session = Depends(get_db)):
    return br_service.list_brs(db, project_id, include_retired)


@router.get("/business-requirements/{id}", response_model=BrOut, **_br_r.route)
def read_br(id: int, br: BusinessRequirement = Depends(_br_r.dep)):
    return br


@router.patch("/business-requirements/{id}", response_model=BrOut, **_br_w.route)
def update_br(id: int, body: BrPatch, br: BusinessRequirement = Depends(_br_w.dep),
              user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    fields = body.model_dump(exclude_unset=True, exclude={"row_version", "status_code"})
    return br_service.update_br(db, _uid(user), br, body.row_version, fields, body.status_code)


_retire_and_restore("business-requirements", BusinessRequirement, BrOut)


@router.get("/business-requirements/{id}/data-entities", response_model=list[BrDataEntityOut],
            **_br_r.route)
def list_br_data(id: int, br: BusinessRequirement = Depends(_br_r.dep), db: Session = Depends(get_db)):
    return br_service.list_data_links(db, br)


@router.post("/business-requirements/{id}/data-entities", response_model=BrDataEntityOut,
             status_code=201, **_br_w.route)
def link_br_data(id: int, body: BrDataEntityIn, br: BusinessRequirement = Depends(_br_w.dep),
                 user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return br_service.link_data_entity(db, _uid(user), br, body.data_entity_id, body.crud_code,
                                       body.usage_note)


@router.delete("/business-requirements/{id}/data-entities/{link_id}", status_code=204, **_br_w.route)
def unlink_br_data(id: int, link_id: int, row_version: int, br: BusinessRequirement = Depends(_br_w.dep),
                   user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    br_service.unlink_data_entity(db, _uid(user), _child(db, BrDataEntity, link_id, "br_id", br.br_id),
                                  row_version)


@router.get("/business-requirements/{id}/org-roles", response_model=list[BrRaciOut], **_br_r.route)
def list_br_roles(id: int, br: BusinessRequirement = Depends(_br_r.dep), db: Session = Depends(get_db)):
    return raci.list_links(db, BrOrgRole, br.br_id)


@router.post("/business-requirements/{id}/org-roles", response_model=BrRaciOut, status_code=201,
             **_br_w.route)
def link_br_role(id: int, body: RaciIn, br: BusinessRequirement = Depends(_br_w.dep),
                 user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return raci.link(db, _uid(user), BrOrgRole, br, body.org_role_id, body.raci_code)


@router.delete("/business-requirements/{id}/org-roles/{link_id}", status_code=204, **_br_w.route)
def unlink_br_role(id: int, link_id: int, row_version: int, br: BusinessRequirement = Depends(_br_w.dep),
                   user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    raci.unlink(db, _uid(user), _child(db, BrOrgRole, link_id, "br_id", br.br_id), row_version)


# ---- solutions and the BRs they answer (§7.5, §4.3, docs/slice5_spec.md) -----------------
_sol_r, _sol_w = _og(Solution, "VIEW"), _og(Solution, "EDIT", "SOLUTION")
_br_sol_w = _og(BusinessRequirement, "EDIT", "SOLUTION")
_sol_app_w = _og(Solution, "EDIT", ("SOLUTION", "APPLICATION"))


@router.get("/projects/{project_id}/solutions", response_model=list[SolutionListOut], **_read.route)
def list_solutions(project_id: int, include_retired: bool = False, db: Session = Depends(get_db)):
    return [SolutionListOut.model_validate(s).model_copy(update={"live_br_count": n})
            for s, n in sol_service.list_solutions(db, project_id, include_retired)]


@router.post("/projects/{project_id}/solutions", response_model=SolutionOut, status_code=201,
             **_edit_sol.route)
def create_solution(project_id: int, body: SolutionIn, user: AppUser = Depends(current_user),
                    db: Session = Depends(get_db)):
    return sol_service.create_solution(db, _uid(user), project_id, body.solution_name, body.category_code,
                                       body.model_dump(exclude={"solution_name", "category_code"}))


@router.get("/solutions/{id}", response_model=SolutionOut, **_sol_r.route)
def read_solution(id: int, sol: Solution = Depends(_sol_r.dep)):
    return sol


@router.patch("/solutions/{id}", response_model=SolutionOut, **_sol_w.route)
def update_solution(id: int, body: SolutionPatch, sol: Solution = Depends(_sol_w.dep),
                    user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    fields = body.model_dump(exclude_unset=True, exclude={"row_version", "category_code", "status_code"})
    return sol_service.update_solution(db, _uid(user), sol, body.row_version, fields,
                                       body.category_code, body.status_code)


_retire_and_restore("solutions", Solution, SolutionOut, on_restore=sol_service.restore_solution,
                    component="SOLUTION")


@router.get("/solutions/{id}/business-requirements", response_model=list[SolutionBrOut], **_sol_r.route)
def list_solution_brs(id: int, sol: Solution = Depends(_sol_r.dep), db: Session = Depends(get_db)):
    return sol_service.links_of_solution(db, sol)


@router.get("/business-requirements/{id}/solutions", response_model=list[BrSolutionOut], **_br_r.route)
def list_br_solutions(id: int, br: BusinessRequirement = Depends(_br_r.dep), db: Session = Depends(get_db)):
    return sol_service.links_of_br(db, br)


@router.post("/business-requirements/{id}/solutions", response_model=BrSolutionOut, status_code=201,
             **_br_sol_w.route)
def link_br_solution(id: int, body: BrSolutionIn, br: BusinessRequirement = Depends(_br_sol_w.dep),
                     user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    row = sol_service.link(db, _uid(user), br, body.solution_id, body.coverage_note)
    return sol_service.as_br_link(db, row)


@router.patch("/business-requirements/{id}/solutions/{link_id}", response_model=BrSolutionOut,
              **_br_sol_w.route)
def edit_br_solution(id: int, link_id: int, body: BrSolutionPatch,
                     br: BusinessRequirement = Depends(_br_sol_w.dep), user: AppUser = Depends(current_user),
                     db: Session = Depends(get_db)):
    row = sol_service.edit_note(db, _uid(user), _child(db, BrSolution, link_id, "br_id", br.br_id),
                                body.row_version, body.coverage_note)
    return sol_service.as_br_link(db, row)


@router.delete("/business-requirements/{id}/solutions/{link_id}", response_model=WarningsOut, **_br_sol_w.route)
def unlink_br_solution(id: int, link_id: int, row_version: int, br: BusinessRequirement = Depends(_br_sol_w.dep),
                       user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    """200 with the D-52 drift warnings (slice10b §2.2): FRs whose tag now answers none of their BRs."""
    return {"warnings": sol_service.unlink(db, _uid(user), _child(db, BrSolution, link_id, "br_id", br.br_id),
                                           row_version)}


# ---- function requirements (§7.5, D-27/D-28, docs/slice6a_spec.md) -------------------------
_fr_r, _fr_w = _og(FunctionRequirement, "VIEW"), _og(FunctionRequirement, "EDIT", "FUNCTION_REQUIREMENT")
_fr_effort_w = _og(FunctionRequirement, "EDIT", ("FUNCTION_REQUIREMENT", "EFFORT"))
_fr_iface_w = _og(FunctionRequirement, "EDIT", ("FUNCTION_REQUIREMENT", "APPLICATION"))


def _fr_out(fr: FunctionRequirement, warnings: list[str] | None = None) -> FrOut:
    return FrOut.model_validate(fr).model_copy(update={"warnings": warnings or []})


@router.get("/projects/{project_id}/function-requirements", response_model=list[FrOut], **_read.route)
def list_frs(project_id: int, include_retired: bool = False, unlinked: bool = False, unassigned: bool = False,
             db: Session = Depends(get_db)):
    """slice10b §6.10: `unlinked` = no live BR link (untraced); `unassigned` = no solution."""
    return fr_service.list_frs(db, project_id, include_retired, unlinked, unassigned)


@router.post("/projects/{project_id}/function-requirements", response_model=FrOut, status_code=201,
             **_edit_fr.route)
def create_fr(project_id: int, body: FrIn, user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    if body.br_id is not None:
        fr_service.scoped_br(db, project_id, body.br_id)                 # 404 before 409 COMPONENT_OFF
    if body.solution_id is not None:
        components.require_on(db, project_id, "SOLUTION")
    fr, warnings = fr_service.create_fr(db, _uid(user), project_id, body.fr_name, body.fr_type_code,
                                        body.solution_id, body.model_dump(include={"description", "acceptance_note"}),
                                        br_id=body.br_id)
    return _fr_out(fr, warnings)


@router.get("/function-requirements/{id}", response_model=FrOut, **_fr_r.route)
def read_fr(id: int, fr: FunctionRequirement = Depends(_fr_r.dep), db: Session = Depends(get_db)):
    return fr_service.with_br_count(db, fr)


@router.patch("/function-requirements/{id}", response_model=FrOut, **_fr_w.route)
def update_fr(id: int, body: FrPatch, fr: FunctionRequirement = Depends(_fr_w.dep),
              user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    sent = body.model_dump(exclude_unset=True)
    fields = {k: sent[k] for k in fr_service.EDITABLE if k in sent}
    extra = {"solution_id": sent["solution_id"]} if "solution_id" in sent else {}
    if extra.get("solution_id") is not None:
        components.require_on(db, fr.project_id, "SOLUTION")
    fr, warnings = fr_service.update_fr(db, _uid(user), fr, body.row_version, fields,
                                        sent.get("fr_type_code"), sent.get("fulfilment_status_code"), **extra)
    return _fr_out(fr, warnings).model_copy(update={"effort_change": getattr(fr, "effort_change", None)})


def _restore_fr(db: Session, actor_id: int, fr: FunctionRequirement) -> FunctionRequirement:
    """DR7-P2: a rated FR needs EFFORT on, a linked one SOLUTION, before it comes back live."""
    components.require_on(db, fr.project_id, components.needed_for_rows([fr]))
    lifecycle.restore(db, actor_id, fr)
    # slice10b §2.2 case 5: the tag comes back as it was; say so if it answers none of the FR's BRs
    return _fr_out(fr_service.with_br_count(db, fr), fr_service.drift_warnings(db, [fr.fr_id], include_no_br=True))


_retire_and_restore("function-requirements", FunctionRequirement, FrOut, on_restore=_restore_fr,
                    component="FUNCTION_REQUIREMENT")


@router.get("/solutions/{id}/function-requirements", response_model=list[FrOut], **_sol_r.route)
def list_solution_frs(id: int, sol: Solution = Depends(_sol_r.dep), db: Session = Depends(get_db)):
    counts = fr_service.br_counts(db, sol.project_id)
    return [FrOut.model_validate(f).model_copy(update={"br_count": counts.get(f.fr_id, 0)})
            for f in fr_service.frs_of_solution(db, sol)]


# ---- BR ↔ FR, the direct mapping (D-52, docs/slice10b_schema.md §1.2, §2, §4.1) --------------------------
# Link writes need FUNCTION_REQUIREMENT only (Q-11): a project with SOLUTION off can still map BR → FR.
_br_fr_w = _og(BusinessRequirement, "EDIT", "FUNCTION_REQUIREMENT")


@router.get("/business-requirements/{id}/function-requirements", response_model=list[BrFrOut], **_br_r.route)
def list_br_frs(id: int, br: BusinessRequirement = Depends(_br_r.dep), db: Session = Depends(get_db)):
    return fr_service.frs_of_br(db, br)


@router.post("/business-requirements/{id}/function-requirements", response_model=BrFrOut, status_code=201,
             **_br_fr_w.route)
def link_br_fr(id: int, body: BrFrIn, br: BusinessRequirement = Depends(_br_fr_w.dep),
               user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    row, warnings = fr_service.link_fr(db, _uid(user), br, body.fr_id, body.coverage_note)
    return {**fr_service.br_fr_row(db, row), "warnings": warnings}


@router.patch("/business-requirements/{id}/function-requirements/{link_id}", response_model=BrFrOut,
              **_br_fr_w.route)
def edit_br_fr(id: int, link_id: int, body: BrFrPatch, br: BusinessRequirement = Depends(_br_fr_w.dep),
               user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    row = fr_service.edit_link_note(db, _uid(user), _child(db, BrFunctionRequirement, link_id, "br_id", br.br_id),
                                    body.row_version, body.coverage_note)
    return fr_service.br_fr_row(db, row)


@router.delete("/business-requirements/{id}/function-requirements/{link_id}", response_model=WarningsOut,
               **_br_fr_w.route)
def unlink_br_fr(id: int, link_id: int, row_version: int, br: BusinessRequirement = Depends(_br_fr_w.dep),
                 user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    """200 with the drift warnings (§2.2): the FR's tag now answers none of its BRs, or it has no BR left."""
    return {"warnings": fr_service.unlink_fr(
        db, _uid(user), _child(db, BrFunctionRequirement, link_id, "br_id", br.br_id), row_version)}


@router.put("/business-requirements/{id}/function-requirements/{link_id}/solution", response_model=BrFrOut,
            **_br_fr_w.route)
def tag_br_fr(id: int, link_id: int, body: BrFrSolutionIn, br: BusinessRequirement = Depends(_br_fr_w.dep),
              user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    """The FR's solution tag, from this BR's row: one of THIS BR's live solutions, or none (422 otherwise).
    Setting one needs SOLUTION on too; clearing needs only FUNCTION_REQUIREMENT (Q-11)."""
    link = _child(db, BrFunctionRequirement, link_id, "br_id", br.br_id)        # 404 before 409
    if body.solution_id is not None:
        components.require_on(db, br.project_id, "SOLUTION")
    row, warnings = fr_service.set_solution_from_br(db, _uid(user), br, link, body.solution_id, body.fr_row_version)
    return {**row, "warnings": warnings}


@router.get("/function-requirements/{id}/business-requirements", response_model=list[FrBrOut], **_fr_r.route)
def list_fr_brs(id: int, fr: FunctionRequirement = Depends(_fr_r.dep), db: Session = Depends(get_db)):
    return fr_service.brs_of_fr(db, fr)


# ---- rate card and effort days (§4.8, §7.13, D-13, docs/slice6c_spec.md) ----------------------
@router.get("/projects/{project_id}/rate-card", response_model=RateCardOut, **_read.route)
def read_rate_card(project_id: int, db: Session = Depends(get_db)):
    return effort_service.read_card(db, project_id)


@router.put("/projects/{project_id}/rate-card", response_model=RateCardChangeOut, **_edit_effort.route)   # S6c-3: any User (EDIT)
def maintain_rate_card(project_id: int, body: RateCardIn, user: AppUser = Depends(current_user),
                       db: Session = Depends(get_db)):
    return effort_service.maintain_card(db, _uid(user), project_id, body.change_rationale, body.cells, body.confirm_high)


@router.patch("/function-requirements/{id}/complexity", response_model=FrOut, **_fr_effort_w.route)
def rate_function_requirement(id: int, body: ComplexityIn, fr: FunctionRequirement = Depends(_fr_effort_w.dep),
                              user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return effort_service.rate_fr(db, _uid(user), fr, body.row_version, body.complexity_code)


@router.get("/projects/{project_id}/effort-summary", response_model=EffortSummaryOut, **_read.route)
def effort_summary(project_id: int, db: Session = Depends(get_db)):
    return effort_service.summary(db, project_id)


# ---- interface detail and the generated interface list (§7.5, D-27, docs/slice6b2_spec.md) ---
@router.get("/function-requirements/{id}/interface", response_model=InterfaceOut, **_fr_r.route)
def read_interface(id: int, fr: FunctionRequirement = Depends(_fr_r.dep), db: Session = Depends(get_db)):
    return iface_service.read_interface(db, fr)


@router.put("/function-requirements/{id}/interface", response_model=InterfaceOut, **_fr_iface_w.route)
def describe_interface(id: int, body: InterfaceIn, fr: FunctionRequirement = Depends(_fr_iface_w.dep),
                       user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return iface_service.describe_interface(db, _uid(user), fr, body)


@router.delete("/function-requirements/{id}/interface", status_code=204, **_fr_iface_w.route)
def remove_interface(id: int, row_version: int, fr: FunctionRequirement = Depends(_fr_iface_w.dep),
                     user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    iface_service.remove_interface(db, _uid(user), fr, row_version)


@router.get("/projects/{project_id}/interfaces", response_model=InterfaceListOut, **_read.route)
def interface_list(project_id: int, source: int | None = None, target: int | None = None,
                   status: str | None = None, db: Session = Depends(get_db)):
    return iface_service.interface_list(db, project_id, source, target, status)


# ---- applications: catalogue, to-be allocation, as-is support (§7.5, D-8, docs/slice6b1_spec.md)
_app_r, _app_w = _og(Application, "VIEW"), _og(Application, "EDIT", "APPLICATION")


@router.get("/projects/{project_id}/applications", response_model=list[ApplicationListOut], **_read.route)
def list_applications(project_id: int, include_retired: bool = False, db: Session = Depends(get_db)):
    return [ApplicationListOut.model_validate(a).model_copy(update={"live_solution_count": ns, "live_step_count": nn})
            for a, ns, nn in app_service.list_applications(db, project_id, include_retired)]


@router.post("/projects/{project_id}/applications", response_model=ApplicationOut, status_code=201, **_edit_app.route)
def create_application(project_id: int, body: ApplicationIn, user: AppUser = Depends(current_user),
                       db: Session = Depends(get_db)):
    return app_service.create_application(db, _uid(user), project_id, body.application_code, body.application_name,
                                          body.lifecycle_code, body.kind_code,
                                          body.model_dump(include={"vendor", "version_label", "description"}))


@router.get("/applications/{id}", response_model=ApplicationOut, **_app_r.route)
def read_application(id: int, app: Application = Depends(_app_r.dep)):
    return app


@router.patch("/applications/{id}", response_model=ApplicationOut, **_app_w.route)
def update_application(id: int, body: ApplicationPatch, app: Application = Depends(_app_w.dep),
                       user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    app, warnings = app_service.update_application(db, _uid(user), app, body.row_version,
                                                   body.model_dump(exclude_unset=True, exclude={"row_version"}))
    return ApplicationOut.model_validate(app).model_copy(update={"warnings": warnings})


_retire_and_restore("applications", Application, ApplicationOut, on_restore=app_service.restore_application,
                    component="APPLICATION")


@router.get("/applications/{id}/solutions", response_model=list[AllocationOut], **_app_r.route)
def list_application_solutions(id: int, app: Application = Depends(_app_r.dep), db: Session = Depends(get_db)):
    return app_service.allocations(db, application_id=app.application_id)


@router.get("/applications/{id}/bfc-nodes", response_model=list[SupportOut], **_app_r.route)
def list_application_steps(id: int, app: Application = Depends(_app_r.dep), db: Session = Depends(get_db)):
    return app_service.supports(db, application_id=app.application_id)


@router.get("/solutions/{id}/applications", response_model=list[AllocationOut], **_sol_r.route)
def list_solution_applications(id: int, sol: Solution = Depends(_sol_r.dep), db: Session = Depends(get_db)):
    return app_service.allocations(db, solution_id=sol.solution_id)


@router.post("/solutions/{id}/applications", response_model=AllocationOut, status_code=201, **_sol_app_w.route)
def allocate_application(id: int, body: AllocationIn, sol: Solution = Depends(_sol_app_w.dep),
                         user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return app_service.as_alloc(app_service.link_solution(db, _uid(user), sol, body.application_id, body.note))


@router.patch("/solutions/{id}/applications/{link_id}", response_model=AllocationOut, **_sol_app_w.route)
def edit_allocation(id: int, link_id: int, body: LinkNotePatch, sol: Solution = Depends(_sol_app_w.dep),
                    user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    row = _child(db, ApplicationSolution, link_id, "solution_id", sol.solution_id)
    return app_service.as_alloc(app_service.edit_note(db, _uid(user), row, body.row_version, body.note))


@router.delete("/solutions/{id}/applications/{link_id}", status_code=204, **_sol_app_w.route)
def unallocate_application(id: int, link_id: int, row_version: int, sol: Solution = Depends(_sol_app_w.dep),
                           user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    app_service.unlink(db, _uid(user), _child(db, ApplicationSolution, link_id, "solution_id", sol.solution_id),
                       row_version)


@router.get("/bfc-nodes/{id}/applications", response_model=list[SupportOut], **_node_r.route)
def list_step_applications(id: int, node: BfcNode = Depends(_node_r.dep), db: Session = Depends(get_db)):
    return app_service.supports(db, bfc_node_id=node.bfc_node_id)


@router.post("/bfc-nodes/{id}/applications", response_model=SupportOut, status_code=201, **_node_asis_w.route)
def link_step_application(id: int, body: SupportIn, node: BfcNode = Depends(_node_asis_w.dep),
                          user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    row, warnings = app_service.link_step(db, _uid(user), node, body.application_id, body.note)
    return {**app_service.as_support(row), "warnings": warnings}


@router.patch("/bfc-nodes/{id}/applications/{link_id}", response_model=SupportOut, **_node_asis_w.route)
def edit_step_application(id: int, link_id: int, body: LinkNotePatch, node: BfcNode = Depends(_node_asis_w.dep),
                          user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    row = _child(db, ApplicationBfcNode, link_id, "bfc_node_id", node.bfc_node_id)
    return app_service.as_support(app_service.edit_note(db, _uid(user), row, body.row_version, body.note))


@router.delete("/bfc-nodes/{id}/applications/{link_id}", status_code=204, **_node_asis_w.route)
def unlink_step_application(id: int, link_id: int, row_version: int, node: BfcNode = Depends(_node_asis_w.dep),
                            user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    app_service.unlink(db, _uid(user), _child(db, ApplicationBfcNode, link_id, "bfc_node_id", node.bfc_node_id),
                       row_version)


# ---- data entities and fields (§7.4) ------------------------------------------------------
_de_r, _de_w = _og(DataEntity, "VIEW"), _og(DataEntity, "EDIT")
_df_w = _og(DataField, "EDIT")


@router.get("/projects/{project_id}/data-entities", response_model=list[DataEntityListOut], **_read.route)
def list_entities(project_id: int, include_retired: bool = False, db: Session = Depends(get_db)):
    counts = de_service.live_field_counts(db, project_id)
    return [DataEntityListOut.model_validate(de).model_copy(
                update={"live_field_count": counts.get(de.data_entity_id, 0)})
            for de in de_service.list_entities(db, project_id, include_retired)]


@router.post("/projects/{project_id}/data-entities", response_model=DataEntityOut, status_code=201,
             **_edit.route)
def create_entity(project_id: int, body: DataEntityIn, user: AppUser = Depends(current_user),
                  db: Session = Depends(get_db)):
    return de_service.create_entity(db, _uid(user), project_id, body.de_name, body.description,
                                    body.business_owner_note)


@router.get("/data-entities/{id}", response_model=DataEntityOut, **_de_r.route)
def read_entity(id: int, de: DataEntity = Depends(_de_r.dep)):
    return de


@router.patch("/data-entities/{id}", response_model=DataEntityOut, **_de_w.route)
def update_entity(id: int, body: DataEntityPatch, de: DataEntity = Depends(_de_w.dep),
                  user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return de_service.update_entity(db, _uid(user), de, body.row_version,
                                    body.model_dump(exclude_unset=True, exclude={"row_version"}))


_retire_and_restore("data-entities", DataEntity, DataEntityOut)


@router.get("/data-entities/{id}/business-requirements", response_model=list[DataEntityUseOut],
            **_de_r.route)
def entity_used_by(id: int, de: DataEntity = Depends(_de_r.dep), db: Session = Depends(get_db)):
    return de_service.used_by(db, de)


@router.get("/data-entities/{id}/fields", response_model=list[DataFieldOut], **_de_r.route)
def list_fields(id: int, include_retired: bool = False, de: DataEntity = Depends(_de_r.dep),
                db: Session = Depends(get_db)):
    return de_service.list_fields(db, de, include_retired)


@router.post("/data-entities/{id}/fields", response_model=DataFieldOut, status_code=201, **_de_w.route)
def create_field(id: int, body: DataFieldIn, de: DataEntity = Depends(_de_w.dep),
                 user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return de_service.create_field(db, _uid(user), de, body.field_name,
                                   body.model_dump(exclude={"field_name"}))


@router.patch("/data-fields/{id}", response_model=DataFieldOut, **_df_w.route)
def update_field(id: int, body: DataFieldPatch, f: DataField = Depends(_df_w.dep),
                 user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    spec = body.model_dump(exclude_unset=True, exclude={"row_version", "field_name"})
    return de_service.update_field(db, _uid(user), f, body.row_version, body.field_name, spec)


_retire_and_restore("data-fields", DataField, DataFieldOut, on_restore=de_service.restore_field)


@router.get("/projects/{project_id}/erd", response_model=ErdGraphOut, **_read.route)
def erd_graph(project_id: int, subject_area: int | None = None, db: Session = Depends(get_db)):
    """The logical ERD (§7.4, D-29). An unknown, other-project or retired area node is a 404."""
    return de_service.generate_erd(db, project_id, subject_area)


@router.get("/projects/{project_id}/erd/export", response_class=PlainTextResponse, **_read.route)
def erd_export(project_id: int, format: str = "mermaid", subject_area: int | None = None,
               db: Session = Depends(get_db)):
    """The logical ERD as Mermaid erDiagram text (§7.4 export_erd, R2-S7)."""
    render.check_format(format)
    return PlainTextResponse(render.export_erd(de_service.generate_erd(db, project_id, subject_area)))


# ---- external parties (D-24a) -------------------------------------------------------------
_ext_w = _og(ExternalEntity, "EDIT")


@router.get("/projects/{project_id}/external-entities", response_model=list[ExternalEntityOut],
            **_read.route)
def list_parties(project_id: int, include_retired: bool = False, db: Session = Depends(get_db)):
    return ext_service.list_parties(db, project_id, include_retired)


@router.post("/projects/{project_id}/external-entities", response_model=ExternalEntityOut,
             status_code=201, **_edit.route)
def create_party(project_id: int, body: ExternalEntityIn, user: AppUser = Depends(current_user),
                 db: Session = Depends(get_db)):
    return ext_service.create_party(db, _uid(user), project_id, body.ext_name, body.kind_code,
                                    body.description)


@router.patch("/external-entities/{id}", response_model=ExternalEntityOut, **_ext_w.route)
def update_party(id: int, body: ExternalEntityPatch, ext: ExternalEntity = Depends(_ext_w.dep),
                 user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return ext_service.update_party(db, _uid(user), ext, body.row_version,
                                    body.model_dump(exclude_unset=True, exclude={"row_version"}))


_retire_and_restore("external-entities", ExternalEntity, ExternalEntityOut)


# ---- client organisation ------------------------------------------------------------------
_unit_w, _role_w = _og(OrgUnit, "EDIT"), _og(OrgRole, "EDIT")


@router.get("/projects/{project_id}/org-units", response_model=list[OrgUnitOut], **_read.route)
def list_units(project_id: int, include_retired: bool = False, db: Session = Depends(get_db)):
    return client_org.list_units(db, project_id, include_retired)


@router.post("/projects/{project_id}/org-units", response_model=OrgUnitOut, status_code=201,
             **_edit.route)
def create_unit(project_id: int, body: OrgUnitIn, user: AppUser = Depends(current_user),
                db: Session = Depends(get_db)):
    return client_org.create_unit(db, _uid(user), project_id, body.parent_org_unit_id,
                                  body.org_unit_code, body.org_unit_name, body.level_code,
                                  body.description)


@router.patch("/org-units/{id}", response_model=OrgUnitOut, **_unit_w.route)
def update_unit(id: int, body: OrgUnitPatch, unit: OrgUnit = Depends(_unit_w.dep),
                user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return client_org.update_unit(db, _uid(user), unit, body.row_version,
                                  body.model_dump(exclude_unset=True, exclude={"row_version", "level_code"}),
                                  body.level_code)


_retire_and_restore("org-units", OrgUnit, OrgUnitOut, on_restore=client_org.restore_unit)


@router.get("/projects/{project_id}/org-roles", response_model=list[OrgRoleOut], **_read.route)
def list_roles(project_id: int, include_retired: bool = False, db: Session = Depends(get_db)):
    return client_org.list_roles(db, project_id, include_retired)


@router.post("/projects/{project_id}/org-roles", response_model=OrgRoleOut, status_code=201,
             **_edit.route)
def create_role(project_id: int, body: OrgRoleIn, user: AppUser = Depends(current_user),
                db: Session = Depends(get_db)):
    return client_org.create_role(db, _uid(user), project_id, body.org_unit_id, body.org_role_code,
                                  body.org_role_name, body.responsibility_desc, body.headcount)


@router.patch("/org-roles/{id}", response_model=OrgRoleOut, **_role_w.route)
def update_role(id: int, body: OrgRolePatch, role: OrgRole = Depends(_role_w.dep),
                user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return client_org.update_role(db, _uid(user), role, body.row_version,
                                  body.model_dump(exclude_unset=True, exclude={"row_version"}))


_retire_and_restore("org-roles", OrgRole, OrgRoleOut)
