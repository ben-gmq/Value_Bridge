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


# ---- issues: raise, edit, resolve, reopen, retire (step B; criteria 1-3, 6, 9, 10, 12, 13, 15) --------------------
def issue(client, ed, raiser, title="Credit field missing", expect=201, headers=None, project=None, **kw):
    body = {"title": title, "severity_code": "HIGH", "issue_type_code": "DATA",
            "raised_by_stakeholder_id": raiser["stakeholder_id"], **kw}
    r = client.post(f"{API}/projects/{project or ed['p']}/issues", headers=headers or ed["h"], json=body)
    assert r.status_code == expect, r.text
    return r.json()


def get_issue(client, ed, i):
    return client.get(f"{API}/issues/{i['issue_id']}", headers=ed["h"]).json()


def resolve(client, ed, i, status="RESOLVED", resolution="Field added in the target design", rv=None):
    return client.post(f"{API}/issues/{i['issue_id']}/resolve", headers=ed["h"],
                       json={"row_version": rv or get_issue(client, ed, i)["row_version"], "status_code": status,
                             "resolution": resolution})


def reopen(client, ed, i):
    return client.post(f"{API}/issues/{i['issue_id']}/reopen", headers=ed["h"],
                       json={"row_version": get_issue(client, ed, i)["row_version"]})


def edit(client, ed, i, **body):
    return client.patch(f"{API}/issues/{i['issue_id']}", headers=ed["h"],
                        json={"row_version": get_issue(client, ed, i)["row_version"], **body})


def test_raise_mints_numbers_at_save_and_keeps_raiser_and_recorder_apart(client, ed, world, db):
    from services.baseline import local_today
    s = stakeholder(client, ed, "Anan")
    a = issue(client, ed, s)
    b = issue(client, ed, s, "Second", raised_date="2026-10-01", target_date="2026-11-01")
    assert (a["issue_number"], b["issue_number"]) == ("ISS-0001", "ISS-0002")
    assert a["raised_by_stakeholder_id"] == s["stakeholder_id"]
    assert a["recorded_by_user_id"] == world["users"]["editor"]                               # from the JWT
    assert a["raised_date"] == local_today().isoformat() and b["raised_date"] == "2026-10-01"  # I-6
    assert (a["status_code"], a["status_behaviour"], a["resolved_at"]) == ("OPEN", "OPEN", None)
    issue(client, ed, s, "Bad dates", raised_date="2026-10-02", target_date="2026-10-01", expect=422)
    issue(client, ed, s, "   ", expect=422)
    r = client.post(f"{API}/projects/{ed['p']}/issues", headers=ed["h"],             # law 6: no derived values
                    json={"title": "x", "severity_code": "HIGH", "issue_type_code": "DATA", "issue_number": "ISS-9999",
                          "recorded_by_user_id": 1, "raised_by_stakeholder_id": s["stakeholder_id"]})
    assert r.status_code == 201 and r.json()["issue_number"] == "ISS-0003"
    assert r.json()["recorded_by_user_id"] == world["users"]["editor"]


def test_a_raiser_of_another_project_or_retired_is_refused(client, ed, world):
    other = client.post(f"{API}/projects/{world['p_sales']}/stakeholders", headers=world["admin"],
                        json={"stakeholder_name": "Elsewhere"}).json()
    issue(client, ed, other, expect=422)                                                      # criterion 2
    s = stakeholder(client, ed, "Anan")
    assert retire_stk(client, ed, s).status_code == 204
    issue(client, ed, s, expect=422)


def test_resolve_needs_a_closed_status_and_a_resolution(client, ed, world):
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    assert resolve(client, ed, i, resolution="   ").status_code == 422                        # criterion 3
    assert resolve(client, ed, i, status="IN_PROGRESS").status_code == 422                    # an open status
    r = resolve(client, ed, i)
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["status_code"], out["status_behaviour"]) == ("RESOLVED", "CLOSED")
    assert out["resolved_at"] and out["resolved_by_user_id"] == world["users"]["editor"]
    r = resolve(client, ed, i, status="CLOSED", resolution="Verified in UAT")                  # RESOLVED → CLOSED
    assert r.status_code == 200 and r.json()["resolution"] == "Verified in UAT"


def test_patch_moves_only_among_open_statuses_and_never_on_a_closed_issue(client, ed):
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    assert edit(client, ed, i, status_code="RESOLVED").status_code == 422                     # criterion 12 (R2)
    r = edit(client, ed, i, status_code="DEFERRED", severity_code="CRITICAL", target_date="2027-01-31")
    assert r.status_code == 200 and (r.json()["status_code"], r.json()["status_behaviour"]) == ("DEFERRED", "OPEN")
    assert resolve(client, ed, i).status_code == 200
    r = edit(client, ed, i, status_code="IN_PROGRESS")
    assert r.status_code == 409 and "reopen" in r.json()["detail"]                             # N1
    assert edit(client, ed, i, title="Renamed while closed").status_code == 200              # other fields still edit


def test_reopen_clears_the_stamp_and_keeps_the_text(client, ed):
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    assert reopen(client, ed, i).status_code == 409                                           # not closed
    assert resolve(client, ed, i, resolution="Added").status_code == 200
    r = reopen(client, ed, i)
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["status_code"], out["resolved_at"], out["resolved_by_user_id"], out["resolution"]) == \
        ("OPEN", None, None, "Added")                                                          # R3


def test_two_resolves_with_one_row_version_conflict(client, ed):
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    rv = get_issue(client, ed, i)["row_version"]
    assert resolve(client, ed, i, rv=rv).status_code == 200
    assert resolve(client, ed, i, status="CLOSED", rv=rv).status_code == 409                   # criterion 13


def test_the_database_refuses_a_closed_status_without_its_stamp(client, ed, db):
    from sqlalchemy.exc import IntegrityError
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    closed = code_id(db, "ISSUE_STATUS", "RESOLVED")
    try:
        db.execute(text("UPDATE issue SET status_code_id = :c, status_behaviour = 'CLOSED' WHERE issue_id = :i"),
                   {"c": closed, "i": i["issue_id"]})
        raise AssertionError("closed without resolved_at was stored")
    except IntegrityError as e:
        assert "ck_issue_resolved_iff_closed" in str(e)
    finally:
        db.rollback()
    try:                                                                       # behaviour must match the code's own
        db.execute(text("UPDATE issue SET status_behaviour = 'CLOSED', resolved_at = now(), resolved_by_user_id = "
                        "created_by, resolution = 'x' WHERE issue_id = :i"), {"i": i["issue_id"]})
        raise AssertionError("OPEN stored as closed")
    except IntegrityError as e:
        assert "fk_issue_status" in str(e)
    finally:
        db.rollback()


def test_retire_and_restore_and_the_raiser_cannot_be_retired_meanwhile(client, ed):
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    r = retire_stk(client, ed, s)
    assert r.status_code == 409 and "ISS-0001" in r.json()["detail"]                          # I-7, criterion 6
    rv = get_issue(client, ed, i)["row_version"]
    assert client.delete(f"{API}/issues/{i['issue_id']}", headers=ed["h"], params={"row_version": rv}).status_code == 204
    assert [x["issue_number"] for x in client.get(f"{API}/projects/{ed['p']}/issues", headers=ed["h"]).json()] == []
    assert retire_stk(client, ed, s).status_code == 204
    r = client.patch(f"{API}/issues/{i['issue_id']}/restore", headers=ed["h"])
    assert r.status_code == 409                                                                 # restore the raiser first
    assert client.patch(f"{API}/stakeholders/{s['stakeholder_id']}/restore", headers=ed["h"]).status_code == 200
    r = client.patch(f"{API}/issues/{i['issue_id']}/restore", headers=ed["h"])
    assert r.status_code == 200 and r.json()["issue_number"] == "ISS-0001"                    # the number comes back


def test_the_list_filters(client, ed):
    a, b = stakeholder(client, ed, "Anan"), stakeholder(client, ed, "Bee")
    i1 = issue(client, ed, a, severity_code="CRITICAL")
    issue(client, ed, b, issue_type_code="PROCESS")
    i3 = issue(client, ed, a)
    assert resolve(client, ed, i3).status_code == 200

    def nums(**q):
        r = client.get(f"{API}/projects/{ed['p']}/issues", headers=ed["h"], params=q)
        assert r.status_code == 200, r.text
        return [x["issue_number"] for x in r.json()]
    assert nums() == ["ISS-0001", "ISS-0002", "ISS-0003"]
    assert nums(open_only=True) == ["ISS-0001", "ISS-0002"]
    assert nums(severity="CRITICAL") == [i1["issue_number"]]
    assert nums(issue_type="PROCESS") == ["ISS-0002"]
    assert nums(raiser=a["stakeholder_id"]) == ["ISS-0001", "ISS-0003"]
    assert nums(status="RESOLVED") == ["ISS-0003"]


def test_issue_access_and_component_gate(client, ed, world, db):
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    assert client.get(f"{API}/issues/{i['issue_id']}", headers=ed["rv"]).status_code == 200
    issue(client, ed, s, headers=ed["rv"], expect=403)
    assert client.get(f"{API}/issues/{i['issue_id']}", headers=ed["out"]).status_code == 404   # criterion 10
    assert client.get(f"{API}/projects/{ed['p']}/issues", headers=ed["out"]).status_code == 404
    r = client.post(f"{API}/issues/{i['issue_id']}/resolve", headers=ed["out"],
                    json={"row_version": 1, "status_code": "RESOLVED", "resolution": "x"})
    assert r.status_code == 404


def test_no_audit_event_carries_a_title_or_a_name(client, ed, db):
    """R7, criterion 15 (sara B L-1): retire and restore both kinds, then read every event they wrote."""
    s = stakeholder(client, ed, "Anan Secretname")
    i = issue(client, ed, s, "Secret title")
    for path, row in ((f"/issues/{i['issue_id']}", i),):
        rv = cur(client, ed, path)["row_version"]
        assert client.delete(f"{API}{path}", headers=ed["h"], params={"row_version": rv}).status_code == 204
        assert client.patch(f"{API}{path}/restore", headers=ed["h"]).status_code == 200
    rv = cur(client, ed, f"/issues/{i['issue_id']}")["row_version"]
    assert client.delete(f"{API}/issues/{i['issue_id']}", headers=ed["h"], params={"row_version": rv}).status_code == 204
    assert retire_stk(client, ed, s).status_code == 204
    assert client.patch(f"{API}/stakeholders/{s['stakeholder_id']}/restore", headers=ed["h"]).status_code == 200
    events = list(db.scalars(select(AuditEvent).where(AuditEvent.target_table.in_(("issue", "stakeholder")))))
    assert {e.target_table for e in events} == {"issue", "stakeholder"} and len(events) >= 5
    assert all("Secret" not in str(e.detail) for e in events)


def test_issue_writes_are_refused_with_the_component_off(client, ed, world):
    """Criterion 9 for issue writes (sara B L-2): the user sees 409 COMPONENT_OFF, not just a declared guard."""
    from tests.conftest import ALL_COMPONENTS
    without = [c for c in ALL_COMPONENTS if c != "ISSUE"]
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    pv = client.put(f"{API}/projects/{ed['p']}/components", headers=world["admin"],
                    json={"component_codes": without}).json()
    assert any("ISS-0001" in b["message"] for b in pv["blockers"])            # a live issue keeps ISSUE on (R10)
    rv = get_issue(client, ed, i)["row_version"]
    assert client.delete(f"{API}/issues/{i['issue_id']}", headers=ed["h"], params={"row_version": rv}).status_code == 204
    assert retire_stk(client, ed, s).status_code == 204
    switch(client, world, ed["p"], without)
    for r in (client.post(f"{API}/projects/{ed['p']}/issues", headers=ed["h"],
                          json={"title": "x", "severity_code": "HIGH", "issue_type_code": "DATA",
                                "raised_by_stakeholder_id": s["stakeholder_id"]}),
              client.post(f"{API}/issues/{i['issue_id']}/resolve", headers=ed["h"],
                          json={"row_version": i["row_version"], "status_code": "RESOLVED", "resolution": "x"})):
        assert r.status_code == 409 and r.headers.get("X-VB-Error") == "COMPONENT_OFF", r.text
    assert client.get(f"{API}/issues/{i['issue_id']}", headers=ed["h"]).status_code == 200    # reads stay open


# ---- links, step retire, the dashboard and the M3 tile (step C; criteria 4, 5, 7, 11, 14, 16, 17) ------------------
def two_areas(client, ed):
    """Two L1 areas (Sales, Finance), one process step each; returns the two steps' BRs."""
    from tests.test_scope_api import node
    from tests.test_step_retire import _br
    out = []
    for area, step_name in (("Sales", "Take order"), ("Finance", "Post invoice")):
        a = node(client, ed, area)
        b = node(client, ed, f"{area} flow", a["bfc_node_id"])
        s = node(client, ed, step_name, b["bfc_node_id"], is_process=True)
        out.append(_br(client, ed, s["bfc_node_id"]))
    return out


def link(client, ed, i, br, expect=201, headers=None):
    r = client.post(f"{API}/issues/{i['issue_id']}/brs", headers=headers or ed["h"], json={"br_id": br["br_id"]})
    assert r.status_code == expect, r.text
    return r.json()


def unlink(client, ed, i, lnk, headers=None, issue_id=None):
    return client.delete(f"{API}/issues/{issue_id or i['issue_id']}/brs/{lnk['issue_br_id']}",
                         headers=headers or ed["h"], params={"row_version": lnk["row_version"]})


def dash(client, ed):
    r = client.get(f"{API}/projects/{ed['p']}/issue-dashboard", headers=ed["h"])
    assert r.status_code == 200, r.text
    return r.json()


def test_links_span_brs_and_relink_restores_the_row(client, ed):
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    br1, br2 = two_areas(client, ed)
    l1 = link(client, ed, i, br1)
    link(client, ed, i, br2)
    link(client, ed, i, br1, expect=409)                                                       # already linked
    link(client, ed, i, {"br_id": 999999}, expect=422)
    assert unlink(client, ed, i, l1).status_code == 204
    again = link(client, ed, i, br1)
    assert again["issue_br_id"] == l1["issue_br_id"]                                           # S1-7: same row
    r = client.get(f"{API}/issues/{i['issue_id']}/brs", headers=ed["h"]).json()
    assert [x["br_number"] for x in r] == sorted([br1["br_number"], br2["br_number"]])


def test_an_issue_with_links_cannot_be_retired(client, ed):
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    br1, _ = two_areas(client, ed)
    link(client, ed, i, br1)
    rv = get_issue(client, ed, i)["row_version"]
    r = client.delete(f"{API}/issues/{i['issue_id']}", headers=ed["h"], params={"row_version": rv})
    assert r.status_code == 409 and br1["br_number"] in r.json()["detail"]                     # I-4


def test_unlinking_another_issues_link_is_404_and_writes_nothing(client, ed, world, db):
    """Criterion 11 (R1): the link is fetched under the issue in the path; another project's link is a 404."""
    s = stakeholder(client, ed, "Anan")
    mine = issue(client, ed, s)
    br1, _ = two_areas(client, ed)
    theirs_p = world["p_sales"]
    ts = stakeholder(client, ed, "Zed", headers=world["admin"], project=theirs_p)
    theirs = issue(client, ed, ts, headers=world["admin"], project=theirs_p)
    a = client.post(f"{API}/projects/{theirs_p}/bfc-nodes", headers=world["admin"],
                    json={"node_name": "Ops", "parent_bfc_node_id": None}).json()
    b = client.post(f"{API}/projects/{theirs_p}/bfc-nodes", headers=world["admin"],
                    json={"node_name": "Ops flow", "parent_bfc_node_id": a["bfc_node_id"]}).json()
    st = client.post(f"{API}/projects/{theirs_p}/bfc-nodes", headers=world["admin"],
                     json={"node_name": "Ship", "parent_bfc_node_id": b["bfc_node_id"], "is_process": True}).json()
    their_br = next(x for x in client.get(f"{API}/projects/{theirs_p}/business-requirements",
                                          headers=world["admin"]).json() if x["bfc_node_id"] == st["bfc_node_id"])
    their_link = link(client, ed, theirs, their_br, headers=world["admin"])
    link(client, ed, mine, their_br, expect=422)                                               # criterion 4
    assert unlink(client, ed, mine, their_link, issue_id=mine["issue_id"]).status_code == 404
    still = db.execute(text("SELECT is_active FROM issue_br WHERE issue_br_id = :i"),
                       {"i": their_link["issue_br_id"]}).scalar_one()
    assert still is True


def test_a_step_retire_takes_the_link_and_names_the_issue_which_stays_live(client, ed):
    from tests.test_step_retire import preview, restore, retire
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    br1, br2 = two_areas(client, ed)
    link(client, ed, i, br1)
    link(client, ed, i, br2)
    p = preview(client, ed, br1["bfc_node_id"]).json()
    assert p["issues"] == ["ISS-0001"] and not p["blockers"]                                   # criterion 5, I-3
    assert retire(client, ed, br1["bfc_node_id"]).status_code in (200, 204)
    assert get_issue(client, ed, i)["is_active"]                                               # the issue survives
    live = [x["br_number"] for x in client.get(f"{API}/issues/{i['issue_id']}/brs", headers=ed["h"]).json()]
    assert live == [br2["br_number"]]
    r = restore(client, ed, br1["bfc_node_id"])
    assert r.status_code in (200, 204), r.text
    live = [x["br_number"] for x in client.get(f"{API}/issues/{i['issue_id']}/brs", headers=ed["h"]).json()]
    assert live == sorted([br1["br_number"], br2["br_number"]])                                 # back with the step


def test_a_step_restore_is_refused_while_its_issue_is_retired(client, ed):
    from tests.test_step_retire import restore, retire
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s)
    br1, _ = two_areas(client, ed)
    link(client, ed, i, br1)
    assert retire(client, ed, br1["bfc_node_id"]).status_code in (200, 204)
    rv = get_issue(client, ed, i)["row_version"]
    assert client.delete(f"{API}/issues/{i['issue_id']}", headers=ed["h"], params={"row_version": rv}).status_code == 204
    r = restore(client, ed, br1["bfc_node_id"])
    assert r.status_code == 409 and "ISS-0001" in r.json()["detail"], r.text                   # restore the issue first
    assert r.headers.get("X-VB-Error") == "RESTORE_FIRST"                                       # schema §4 (sara C L6)


def test_the_dashboard_counts_areas_raisers_overdue_and_agrees_with_the_list(client, ed):
    """Criteria 7, 14, 16, 17: a two-area issue counts in both areas and once in the total; an unlinked one under
    "No area"; DEFERRED counts as open and overdue; the tile's Critical counts CRITICAL only."""
    a, b = stakeholder(client, ed, "Anan"), stakeholder(client, ed, "Bee")
    br1, br2 = two_areas(client, ed)
    both = issue(client, ed, a, "Both areas", severity_code="CRITICAL")
    link(client, ed, both, br1)
    link(client, ed, both, br2)
    sales = issue(client, ed, a, "Sales only", severity_code="HIGH", issue_type_code="PROCESS")
    link(client, ed, sales, br1)
    loose = issue(client, ed, b, "No area", severity_code="LOW", raised_date="2026-01-01", target_date="2026-01-31")
    assert edit(client, ed, loose, status_code="DEFERRED").status_code == 200
    done = issue(client, ed, b, "Closed one", severity_code="CRITICAL")
    assert resolve(client, ed, done).status_code == 200

    d = dash(client, ed)
    assert (d["open"], d["critical"], d["overdue"]) == (3, 1, 1)                                # 16, 17
    assert d["severities"] == ["CRITICAL", "HIGH", "MEDIUM", "LOW"]                             # all four shown
    cell = {r["severity_code"]: r["counts"] for r in d["by_severity_type"]}
    assert (cell["CRITICAL"]["DATA"], cell["HIGH"]["PROCESS"], cell["LOW"]["DATA"]) == (1, 1, 1)
    areas = {r["name"]: r["open"] for r in d["by_area"]}
    assert areas == {"Sales": 2, "Finance": 1} and d["no_area"] == 1                            # 14: rows ≠ total
    assert {r["name"]: r["open"] for r in d["by_raiser"]} == {"Anan": 2, "Bee": 1}

    def nums(**q):
        return [x["issue_number"] for x in client.get(f"{API}/projects/{ed['p']}/issues", headers=ed["h"],
                                                      params={"open_only": True, **q}).json()]
    by_area = {r["area_id"]: r["open"] for r in d["by_area"]}
    for area_id, n in by_area.items():                                                          # 7: list agrees
        assert len(nums(area=str(area_id))) == n
    assert nums(area="none") == [loose["issue_number"]]
    assert len(nums(severity="CRITICAL")) == d["critical"]
    for r in d["by_raiser"]:
        assert len(nums(raiser=r["stakeholder_id"])) == r["open"]
    tile = client.get(f"{API}/projects/{ed['p']}/scope-summary", headers=ed["h"]).json()["totals"]
    assert (tile["issues_open"], tile["issues_critical"]) == (3, 1)                             # M3: Critical only
