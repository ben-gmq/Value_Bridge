"""Code-list maintenance (wave 1g; docs/slice1g_spec.md §9). HTTP in and out only: services/code_lists owns the rules.

A project's lists: project ADMIN (G-5, D-71) — a project member at Admin or a platform admin. The company library:
platform admins. A code_master row's own routes take the tier of the row: a company row is platform-admin only (404 to
anyone else, R9), a project row needs that project's ADMIN. Writes skip the guard's share lock because the service takes
the project row FOR UPDATE first (N3)."""
from fastapi import Depends
from sqlalchemy.orm import Session

from database import get_db
from models import AppUser, CodeMaster
from routers.guards import GuardedRouter, authenticated, object_guard, platform_admin, project_ctx
from schemas.common import CodeAddIn, CodeHideIn, CodeListOut, CodeOut, CodePatch
from services import code_lists
from services import project as project_service

router = GuardedRouter(tags=["code-lists"])
_auth = authenticated()
_admin = platform_admin()
_reader = project_ctx("VIEW")
_proj_admin = project_ctx("ADMIN", share_lock=False)
_code_row = object_guard(CodeMaster, "ADMIN", id_param="code_id", share_lock=False)


@router.get("/projects/{project_id}/code-lists", response_model=list[CodeListOut], **_reader.route)
def project_lists(project_id: int, db: Session = Depends(get_db)):
    return code_lists.list_for_project(db, project_service.get_project(db, project_id))


@router.post("/projects/{project_id}/code-lists/hidden", status_code=201, **_proj_admin.route)
def hide(project_id: int, body: CodeHideIn, actor: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    v = code_lists.hide(db, actor, project_service.get_project(db, project_id), body.code_id)
    return {"project_code_visibility_id": v.project_code_visibility_id, "code_id": v.code_id}


@router.delete("/projects/{project_id}/code-lists/hidden", status_code=204, **_proj_admin.route)
def unhide(project_id: int, code_id: int, actor: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    code_lists.unhide(db, actor, project_service.get_project(db, project_id), code_id)


@router.post("/projects/{project_id}/code-lists/{category}", response_model=CodeOut, status_code=201,
             **_proj_admin.route)
def add_project_code(project_id: int, category: str, body: CodeAddIn, actor: AppUser = Depends(_auth.dep),
                     db: Session = Depends(get_db)):
    return code_lists.add_project_code(db, actor, project_service.get_project(db, project_id), category.upper(),
                                       body.code, body.label, body.behaviour_code, body.sort_order)


@router.get("/code-lists", response_model=list[CodeListOut], **_admin.route)
def company_lists(db: Session = Depends(get_db)):
    return code_lists.list_company(db)


@router.post("/code-lists/{category}", response_model=CodeOut, status_code=201, **_admin.route)
def add_company_code(category: str, body: CodeAddIn, actor: AppUser = Depends(_admin.dep),
                     db: Session = Depends(get_db)):
    return code_lists.add_company_code(db, actor, category.upper(), body.code, body.label, body.behaviour_code,
                                       body.sort_order)


@router.patch("/code-master/{code_id}", response_model=CodeOut, **_code_row.route)
def change_code(code_id: int, body: CodePatch, row: CodeMaster = Depends(_code_row.dep),
                actor: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    return code_lists.update_code(db, actor, row, body.row_version, body.label, body.sort_order, body.behaviour_code)


@router.delete("/code-master/{code_id}", status_code=204, **_code_row.route)
def retire_code(code_id: int, row_version: int, row: CodeMaster = Depends(_code_row.dep),
                actor: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    code_lists.retire_code(db, actor, row, row_version)


@router.patch("/code-master/{code_id}/restore", response_model=CodeOut, **_code_row.route)
def restore_code(code_id: int, body: CodePatch, row: CodeMaster = Depends(_code_row.dep),
                 actor: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    return code_lists.restore_code(db, actor, row, body.row_version)
