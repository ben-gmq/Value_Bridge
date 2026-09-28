"""Platform administration: users and clients (§9). Every route is PLATFORM_ADMIN."""
from fastapi import Depends
from sqlalchemy.orm import Session

from database import get_db
from models import AppUser
from routers.guards import GuardedRouter, platform_admin
from schemas.common import ClientIn, ClientOut, UserIn, UserOut
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
                                  body.is_platform_admin)


@router.patch("/users/{id}/deactivate", response_model=UserOut, **_admin.route)
def deactivate_user(id: int, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return user_admin.deactivate_user(db, actor, id)


@router.get("/clients", response_model=list[ClientOut], **_admin.route)
def list_clients(db: Session = Depends(get_db)):
    return project_service.list_clients(db)


@router.post("/clients", response_model=ClientOut, status_code=201, **_admin.route)
def create_client(body: ClientIn, actor: AppUser = Depends(_admin.dep), db: Session = Depends(get_db)):
    return project_service.create_client(db, actor, body.client_code, body.client_name, body.industry)
