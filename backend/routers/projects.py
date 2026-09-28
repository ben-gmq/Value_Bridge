"""Projects, programs, access and code lookups (§9, D-32)."""
from fastapi import Depends
from sqlalchemy.orm import Session

from database import get_db
from models import AppUser, UserAccessGrant
from routers.guards import (GuardedRouter, authenticated, object_guard, platform_admin,
                            program_ctx, project_ctx)
from schemas.common import (CodeOut, EffectiveAccessOut, GrantIn, GrantOut, ProgramIn,
                            ProgramMoveIn, ProgramOut, ProjectIn, ProjectOut, ProjectPatch,
                            ReassignIn)
from services import code_master
from services import program as program_service
from services import project as project_service

router = GuardedRouter(tags=["projects"])
_auth = authenticated()
_admin = platform_admin()
_reader = project_ctx("REVIEWER")
_owner = project_ctx("OWNER")
_prog_reader = program_ctx("REVIEWER")
_revoker = object_guard(UserAccessGrant, "OWNER")


# ---- projects ----
@router.get("/projects", response_model=list[ProjectOut], **_auth.route)
def list_projects(user: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    return project_service.list_visible_projects(db, user)


@router.post("/projects", response_model=ProjectOut, status_code=201, **_admin.route)
def create_project(body: ProjectIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return project_service.create_project(db, actor, body.client_id, body.project_code,
                                          body.project_name, body.program_id, body.start_date,
                                          body.end_date)


@router.get("/projects/{project_id}", response_model=ProjectOut, **_reader.route)
def read_project(project_id: int, db: Session = Depends(get_db)):
    return project_service.get_project(db, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut, **_owner.route)
def update_project(project_id: int, body: ProjectPatch, db: Session = Depends(get_db),
                   user: AppUser = Depends(_auth.dep)):
    fields = body.model_dump(exclude_unset=True, exclude={"row_version"})
    return project_service.update_project(db, user, project_service.get_project(db, project_id),
                                          body.row_version, fields)


@router.get("/projects/{project_id}/code-master/{category}", response_model=list[CodeOut],
            **_reader.route)
def project_codes(project_id: int, category: str, db: Session = Depends(get_db)):
    return code_master.resolve(db, project_id, category.upper())


# ---- access ----
@router.get("/projects/{project_id}/access", response_model=list[EffectiveAccessOut], **_owner.route)
def effective_access(project_id: int, db: Session = Depends(get_db)):
    return project_service.effective_access(db, project_service.get_project(db, project_id))


@router.post("/projects/{project_id}/access", response_model=GrantOut, status_code=201,
             **_owner.route)
def grant_project(project_id: int, body: GrantIn, actor: AppUser = Depends(_auth.dep),
                  db: Session = Depends(get_db)):
    return project_service.grant_access(db, actor, body.user_id, body.project_role_code,
                                        project_id=project_id, row_version=body.row_version)


@router.delete("/access/{id}", response_model=GrantOut, **_revoker.route)
def revoke(id: int, grant: UserAccessGrant = Depends(_revoker.dep),
           actor: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    return project_service.revoke_access(db, actor, grant)


@router.post("/access/reassign", response_model=GrantOut, **_admin.route)
def reassign(body: ReassignIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return project_service.reassign_access(db, actor, body.user_id, body.project_role_code,
                                           body.rationale, project_id=body.project_id,
                                           program_id=body.program_id)


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


@router.post("/programs/{program_id}/access", response_model=GrantOut, status_code=201,
             **_admin.route)
def grant_program(program_id: int, body: GrantIn, actor: AppUser = Depends(_admin.dep),
                  db: Session = Depends(get_db)):
    return project_service.grant_access(db, actor, body.user_id, body.project_role_code,
                                        program_id=program_id, row_version=body.row_version)
