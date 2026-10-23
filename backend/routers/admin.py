"""Platform administration: users and clients (§9). Every route is PLATFORM_ADMIN."""
from fastapi import Depends
from sqlalchemy.orm import Session

from database import get_db
from models import AppUser
from routers.guards import GuardedRouter, platform_admin
from schemas.common import (AccessChangeIn, AccessChangePreviewOut, ClientIn, ClientOut, PlatformAdminIn, UserIn,
                            UserKindIn, UserOut)
from schemas.admin_grant import GrantDecideIn, GrantRejectIn, GrantRequestIn
from services import admin_grant
from services import project as project_service
from services import user_admin

router = GuardedRouter(tags=["admin"])
_admin = platform_admin()


@router.get("/users", response_model=list[UserOut], **_admin.route)
def list_users(db: Session = Depends(get_db)):
    return user_admin.list_users(db)


@router.post("/users", response_model=UserOut, status_code=201, **_admin.route)
def create_user(body: UserIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return user_admin.create_user(db, actor, body.email, body.display_name, body.initial_password,
                                  body.user_kind)


@router.post("/users/{id}/access-change-preview", response_model=AccessChangePreviewOut, **_admin.route)
def access_change_preview(id: int, body: AccessChangeIn, db: Session = Depends(get_db)):
    """No write: the memberships a change of kind or admin flag brings back into force, and the hash to confirm."""
    return user_admin.access_change_preview(db, id, body.user_kind, body.is_platform_admin)


@router.patch("/users/{id}/kind", response_model=UserOut, **_admin.route)
def set_user_kind(id: int, body: UserKindIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return user_admin.set_user_kind(db, actor, id, body.user_kind, body.row_version, body.confirm_hash)


@router.patch("/users/{id}/platform-admin", response_model=UserOut, **_admin.route)
def set_platform_admin(id: int, body: PlatformAdminIn, actor: AppUser = Depends(_admin.dep),
                       db: Session = Depends(get_db)):
    return user_admin.set_platform_admin(db, actor, id, body.is_platform_admin, body.rationale,
                                         body.row_version, body.user_kind, body.confirm_hash)


@router.get("/admin/grant-requests", **_admin.route)
def list_grant_requests(db: Session = Depends(get_db)):
    """Slice 17: every request for platform-admin rights, open first."""
    return admin_grant.list_requests(db)


@router.post("/users/{id}/grant-requests", status_code=201, **_admin.route)
def request_grant(id: int, body: GrantRequestIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return admin_grant.rows(db, [admin_grant.request(db, actor, id, body.reason)])[0]


@router.post("/grant-requests/{id}/approve", **_admin.route)
def approve_grant(id: int, body: GrantDecideIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return admin_grant.rows(db, [admin_grant.approve(db, actor, id, body.row_version)])[0]


@router.post("/grant-requests/{id}/reject", **_admin.route)
def reject_grant(id: int, body: GrantRejectIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return admin_grant.rows(db, [admin_grant.reject(db, actor, id, body.reason, body.row_version)])[0]


@router.post("/grant-requests/{id}/cancel", **_admin.route)
def cancel_grant(id: int, body: GrantDecideIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return admin_grant.rows(db, [admin_grant.cancel(db, actor, id, body.row_version)])[0]


@router.patch("/users/{id}/deactivate", response_model=UserOut, **_admin.route)
def deactivate_user(id: int, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return user_admin.deactivate_user(db, actor, id)


@router.get("/clients", response_model=list[ClientOut], **_admin.route)
def list_clients(db: Session = Depends(get_db)):
    return project_service.list_clients(db)


@router.post("/clients", response_model=ClientOut, status_code=201, **_admin.route)
def create_client(body: ClientIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return project_service.create_client(db, actor, body.client_code, body.client_name, body.industry)
