"""Control-B2: organisation impact and stakeholder engagement, their panel rows (docs/slice_control_b_spec.md §7 tests 2,
3; CB-2, CB-3; acceptance 73). Grade 2: a silent GREEN reaches a steering decision and is corrected once noticed.

Deliberately uncovered: weighting changes by solution category (assumption B2 — every change weighs the same); the
as-is RACI column beyond one case, as it is context and never counted."""
from models.control import REGISTRY
from services import components, control
from tests.test_br_fr import set_components
from tests.test_control import edit, panel, row
from tests.test_control_b import _as_is
from tests.test_migration_0052 import br_role, step_role
from tests.test_scope_api import API, ed, node  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol


def impact(client, ed, headers=None, expect=200):
    r = client.get(f"{API}/projects/{ed['p']}/org-impact", headers=headers or ed["rv"])
    assert r.status_code == expect, r.text
    return r.json()


def engagement(client, ed, headers=None, expect=200):
    r = client.get(f"{API}/projects/{ed['p']}/stakeholder-engagement", headers=headers or ed["rv"])
    assert r.status_code == expect, r.text
    return r.json()


def changes(client, ed, n, solution=None):
    """n process steps under one area, each BR answered by one live solution: n changes. Returns the BR ids."""
    group = node(client, ed, "Orders", node(client, ed, "Sales")["bfc_node_id"])["bfc_node_id"]
    steps = {node(client, ed, f"Step {i:02}", group, is_process=True)["bfc_node_id"] for i in range(n)}
    brs = [b["br_id"] for b in client.get(f"{API}/projects/{ed['p']}/business-requirements", headers=ed["h"]).json()
           if b["bfc_node_id"] in steps]
    s = solution or sol(client, ed, "Order portal", "TECHNOLOGY")
    for br in brs:
        assert link(client, ed, br, s["solution_id"]).status_code == 201
    return sorted(brs)


def unit(client, ed, code, parent=None):
    u = client.post(f"{API}/projects/{ed['p']}/org-units", headers=ed["h"],
                    json={"org_unit_code": code, "org_unit_name": f"Unit {code}", "parent_org_unit_id": parent})
    assert u.status_code == 201, u.text
    r = client.post(f"{API}/projects/{ed['p']}/org-roles", headers=ed["h"],
                    json={"org_unit_id": u.json()["org_unit_id"], "org_role_code": f"R{code}",
                          "org_role_name": f"{code} lead"})
    assert r.status_code == 201, r.text
    return {**u.json(), "role": r.json()}


def speak(client, ed, u, name=None):
    """A stakeholder in the unit raises one issue."""
    s = client.post(f"{API}/projects/{ed['p']}/stakeholders", headers=ed["h"],
                    json={"stakeholder_name": name or f"Person {u['org_unit_code']}", "org_unit_id": u["org_unit_id"]})
    assert s.status_code == 201, s.text
    i = client.post(f"{API}/projects/{ed['p']}/issues", headers=ed["h"],
                    json={"title": "Not consulted", "severity_code": "HIGH", "issue_type_code": "DATA",
                          "raised_by_stakeholder_id": s.json()["stakeholder_id"]})
    assert i.status_code == 201, i.text
    return i.json()


def units_by_code(out):
    return {u["org_unit_code"]: u for u in out["units"]}


# ---- 2. organisation impact ------------------------------------------------------------------------------------------
def test_responsible_or_accountable_counts_consulted_and_informed_do_not_and_the_40_60_boundaries(client, ed):
    brs = changes(client, ed, 5)
    fin, ops = unit(client, ed, "FIN"), unit(client, ed, "OPS")
    br_role(client, ed, brs[0], fin["role"], "A")
    br_role(client, ed, brs[1], fin["role"], "R")
    br_role(client, ed, brs[0], ops["role"], "R")
    br_role(client, ed, brs[2], ops["role"], "C")
    br_role(client, ed, brs[3], ops["role"], "I")
    out = impact(client, ed)
    got = units_by_code(out)
    assert (got["FIN"]["changes"], got["FIN"]["share"], got["FIN"]["ra_roles"]) == (2, "40.00", ["RFIN"])
    assert (got["OPS"]["changes"], got["OPS"]["share"], got["OPS"]["heard_only"]) == (1, "20.00", 2)
    assert out["headline"] == {"measured": "40.00", "reason": None, "top_unit": "Unit FIN", "changes": 5,
                               "changes_without_ra": 3, "units_on": 2}
    assert row(panel(client, ed), "org_impact_heatmap")["verdict"] == "GREEN"      # equal to the threshold
    br_role(client, ed, brs[2], fin["role"], "R")
    r = row(panel(client, ed), "org_impact_heatmap")
    assert (r["measured"], r["verdict"]) == ("60.00", "FLAG")                     # equal to escalate: FLAG
    br_role(client, ed, brs[3], fin["role"], "A")
    assert row(panel(client, ed), "org_impact_heatmap")["verdict"] == "ESCALATE"
    impact(client, ed, headers=ed["out"], expect=404)


def test_a_rejected_solution_is_not_a_change_and_a_unit_on_every_change_reads_100(client, ed):
    brs = changes(client, ed, 2)
    dropped = sol(client, ed, "Dropped idea", "PROCESS")
    r = client.patch(f"{API}/solutions/{dropped['solution_id']}", headers=ed["h"],
                     json={"row_version": dropped["row_version"], "status_code": "REJECTED"})
    assert r.status_code == 200, r.text
    billing = node(client, ed, "Invoicing", node(client, ed, "Billing")["bfc_node_id"])
    third = node(client, ed, "Step 99", billing["bfc_node_id"], is_process=True)
    br3 = next(b["br_id"] for b in client.get(f"{API}/projects/{ed['p']}/business-requirements",
                                              headers=ed["h"]).json() if b["bfc_node_id"] == third["bfc_node_id"])
    assert link(client, ed, br3, dropped["solution_id"]).status_code == 201
    fin, ops = unit(client, ed, "FIN"), unit(client, ed, "OPS")
    for br in (*brs, br3):
        br_role(client, ed, br, fin["role"], "R")
    br_role(client, ed, brs[0], ops["role"], "A")
    out = impact(client, ed)
    assert (out["headline"]["changes"], out["headline"]["measured"]) == (2, "100.00")
    assert units_by_code(out)["FIN"]["changes"] == 2


def test_org_impact_is_not_measured_without_solutions_changes_raci_or_two_units(client, ed, world):
    set_components(client, world, ed["p"], ["AS_IS"])                       # before any row needs it
    out = impact(client, ed)
    assert (out["headline"]["reason"], out["units"]) == ("SOLUTION_OFF", None)
    assert row(panel(client, ed), "org_impact_heatmap")["verdict"] == "NOT_MEASURED"
    set_components(client, world, ed["p"], ["SOLUTION", "ISSUE"])
    assert impact(client, ed)["headline"]["reason"] == "NO_CHANGES"
    brs = changes(client, ed, 2)
    fin = unit(client, ed, "FIN")
    assert impact(client, ed)["headline"]["reason"] == "NO_RA_ON_CHANGES"
    br_role(client, ed, brs[0], fin["role"], "R")
    h = impact(client, ed)["headline"]
    assert (h["reason"], h["measured"]) == ("FEWER_THAN_TWO_UNITS", None)    # a one-unit chart always reads 100 %
    unit(client, ed, "OPS")                                                  # holds a role, on nothing
    assert impact(client, ed)["headline"]["measured"] == "50.00"


def test_the_as_is_raci_is_shown_as_context_and_never_counted(client, ed, db):
    brs = changes(client, ed, 2)
    fin, ops = unit(client, ed, "FIN"), unit(client, ed, "OPS")
    br_role(client, ed, brs[0], fin["role"], "R")
    br_role(client, ed, brs[1], ops["role"], "R")
    url = f"{API}/projects/{ed['p']}/bfc-sets/AS_IS/copy-from/TO_BE"
    prev = client.post(url, headers=ed["h"], json={}).json()
    assert client.post(url, headers=ed["h"], json={"confirm_hash": prev["confirm_hash"]}).status_code == 200
    got = units_by_code(impact(client, ed))                                  # the copy carried the RACI over
    assert (got["FIN"]["as_is_steps"], got["OPS"]["as_is_steps"]) == (1, 1)
    step_role(client, ed, _as_is(db, ed, "Step 01"), fin["role"], "A")
    out = impact(client, ed)
    got = units_by_code(out)
    assert (got["FIN"]["changes"], got["FIN"]["as_is_steps"], got["OPS"]["as_is_steps"]) == (1, 2, 1)
    assert out["headline"]["measured"] == "50.00"


# ---- 3. stakeholder engagement ---------------------------------------------------------------------------------------
def test_a_direct_parent_gives_voice_and_a_grandparent_does_not(client, ed):
    brs = changes(client, ed, 4)
    hq = unit(client, ed, "HQ")
    sales = unit(client, ed, "SALES", hq["org_unit_id"])
    team = unit(client, ed, "TEAM", sales["org_unit_id"])
    br_role(client, ed, brs[0], sales["role"], "R")
    br_role(client, ed, brs[1], team["role"], "R")
    br_role(client, ed, brs[2], hq["role"], "A")
    assert engagement(client, ed)["headline"]["reason"] == "NO_ISSUES"       # an unused log is not silence
    assert row(panel(client, ed), "stakeholder_engagement")["verdict"] == "NOT_MEASURED"
    speak(client, ed, hq, "Head office sponsor")
    out = engagement(client, ed)
    got = units_by_code(out)
    assert (got["HQ"]["voice"], got["HQ"]["speakers"][0]["stakeholder_name"]) == ("OWN", "Head office sponsor")
    assert (got["SALES"]["voice"], got["SALES"]["parent_issues_raised"]) == ("PARENT", 1)
    assert got["TEAM"]["voice"] is None                                      # the grandparent does not speak for it
    assert out["headline"] == {"measured": "25.00", "reason": None, "top_unit": "Unit TEAM", "issues": 1,
                               "affected_units": 3, "silent_units": 1, "changes_without_ra": 1}   # sara M1
    assert row(panel(client, ed), "stakeholder_engagement")["verdict"] == "FLAG"
    speak(client, ed, team)
    out = engagement(client, ed)
    assert (out["headline"]["measured"], out["headline"]["silent_units"]) == ("0.00", 0)
    assert row(panel(client, ed), "stakeholder_engagement")["verdict"] == "GREEN"
    engagement(client, ed, headers=ed["out"], expect=404)


def test_acceptance_73_on_a_chart_of_twelve_units_and_the_10_25_boundaries(client, ed):
    """Twenty changes over twelve roughly equal units; every unit speaks except the ones under test."""
    brs = changes(client, ed, 20)
    us = [unit(client, ed, f"U{i:02}") for i in range(12)]
    loads = [2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 1]                            # 20 changes, one unit each
    i = 0
    for u, n in zip(us, loads):
        for _ in range(n):
            br_role(client, ed, brs[i], u["role"], "R")
            i += 1
    for u in us[1:]:
        speak(client, ed, u)
    r = row(panel(client, ed), "stakeholder_engagement")
    assert (r["measured"], r["verdict"]) == ("10.00", "GREEN")              # silent U00 on 2 of 20: equal to 10
    assert row(panel(client, ed), "org_impact_heatmap")["verdict"] == "GREEN"   # nothing concentrated
    for br in brs[8:11]:                                                    # U00 on 5 of 20 = 25 %
        br_role(client, ed, br, us[0]["role"], "A")
    r = row(panel(client, ed), "stakeholder_engagement")
    assert (r["measured"], r["verdict"], r["figures"]["top_unit"]) == ("25.00", "FLAG", "Unit U00")
    br_role(client, ed, brs[11], us[0]["role"], "A")                        # 6 of 20 = 30 %: acceptance 73
    assert row(panel(client, ed), "stakeholder_engagement")["verdict"] == "ESCALATE"
    edit(client, ed, "stakeholder_engagement", escalate_value="35")
    assert row(panel(client, ed), "stakeholder_engagement")["verdict"] == "FLAG"


def test_stakeholder_engagement_needs_issues_and_solutions_and_org_impact(client, ed, world):
    set_components(client, world, ed["p"], ["SOLUTION"])                     # before any row needs it
    assert engagement(client, ed)["headline"]["reason"] == "ISSUE_OFF"
    set_components(client, world, ed["p"], ["ISSUE"])
    out = engagement(client, ed)
    assert (out["headline"]["reason"], out["units"]) == ("SOLUTION_OFF", None)
    set_components(client, world, ed["p"], ["SOLUTION", "ISSUE"])
    brs = changes(client, ed, 1)
    fin = unit(client, ed, "FIN")
    br_role(client, ed, brs[0], fin["role"], "R")
    speak(client, ed, fin)
    assert engagement(client, ed)["headline"]["reason"] == "FEWER_THAN_TWO_UNITS"   # org impact's own reason


# ---- acceptance 74 ---------------------------------------------------------------------------------------------------
def test_every_registry_analysis_returns_a_headline_and_every_house_rule_is_built(ed, db):
    on = frozenset(components.enabled(db, ed["p"]))
    for code in REGISTRY:
        h = control.headline(db, ed["p"], code, on)
        assert set(h) == {"measured", "reason", "figures"}
        assert (h["reason"] == "NOT_BUILT") == (code not in control.ORDER), code
    assert len(control.ORDER) == 8
