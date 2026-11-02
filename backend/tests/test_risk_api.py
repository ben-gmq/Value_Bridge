"""Slice Risks — the register and promote to an issue through the API (docs/slice_risks_spec.md §9 criteria 1–6, 9;
design criteria 61–62). Grade 2: a wrong score or a half-done promote reaches a steering meeting and is corrected once
noticed.

Deliberately uncovered: a true two-connection race between an owner-role retire and a risk save (the FOR SHARE read
carries it, as for issues); ageing beyond "days since raised"; more than 500 risks per project."""
from datetime import timedelta

from sqlalchemy import select, text

from models import AuditEvent
from services.baseline import local_today
from tests.conftest import ALL_COMPONENTS
from tests.test_code_lists import add_company, add_project, cl, code_id  # noqa: F401 — cl is a fixture
from tests.test_components import switch
from tests.test_control import role
from tests.test_issue_api import stakeholder
from tests.test_phasing_api import wave
from tests.test_scope_api import API, ed, node  # noqa: F401 — ed is a fixture
from tests.test_solution_api import sol


def risk(client, ed, owner, title="Key user unavailable in UAT", p="LIKELY", i="MAJOR", expect=201, headers=None,
         project=None, **kw):
    r = client.post(f"{API}/projects/{project or ed['p']}/risks", headers=headers or ed["h"],
                    json={"title": title, "probability_code": p, "impact_code": i,
                          "owner_org_role_id": owner["org_role_id"], **kw})
    assert r.status_code == expect, r.text
    return r.json()


def get(client, ed, r):
    return client.get(f"{API}/risks/{r['risk_id']}", headers=ed["h"]).json()


def edit(client, ed, r, expect=200, **body):
    rv = get(client, ed, r)["row_version"]
    out = client.patch(f"{API}/risks/{r['risk_id']}", headers=ed["h"], json={"row_version": rv, **body})
    assert out.status_code == expect, out.text
    return out.json()


def promote(client, ed, r, raiser, expect=200, **kw):
    rv = get(client, ed, r)["row_version"]
    out = client.post(f"{API}/risks/{r['risk_id']}/materialise", headers=ed["h"],
                      json={"row_version": rv, "raised_by_stakeholder_id": raiser["stakeholder_id"],
                            "severity_code": "HIGH", "issue_type_code": "DATA", **kw})
    assert out.status_code == expect, out.text
    return out.json()


def register(client, ed, **params):
    r = client.get(f"{API}/projects/{ed['p']}/risks", headers=ed["h"], params=params)
    assert r.status_code == 200, r.text
    return r.json()


def retire(client, ed, r):
    rv = get(client, ed, r)["row_version"]
    return client.delete(f"{API}/risks/{r['risk_id']}", headers=ed["h"], params={"row_version": rv})


# ---- 1, 2. the score (criterion 61, RK-1) ----------------------------------------------------------------------------
def test_score_is_weight_times_weight_and_never_taken_from_the_body(client, ed):
    owner = role(client, ed)
    high = risk(client, ed, owner, p="LIKELY", i="MAJOR", exposure_score=1)
    mid = risk(client, ed, owner, "Vendor late", p="POSSIBLE", i="MODERATE")
    assert (high["risk_number"], high["exposure_score"], mid["exposure_score"]) == ("RSK-0001", 16, 9)
    assert high["exposure_score"] > mid["exposure_score"]
    assert edit(client, ed, high, probability_code="RARE", exposure_score=25)["exposure_score"] == 4
    assert edit(client, ed, high, impact_code="SEVERE")["exposure_score"] == 5


def test_a_renamed_or_added_level_scores_by_its_weight(client, cl, db):
    owner = role(client, {"p": cl["p"], "h": cl["h"]})
    add_project(client, cl, "RISK_PROBABILITY", "LIKELY", "Probable")                # a project rename keeps W4
    add_project(client, cl, "RISK_IMPACT", "CRIPPLING", "Crippling", behaviour_code="W5")
    add_project(client, cl, "RISK_IMPACT", "ODD", "Odd", behaviour_code="W9", expect=422)
    r = risk(client, {"p": cl["p"], "h": cl["h"]}, owner, p="LIKELY", i="CRIPPLING")
    assert (r["probability_weight"], r["impact_weight"], r["exposure_score"]) == ("W4", "W5", 20)


# ---- 3. promote (criterion 62, RK-4, R1-1) ---------------------------------------------------------------------------
def test_promote_creates_and_links_the_issue_and_the_risk_stays(client, ed, db):
    owner, raiser = role(client, ed), stakeholder(client, ed)
    r = risk(client, ed, owner, description="Only two key users", raised_date=str(local_today() - timedelta(days=30)),
             target_date=str(local_today() - timedelta(days=5)))                       # overdue still promotes (R1-1)
    out = promote(client, ed, r, raiser)
    issue, after = out["issue"], out["risk"]
    assert (issue["title"], issue["description"], issue["target_date"]) == (r["title"], "Only two key users", None)
    assert (after["status_code"], after["status_behaviour"], after["materialised_issue_id"]) == (
        "MATERIALISED", "MATERIALISED", issue["issue_id"])
    assert after["materialised_issue_number"] == issue["issue_number"] and after["is_active"]
    assert [x["risk_id"] for x in register(client, ed, issue_id=issue["issue_id"])] == [r["risk_id"]]
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "RISK_MATERIALISED")).one()
    assert ev.detail["issue_number"] == issue["issue_number"] and "title" not in str(ev.detail)
    promote(client, ed, r, raiser, expect=409)                                         # twice


def retire_stk_ok(client, ed, s) -> bool:
    """ISSUE cannot switch off under a live stakeholder (slice14 R10); the raiser is retired first."""
    from tests.test_issue_api import retire_stk
    return retire_stk(client, ed, s).status_code == 204


def test_promote_with_issue_off_or_a_bad_raiser_writes_nothing(client, ed, world, db):
    owner, raiser = role(client, ed), stakeholder(client, ed)
    r = risk(client, ed, owner)
    promote(client, ed, r, {"stakeholder_id": 999999}, expect=422)                     # fails inside raise_issue
    assert retire_stk_ok(client, ed, raiser)
    switch(client, world, ed["p"], [c for c in ALL_COMPONENTS if c != "ISSUE"])
    out = promote(client, ed, r, {"stakeholder_id": raiser["stakeholder_id"]}, expect=409)
    assert out["detail"]
    assert db.execute(text("SELECT count(*) FROM issue")).scalar() == 0
    assert get(client, ed, r)["status_code"] == "OPEN" and get(client, ed, r)["materialised_issue_id"] is None


# ---- 4. a materialised risk is the record (R1-2, R2 NEW-1) -----------------------------------------------------------
def test_a_materialised_risk_keeps_its_evidence_but_can_be_repointed(client, ed):
    owner, other, raiser = role(client, ed), role(client, ed, code="CFO"), stakeholder(client, ed)
    r = risk(client, ed, owner)
    issue = promote(client, ed, r, raiser)["issue"]
    edit(client, ed, r, expect=409, impact_code="MINOR")
    edit(client, ed, r, expect=409, title="Softer wording")
    assert edit(client, ed, r, owner_org_role_id=other["org_role_id"])["owner_org_role_id"] == other["org_role_id"]
    assert retire(client, ed, r).status_code == 409
    rv = client.get(f"{API}/issues/{issue['issue_id']}", headers=ed["h"]).json()["row_version"]
    blocked = client.delete(f"{API}/issues/{issue['issue_id']}", headers=ed["h"], params={"row_version": rv})
    assert blocked.status_code == 409 and r["risk_number"] in blocked.json()["detail"]


def test_materialised_cannot_be_set_by_patch_and_statuses_move_freely_otherwise(client, ed):
    owner = role(client, ed)
    r = risk(client, ed, owner)
    edit(client, ed, r, expect=422, status_code="MATERIALISED")
    assert edit(client, ed, r, status_code="MITIGATING")["status_behaviour"] == "OPEN"
    assert edit(client, ed, r, status_code="CLOSED")["status_behaviour"] == "CLOSED"
    assert edit(client, ed, r, status_code="OPEN")["status_behaviour"] == "OPEN"


def test_the_score_change_is_audited_with_codes_only(client, ed, db):
    owner = role(client, ed)
    r = risk(client, ed, owner, mitigation="Back-up key user named")
    edit(client, ed, r, probability_code="UNLIKELY")
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "RISK_UPDATED")).one()
    assert ev.detail["before"]["probability"] == "LIKELY" and ev.detail["before"]["exposure_score"] == 16
    assert ev.detail["after"]["probability"] == "UNLIKELY" and ev.detail["after"]["exposure_score"] == 8
    assert "Back-up" not in str(ev.detail) and r["title"] not in str(ev.detail)


# ---- 4a. the risk lists' behaviours are fixed (R1-4, apple L1) -------------------------------------------------------
def test_risk_status_behaviours_are_fixed_and_a_retired_risk_keeps_its_weight(client, cl, db):
    for code in ("OPEN", "MITIGATING", "CLOSED", "MATERIALISED"):
        cid = code_id(db, "RISK_STATUS", code)
        rv = db.execute(text(f"SELECT row_version FROM code_master WHERE code_id = {cid}")).scalar()
        r = client.patch(f"{API}/code-master/{cid}", headers=cl["admin"],
                         json={"row_version": rv, "behaviour_code": "CLOSED" if code != "CLOSED" else "OPEN"})
        assert r.status_code == 409, (code, r.text)
    add_project(client, cl, "RISK_STATUS", "WATCHING", "Watching", behaviour_code="OPEN", expect=409)  # company-only
    added = add_company(client, cl, "RISK_IMPACT", "TOTAL", "Total", behaviour_code="W5")
    owner = role(client, {"p": cl["p"], "h": cl["h"]})
    r = risk(client, {"p": cl["p"], "h": cl["h"]}, owner, i="TOTAL")
    assert retire(client, {"p": cl["p"], "h": cl["h"]}, r).status_code == 204
    rv = db.execute(text(f"SELECT row_version FROM code_master WHERE code_id = {added['code_id']}")).scalar()
    out = client.patch(f"{API}/code-master/{added['code_id']}", headers=cl["admin"],
                       json={"row_version": rv, "behaviour_code": "W1"})
    assert out.status_code == 409, out.text                                          # not the FK's 500


# ---- 5. checks -------------------------------------------------------------------------------------------------------
def test_stale_component_off_and_foreign_or_retired_links(client, ed, world):
    owner = role(client, ed)
    r = risk(client, ed, owner)
    out = client.patch(f"{API}/risks/{r['risk_id']}", headers=ed["h"], json={"row_version": 99, "title": "x"})
    assert out.status_code == 409
    foreign = role(client, {"p": world["p_sales"], "h": world["admin"]}, code="EXT")
    risk(client, ed, foreign, expect=422)                                           # another project's role
    risk(client, ed, {"org_role_id": 999999}, expect=422)
    gone = role(client, ed, code="OLD")
    assert client.delete(f"{API}/org-roles/{gone['org_role_id']}", headers=ed["h"],
                         params={"row_version": gone["row_version"]}).status_code == 204
    risk(client, ed, gone, expect=422)
    risk(client, ed, owner, bfc_node_id=999999, expect=422)
    risk(client, ed, owner, raised_date=str(local_today() + timedelta(days=1)), expect=422)
    risk(client, ed, owner, raised_date="2026-10-01", target_date="2026-09-30", expect=422)
    edit(client, ed, r, expect=422, raised_date="2026-01-01", target_date="2025-12-31")   # NEW-2: a 422, never a 500
    blocked = switch(client, world, ed["p"], [c for c in ALL_COMPONENTS if c != "RISK"])
    assert blocked.status_code == 409 and r["risk_number"] in blocked.json()["detail"]    # live risks keep it on
    assert retire(client, ed, r).status_code == 204
    switch(client, world, ed["p"], [c for c in ALL_COMPONENTS if c != "RISK"])
    out = client.post(f"{API}/projects/{ed['p']}/risks", headers=ed["h"],
                      json={"title": "x", "probability_code": "RARE", "impact_code": "MINOR",
                            "owner_org_role_id": owner["org_role_id"]})
    assert out.status_code == 409 and out.headers.get("X-VB-Error") == "COMPONENT_OFF"
    assert client.get(f"{API}/projects/{ed['p']}/risks", headers=ed["h"]).status_code == 200


def test_readers_and_outsiders(client, ed):
    owner = role(client, ed)
    r = risk(client, ed, owner)
    assert client.get(f"{API}/risks/{r['risk_id']}", headers=ed["rv"]).status_code == 200
    risk(client, ed, owner, headers=ed["rv"], expect=403)
    assert client.get(f"{API}/risks/{r['risk_id']}", headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/projects/{ed['p']}/risks", headers=ed["out"]).status_code == 404


# ---- 6. the register -------------------------------------------------------------------------------------------------
def test_register_order_filters_and_retired(client, ed):
    owner, cfo = role(client, ed), role(client, ed, code="CFO")
    w = wave(client, ed)
    low = risk(client, ed, owner, "Low", p="RARE", i="MINOR")
    old = risk(client, ed, owner, "Old high", raised_date=str(local_today() - timedelta(days=9)))
    new = risk(client, ed, cfo, "New high", phase_id=w["phase_id"])
    shut = risk(client, ed, owner, "Closed severe", p="ALMOST_CERTAIN", i="SEVERE")
    edit(client, ed, shut, status_code="CLOSED")
    assert [x["title"] for x in register(client, ed)] == ["Old high", "New high", "Low", "Closed severe"]
    assert [x["title"] for x in register(client, ed, owner_org_role_id=cfo["org_role_id"])] == ["New high"]
    assert [x["title"] for x in register(client, ed, phase_id=w["phase_id"])] == ["New high"]
    assert [x["title"] for x in register(client, ed, status="CLOSED")] == ["Closed severe"]
    assert retire(client, ed, low).status_code == 204
    assert "Low" not in [x["title"] for x in register(client, ed)]
    assert "Low" in [x["title"] for x in register(client, ed, include_retired=True)]
    assert old["risk_number"] < new["risk_number"]


# ---- 9. nothing cascades -----------------------------------------------------------------------------------------------
def test_a_live_risk_blocks_retiring_what_it_points_at_and_restore_needs_them(client, ed):
    owner = role(client, ed)
    s = sol(client, ed)
    r = risk(client, ed, owner, solution_id=s["solution_id"])
    out = client.delete(f"{API}/org-roles/{owner['org_role_id']}", headers=ed["h"],
                        params={"row_version": owner["row_version"]})
    assert out.status_code == 409 and r["risk_number"] in out.json()["detail"]
    assert retire(client, ed, r).status_code == 204
    assert client.delete(f"{API}/solutions/{s['solution_id']}", headers=ed["h"],
                         params={"row_version": s["row_version"]}).status_code == 204
    assert client.patch(f"{API}/risks/{r['risk_id']}/restore", headers=ed["h"]).status_code == 409


def test_a_live_risk_on_a_step_blocks_the_step_retire(client, ed):
    owner = role(client, ed)
    area = node(client, ed, "Sales")
    group = node(client, ed, "Order to cash", area["bfc_node_id"])
    step = node(client, ed, "Take order", group["bfc_node_id"], is_process=True)
    r = risk(client, ed, owner, bfc_node_id=step["bfc_node_id"])
    out = client.delete(f"{API}/bfc-nodes/{step['bfc_node_id']}", headers=ed["h"],
                        params={"row_version": step["row_version"]})
    assert out.status_code == 409 and r["risk_number"] in out.json()["detail"], out.text
