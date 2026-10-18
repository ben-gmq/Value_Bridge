"""Slice 14 — the Issue module through the API (docs/slice14_issue_spec.md §10; I-1…I-16). Grade 2 for the issue data
and its dashboard (figures a consultant decides from); Grade 1 for the hash bump, proven in test_baseline_issue.py.

Step A: stakeholders and the company-only issue statuses.
Deliberately uncovered: a true two-connection race between a unit retire and a stakeholder save (the FOR SHARE lock
order, R11, carries it), and a stakeholder name over 200 characters (the schema's max_length refuses it first)."""
from sqlalchemy import select, text

from models import AuditEvent
from tests.test_code_lists import add_company, add_project, cl, code_id  # noqa: F401 — cl is a fixture
from tests.test_components import switch
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture


def unit(client, ed, code="SALES"):
    r = client.post(f"{API}/projects/{ed['p']}/org-units", headers=ed["h"],
                    json={"org_unit_code": code, "org_unit_name": code.title()})
    assert r.status_code == 201, r.text
    return r.json()


def stakeholder(client, ed, name="Somchai P.", expect=201, headers=None, project=None, **kw):
    r = client.post(f"{API}/projects/{project or ed['p']}/stakeholders", headers=headers or ed["h"],
                    json={"stakeholder_name": name, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def cur(client, ed, path):
    return client.get(f"{API}{path}", headers=ed["h"]).json()


def retire_stk(client, ed, s, headers=None):
    rv = cur(client, ed, f"/stakeholders/{s['stakeholder_id']}")["row_version"]
    return client.delete(f"{API}/stakeholders/{s['stakeholder_id']}", headers=headers or ed["h"],
                         params={"row_version": rv})


# ---- stakeholders -----------------------------------------------------------------------------------------------
def test_create_edit_retire_and_restore_a_stakeholder(client, ed, db):
    u = unit(client, ed)
    s = stakeholder(client, ed, "  Somchai P. ", job_title="AR lead", org_unit_id=u["org_unit_id"], is_bpo=False)
    assert (s["stakeholder_name"], s["job_title"], s["org_unit_id"]) == ("Somchai P.", "AR lead", u["org_unit_id"])
    r = client.patch(f"{API}/stakeholders/{s['stakeholder_id']}", headers=ed["h"],
                     json={"row_version": s["row_version"], "org_unit_id": None, "is_bpo": True})
    assert r.status_code == 200, r.text
    assert (r.json()["org_unit_id"], r.json()["is_bpo"]) == (None, True)                       # I-2: unit optional
    stale = client.patch(f"{API}/stakeholders/{s['stakeholder_id']}", headers=ed["h"],
                         json={"row_version": s["row_version"], "job_title": "x"})
    assert stale.status_code == 409
    assert retire_stk(client, ed, s).status_code == 204
    names = [x["stakeholder_name"] for x in cur(client, ed, f"/projects/{ed['p']}/stakeholders")]
    assert names == []
    r = client.patch(f"{API}/stakeholders/{s['stakeholder_id']}/restore", headers=ed["h"])
    assert r.status_code == 200 and r.json()["is_active"], r.text
    # R7: the audit names the stakeholder by id, never by name
    details = [e.detail for e in db.scalars(select(AuditEvent).where(AuditEvent.target_table == "stakeholder"))]
    assert details and all("Somchai" not in str(d) for d in details)


def test_a_name_is_unique_per_org_unit_only(client, ed):
    a, b = unit(client, ed, "SALES"), unit(client, ed, "FIN")
    stakeholder(client, ed, "Anan", org_unit_id=a["org_unit_id"])
    stakeholder(client, ed, " anan ", org_unit_id=a["org_unit_id"], expect=409)                # same unit
    stakeholder(client, ed, "Anan", org_unit_id=b["org_unit_id"])                              # I-16
    stakeholder(client, ed, "Anan")                                                            # no unit
    stakeholder(client, ed, "ANAN", expect=409)                                                # no unit twice
    stakeholder(client, ed, "   ", expect=422)


def test_restore_is_refused_when_a_namesake_took_the_name(client, ed):
    s = stakeholder(client, ed, "Anan")
    assert retire_stk(client, ed, s).status_code == 204
    stakeholder(client, ed, "Anan")
    r = client.patch(f"{API}/stakeholders/{s['stakeholder_id']}/restore", headers=ed["h"])
    assert r.status_code == 409


def test_an_org_unit_of_another_project_or_retired_is_refused(client, ed, world):
    other = client.post(f"{API}/projects/{world['p_sales']}/org-units", headers=world["admin"],
                        json={"org_unit_code": "X", "org_unit_name": "X"}).json()
    stakeholder(client, ed, "Anan", org_unit_id=other["org_unit_id"], expect=422)
    u = unit(client, ed)
    assert client.delete(f"{API}/org-units/{u['org_unit_id']}", headers=ed["h"],
                         params={"row_version": u["row_version"]}).status_code == 204
    stakeholder(client, ed, "Anan", org_unit_id=u["org_unit_id"], expect=409)


def test_an_org_unit_with_a_live_stakeholder_cannot_be_retired(client, ed):
    u = unit(client, ed)
    s = stakeholder(client, ed, "Anan", org_unit_id=u["org_unit_id"])
    r = client.delete(f"{API}/org-units/{u['org_unit_id']}", headers=ed["h"],
                      params={"row_version": u["row_version"]})
    assert r.status_code == 409 and f"Stakeholder: #{s['stakeholder_id']}" in r.json()["detail"], r.text
    assert retire_stk(client, ed, s).status_code == 204
    assert client.delete(f"{API}/org-units/{u['org_unit_id']}", headers=ed["h"],
                         params={"row_version": u["row_version"]}).status_code == 204


def test_readers_and_outsiders(client, ed):
    s = stakeholder(client, ed, "Anan")
    assert client.get(f"{API}/projects/{ed['p']}/stakeholders", headers=ed["rv"]).status_code == 200
    stakeholder(client, ed, "Bee", headers=ed["rv"], expect=403)
    assert client.get(f"{API}/stakeholders/{s['stakeholder_id']}", headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/projects/{ed['p']}/stakeholders", headers=ed["out"]).status_code == 404
    stakeholder(client, ed, "Bee", headers=ed["out"], expect=404)


def test_component_issue_gates_writes_and_cannot_go_off_under_stakeholders(client, ed, world):
    from tests.conftest import ALL_COMPONENTS
    without = [c for c in ALL_COMPONENTS if c != "ISSUE"]
    s = stakeholder(client, ed, "Anan")
    url = f"{API}/projects/{ed['p']}/components"
    preview = client.put(url, headers=world["admin"], json={"component_codes": without}).json()
    assert preview["blockers"], preview                                                         # R10
    r = client.put(url, headers=world["admin"], json={"component_codes": without,
                                                      "confirm_hash": preview["confirm_hash"]})
    assert r.status_code == 409 and f"{s['stakeholder_id']}" in r.json()["detail"], r.text
    assert retire_stk(client, ed, s).status_code == 204
    switch(client, world, ed["p"], without)
    r = client.post(f"{API}/projects/{ed['p']}/stakeholders", headers=ed["h"], json={"stakeholder_name": "Bee"})
    assert r.status_code == 409 and r.headers.get("X-VB-Error") == "COMPONENT_OFF"
    assert client.get(f"{API}/projects/{ed['p']}/stakeholders", headers=ed["h"]).status_code == 200   # reads ungated


# ---- issue statuses are company-only (I-1); CRITICAL is pinned (I-13) --------------------------------------------
def test_issue_statuses_are_company_only_with_a_behaviour(client, cl, db):
    add_project(client, cl, "ISSUE_STATUS", "OPEN", "Raised", expect=409)
    add_project(client, cl, "ISSUE_STATUS", "WAITING", "Waiting", behaviour_code="OPEN", expect=409)
    r = client.post(f"{API}/projects/{cl['p']}/code-lists/hidden", headers=cl["pa"],
                    json={"code_id": code_id(db, "ISSUE_STATUS", "DEFERRED")})
    assert r.status_code == 409
    add_company(client, cl, "ISSUE_STATUS", "WAITING", "Waiting", expect=422)                  # needs a behaviour
    add_company(client, cl, "ISSUE_STATUS", "WAITING", "Waiting", behaviour_code="FORM", expect=422)
    w = add_company(client, cl, "ISSUE_STATUS", "WAITING", "Waiting on client", behaviour_code="OPEN")
    assert w["behaviour_code"] == "OPEN"
    opened = code_id(db, "ISSUE_STATUS", "OPEN")
    rv = db.execute(text("SELECT row_version FROM code_master WHERE code_id = :i"), {"i": opened}).scalar_one()
    r = client.patch(f"{API}/code-master/{opened}", headers=cl["admin"], json={"row_version": rv, "label": "Raised"})
    assert r.status_code == 200, r.text                                                         # platform admin relabels
    r = client.patch(f"{API}/code-master/{opened}", headers=cl["admin"],
                     json={"row_version": rv + 1, "behaviour_code": "CLOSED"})
    assert r.status_code == 409                                                                 # sara A M-2
    r = client.delete(f"{API}/code-master/{opened}", headers=cl["admin"], params={"row_version": rv + 1})
    assert r.status_code == 409                                                                 # pinned: never retired


def test_critical_severity_is_pinned_and_the_others_are_project_editable(client, cl, db):
    r = client.post(f"{API}/projects/{cl['p']}/code-lists/hidden", headers=cl["pa"],
                    json={"code_id": code_id(db, "ISSUE_SEVERITY", "CRITICAL")})
    assert r.status_code == 409
    r = client.post(f"{API}/projects/{cl['p']}/code-lists/hidden", headers=cl["pa"],
                    json={"code_id": code_id(db, "ISSUE_SEVERITY", "LOW")})
    assert r.status_code == 201, r.text
    add_project(client, cl, "ISSUE_SEVERITY", "HIGH", "Major")
