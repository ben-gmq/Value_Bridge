"""Slice Benefits — register, links, value ranking and the benefit gap through the API (docs/slice_benefits_spec.md
§10 criteria 1–8, 11; design criteria 59, 60, 128, 130). Grade 2: a wrong ranking or gap reaches a steering meeting
and is corrected once noticed.

Deliberately uncovered (plan §8): a true two-connection race on the 100 % cap (the FOR UPDATE lock is exercised
sequentially; the database guard FKs carry the solution-retire race and are proven directly); values near the
numeric(18,2) limit."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models import AuditEvent
from services import benefit as benefit_service
from tests.conftest import ALL_COMPONENTS
from tests.test_components import switch
from tests.test_control import panel, role, row
from tests.test_effort_api import rate
from tests.test_function_requirement_api import fr
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import sol


def benefit(client, ed, owner, name="Lower DSO", unit="THB", base="100", target="160", typ="COST_REDUCTION",
            expect=201, headers=None, project=None, **kw):
    body = {"benefit_name": name, "benefit_type_code": typ, "measure_name": "Measure", "measure_unit": unit,
            "baseline_value": base, "target_value": target, "accountable_org_role_id": owner["org_role_id"], **kw}
    r = client.post(f"{API}/projects/{project or ed['p']}/benefits", headers=headers or ed["h"], json=body)
    assert r.status_code == expect, r.text
    return r.json()


def get(client, ed, b):
    return client.get(f"{API}/benefits/{b['benefit_id']}", headers=ed["h"]).json()


def edit(client, ed, b, expect=200, **body):
    rv = get(client, ed, b)["row_version"]
    out = client.patch(f"{API}/benefits/{b['benefit_id']}", headers=ed["h"], json={"row_version": rv, **body})
    assert out.status_code == expect, out.text
    return out.json()


def put(client, ed, b, s, pct, expect=200, headers=None):
    r = client.put(f"{API}/benefits/{b['benefit_id']}/solutions/{s['solution_id']}", headers=headers or ed["h"],
                   json={"contribution_pct": str(pct)})
    assert r.status_code == expect, r.text
    return r.json()


def ranking(client, ed):
    r = client.get(f"{API}/projects/{ed['p']}/value-ranking", headers=ed["h"])
    assert r.status_code == 200, r.text
    return r.json()


def gap(client, ed):
    r = client.get(f"{API}/projects/{ed['p']}/benefit-gap", headers=ed["h"])
    assert r.status_code == 200, r.text
    return r.json()


def worked(client, ed, name, n_rated=1, n_unrated=0, category="PEOPLE"):
    """A solution with `n_rated` rated FORM FRs (SIMPLE) and `n_unrated` unrated ones."""
    s = sol(client, ed, name, category)
    for i in range(n_rated + n_unrated):
        f = fr(client, ed, f"{name} form {i}", "FORM", solution_id=s["solution_id"])
        if i < n_rated:
            assert rate(client, ed, f, "SIMPLE").status_code == 200
    return s


def retire_solution(client, ed, s):
    rv = client.get(f"{API}/solutions/{s['solution_id']}", headers=ed["h"]).json()["row_version"]
    return client.delete(f"{API}/solutions/{s['solution_id']}", headers=ed["h"], params={"row_version": rv})


def reject(client, ed, s):
    rv = client.get(f"{API}/solutions/{s['solution_id']}", headers=ed["h"]).json()["row_version"]
    r = client.patch(f"{API}/solutions/{s['solution_id']}", headers=ed["h"],
                     json={"row_version": rv, "status_code": "REJECTED"})
    assert r.status_code == 200, r.text


def unit_of(out, key):
    return next(u for u in out["units"] if u["unit_key"] == key)


# ---- the register (criteria 1, 2, 3) -------------------------------------------------------------------------------
def test_create_mints_a_number_starts_forecast_and_audits_no_text(client, ed, db):
    owner = role(client, ed)
    b = benefit(client, ed, owner, benefit_number="BEN-9999", status_code="REALISED")      # derived values dropped
    assert (b["benefit_number"], b["status_code"], b["status_behaviour"]) == ("BEN-0001", "FORECAST", "LIVE")
    assert b["accountable_org_role_code"] == "PMO" and b["link_total_pct"] == "0.00"
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "BENEFIT_CREATED")).one()
    assert ev.detail["benefit_number"] == "BEN-0001" and "Lower DSO" not in str(ev.detail)       # R7
    assert "THB" not in str(ev.detail)


def test_no_accountable_role_is_422_and_the_column_is_not_null(client, ed, db):
    """Criterion 59."""
    r = client.post(f"{API}/projects/{ed['p']}/benefits", headers=ed["h"],
                    json={"benefit_name": "X", "benefit_type_code": "REVENUE", "measure_name": "M",
                          "measure_unit": "THB", "baseline_value": "1", "target_value": "2"})
    assert r.status_code == 422
    assert db.execute(text("SELECT is_nullable FROM information_schema.columns WHERE table_name = 'benefit' "
                           "AND column_name = 'accountable_org_role_id'")).scalar_one() == "NO"


def test_target_equal_to_baseline_is_refused_by_the_api_and_the_database(client, ed, db):
    """BN-1."""
    owner = role(client, ed)
    r = client.post(f"{API}/projects/{ed['p']}/benefits", headers=ed["h"],
                    json={"benefit_name": "X", "benefit_type_code": "REVENUE", "measure_name": "M",
                          "measure_unit": "THB", "baseline_value": "5", "target_value": "5.00",
                          "accountable_org_role_id": owner["org_role_id"]})
    assert r.status_code == 422 and "differ" in r.json()["detail"]
    b = benefit(client, ed, owner)
    edit(client, ed, b, 422, target_value="100")
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE benefit SET target_value = baseline_value WHERE benefit_id = :b"),
                   {"b": b["benefit_id"]})
    db.rollback()


def test_a_foreign_or_retired_accountable_role_and_blank_names_are_422(client, ed, world):
    owner = role(client, ed)
    other = role(client, {"h": world["admin"], "p": world["p_sales"]}, code="EXT")
    benefit(client, ed, other, expect=422)
    benefit(client, ed, owner, name="   ", expect=422)
    b = benefit(client, ed, owner)
    edit(client, ed, b, 422, measure_unit="  ")


def test_twenty_concurrent_creates_mint_ben_0001_to_0020(client, ed, world):
    """Criterion 130."""
    owner = role(client, ed)
    actor = world["users"]["editor"]

    def make(i):
        with SessionLocal() as s:
            b = benefit_service.create_benefit(s, actor, ed["p"], {
                "benefit_name": f"B{i}", "benefit_type_code": "REVENUE", "measure_name": "M", "measure_unit": "THB",
                "baseline_value": Decimal(0), "target_value": Decimal(i + 1),
                "accountable_org_role_id": owner["org_role_id"]})
            return b.benefit_number

    with ThreadPoolExecutor(max_workers=8) as pool:
        numbers = sorted(pool.map(make, range(20)))
    assert numbers == [f"BEN-{n:04d}" for n in range(1, 21)]


def test_status_moves_by_code_and_abandoned_carries_its_behaviour(client, ed):
    owner = role(client, ed)
    b = benefit(client, ed, owner)
    out = edit(client, ed, b, status_code="ABANDONED")
    assert (out["status_code"], out["status_behaviour"]) == ("ABANDONED", "ABANDONED")
    assert [x["benefit_number"] for x in client.get(f"{API}/projects/{ed['p']}/benefits", headers=ed["h"],
                                                    params={"status": "ABANDONED"}).json()] == ["BEN-0001"]
    edit(client, ed, b, 400, status_code="NOPE")


def test_values_of_an_increase_and_a_reduction(client, ed):
    """Criterion 128 / BN-1: 100 → 160 at 50 % is 30; 10 → 6 at 100 % is 4."""
    owner = role(client, ed)
    s1, s2 = sol(client, ed, "Billing"), sol(client, ed, "Dunning")
    up = benefit(client, ed, owner, base="100", target="160")
    down = benefit(client, ed, owner, unit="hours", base="10", target="6")
    assert put(client, ed, up, s1, 50)["value"] == "30.00"
    assert put(client, ed, down, s2, 100)["value"] == "4.00"


# ---- links (criteria 6, 7) -----------------------------------------------------------------------------------------
def test_links_cap_at_100_and_reweight_restores_and_idempotent(client, ed, db):
    owner = role(client, ed)
    b = benefit(client, ed, owner)
    s1, s2, s3 = sol(client, ed, "A"), sol(client, ed, "B"), sol(client, ed, "C")
    first = put(client, ed, b, s1, 60)
    put(client, ed, b, s2, 40)
    r = client.put(f"{API}/benefits/{b['benefit_id']}/solutions/{s3['solution_id']}", headers=ed["h"],
                   json={"contribution_pct": "0.01"})
    assert r.status_code == 409 and "100.00" in r.json()["detail"]                       # names the total
    assert put(client, ed, b, s1, 50)["benefit_solution_id"] == first["benefit_solution_id"]   # re-weight own row
    put(client, ed, b, s1, 50)                                                           # same % twice
    events = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "BENEFIT_SOLUTION_LINKED")).all()
    assert len(events) == 3
    assert client.delete(f"{API}/benefits/{b['benefit_id']}/solutions/{s1['solution_id']}",
                         headers=ed["h"]).status_code == 204
    again = put(client, ed, b, s1, 10)
    assert again["benefit_solution_id"] == first["benefit_solution_id"]                  # S1-7: the same row
    out = get(client, ed, b)
    assert (out["link_total_pct"], out["linked_solutions"]) == ("50.00", [s1["solution_number"], s2["solution_number"]])
    put(client, ed, b, s3, 0, expect=422)
    put(client, ed, b, s3, "100.5", expect=422)


def test_foreign_or_missing_solution_is_404_and_a_retired_one_409(client, ed, world):
    owner = role(client, ed)
    b = benefit(client, ed, owner)
    foreign = sol(client, ed, "Elsewhere", headers=world["admin"], project=world["p_sales"])
    put(client, ed, b, foreign, 10, expect=404)
    put(client, ed, b, {"solution_id": 99_999_999}, 10, expect=404)
    s = sol(client, ed, "Gone")
    assert retire_solution(client, ed, s).status_code == 204
    put(client, ed, b, s, 10, expect=409)


def test_the_database_refuses_a_live_link_under_a_retired_solution(client, ed, db):
    """Criterion 6 / R1-M1: with the service check skipped, the guard FK still refuses."""
    owner = role(client, ed)
    b, s = benefit(client, ed, owner), sol(client, ed, "Held")
    put(client, ed, b, s, 25)
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE solution SET is_active = false WHERE solution_id = :s"), {"s": s["solution_id"]})
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE benefit SET is_active = false WHERE benefit_id = :b"), {"b": b["benefit_id"]})
    db.rollback()


def test_retires_are_refused_while_links_live_naming_both_ends(client, ed):
    owner = role(client, ed)
    b, s = benefit(client, ed, owner), sol(client, ed, "Held")
    put(client, ed, b, s, 25)
    r = retire_solution(client, ed, s)
    assert r.status_code == 409 and f"BEN-0001 ↔ {s['solution_number']}" in r.json()["detail"]
    rv = get(client, ed, b)["row_version"]
    r = client.delete(f"{API}/benefits/{b['benefit_id']}", headers=ed["h"], params={"row_version": rv})
    assert r.status_code == 409
    rv_role = owner["row_version"]
    r = client.delete(f"{API}/org-roles/{owner['org_role_id']}", headers=ed["h"], params={"row_version": rv_role})
    assert r.status_code == 409 and "BEN-0001" in r.json()["detail"]                    # apple L1
    client.delete(f"{API}/benefits/{b['benefit_id']}/solutions/{s['solution_id']}", headers=ed["h"])
    rv = get(client, ed, b)["row_version"]
    assert client.delete(f"{API}/benefits/{b['benefit_id']}", headers=ed["h"],
                         params={"row_version": rv}).status_code == 204
    r = client.patch(f"{API}/benefits/{b['benefit_id']}/restore", headers=ed["h"])
    assert r.status_code == 200 and r.json()["benefit_number"] == "BEN-0001"


def test_the_solution_page_lists_its_benefits(client, ed):
    owner = role(client, ed)
    s = sol(client, ed, "Billing")
    put(client, ed, benefit(client, ed, owner), s, 50)
    out = client.get(f"{API}/solutions/{s['solution_id']}/benefits", headers=ed["rv"]).json()
    assert [(x["benefit_number"], x["contribution_pct"], x["value"]) for x in out] == [("BEN-0001", "50.00", "30.00")]


# ---- value ranking (criteria 3, 4, 5) ------------------------------------------------------------------------------
def test_two_units_rank_apart_and_the_bottom_quartile_is_a_candidate_unless_it_delivers_elsewhere(client, ed):
    """Criteria 60, 128: high value per day above low; four ranked → the last is the candidate."""
    owner = role(client, ed)
    sols = [worked(client, ed, n) for n in ("S1", "S2", "S3", "S4")]
    b = benefit(client, ed, owner, base="0", target="1000")
    for s, pct in zip(sols, (40, 30, 20, 10)):
        put(client, ed, b, s, pct)
    thb = unit_of(ranking(client, ed), "thb")
    assert [r["solution_number"] for r in thb["ranked"]] == [s["solution_number"] for s in sols]
    assert [r["displacement_candidate"] for r in thb["ranked"]] == [False, False, False, True]
    hours = benefit(client, ed, owner, unit=" Hours ", base="10", target="6")
    put(client, ed, hours, sols[3], 100)
    out = ranking(client, ed)
    assert sorted(u["unit_key"] for u in out["units"]) == ["hours", "thb"]           # never a mixed ratio
    last = unit_of(out, "thb")["ranked"][-1]
    assert (last["bottom_quartile"], last["displacement_candidate"]) == (True, False)
    assert last["also_delivers"] == [{"unit": "Hours", "value": "4.00"}]
    assert unit_of(out, "hours")["ranked"][0]["value"] == "4.00"                     # that unit's value only


def test_partly_rated_no_work_untagged_and_reconciliation(client, ed):
    """Criterion 5 / R1-H1, R2-M1."""
    owner = role(client, ed)
    full, partly, empty = worked(client, ed, "Full"), worked(client, ed, "Partly", 1, 3), sol(client, ed, "Empty")
    lonely = worked(client, ed, "Lonely")                                            # effort, no benefit
    rejected = worked(client, ed, "Rejected")
    loose = fr(client, ed, "Untagged form", "FORM")
    assert rate(client, ed, loose, "SIMPLE").status_code == 200
    b = benefit(client, ed, owner)
    for s in (full, partly, empty, rejected):
        put(client, ed, b, s, 20)
    reject(client, ed, rejected)
    out = ranking(client, ed)
    thb = unit_of(out, "thb")
    assert [r["solution_number"] for r in thb["ranked"]] == [full["solution_number"]]
    assert [(r["solution_number"], r["rated_count"], r["fr_count"]) for r in thb["partly_rated"]] == [
        (partly["solution_number"], 1, 4)]
    assert [r["solution_number"] for r in thb["no_work"]] == [empty["solution_number"]]
    assert thb["benefits"] == [{"benefit_id": b["benefit_id"], "benefit_number": "BEN-0001",
                                "unassigned_pct": "40.00", "on_rejected_pct": "20.00"}]
    day = Decimal(thb["ranked"][0]["effort_days"])
    assert Decimal(out["untagged_effort_days"]) == day
    rec = out["reconciliation"]
    assert Decimal(rec["difference"]) == 0 and Decimal(rec["rejected"]) == day
    assert Decimal(rec["no_benefit"]) == day                                          # Lonely
    assert Decimal(rec["with_value"]) == 2 * day                                      # Full + Partly's rated one
    assert lonely["solution_number"] not in str(thb)


def test_effort_off_ranks_nothing_and_shows_values(client, ed, world):
    owner = role(client, ed)
    switch(client, world, ed["p"], [c for c in ALL_COMPONENTS if c not in ("EFFORT", "CHANGE_REQUEST")])
    s = sol(client, ed, "Billing")
    fr(client, ed, "Form", "FORM", solution_id=s["solution_id"])
    put(client, ed, benefit(client, ed, owner), s, 50)
    out = ranking(client, ed)
    assert (out["measured"], out["reason"], out["reconciliation"]) == (False, "EFFORT_OFF", None)
    assert unit_of(out, "thb")["ranked"] == [] and unit_of(out, "thb")["values"][0]["value"] == "30.00"
    assert gap(client, ed)["headline"]["reason"] == "EFFORT_OFF"


# ---- benefit gap and the house rule (criteria 7, 8) ----------------------------------------------------------------
def test_gap_is_25_percent_escalates_and_unrated_work_counts(client, ed):
    owner = role(client, ed)
    sols = [worked(client, ed, n) for n in ("S1", "S2", "S3")]
    bare = worked(client, ed, "Bare", 0, 2)                                           # only unrated FRs
    sol(client, ed, "No work")                                                       # carries no work: not counted
    b = benefit(client, ed, owner)
    for s in sols:
        put(client, ed, b, s, 10)
    g = gap(client, ed)
    assert (g["headline"]["measured"], g["headline"]["carrying_count"]) == ("25.00", 4)
    assert [x["solution_number"] for x in g["gap"]] == [bare["solution_number"]]
    r = row(panel(client, ed), "benefit_gap")
    assert (r["measured"], r["verdict"]) == ("25.00", "ESCALATE")


def test_abandoned_benefits_and_rejected_solutions_leave_ranking_and_gap(client, ed):
    owner = role(client, ed)
    a, z = worked(client, ed, "A"), worked(client, ed, "Z")
    b = benefit(client, ed, owner)
    put(client, ed, b, a, 50)
    put(client, ed, b, z, 50)
    reject(client, ed, z)
    g = gap(client, ed)
    assert (g["headline"]["measured"], g["headline"]["carrying_count"]) == ("0.00", 1)
    edit(client, ed, b, status_code="ABANDONED")
    assert ranking(client, ed)["units"] == []
    g = gap(client, ed)
    assert [x["solution_number"] for x in g["gap"]] == [a["solution_number"]] and g["headline"]["measured"] == "100.00"


def test_fragile_benefits_lean_only_on_technology(client, ed):
    owner = role(client, ed)
    tech = sol(client, ed, "Platform", "TECHNOLOGY")
    b = benefit(client, ed, owner)
    put(client, ed, b, tech, 50)
    assert [x["benefit_number"] for x in gap(client, ed)["fragile"]] == ["BEN-0001"]
    put(client, ed, b, sol(client, ed, "Training", "PEOPLE"), 10)
    assert gap(client, ed)["fragile"] == []


# ---- component and access (criterion 11) ---------------------------------------------------------------------------
def test_benefit_off_refuses_writes_and_cannot_be_switched_off_under_a_live_benefit(client, ed, world):
    owner = role(client, ed)
    b = benefit(client, ed, owner)
    blocked = switch(client, world, ed["p"], [c for c in ALL_COMPONENTS if c != "BENEFIT"])
    assert blocked.status_code == 409 and "BEN-0001" in blocked.json()["detail"]
    rv = get(client, ed, b)["row_version"]
    assert client.delete(f"{API}/benefits/{b['benefit_id']}", headers=ed["h"],
                         params={"row_version": rv}).status_code == 204
    switch(client, world, ed["p"], [c for c in ALL_COMPONENTS if c != "BENEFIT"])
    r = client.post(f"{API}/projects/{ed['p']}/benefits", headers=ed["h"], json={})
    assert r.status_code == 409 and r.headers.get("X-VB-Error") == "COMPONENT_OFF"
    assert gap(client, ed)["headline"]["reason"] == "BENEFIT_OFF"
    assert ranking(client, ed)["reason"] == "BENEFIT_OFF"


def test_viewers_read_but_never_write_and_outsiders_see_nothing(client, ed):
    owner = role(client, ed)
    b = benefit(client, ed, owner)
    s = sol(client, ed, "Billing")
    benefit(client, ed, owner, headers=ed["rv"], expect=403)
    put(client, ed, b, s, 10, headers=ed["rv"], expect=403)
    assert client.get(f"{API}/benefits/{b['benefit_id']}", headers=ed["rv"]).status_code == 200
    for path in (f"/benefits/{b['benefit_id']}", f"/projects/{ed['p']}/benefits",
                 f"/projects/{ed['p']}/value-ranking", f"/projects/{ed['p']}/benefit-gap",
                 f"/solutions/{s['solution_id']}/benefits"):
        assert client.get(f"{API}{path}", headers=ed["out"]).status_code == 404, path
