"""THE GUARD REGISTRY (§7.8, R2-S1). Every route declares exactly one guard.

Usage:
    router = GuardedRouter(prefix="/projects")
    g = project_ctx("REVIEWER")
    @router.get("/{project_id}", **g.route)
    def read(project_id: int, grant=Depends(g.dep)): ...

A route registered without `**guard.route` raises RouteDefinitionError at import time, and
acceptance criterion 49 (tests/test_route_guards.py) re-proves it over the running app.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser
from services import access

GUARD_KEY = "x-vb-guard"
# Every guard dependency ever built, by identity → its kind. Criterion 49 checks that each
# route's declared kind is backed by an attached dependency of the same kind — a hand-written
# openapi_extra marker without the real Depends cannot pass (sara H2d).
GUARD_DEPS: dict[int, "Guard"] = {}


class Guard(str, Enum):
    PUBLIC = "PUBLIC"                  # no JWT — login and first-run setup only
    AUTHENTICATED = "AUTHENTICATED"    # JWT only; the service filters what is returned
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    PROJECT_CTX = "PROJECT_CTX"        # /…/{project_id}/… → require_project
    OBJECT_GUARD = "OBJECT_GUARD"      # /<things>/{id} → resolve owning project, then guard
    PROGRAM_CTX = "PROGRAM_CTX"        # /programs/{program_id}/… → require_program


class RouteDefinitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class GuardSpec:
    kind: Guard
    dep: Callable[..., Any]
    min_role: str | None = None
    model: type | None = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        GUARD_DEPS[id(self.dep)] = self.kind

    @property
    def route(self) -> dict:
        """kwargs for the route decorator: the dependency plus the guard marker."""
        return {"dependencies": [Depends(self.dep)],
                "openapi_extra": {GUARD_KEY: {"kind": self.kind.value, "min_role": self.min_role,
                                              "model": self.model.__name__ if self.model else None}}}


class GuardedRouter(APIRouter):
    """The only router type the app uses. Refuses any route without a guard marker."""

    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        extra = kwargs.get("openapi_extra") or {}
        if GUARD_KEY not in extra:
            methods = ",".join(sorted(kwargs.get("methods") or []))
            raise RouteDefinitionError(f"{methods} {self.prefix}{path} declares no guard")
        super().add_api_route(path, endpoint, **kwargs)


# ---- the six guards -------------------------------------------------------------------

def _public() -> None:
    return None


def public() -> GuardSpec:
    return GuardSpec(Guard.PUBLIC, _public)


def authenticated() -> GuardSpec:
    def dep(user: AppUser = Depends(current_user)) -> AppUser:
        return user
    return GuardSpec(Guard.AUTHENTICATED, dep)


def platform_admin() -> GuardSpec:
    def dep(user: AppUser = Depends(current_user)) -> AppUser:
        if not user.is_platform_admin:          # re-read from the row every request (S4)
            raise HTTPException(403, "Platform administrators only")
        return user
    return GuardSpec(Guard.PLATFORM_ADMIN, dep)


def project_ctx(min_role: str) -> GuardSpec:
    def dep(project_id: int, user: AppUser = Depends(current_user),
            db: Session = Depends(get_db)) -> access.EffectiveGrant:
        return access.require_project(db, user, project_id, min_role)
    return GuardSpec(Guard.PROJECT_CTX, dep, min_role)


def program_ctx(min_role: str) -> GuardSpec:
    def dep(program_id: int, user: AppUser = Depends(current_user),
            db: Session = Depends(get_db)) -> access.EffectiveGrant:
        return access.require_program(db, user, program_id, min_role)
    return GuardSpec(Guard.PROGRAM_CTX, dep, min_role)


def object_guard(model: type, min_role: str, id_param: str = "id") -> GuardSpec:
    """For routes carrying an object id and no project (finding S3). The owning project is
    resolved from the object before anything is returned. `model` must implement
    owning_project_id(); an object that resolves to no project is platform-admin only."""
    if not hasattr(model, "owning_project_id"):
        raise RouteDefinitionError(f"{model.__name__} has no owning_project_id()")

    def dep(request: Request, user: AppUser = Depends(current_user),
            db: Session = Depends(get_db)):
        raw = request.path_params.get(id_param)
        obj = db.get(model, int(raw)) if raw and str(raw).isdigit() else None
        if obj is None:
            raise HTTPException(404, access.NOT_FOUND)
        owner = obj.owning_project_id()
        if owner is None:
            if not user.is_platform_admin:
                raise HTTPException(404, access.NOT_FOUND)
        else:
            access.require_project(db, user, owner, min_role)
        return obj
    return GuardSpec(Guard.OBJECT_GUARD, dep, min_role, model)
