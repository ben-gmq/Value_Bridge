"""Projects, programs, components, members and code lookups (§9; D-37, D-40, slice7_schema §8)."""
from fastapi import Depends
from sqlalchemy.orm import Session

from database import get_db
from models import AppUser, ProjectMember
from routers.guards import (GuardedRouter, authenticated, object_guard, platform_admin,
                            program_ctx, project_ctx)
from schemas.common import (CodeOut, ComponentOut, ComponentsChangeOut, ComponentsIn, DepthIn, DfdRuleIn,
                            DfdRuleOut, DfdRulePreviewIn, DfdRulePreviewOut,
                            EffectiveAccessOut, MemberIn, MemberOut, MemberPatch, PersonOut,
                            ProgramIn, ProgramMoveIn, ProgramOut, ProjectIn, ProjectOut, ProjectPatch,
                            RestrictionIn, RestrictionOut, TemplateOut)
from schemas.process_flow import FteBasisIn, FteBasisOut, VolumeSummaryOut
from services import access, code_master, components, dfd_rule, process_volume
from services import program as program_service
from services import project as project_service

router = GuardedRouter(tags=["projects"])
_auth = authenticated()
_admin = platform_admin()
_reader = project_ctx("VIEW")
_editor = project_ctx("EDIT")
_proj_admin = project_ctx("ADMIN")             # a project admin or a platform admin: members, access list (D-71)
_platform = project_ctx("PLATFORM")            # platform admins only: the FTC-only project settings (D-71 (6))
_prog_reader = program_ctx("VIEW")
_member_admin = object_guard(ProjectMember, "ADMIN")


# ---- projects ----
@router.get("/projects", response_model=list[ProjectOut], **_auth.route)
def list_projects(user: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    return project_service.list_visible_projects(db, user)


@router.post("/projects", response_model=ProjectOut, status_code=201, **_admin.route)
def create_project(body: ProjectIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return project_service.create_project(db, actor, body.client_id, body.project_code,
                                          body.project_name, body.program_id, body.start_date,
                                          body.end_date, component_codes=body.component_codes,
                                          is_restricted=body.is_restricted,
                                          template_code=body.template_code,
                                          data_model_depth=body.data_model_depth,
                                          dfd_rule=body.dfd_rule)


@router.get("/projects/{project_id}", response_model=ProjectOut, **_reader.route)
def read_project(project_id: int, eff: access.EffectiveAccess = Depends(_reader.dep),
                 db: Session = Depends(get_db)):
    p = project_service.get_project(db, project_id)
    return ProjectOut.model_validate(p).model_copy(update={"my_access_level": eff.level})


@router.patch("/projects/{project_id}", response_model=ProjectOut, **_editor.route)
def update_project(project_id: int, body: ProjectPatch, db: Session = Depends(get_db),
                   user: AppUser = Depends(_auth.dep)):
    fields = body.model_dump(exclude_unset=True, exclude={"row_version"})
    return project_service.update_project(db, user, project_service.get_project(db, project_id),
                                          body.row_version, fields)


@router.get("/projects/{project_id}/code-master/{category}", response_model=list[CodeOut],
            **_reader.route)
def project_codes(project_id: int, category: str, db: Session = Depends(get_db)):
    return code_master.resolve(db, project_id, category.upper())


# ---- components and data model depth (D-37, D-39, slice7_schema §5) ----
@router.get("/project-templates", response_model=list[TemplateOut], **_auth.route)
def list_templates(db: Session = Depends(get_db)):
    return components.templates(db)


@router.get("/project-components", response_model=list[ComponentOut], **_auth.route)
def component_catalogue(db: Session = Depends(get_db)):
    return components.catalogue(db)


@router.get("/projects/{project_id}/components", response_model=list[ComponentOut], **_reader.route)
def read_components(project_id: int, db: Session = Depends(get_db)):
    return components.describe(db, project_id)


@router.put("/projects/{project_id}/components", response_model=ComponentsChangeOut, **_platform.route)
def set_components(project_id: int, body: ComponentsIn, actor: AppUser = Depends(_auth.dep),
                   db: Session = Depends(get_db)):
    """Platform admin [Q-10]. Without confirm_hash: the preview. With it: applied, audited."""
    return components.set_components(db, actor, project_service.get_project(db, project_id),
                                     body.component_codes, body.confirm_hash)


@router.put("/projects/{project_id}/data-model-depth", response_model=ProjectOut, **_platform.route)
def set_depth(project_id: int, body: DepthIn, actor: AppUser = Depends(_auth.dep),
              db: Session = Depends(get_db)):
    return components.set_depth(db, actor, project_service.get_project(db, project_id),
                                body.data_model_depth, body.row_version)


# ---- the FTE basis and the volume summary (D-67, slice 13c): a platform admin sets the basis (Q-7, D-71 (6));
# everyone who sees the project reads the summary. A project setting, not a component write: no component=.
@router.put("/projects/{project_id}/fte-basis", response_model=FteBasisOut, **_platform.route)
def set_fte_basis(project_id: int, body: FteBasisIn, actor: AppUser = Depends(_auth.dep),
                  db: Session = Depends(get_db)):
    return process_volume.set_basis(db, actor.app_user_id, project_service.get_project(db, project_id),
                                    body.row_version, body.working_days_per_year, body.hours_per_working_day)


@router.get("/projects/{project_id}/volume-summary", response_model=VolumeSummaryOut, **_reader.route)
def volume_summary(project_id: int, db: Session = Depends(get_db)):
    return process_volume.summary(db, project_service.get_project(db, project_id))


# ---- the DFD rule (D-70; slice13_schema §2.5): everyone sees it, a platform admin changes it (Q-5, D-71 (6)).
# A project setting, not a component write: no component= (the rule only has effect where the chart's DFD is on).
@router.get("/projects/{project_id}/dfd-rule", response_model=DfdRuleOut, **_reader.route)
def read_dfd_rule(project_id: int, db: Session = Depends(get_db)):
    return dfd_rule.describe(db, project_service.get_project(db, project_id))


@router.post("/projects/{project_id}/dfd-rule/preview", response_model=DfdRulePreviewOut, **_platform.route)
def preview_dfd_rule(project_id: int, body: DfdRulePreviewIn, db: Session = Depends(get_db)):
    """No write: per chart, the lights under the proposed rule and what the next freeze would refuse."""
    return dfd_rule.preview(db, project_service.get_project(db, project_id), body.bfc_set_code, body.codes)


@router.put("/projects/{project_id}/dfd-rule", response_model=DfdRuleOut, **_platform.route)
def set_dfd_rule(project_id: int, body: DfdRuleIn, actor: AppUser = Depends(_auth.dep),
                 db: Session = Depends(get_db)):
    return dfd_rule.set_rule(db, actor, project_service.get_project(db, project_id), body.bfc_set_code,
                             body.codes, body.row_version, body.preview_digest)


# ---- access: who can open the project, members (project ADMIN), restriction (PLATFORM) (D-40, OR-6, D-71) ----
@router.get("/projects/{project_id}/access", response_model=EffectiveAccessOut, **_proj_admin.route)
def effective_access(project_id: int, db: Session = Depends(get_db)):
    return project_service.effective_access(db, project_service.get_project(db, project_id))


@router.get("/projects/{project_id}/members", response_model=list[MemberOut], **_proj_admin.route)
def list_members(project_id: int, db: Session = Depends(get_db)):
    return project_service.list_members(db, project_service.get_project(db, project_id))


@router.get("/projects/{project_id}/member-candidates", response_model=list[PersonOut], **_proj_admin.route)
def member_candidates(project_id: int, db: Session = Depends(get_db)):
    """Who a project admin may add — /users stays platform-admin only (D-71 (5))."""
    return project_service.member_candidates(db, project_service.get_project(db, project_id))


@router.post("/projects/{project_id}/members", response_model=MemberOut, status_code=201,
             **_proj_admin.route)
def add_member(project_id: int, body: MemberIn, actor: AppUser = Depends(_auth.dep),
               db: Session = Depends(get_db)):
    m = project_service.add_member(db, actor, project_service.get_project(db, project_id),
                                   body.user_id, body.access_level, body.member_note)
    return project_service._member_row(db, m)


@router.patch("/project-members/{id}", response_model=MemberOut, **_member_admin.route)
def change_member(id: int, body: MemberPatch, m: ProjectMember = Depends(_member_admin.dep),
                  actor: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    project_service.change_member_level(db, actor, m, body.access_level, body.row_version)
    return project_service._member_row(db, m)


@router.delete("/project-members/{id}", status_code=204, **_member_admin.route)
def remove_member(id: int, row_version: int, m: ProjectMember = Depends(_member_admin.dep),
                  actor: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    project_service.remove_member(db, actor, m, row_version)


@router.put("/projects/{project_id}/restriction", response_model=RestrictionOut, **_platform.route)
def set_restriction(project_id: int, body: RestrictionIn, actor: AppUser = Depends(_auth.dep),
                    db: Session = Depends(get_db)):
    """Preview (no hash) names who loses, gains and keeps access; confirm applies it (§8.3, DR7-D2)."""
    return project_service.set_restriction(db, actor, project_service.get_project(db, project_id),
                                           body.is_restricted, body.confirm_hash)


# ---- programs ----
@router.get("/programs", response_model=list[ProgramOut], **_auth.route)
def list_programs(user: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    return program_service.list_visible_programs(db, user)


@router.post("/programs", response_model=ProgramOut, status_code=201, **_admin.route)
def create_program(body: ProgramIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return program_service.create_program(db, actor, body.client_id, body.program_code,
                                          body.program_name, body.description)


@router.get("/programs/{program_id}", response_model=ProgramOut, **_prog_reader.route)
def read_program(program_id: int, db: Session = Depends(get_db)):
    return program_service.get_program(db, program_id)


@router.get("/programs/{program_id}/projects", response_model=list[ProjectOut], **_prog_reader.route)
def program_projects(program_id: int, user: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    return program_service.program_projects(db, user, program_id)


@router.post("/programs/{program_id}/projects", **_admin.route)
def add_project_to_program(program_id: int, body: ProgramMoveIn, actor: AppUser = Depends(_admin.dep),
                           db: Session = Depends(get_db)):
    return program_service.move_project_program(db, actor, body.project_id, program_id,
                                                body.confirm_hash)


@router.delete("/programs/{program_id}/projects/{project_id}", **_admin.route)
def remove_project_from_program(program_id: int, project_id: int, confirm_hash: str | None = None,
                                actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return program_service.move_project_program(db, actor, project_id, None, confirm_hash,
                                                expected_from_program_id=program_id)   # M1
