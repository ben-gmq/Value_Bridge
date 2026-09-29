"""Slice 1 routes (§9): the function chart, business requirements, data entities and fields,
external parties, the client organisation, and the links between them.

Every route declares one guard. Project-scoped collections use project_ctx; everything under
/<things>/{id} uses object_guard, so a row in a project you cannot see is a 404. There is no
"create a requirement" route: a BR appears with its process step (D-2, §7.3).
"""
from fastapi import Depends
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import (AppUser, BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow, BfcNodeOrgRole,
                    BrDataEntity, BrOrgRole, BusinessRequirement, DataEntity, DataField,
                    ExternalEntity, OrgRole, OrgUnit)
from routers.guards import GuardedRouter, object_guard, project_ctx
from schemas.scope import (BfcNodeIn, BfcNodeOut, BfcNodePatch, BrDataEntityIn, BrDataEntityOut,
                           BrOut, BrPatch, BrRaciOut, DataEntityIn, DataEntityOut, DataEntityPatch,
                           DataEntityUseOut,
                           DataFieldIn, DataFieldOut, DataFieldPatch, ExternalEntityIn,
                           ExternalEntityOut, ExternalEntityPatch, ExternalFlowIn, ExternalFlowOut,
                           OrgRoleIn, OrgRoleOut, OrgRolePatch, OrgUnitIn, OrgUnitOut, OrgUnitPatch,
                           ProcessIn, ProcessOut, RaciIn, ReorderIn, StepIoIn, StepIoOut,
                           StepRaciOut, TreeNodeOut)
from services import bfc, business_requirement as br_service, client_org, data_entity as de_service
from services import external_entity as ext_service, lifecycle, raci, step_io

router = GuardedRouter(tags=["scope"])
_read = project_ctx("REVIEWER")
_edit = project_ctx("EDITOR")


def _og(model, role):
    return object_guard(model, role)


def _uid(user: AppUser) -> int:
    return user.app_user_id


_child = lifecycle.child_of


def _retire_and_restore(prefix: str, model, out, on_restore=None):
    """DELETE (soft, refuse-with-dependents) and PATCH …/restore for one RESTORABLE entity."""
    g = _og(model, "EDITOR")

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
_node_r, _node_w = _og(BfcNode, "REVIEWER"), _og(BfcNode, "EDITOR")


@router.get("/projects/{project_id}/bfc-tree", response_model=list[TreeNodeOut], **_read.route)
def bfc_tree(project_id: int, include_retired: bool = False, db: Session = Depends(get_db)):
    return [{**BfcNodeOut.model_validate(r["node"]).model_dump(), "br_number": r["br_number"]}
            for r in bfc.tree(db, project_id, include_retired)]


@router.post("/projects/{project_id}/bfc-nodes", response_model=BfcNodeOut, status_code=201, **_edit.route)
def create_node(project_id: int, body: BfcNodeIn, user: AppUser = Depends(current_user),
                db: Session = Depends(get_db)):
    return bfc.create_node(db, _uid(user), project_id, body.parent_bfc_node_id, body.node_name,
                           body.is_process, body.purpose_desc)


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


_retire_and_restore("bfc-nodes", BfcNode, BfcNodeOut, on_restore=bfc.restore_node)


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
             **_node_w.route)
def link_external_flow(id: int, body: ExternalFlowIn, node: BfcNode = Depends(_node_w.dep),
                       user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return bfc.link_external_flow(db, _uid(user), node, body.external_entity_id, body.direction,
                                  body.data_entity_id, body.flow_label, body.note)


@router.delete("/bfc-nodes/{id}/external-flows/{link_id}", status_code=204, **_node_w.route)
def unlink_external_flow(id: int, link_id: int, row_version: int, node: BfcNode = Depends(_node_w.dep),
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
_br_r, _br_w = _og(BusinessRequirement, "REVIEWER"), _og(BusinessRequirement, "EDITOR")


@router.get("/projects/{project_id}/business-requirements", response_model=list[BrOut], **_read.route)
def list_brs(project_id: int, db: Session = Depends(get_db)):
    return br_service.list_brs(db, project_id)


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


# ---- data entities and fields (§7.4) ------------------------------------------------------
_de_r, _de_w = _og(DataEntity, "REVIEWER"), _og(DataEntity, "EDITOR")
_df_w = _og(DataField, "EDITOR")


@router.get("/projects/{project_id}/data-entities", response_model=list[DataEntityOut], **_read.route)
def list_entities(project_id: int, db: Session = Depends(get_db)):
    return de_service.list_entities(db, project_id)


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
def list_fields(id: int, de: DataEntity = Depends(_de_r.dep), db: Session = Depends(get_db)):
    return de_service.list_fields(db, de)


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


# ---- external parties (D-24a) -------------------------------------------------------------
_ext_w = _og(ExternalEntity, "EDITOR")


@router.get("/projects/{project_id}/external-entities", response_model=list[ExternalEntityOut],
            **_read.route)
def list_parties(project_id: int, db: Session = Depends(get_db)):
    return ext_service.list_parties(db, project_id)


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
_unit_w, _role_w = _og(OrgUnit, "EDITOR"), _og(OrgRole, "EDITOR")


@router.get("/projects/{project_id}/org-units", response_model=list[OrgUnitOut], **_read.route)
def list_units(project_id: int, db: Session = Depends(get_db)):
    return client_org.list_units(db, project_id)


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
def list_roles(project_id: int, db: Session = Depends(get_db)):
    return client_org.list_roles(db, project_id)


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
