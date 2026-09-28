"""/auth — at the root, not under /api/v1 (FTC-PC landmine 6: the frontend depends on it)."""
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from database import get_db
from models import AppUser
from routers.guards import GuardedRouter, authenticated, public
from schemas.common import GrantOut, LoginIn, MeOut, SetupIn, TokenOut, UserOut
from services import access, auth_service

router = GuardedRouter(prefix="/auth", tags=["auth"])
_public = public()
_auth = authenticated()


@router.post("/login", response_model=TokenOut, **_public.route)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    token, user = auth_service.login(db, body.email, body.password, body.remember_me, ip)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/setup", **_public.route)
def setup_status(db: Session = Depends(get_db)):
    return {"setup_required": auth_service.setup_required(db)}


@router.post("/setup", response_model=UserOut, status_code=201, **_public.route)
def setup(body: SetupIn, db: Session = Depends(get_db)):
    return auth_service.first_run_setup(db, body.email, body.display_name, body.password)


@router.get("/me", response_model=MeOut, **_auth.route)
def me(user: AppUser = Depends(_auth.dep), db: Session = Depends(get_db)):
    if user.is_platform_admin:
        return MeOut(user=UserOut.model_validate(user), grant=None, role=None, scope="PLATFORM_ADMIN")
    g = access.live_grant(db, user)
    if g is None:
        return MeOut(user=UserOut.model_validate(user), grant=None, role=None, scope="NONE")
    return MeOut(user=UserOut.model_validate(user), grant=GrantOut.model_validate(g),
                 role=access.grant_role(db, g), scope="PROJECT" if g.project_id else "PROGRAM")
