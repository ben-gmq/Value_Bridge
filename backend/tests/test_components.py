"""Slice 7a: project components and data model depth (D-37, D-39, OR-1…OR-3; slice7_schema §1–§5).

Grade 1 for the guard (a write to a component that is off must never land), so the refusal is
asserted on every route family and its order against 404 and 403 is pinned."""
from sqlalchemy import select

from models import AuditEvent
from tests.conftest import ALL_COMPONENTS, login, restrict
from tests.test_erd_api import erd, field, pk
from tests.test_scope_api import API, ed, entity  # noqa: F401 — ed is a fixture


def new_project(client, w, code, components, template=None, depth=None, expect=201):
    body = {"client_id": w["client_id"], "project_code": code, "project_name": code,
            "component_codes": components, "is_restricted": False}
    if template:
        body["template_code"] = template
    if depth:
        body["data_model_depth"] = depth
    r = client.post(f"{API}/projects", headers=w["admin"], json=body)
    assert r.status_code == expect, r.text
    return r.json()


def editor_on(client, w, project_id, user="editor"):
    """D-40: a USER edits every unrestricted project; nothing to grant."""
    return login(client, f"{user}@example.test")


def comps(client, headers, project_id):
    return {c["code"]: c for c in client.get(f"{API}/projects/{project_id}/components",
                                            headers=headers).json()}


def put_components(client, w, project_id, codes, confirm=None):
    return client.put(f"{API}/projects/{project_id}/components", headers=w["admin"],
                      json={"component_codes": codes, "confirm_hash": confirm})


def switch(client, w, project_id, codes):
    preview = put_components(client, w, project_id, codes)
    assert preview.status_code == 200, preview.text
    return put_components(client, w, project_id, codes, preview.json()["confirm_hash"])


# ---- templates and creation -------------------------------------------------------------------
def test_three_templates_with_their_components(client, world):
    t = {x["code"]: x["components"] for x in client.get(f"{API}/project-templates", headers=world["admin"]).json()}
    assert t["REQUIREMENTS_ONLY"] == ["ISSUE"]
    assert t["DATA_AND_PROCESS"] == sorted(["TO_BE_DFD", "AS_IS", "APPLICATION", "ISSUE"])
    assert "AS_IS" not in t["FULL_DELIVERY"] and "EFFORT" in t["FULL_DELIVERY"]


def test_the_catalogue_lists_every_component_with_its_needs(client, world):
    cat = {c["code"]: c for c in client.get(f"{API}/project-components", headers=world["admin"]).json()}
    assert set(cat) == set(ALL_COMPONENTS)
    assert cat["CHANGE_REQUEST"]["requires"] == ["EFFORT"] and cat["WBS"]["available"] is False


def test_create_refuses_a_set_missing_a_dependency_and_names_it(client, world):
    r = new_project(client, world, "BAD", ["EFFORT"], expect=422)
    assert "Function requirements" in r["detail"]
    r = new_project(client, world, "BAD2", ["CHANGE_REQUEST", "EFFORT"], expect=422)
    assert "Function requirements" in r["detail"]
    new_project(client, world, "BAD3", ["NOPE"], expect=400)
    new_project(client, world, "BAD4", ["ISSUE"], template="NOPE", expect=400)


def test_create_stores_components_depth_and_audits_the_template(client, world, db):
    p = new_project(client, world, "REQ", ["ISSUE"], template="REQUIREMENTS_ONLY", depth="KEYS_ONLY")
    assert p["data_model_depth"] == "KEYS_ONLY"
    c = comps(client, world["admin"], p["project_id"])
    assert {k for k, v in c.items() if v["enabled"]} == {"ISSUE"}
    assert c["EFFORT"]["requires"] == ["FUNCTION_REQUIREMENT"]
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PROJECT_CREATED",
                                             AuditEvent.project_id == p["project_id"])).one()
    assert ev.detail["template_code"] == "REQUIREMENTS_ONLY" and ev.detail["components"] == ["ISSUE"]
    assert ev.detail["data_model_depth"] == "KEYS_ONLY"


# ---- the guard ------------------------------------------------------------------------------
def test_writes_to_an_off_component_are_409_and_reads_still_work(client, world):
    p = new_project(client, world, "REQ", ["ISSUE"])["project_id"]
    h = editor_on(client, world, p)
    for path, body in ((f"/projects/{p}/solutions", {"solution_name": "S", "category_code": "PROCESS"}),
                       (f"/projects/{p}/function-requirements", {"fr_name": "F", "fr_type_code": "FORM"}),
                       (f"/projects/{p}/applications", {"application_code": "SAP", "application_name": "SAP",
                                                        "lifecycle_code": "AS_IS"})):
        r = client.post(f"{API}{path}", headers=h, json=body)
        assert r.status_code == 409, (path, r.text)
        assert r.headers["X-VB-Error"] == "COMPONENT_OFF"
    r = client.put(f"{API}/projects/{p}/rate-card", headers=h, json={"change_rationale": "x", "cells": []})
    assert r.status_code == 409 and r.headers["X-VB-Error"] == "COMPONENT_OFF"
    for path in ("solutions", "function-requirements", "applications", "rate-card"):
        assert client.get(f"{API}/projects/{p}/{path}", headers=h).status_code == 200, path
    # the always-on core still writes: the chart and data entities are never a component
    assert client.post(f"{API}/projects/{p}/bfc-nodes", headers=h,
                       json={"node_name": "Sales", "parent_bfc_node_id": None}).status_code == 201
    assert client.post(f"{API}/projects/{p}/data-entities", headers=h, json={"de_name": "Order"}).status_code == 201


def test_admins_are_refused_too_and_the_order_is_404_then_403_then_409(client, world):
    p = new_project(client, world, "REQ", ["ISSUE"])["project_id"]
    body = {"solution_name": "S", "category_code": "PROCESS"}
    r = client.post(f"{API}/projects/{p}/solutions", headers=world["admin"], json=body)
    assert r.status_code == 409                                         # Q-20: admins gated too
    restrict(client, world["admin"], p, {world["users"]["reviewer"]: "VIEW"})
    out = login(client, "outsider@example.test")
    assert client.post(f"{API}/projects/{p}/solutions", headers=out, json=body).status_code == 404
    rv = login(client, "reviewer@example.test")
    assert client.post(f"{API}/projects/{p}/solutions", headers=rv, json=body).status_code == 403


def test_linking_an_fr_to_a_solution_needs_solutions_on(client, world):
    p = new_project(client, world, "FRS", ["FUNCTION_REQUIREMENT"])["project_id"]
    h = editor_on(client, world, p)
    r = client.post(f"{API}/projects/{p}/function-requirements", headers=h,
                    json={"fr_name": "F", "fr_type_code": "FORM"})
    assert r.status_code == 201, r.text
    r = client.post(f"{API}/projects/{p}/function-requirements", headers=h,
                    json={"fr_name": "G", "fr_type_code": "FORM", "solution_id": 1})
    assert r.status_code == 409 and r.headers["X-VB-Error"] == "COMPONENT_OFF"


# ---- switching ------------------------------------------------------------------------------
def test_switch_on_previews_adds_dependencies_then_applies_and_audits(client, world, db):
    p = new_project(client, world, "REQ", ["ISSUE"])["project_id"]
    prev = put_components(client, world, p, ["ISSUE", "EFFORT"]).json()
    assert prev["applied"] is False and prev["turn_on"] == ["EFFORT", "FUNCTION_REQUIREMENT"]
    assert prev["added_by_dependency"] == ["FUNCTION_REQUIREMENT"] and prev["blockers"] == []
    assert comps(client, world["admin"], p)["EFFORT"]["enabled"] is False      # nothing written
    r = put_components(client, world, p, ["ISSUE", "EFFORT"], prev["confirm_hash"])
    assert r.status_code == 200 and r.json()["applied"] is True
    assert comps(client, world["admin"], p)["FUNCTION_REQUIREMENT"]["enabled"] is True
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PROJECT_COMPONENTS_CHANGED")).one()
    assert ev.detail["on"] == ["EFFORT", "FUNCTION_REQUIREMENT"] and ev.detail["off"] == []


def test_switch_off_is_refused_while_live_rows_exist_and_restores_the_same_row(client, world):
    p = new_project(client, world, "S", ["SOLUTION", "ISSUE"])["project_id"]
    h = editor_on(client, world, p)
    s = client.post(f"{API}/projects/{p}/solutions", headers=h,
                    json={"solution_name": "Credit check", "category_code": "PROCESS"}).json()
    prev = put_components(client, world, p, ["ISSUE"]).json()
    [b] = prev["blockers"]
    assert b["reason"] == "LIVE_ROWS" and b["count"] == 1 and b["sample"] == [s["solution_number"]]
    r = put_components(client, world, p, ["ISSUE"], prev["confirm_hash"])
    assert r.status_code == 409 and s["solution_number"] in r.json()["detail"]
    assert client.delete(f"{API}/solutions/{s['solution_id']}", headers=h,
                         params={"row_version": s["row_version"]}).status_code == 204
    assert switch(client, world, p, ["ISSUE"]).json()["turn_off"] == ["SOLUTION"]
    # the retired solution cannot be restored while Solutions is off
    r = client.patch(f"{API}/solutions/{s['solution_id']}/restore", headers=h)
    assert r.status_code == 409 and r.headers["X-VB-Error"] == "COMPONENT_OFF"
    assert switch(client, world, p, ["ISSUE", "SOLUTION"]).json()["turn_on"] == ["SOLUTION"]
    assert comps(client, world["admin"], p)["SOLUTION"]["enabled"] is True


def test_switch_off_is_refused_while_an_enabled_component_needs_it(client, world, db):
    """OR-2, sara M2: asking to drop FR while Effort stays is refused with the reason, never kept
    on silently; dropping both is allowed."""
    p = new_project(client, world, "E", ["FUNCTION_REQUIREMENT", "EFFORT"])["project_id"]
    prev = put_components(client, world, p, ["EFFORT"]).json()
    [b] = prev["blockers"]
    assert b["reason"] == "NEEDED_BY" and b["component"] == "FUNCTION_REQUIREMENT" and b["by"] == ["EFFORT"]
    r = put_components(client, world, p, ["EFFORT"], prev["confirm_hash"])
    assert r.status_code == 409 and "Effort & rate card needs Function requirements" in r.json()["detail"]
    prev = put_components(client, world, p, []).json()
    assert sorted(prev["turn_off"]) == ["EFFORT", "FUNCTION_REQUIREMENT"] and prev["blockers"] == []


def test_a_confirm_that_changes_nothing_writes_no_audit(client, world, db):
    p = new_project(client, world, "N", ["ISSUE"])["project_id"]
    prev = put_components(client, world, p, ["ISSUE"]).json()
    r = put_components(client, world, p, ["ISSUE"], prev["confirm_hash"]).json()
    assert r["applied"] is False
    assert db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PROJECT_COMPONENTS_CHANGED")).all() == []


def test_a_preview_that_went_stale_is_refused(client, world):
    p = new_project(client, world, "S", ["SOLUTION"])["project_id"]
    h = editor_on(client, world, p)
    prev = put_components(client, world, p, []).json()
    assert prev["blockers"] == []
    client.post(f"{API}/projects/{p}/solutions", headers=h, json={"solution_name": "x", "category_code": "PROCESS"})
    r = put_components(client, world, p, [], prev["confirm_hash"])
    assert r.status_code == 409 and "changed since the preview" in r.json()["detail"]


def test_only_a_platform_admin_switches_components_or_depth(client, world):
    p = new_project(client, world, "S", ALL_COMPONENTS)
    pid = p["project_id"]
    h = editor_on(client, world, pid)
    assert client.put(f"{API}/projects/{pid}/components", headers=h,
                      json={"component_codes": []}).status_code == 403
    assert client.put(f"{API}/projects/{pid}/data-model-depth", headers=h,
                      json={"row_version": p["row_version"], "data_model_depth": "KEYS_ONLY"}).status_code == 403
    assert put_components(client, world, 99999, []).status_code == 404


# ---- data model depth (D-39) ------------------------------------------------------------------
def test_depth_changes_audited_and_drives_the_keys_only_warning(client, world, ed, db):
    from services.consistency import consistency_check
    de = entity(client, ed, "Customer")
    pk(client, ed, de, "customer_id")
    g = erd(client, ed).json()
    assert g["data_model_depth"] == "FULL"
    assert [e["warnings"] for e in g["entities"]] == [["KEYS_ONLY"]]
    assert [r["de_number"] for r in consistency_check(ed["p"], db)["entities_keys_only"]] == [de["de_number"]]
    proj = client.get(f"{API}/projects/{ed['p']}", headers=world["admin"]).json()
    r = client.put(f"{API}/projects/{ed['p']}/data-model-depth", headers=world["admin"],
                   json={"row_version": proj["row_version"], "data_model_depth": "KEYS_ONLY"})
    assert r.status_code == 200 and r.json()["data_model_depth"] == "KEYS_ONLY"
    db.expire_all()
    assert [e["warnings"] for e in erd(client, ed).json()["entities"]] == [[]]
    assert consistency_check(ed["p"], db)["entities_keys_only"] == []
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PROJECT_DEPTH_CHANGED")).one()
    assert ev.detail == {"from": "FULL", "to": "KEYS_ONLY"}
    r = client.put(f"{API}/projects/{ed['p']}/data-model-depth", headers=world["admin"],
                   json={"row_version": proj["row_version"], "data_model_depth": "FULL"})
    assert r.status_code == 409                                              # stale row_version
    # an entity with a non-key attribute is never flagged
    field(client, ed, de, "name")
    assert [e["warnings"] for e in erd(client, ed).json()["entities"]] == [[]]


# ---- backfill (Q-9) -------------------------------------------------------------------------
def test_backfill_touches_only_projects_with_no_component_rows(client, world, db):
    """DR7-P1: a project that chose its components, or had one switched off, is never touched."""
    from sqlalchemy import text
    from services import components
    p = new_project(client, world, "REQ", ["ISSUE"])["project_id"]
    db.execute(text("UPDATE project_component SET is_active = false WHERE project_id = :p"), {"p": p})
    db.commit()                                     # REQ now has a retired row only: still chosen
    from sqlalchemy import create_engine
    from tests.conftest import OWNER_URL
    eng = create_engine(OWNER_URL)                # a pre-7a project: inserted with no components
    with eng.begin() as c:                        # and no PROJECT_CREATED component list
        legacy = c.execute(text(
            "INSERT INTO project (client_id, project_code, project_name, status_code_id, created_by) "
            "SELECT :c, 'OLD', 'Old', code_id, 1 FROM code_master WHERE category = 'PROJECT_STATUS' "
            "AND code = 'PLANNING' AND project_id IS NULL RETURNING project_id"),
            {"c": world["client_id"]}).scalar_one()
    eng.dispose()
    empty = new_project(client, world, "NONE", [])["project_id"]      # sara M1: chose nothing
    out = {r["project_id"]: r["added"] for r in components.backfill(db, "admin@example.test")}
    assert out[legacy] == ALL_COMPONENTS and out[p] == [] and out[empty] == []
    assert all(r["added"] == [] for r in components.backfill(db, "admin@example.test"))


# ---- restores never bring data back into an off component (DR7-P2) ------------------------------
def test_a_rated_fr_is_not_restored_while_effort_is_off(client, world, db):
    from services.consistency import consistency_check
    p = new_project(client, world, "E", ["FUNCTION_REQUIREMENT", "EFFORT"])["project_id"]
    h = editor_on(client, world, p)
    fr = client.post(f"{API}/projects/{p}/function-requirements", headers=h,
                     json={"fr_name": "Order form", "fr_type_code": "FORM"}).json()
    r = client.patch(f"{API}/function-requirements/{fr['fr_id']}/complexity", headers=h,
                     json={"row_version": fr["row_version"], "complexity_code": "SIMPLE"})
    assert r.status_code == 200, r.text
    prev = put_components(client, world, p, ["FUNCTION_REQUIREMENT"]).json()
    assert [b["reason"] for b in prev["blockers"]] == ["LIVE_ROWS"]          # a rated FR blocks
    assert client.delete(f"{API}/function-requirements/{fr['fr_id']}", headers=h,
                         params={"row_version": r.json()["row_version"]}).status_code == 204
    assert switch(client, world, p, ["FUNCTION_REQUIREMENT"]).json()["turn_off"] == ["EFFORT"]
    r = client.patch(f"{API}/function-requirements/{fr['fr_id']}/restore", headers=h)
    assert r.status_code == 409 and r.headers["X-VB-Error"] == "COMPONENT_OFF"
    assert consistency_check(p, db)["rows_in_off_component"] == []
    switch(client, world, p, ["FUNCTION_REQUIREMENT", "EFFORT"])
    r = client.patch(f"{API}/function-requirements/{fr['fr_id']}/restore", headers=h)
    assert r.status_code == 200, r.text
