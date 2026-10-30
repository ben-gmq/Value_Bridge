"""Control rules and the control panel (docs/slice_control_a_spec.md §6; D-19, CT-1…CT-4). Grade 2: a wrong verdict
reaches a steering decision and is corrected once noticed; every threshold change is audited.

Deliberately uncovered (spec §6): each headline is checked against its source report on one fixture only (the reports
have their own tests); concurrent edits beyond the row_version 409."""
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from models import AuditEvent, ControlRule
from services import control
from tests.conftest import owner_engine
from tests.test_baseline import approve, bid, freeze, scope
from tests.test_br_fr import lnk, set_components, two_brs
from tests.test_effort_api import rate
from tests.test_function_requirement_api import fr
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol

CODES = ["priced_diff", "coverage", "solution_matrix", "interface_load", "requirement_volatility", "data_migration_map"]


def panel(client, ed, headers=None, expect=200):
    r = client.get(f"{API}/projects/{ed['p']}/control-panel", headers=headers or ed["h"])
    assert r.status_code == expect, r.text
    return r.json()


def row(out, code):
    return next(r for r in out["rows"] if r["analysis_code"] == code)


def rules(client, ed):
    return {r["analysis_code"]: r for r in client.get(f"{API}/projects/{ed['p']}/control-rules", headers=ed["h"]).json()}


def edit(client, ed, code, expect=200, headers=None, **over):
    cur = rules(client, ed)[code]
    body = {f: cur[f] for f in control.EDITABLE}
    body.update({"change_rationale": "Agreed at mobilisation", "row_version": cur["row_version"]})
    body.update(over)
    r = client.patch(f"{API}/projects/{ed['p']}/control-rules/{code}", headers=headers or ed["h"], json=body)
    assert r.status_code == expect, r.text
    return r.json()


def role(client, ed, project=None, code="PMO"):
    p = project or ed["p"]
    u = client.post(f"{API}/projects/{p}/org-units", headers=ed["h"],
                    json={"org_unit_code": f"U{code}", "org_unit_name": f"Unit {code}"})
    assert u.status_code == 201, u.text
    r = client.post(f"{API}/projects/{p}/org-roles", headers=ed["h"],
                    json={"org_unit_id": u.json()["org_unit_id"], "org_role_code": code, "org_role_name": f"{code} lead"})
    assert r.status_code == 201, r.text
    return r.json()


# ---- 1. the table ----------------------------------------------------------------------------------------------------
def test_the_tiers_are_enforced_by_the_database(client, ed, world):
    """Two partial uniques, the house/owner/author CHECKs and the same-project owner FK (spec §2)."""
    other = role(client, {**ed, "p": world["p_sales"], "h": world["admin"]}, code="OTH")
    with owner_engine().connect() as c:
        def refused(sql):
            tx = c.begin()
            with pytest.raises(IntegrityError):
                c.execute(text(sql))
            tx.rollback()
        refused("INSERT INTO control_rule (project_id, analysis_code, comparison, threshold_value, is_house_default) "
                "VALUES (NULL, 'coverage', 'GT', 1, true)")                                   # second house row
        refused(f"INSERT INTO control_rule (project_id, analysis_code, comparison, threshold_value, is_house_default, "
                f"created_by) VALUES ({ed['p']}, 'coverage', 'GT', 1, false, 1)")             # second project row
        refused(f"INSERT INTO control_rule (project_id, analysis_code, comparison, threshold_value, is_house_default) "
                f"VALUES ({ed['p']}, 'risk_register', 'GT', 1, false)")                       # project row, no author
        refused("INSERT INTO control_rule (project_id, analysis_code, comparison, threshold_value, is_house_default) "
                "VALUES (NULL, 'risk_register', 'GT', 1, false)")                             # house flag wrong
        refused("INSERT INTO control_rule (project_id, analysis_code, comparison, threshold_value, is_house_default) "
                "VALUES (NULL, 'no_such_analysis', 'GT', 1, true)")
        refused("INSERT INTO control_rule (project_id, analysis_code, comparison, threshold_value, is_house_default) "
                "VALUES (NULL, 'risk_register', 'GE', 1, true)")
        refused(f"UPDATE control_rule SET owner_org_role_id = {other['org_role_id']} "
                f"WHERE project_id = {ed['p']} AND analysis_code = 'coverage'")              # another project's role


# ---- 2/3. seeding and create_project ---------------------------------------------------------------------------------
def test_a_new_project_gets_the_four_house_rules_unowned_and_unedited(client, ed, db):
    got = rules(client, ed)
    assert list(got) == CODES
    pd = got["priced_diff"]
    assert (Decimal(pd["threshold_value"]), Decimal(pd["escalate_value"]), pd["comparison"]) == (5, 10, "PCT_GT")
    assert got["coverage"]["escalate_value"] is None
    assert all(r["owner"] is None and r["last_changed_by"] is None and r["row_version"] == 1 for r in got.values())
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PROJECT_CREATED",
                                             AuditEvent.project_id == ed["p"])).one()
    assert ev.detail["control_rules"] == CODES


def test_the_house_tier_is_never_overwritten_and_the_backfill_adds_only_what_is_missing(client, ed, world, db):
    db.execute(text("UPDATE control_rule SET threshold_value = 7 WHERE project_id IS NULL "
                    "AND analysis_code = 'coverage'"))
    db.execute(text(f"UPDATE control_rule SET is_active = false WHERE project_id = {ed['p']} "
                    "AND analysis_code = 'interface_load'"))
    db.commit()
    with owner_engine().begin() as c:                            # the app role cannot delete: stage a missing rule
        c.execute(text(f"DELETE FROM control_rule WHERE project_id = {world['p_fin']} AND analysis_code = 'coverage'"))
    assert control.seed_house(db) == []
    db.commit()
    assert db.scalar(text("SELECT threshold_value FROM control_rule WHERE project_id IS NULL "
                          "AND analysis_code = 'coverage'")) == 7
    out = control.backfill(db, "admin@example.test")
    added = {r["project_id"]: r["added"] for r in out["projects"]}
    assert added[world["p_fin"]] == ["coverage"] and added[world["p_sales"]] == []
    assert added[ed["p"]] == []                                  # a retired rule is still the project's own
    assert control.backfill(db, "admin@example.test")["projects"] == [
        {"project_id": p["project_id"], "added": []} for p in out["projects"]]
    seeded = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "CONTROL_RULES_SEEDED")).all()
    assert [(e.project_id, e.detail["analysis_codes"]) for e in seeded] == [(world["p_fin"], ["coverage"])]
    with pytest.raises(SystemExit):
        control.backfill(db, "editor@example.test")


def test_create_project_is_refused_while_a_measurable_house_rule_is_missing(client, world):
    with owner_engine().begin() as c:
        c.execute(text("DELETE FROM control_rule WHERE project_id IS NULL AND analysis_code = 'interface_load'"))
    r = client.post(f"{API}/projects", headers=world["admin"], json={
        "client_id": world["client_id"], "project_code": "NEWP", "project_name": "New", "program_id": None,
        "component_codes": ["SOLUTION"], "is_restricted": False})
    assert r.status_code == 409 and "seed_control_rules" in r.json()["detail"]


# ---- 4. editing ------------------------------------------------------------------------------------------------------
def test_an_edit_needs_a_reason_and_audits_numbers_not_text(client, ed, db):
    pmo = role(client, ed)
    edit(client, ed, "priced_diff", expect=422, change_rationale="  ")
    out = edit(client, ed, "priced_diff", threshold_value="7.5", owner_org_role_id=pmo["org_role_id"],
               escalation_path="Escalate to J. Tanaka, CFO", change_rationale="Client asked for headroom")
    assert out["owner"] == {"org_role_code": "PMO", "org_role_name": "PMO lead"}
    assert out["last_changed_by"] == "Editor" and out["row_version"] == 2
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "CONTROL_RULE_CHANGED")).one()
    assert ev.detail == {"analysis_code": "priced_diff",
                         "from": {"threshold_value": "5", "owner_org_role_id": None},
                         "to": {"threshold_value": "7.5", "owner_org_role_id": pmo["org_role_id"]},
                         "text_changed": ["escalation_path"], "change_rationale": "Client asked for headroom"}
    assert "Tanaka" not in str(ev.detail)                                    # CT-3
    same = edit(client, ed, "priced_diff")                                    # nothing different: nothing written
    assert same["row_version"] == 2
    assert db.scalar(select(text("count(*)")).select_from(AuditEvent).where(
        AuditEvent.event_type == "CONTROL_RULE_CHANGED")) == 1


def test_agreed_at_is_not_moved_by_an_edit(client, ed):
    before = rules(client, ed)["coverage"]["agreed_at"]
    after = edit(client, ed, "coverage", threshold_value="3")
    assert after["agreed_at"] == before and after["last_changed_at"] is not None


def test_edit_refusals(client, ed, world):
    stale = rules(client, ed)["coverage"]["row_version"]
    edit(client, ed, "coverage", threshold_value="1")
    edit(client, ed, "coverage", expect=409, row_version=stale)
    r = client.patch(f"{API}/projects/{ed['p']}/control-rules/nonsense", headers=ed["h"], json={
        **{f: None for f in control.EDITABLE}, "threshold_value": "1", "is_enabled": True,
        "change_rationale": "x", "row_version": 1})
    assert r.status_code == 422
    r = client.patch(f"{API}/projects/{ed['p']}/control-rules/risk_register", headers=ed["h"], json={
        **{f: None for f in control.EDITABLE}, "threshold_value": "1", "is_enabled": True,
        "change_rationale": "x", "row_version": 1})
    assert r.status_code == 404                                               # in the registry, not on this project
    other = role(client, {**ed, "p": world["p_sales"], "h": world["admin"]}, code="OTH")
    edit(client, ed, "solution_matrix", expect=422, owner_org_role_id=other["org_role_id"])
    edit(client, ed, "solution_matrix", expect=422, escalate_value="70")     # equal to the threshold
    edit(client, ed, "solution_matrix", expect=422, escalate_value="60")     # on the wrong side
    edit(client, ed, "solution_matrix", expect=422, threshold_value="-1")
    edit(client, ed, "solution_matrix", expect=422, comparison="LT")         # server-set, not in the body
    edit(client, ed, "solution_matrix", expect=403, headers=ed["rv"])        # VIEW member, VIEWER kind
    edit(client, ed, "solution_matrix", expect=404, headers=ed["out"])       # restricted, not a member


def test_a_role_that_owns_a_rule_cannot_retire_until_the_rule_is_repointed(client, ed):
    pmo = role(client, ed)
    edit(client, ed, "coverage", owner_org_role_id=pmo["org_role_id"])
    cur = client.get(f"{API}/projects/{ed['p']}/org-roles", headers=ed["h"]).json()[0]
    r = client.delete(f"{API}/org-roles/{pmo['org_role_id']}", headers=ed["h"],
                      params={"row_version": cur["row_version"]})
    assert r.status_code == 409 and "coverage" in r.text, r.text
    edit(client, ed, "coverage", owner_org_role_id=None)
    r = client.delete(f"{API}/org-roles/{pmo['org_role_id']}", headers=ed["h"],
                      params={"row_version": cur["row_version"]})
    assert r.status_code in (200, 204), r.text


# ---- 5/6. headlines and verdicts -------------------------------------------------------------------------------------
def test_an_empty_project_measures_what_it_can(client, ed):
    out = panel(client, ed)
    assert [r["analysis_code"] for r in out["rows"]] == CODES
    assert (row(out, "priced_diff")["verdict"], row(out, "priced_diff")["reason"]) == ("NOT_MEASURED",
                                                                                       "NO_AGREED_BASELINE")
    assert (row(out, "coverage")["measured"], row(out, "coverage")["verdict"]) == ("0.00", "GREEN")
    assert row(out, "solution_matrix")["reason"] == "NO_SOLUTIONS"
    assert row(out, "interface_load")["reason"] == "NO_FRS"
    assert row(out, "requirement_volatility")["reason"] == "NO_BASELINE_PAIR"
    assert row(out, "data_migration_map")["reason"] == "NO_TO_BE_ENTITIES"
    assert [c["analysis_code"] for c in out["coming"]][:2] == ["org_impact_heatmap", "stakeholder_engagement"]
    panel(client, ed, headers=ed["rv"])                                      # VIEW reads it
    panel(client, ed, headers=ed["out"], expect=404)


def test_components_off_are_not_measured_never_zero(client, ed, world):
    set_components(client, world, ed["p"], ["AS_IS"])
    out = panel(client, ed)
    assert {r["analysis_code"]: r["reason"] for r in out["rows"]} == {
        "priced_diff": "NO_AGREED_BASELINE", "coverage": "COMPONENTS_OFF", "solution_matrix": "SOLUTION_OFF",
        "interface_load": "FUNCTION_REQUIREMENT_OFF", "requirement_volatility": "NO_BASELINE_PAIR",
        "data_migration_map": "APPLICATION_OFF"}
    assert {r["verdict"] for r in out["rows"]} == {"NOT_MEASURED"}


def test_interface_share_and_technology_share_against_their_thresholds(client, ed):
    for i in range(3):
        fr(client, ed, f"Form {i}")
    fr(client, ed, "Feed to ERP", "INTERFACE")                               # 1 of 4 = 25 %: equal is GREEN
    out = panel(client, ed)
    assert (row(out, "interface_load")["measured"], row(out, "interface_load")["verdict"]) == ("25.00", "GREEN")
    assert row(out, "interface_load")["figures"] == {"interface_count": 1, "fr_count": 4}
    fr(client, ed, "Feed to bank", "INTERFACE")                              # 2 of 5 = 40 % > 35
    assert row(panel(client, ed), "interface_load")["verdict"] == "ESCALATE"
    edit(client, ed, "interface_load", escalate_value=None)                  # never escalates: FLAG
    assert row(panel(client, ed), "interface_load")["verdict"] == "FLAG"
    edit(client, ed, "interface_load", is_enabled=False)
    off = row(panel(client, ed), "interface_load")
    assert (off["verdict"], off["measured"], off["off_state"]) == (None, "40.00", "SWITCHED_OFF")   # CB-5
    for name in ("Portal", "Engine", "Mobile"):
        sol(client, ed, name, "TECHNOLOGY")
    sol(client, ed, "Approval matrix", "PEOPLE")                             # 3 of 4 = 75 %
    sm = row(panel(client, ed), "solution_matrix")
    assert (sm["measured"], sm["verdict"]) == ("75.00", "FLAG")


def test_coverage_counts_warning_rows_only(client, ed):
    b1, b2, _, _ = two_brs(client, ed)                                       # BRs with no FR: information only
    assert row(panel(client, ed), "coverage")["measured"] == "0.00"
    fr(client, ed, "Untraced form")                                          # fr_without_br is a warning
    cov = row(panel(client, ed), "coverage")
    assert (cov["measured"], cov["verdict"]) == ("1.00", "FLAG")


def test_priced_diff_from_the_agreed_baseline_and_uncosted_growth(client, ed):
    """A1 net growth from the APPROVED baseline; CT-2 an unrated added FR lifts GREEN to FLAG; round 2 N1 a removed
    unrated FR does not."""
    b1 = scope(client, ed)["br1"]                                            # freeze-ready steps
    s = sol(client, ed, "Portal", "TECHNOLOGY")
    link(client, ed, b1["br_id"], s["solution_id"])
    rated = [fr(client, ed, f"Form {i}", solution_id=s["solution_id"]) for i in range(2)]
    for f in rated:
        lnk(client, ed, b1, f)
        assert rate(client, ed, f, "MEDIUM").status_code == 200
    gone = fr(client, ed, "Unrated, later retired", solution_id=s["solution_id"])
    b = freeze(client, ed)
    out = panel(client, ed)
    assert row(out, "priced_diff")["reason"] == "NO_AGREED_BASELINE"         # frozen is not agreed
    approve(client, ed, bid(b))
    pd = row(panel(client, ed), "priced_diff")
    assert (pd["measured"], pd["verdict"], pd["figures"]["unrated_count"]) == ("0.00", "GREEN", 0)
    base = pd["figures"]["base_days"]
    retire = client.get(f"{API}/function-requirements/{gone['fr_id']}", headers=ed["h"]).json()
    r = client.delete(f"{API}/function-requirements/{gone['fr_id']}", headers=ed["h"],
                      params={"row_version": retire["row_version"]})
    assert r.status_code in (200, 204), r.text
    pd = row(panel(client, ed), "priced_diff")
    assert (pd["verdict"], pd["figures"]["unrated_count"]) == ("GREEN", 0)  # N1: removed unrated is not growth
    fr(client, ed, "New, not yet rated", solution_id=s["solution_id"])
    pd = row(panel(client, ed), "priced_diff")
    assert (pd["measured"], pd["verdict"], pd["figures"]["unrated_count"]) == ("0.00", "FLAG", 1)   # CT-2
    extra = fr(client, ed, "New and rated", solution_id=s["solution_id"])
    assert rate(client, ed, extra, "MEDIUM").status_code == 200
    pd = row(panel(client, ed), "priced_diff")
    growth = Decimal(pd["figures"]["net_days"]) * 100 / Decimal(str(base))
    assert Decimal(pd["measured"]) == growth.quantize(Decimal("0.01")) and pd["verdict"] == "ESCALATE"   # 50 %


def test_a_damaged_agreed_baseline_blanks_its_own_row_only(client, ed, monkeypatch):
    fr(client, ed, "Form")
    b = freeze(client, ed)
    approve(client, ed, bid(b))
    monkeypatch.setattr(control.baseline, "verify", lambda db, b: False)
    out = panel(client, ed)
    assert row(out, "priced_diff")["reason"] == "BASELINE_DAMAGED"
    assert row(out, "interface_load")["verdict"] == "GREEN"


def test_verdict_boundaries_for_each_comparison():
    def v(measured, threshold, escalate=None, comparison="GT", code="coverage", **fig):
        r = ControlRule(analysis_code=code, comparison=comparison, threshold_value=Decimal(threshold),
                        escalate_value=None if escalate is None else Decimal(escalate), is_enabled=True)
        return control.verdict(r, control._measure(measured, **fig))
    assert v(5, 5, 10) == "GREEN" and v("5.01", 5, 10) == "FLAG" and v(10, 5, 10) == "FLAG"
    assert v("10.01", 5, 10) == "ESCALATE" and v(1000, 5) == "FLAG"
    assert v(5, 5, 2, "LT") == "GREEN" and v("4.99", 5, 2, "LT") == "FLAG" and v(1, 5, 2, "LT") == "ESCALATE"
    assert v(None, 5) == "NOT_MEASURED"
    assert v(1, 5, code="priced_diff", unrated_count=2) == "FLAG"
