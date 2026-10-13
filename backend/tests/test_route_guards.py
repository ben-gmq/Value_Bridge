"""Acceptance criterion 49 (R2-S1, sara H2): every route declares exactly one guard, the guard
is really attached, and it fits the path. Walks the RUNNING app — no hand-kept list."""
import re

import pytest
from fastapi import Depends
from fastapi.routing import APIRoute

from routers.guards import GUARD_DEPS, GUARD_KEY, GuardedRouter, RouteDefinitionError

PUBLIC_ALLOWED = {("POST", "/auth/login"), ("GET", "/auth/setup"), ("POST", "/auth/setup")}
# §9 lists these admin-only routes although they carry {project_id}. Named one by one, so
# a new {project_id} route can never quietly skip PROJECT_CTX.
PROJECT_ID_ADMIN_ALLOWED = {("DELETE", "/api/v1/programs/{program_id}/projects/{project_id}")}
ID_PARAM = re.compile(r"\{(\w*id)\}")


def _routes():
    from main import app
    return [r for r in app.routes if isinstance(r, APIRoute)]


def test_every_route_declares_a_guard():
    missing = [f"{sorted(r.methods)} {r.path}" for r in _routes()
               if GUARD_KEY not in (r.openapi_extra or {})]
    assert missing == []


def test_declared_guard_is_really_attached():
    bad = []
    for r in _routes():
        kind = r.openapi_extra[GUARD_KEY]["kind"]
        attached = [GUARD_DEPS.get(id(d.dependency)) for d in r.dependencies]
        if [k for k in attached if k is not None] != [kind] and \
                [k.value for k in attached if k is not None] != [kind]:
            bad.append(f"{sorted(r.methods)} {r.path}: marker {kind}, attached {attached}")
    assert bad == []


def test_guards_fit_their_paths():
    bad = []
    for r in _routes():
        kind = r.openapi_extra[GUARD_KEY]["kind"]
        for m in r.methods:
            params = set(ID_PARAM.findall(r.path))
            if kind == "PUBLIC" and (m, r.path) not in PUBLIC_ALLOWED:
                bad.append(f"{m} {r.path}: PUBLIC is for login and first-run setup only")
            if "project_id" in params and kind != "PROJECT_CTX" \
                    and (m, r.path) not in PROJECT_ID_ADMIN_ALLOWED:
                bad.append(f"{m} {r.path}: a {{project_id}} route must be PROJECT_CTX")
            if "program_id" in params and "project_id" not in params and \
                    kind not in ("PROGRAM_CTX", "PLATFORM_ADMIN"):
                bad.append(f"{m} {r.path}: a {{program_id}} route must be PROGRAM_CTX or PLATFORM_ADMIN")
            others = params - {"project_id", "program_id"}
            if others and kind not in ("OBJECT_GUARD", "PROGRAM_CTX", "PLATFORM_ADMIN"):
                bad.append(f"{m} {r.path}: an object-id route ({others}) must be OBJECT_GUARD")
        if kind in ("PROJECT_CTX", "PROGRAM_CTX", "OBJECT_GUARD") and \
                not r.openapi_extra[GUARD_KEY]["min_level"]:
            bad.append(f"{r.path}: {kind} without a minimum level")
        # sara 7b M3: a write is never guarded at VIEW — a viewer can reach no write, by structure
        if kind in ("PROJECT_CTX", "PROGRAM_CTX", "OBJECT_GUARD") and not r.methods <= {"GET", "HEAD"} \
                and r.openapi_extra[GUARD_KEY]["min_level"] not in ("EDIT", "ADMIN"):
            bad.append(f"{sorted(r.methods)} {r.path}: a write guarded at "
                       f"{r.openapi_extra[GUARD_KEY]['min_level']}")
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


def test_spoofed_marker_without_the_dependency_is_caught(monkeypatch):
    """A route that copies the marker but not the Depends must fail the attached-guard test."""
    from main import app
    from routers.guards import GUARD_KEY as K
    router = GuardedRouter()
    router.add_api_route("/spoof/{project_id}", lambda project_id: {}, methods=["GET"],
                         openapi_extra={K: {"kind": "PROJECT_CTX", "min_level": "VIEW", "model": None}})
    spoof = [r for r in router.routes if isinstance(r, APIRoute)][0]
    attached = [GUARD_DEPS.get(id(d.dependency)) for d in spoof.dependencies]
    assert all(a is None for a in attached)   # nothing real is attached → the check above fails it
    assert app is not None


# ---- criterion 49b (D-37, slice7_schema §5.2): every write declares the component it needs -----
# A path fragment → the component every non-GET route containing it must name in its marker.
# A forgotten declaration fails here, as a forgotten guard fails criterion 49.
ROUTE_COMPONENTS = (
    ("/solutions", "SOLUTION"),
    ("/function-requirements", "FUNCTION_REQUIREMENT"),
    ("/business-requirements/{id}/function-requirements", "FUNCTION_REQUIREMENT"),   # D-52 link writes (Q-11)
    ("/applications", "APPLICATION"),
    ("/rate-card", "EFFORT"),
    ("/complexity", "EFFORT"),
    ("/interface", "APPLICATION"),
    ("/bfc-nodes/{id}/applications", "AS_IS"),
    ("/copy-from/", "AS_IS"),
)
# 7c (DR7-D1): these depend on the node's chart, so they must declare the DFD resolver. The performer
# declares only its chart's own resolver, whatever the DFD setting (S10c-2, Ben 2026-10-14).
ROUTE_RESOLVERS = (("/external-flows", "<node_dfd_component>"), ("/performer", "<node_set_component>"),
                   ("/bfc-nodes/{id}/triggers", "<node_dfd_component>"))


def test_every_component_write_declares_its_component():
    bad = []
    for r in _routes():
        if r.methods <= {"GET", "HEAD"}:
            continue
        declared = r.openapi_extra[GUARD_KEY].get("component")
        declared = set(declared) if isinstance(declared, list) else {declared} if declared else set()
        for fragment, code in ROUTE_COMPONENTS:
            if fragment in r.path and code not in declared:
                bad.append(f"{sorted(r.methods)} {r.path}: needs {code}, declares {sorted(declared)}")
        for fragment, resolver in ROUTE_RESOLVERS:
            if fragment in r.path and resolver not in declared:
                bad.append(f"{sorted(r.methods)} {r.path}: needs {resolver}, declares {sorted(declared)}")
    assert bad == []


def test_the_performer_write_is_not_gated_by_the_dfd():
    """S10c-2 (Ben 2026-10-14): the performer is recorded whatever the DFD setting; trigger links stay with it."""
    for r in _routes():
        if r.methods <= {"GET", "HEAD"}:
            continue
        declared = r.openapi_extra[GUARD_KEY].get("component")
        declared = set(declared) if isinstance(declared, list) else {declared} if declared else set()
        if r.path.endswith("/performer"):
            assert declared == {"<node_set_component>"}, (r.path, declared)
        if "/bfc-nodes/{id}/triggers" in r.path:
            assert declared == {"<node_dfd_component>"}, (r.path, declared)


def test_br_fr_link_writes_do_not_need_solution():
    """slice10b Q-11: the link is FR scope, so a project with SOLUTION off can map BR → FR. The tag route
    checks SOLUTION in the body only when a solution is set."""
    found = 0
    for r in _routes():
        if "/business-requirements/{id}/function-requirements" in r.path and not r.methods <= {"GET", "HEAD"}:
            declared = r.openapi_extra[GUARD_KEY].get("component")
            declared = set(declared) if isinstance(declared, list) else {declared} if declared else set()
            assert declared == {"FUNCTION_REQUIREMENT"}, (r.path, declared)
            found += 1
    assert found == 4
