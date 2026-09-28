"""Acceptance criterion 49 (R2-S1): every route declares exactly one guard, and the guard fits
the path. Walks the RUNNING app's routes — there is no hand-kept list to forget."""
import pytest
from fastapi import Depends
from fastapi.routing import APIRoute

from routers.guards import GUARD_KEY, GuardedRouter, RouteDefinitionError

PUBLIC_ALLOWED = {("POST", "/auth/login"), ("GET", "/auth/setup"), ("POST", "/auth/setup")}


def _routes():
    from main import app
    return [r for r in app.routes if isinstance(r, APIRoute)]


def test_every_route_declares_a_guard():
    missing = [f"{sorted(r.methods)} {r.path}" for r in _routes()
               if GUARD_KEY not in (r.openapi_extra or {})]
    assert missing == []


def test_guards_fit_their_paths():
    bad = []
    for r in _routes():
        kind = r.openapi_extra[GUARD_KEY]["kind"]
        methods = r.methods
        if kind == "PUBLIC" and not all((m, r.path) in PUBLIC_ALLOWED for m in methods):
            bad.append(f"{r.path}: PUBLIC is for login and first-run setup only")
        if "{project_id}" in r.path and kind not in ("PROJECT_CTX", "PLATFORM_ADMIN"):
            bad.append(f"{r.path}: a {{project_id}} route must be PROJECT_CTX")
        if "{program_id}" in r.path and kind not in ("PROGRAM_CTX", "PLATFORM_ADMIN"):
            bad.append(f"{r.path}: a {{program_id}} route must be PROGRAM_CTX or PLATFORM_ADMIN")
        if "{id}" in r.path and kind not in ("OBJECT_GUARD", "PLATFORM_ADMIN"):
            bad.append(f"{r.path}: an {{id}} route must be OBJECT_GUARD or PLATFORM_ADMIN")
        if kind in ("PROJECT_CTX", "PROGRAM_CTX", "OBJECT_GUARD") and \
                not r.openapi_extra[GUARD_KEY]["min_role"]:
            bad.append(f"{r.path}: {kind} without a minimum role")
    assert bad == []


def test_unguarded_route_cannot_be_registered():
    router = GuardedRouter(prefix="/x")
    with pytest.raises(RouteDefinitionError):
        @router.get("/leak")
        def leak():
            return {}


def test_unguarded_route_via_add_api_route_is_refused():
    router = GuardedRouter()
    with pytest.raises(RouteDefinitionError):
        router.add_api_route("/leak", lambda: {}, methods=["GET"], dependencies=[Depends(lambda: 1)])
