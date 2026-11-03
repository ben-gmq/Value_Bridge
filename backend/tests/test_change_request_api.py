"""Slice Change requests through the API (docs/slice_change_requests_spec.md §7 criteria 1–12; design criteria 63–66,
190, 192). Grade 2: a wrong price or a gate that lets an uncovered increase through puts wrong figures in front of a
steering meeting and into the decision log; it is recoverable (a new change request corrects it).

Rate card (FTC default): FORM SIMPLE 2 / MEDIUM 4 · INTERFACE SIMPLE 3 · BATCH MEDIUM 5 / COMPLEX 10 days.

Deliberately uncovered (plan §4): a trace over thousands of links (no performance test); a target frozen before hash
spec 2; the D2-2 midnight edge; a true two-connection race on the seed overlap (the FOR UPDATE lock is exercised
sequentially; the cut race is proven at the database's unique index)."""
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from models import AuditEvent, Decision
from tests.conftest import ALL_COMPONENTS
from tests.test_application_api import app
from tests.test_baseline import approve, bid, freeze, preview, scope
from tests.test_benefit_api import benefit, put as put_link
from tests.test_components import switch
from tests.test_control import role
from tests.test_effort_api import rate
from tests.test_function_requirement_api import fr
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link as link_solution, sol


# ---- helpers ---------------------------------------------------------------------------------------------------------
def without(client, world, ed, *off):
    """Every component on except `off` (the admin's confirmed switch)."""
    return switch(client, world, ed["p"], [c for c in ALL_COMPONENTS if c not in off])


def link_fr(client, ed, br, f):
    r = client.post(f"{API}/business-requirements/{br['br_id']}/function-requirements", headers=ed["h"],
                    json={"fr_id": f["fr_id"]})
    assert r.status_code in (200, 201), r.text


def raise_cr(client, ed, target, expect=201, headers=None, project=None, **kw):
    body = {"title": "Add credit check", "rationale": "Client asked at steering", "origin_code": "CLIENT",
            "against_baseline_id": target, **kw}
    r = client.post(f"{API}/projects/{project or ed['p']}/change-requests", headers=headers or ed["h"], json=body)
    assert r.status_code == expect, r.text
    return r.json()


def get(client, ed, cr, headers=None):
    r = client.get(f"{API}/change-requests/{cr['change_request_id']}", headers=headers or ed["h"])
    assert r.status_code == 200, r.text
    return r.json()


def seeds(client, ed, cr, items, expect=200, headers=None):
    """items: [(obj, 'ADD'|'MODIFY'|'REMOVE')] where obj is a BR (br_id) or an FR (fr_id)."""
    body = [{("fr_id" if "fr_id" in o else "br_id"): o.get("fr_id", o.get("br_id")), "impact_type_code": t}
            for o, t in items]
    r = client.put(f"{API}/change-requests/{cr['change_request_id']}/seeds", headers=headers or ed["h"],
                   json={"row_version": get(client, ed, cr)["row_version"], "seeds": body})
    assert r.status_code == expect, r.text
    return r.json()


def analyse(client, ed, cr, expect=200):
    r = client.post(f"{API}/change-requests/{cr['change_request_id']}/analyse", headers=ed["h"],
                    json={"row_version": get(client, ed, cr)["row_version"]})
    assert r.status_code == expect, r.text
    return r.json()


def decide(client, ed, cr, outcome="APPROVED", expect=200, headers=None, **kw):
    body = {"row_version": get(client, ed, cr)["row_version"], "outcome_code": outcome,
            "rationale": "Agreed at steering", "alternative_rejected": "Defer to wave 2", **kw}
    r = client.post(f"{API}/change-requests/{cr['change_request_id']}/decide", headers=headers or ed["h"], json=body)
    assert r.status_code == expect, r.text
    return r.json()


def rated(client, ed, name, fr_type, cx, solution=None):
    f = fr(client, ed, name, fr_type, solution_id=solution["solution_id"] if solution else None)
    assert rate(client, ed, f, cx).status_code == 200
    return f


def cr_world(client, ed, approved=True):
    """v1.0 holds BR1 (linked to SOL-0001, which carries KEEP FORM 2 d, GONE INTERFACE 3 d and TRACED BATCH 10 d, all
    three linked to BR1). Approved by the client unless asked otherwise."""
    sc = scope(client, ed)
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    assert link_solution(client, ed, sc["br1"]["br_id"], s["solution_id"]).status_code == 201
    keep = rated(client, ed, "Order form", "FORM", "SIMPLE", s)
    gone = rated(client, ed, "Legacy feed", "INTERFACE", "SIMPLE", s)
    traced = rated(client, ed, "Nightly batch", "BATCH", "COMPLEX", s)
    for f in (keep, gone, traced):
        link_fr(client, ed, sc["br1"], f)
    v10 = bid(freeze(client, ed))
    if approved:
        approve(client, ed, v10)
    return {**sc, "sol": s, "keep": keep, "gone": gone, "traced": traced, "v10": v10}


def priced_cr_world(client, ed):
    """Criterion 5's change: ADD 5 d + REMOVE 3 d (agreed) + MODIFY 2 → 4 d = +4.00; BR1 seeded MODIFY."""
    w = cr_world(client, ed)
    new = rated(client, ed, "Credit check", "BATCH", "MEDIUM", w["sol"])
    assert rate(client, ed, w["keep"], "MEDIUM").status_code == 200
    cr = raise_cr(client, ed, w["v10"])
    seeds(client, ed, cr, [(w["br1"], "MODIFY"), (w["keep"], "MODIFY"), (w["gone"], "REMOVE"), (new, "ADD")])
    return w, new, analyse(client, ed, cr)


def decrease(client, ed, w, f, approved=True):
    """An approved −n d change on the same target: REMOVE one FR."""
    cut = raise_cr(client, ed, w["v10"], title="Drop the feed")
    seeds(client, ed, cut, [(f, "REMOVE")])
    cut = analyse(client, ed, cut)
    if approved:
        cut = decide(client, ed, cut)
    return cut


# ---- raise (criteria 1, 2) -------------------------------------------------------------------------------------------
def test_raise_mints_numbers_against_frozen_approved_or_the_agreed_superseded_baseline(client, ed, db):
    w = cr_world(client, ed)
    a = raise_cr(client, ed, w["v10"], created_by=999, cr_number="CR-9999", status_code="APPROVED")
    assert (a["cr_number"], a["status_code"], a["status_behaviour"]) == ("CR-0001", "DRAFT", "OPEN")
    assert a["against_label"] == "v1.0" and a["raised_by_name"] == "Editor"
    v11 = bid(freeze(client, ed))                                 # v1.0 (approved) is now the agreed SUPERSEDED one
    assert raise_cr(client, ed, w["v10"])["cr_number"] == "CR-0002"
    assert raise_cr(client, ed, v11)["cr_number"] == "CR-0003"   # FROZEN
    bid(freeze(client, ed))                                       # v1.1 superseded, never agreed
    r = raise_cr(client, ed, v11, expect=422)
    assert "never agreed" in r["detail"]
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "CR_RAISED")).first()
    assert ev.detail["cr_number"] == "CR-0001" and "credit" not in str(ev.detail).lower()          # R7


def test_raise_against_a_baseline_not_in_this_project_is_404(client, ed):
    cr_world(client, ed)
    assert "not found in this project" in raise_cr(client, ed, 10 ** 9, expect=404)["detail"]


def test_a_target_frozen_with_effort_off_is_refused(client, ed, world):
    scope(client, ed)
    assert without(client, world, ed, "EFFORT", "CHANGE_REQUEST").status_code == 200
    v = bid(freeze(client, ed))
    assert without(client, world, ed).status_code == 200
    r = raise_cr(client, ed, v, expect=422)
    assert "carries no prices" in r["detail"]


def test_every_write_is_409_component_off_when_change_requests_are_off(client, ed, world):
    w = cr_world(client, ed)
    cr = raise_cr(client, ed, w["v10"])
    rv = get(client, ed, cr)["row_version"]
    blocked = without(client, world, ed, "CHANGE_REQUEST")          # an undecided change keeps it on
    assert blocked.status_code == 409 and "CR-0001" in blocked.text
    rv_r = client.delete(f"{API}/change-requests/{cr['change_request_id']}", headers=ed["h"], params={"row_version": rv})
    assert rv_r.status_code == 204
    assert without(client, world, ed, "CHANGE_REQUEST").status_code == 200
    cid = cr["change_request_id"]
    for method, path, body in (("post", f"/projects/{ed['p']}/change-requests", {}),
                               ("patch", f"/change-requests/{cid}", {"row_version": 1}),
                               ("put", f"/change-requests/{cid}/seeds", {"row_version": 1, "seeds": []}),
                               ("post", f"/change-requests/{cid}/analyse", {"row_version": 1}),
                               ("post", f"/change-requests/{cid}/decide", {"row_version": 1}),
                               ("patch", f"/change-requests/{cid}/restore", None)):
        r = getattr(client, method)(f"{API}{path}", headers=ed["h"], **({"json": body} if body is not None else {}))
        assert r.status_code == 409 and r.headers.get("X-VB-Error") == "COMPONENT_OFF", (path, r.text)


# ---- seeds (criterion 3) ---------------------------------------------------------------------------------------------
def test_seed_types_must_match_the_target(client, ed):
    w = cr_world(client, ed)
    new = rated(client, ed, "Credit check", "BATCH", "MEDIUM", w["sol"])
    cr = raise_cr(client, ed, w["v10"])
    assert "mark it modify" in seeds(client, ed, cr, [(w["keep"], "ADD")], expect=422)["detail"]
    assert "mark it add" in seeds(client, ed, cr, [(new, "MODIFY")], expect=422)["detail"]
    assert "mark it add" in seeds(client, ed, cr, [(new, "REMOVE")], expect=422)["detail"]
    assert "listed twice" in seeds(client, ed, cr, [(new, "ADD"), (new, "ADD")], expect=422)["detail"]
    out = seeds(client, ed, cr, [(new, "ADD"), (w["br1"], "MODIFY")])
    assert sorted((s["number"], s["impact_type_code"]) for s in out["seeds"]) == [("BR-0001", "MODIFY"),
                                                                                  ("FR-0004", "ADD")]


def test_a_seed_not_in_this_project_is_404(client, ed):
    w = cr_world(client, ed)
    cr = raise_cr(client, ed, w["v10"])
    r = client.put(f"{API}/change-requests/{cr['change_request_id']}/seeds", headers=ed["h"],
                   json={"row_version": get(client, ed, cr)["row_version"],
                         "seeds": [{"fr_id": 10 ** 9, "impact_type_code": "ADD"}]})
    assert r.status_code == 404


def test_one_fr_is_a_seed_of_one_open_change_at_a_time(client, ed):
    w = cr_world(client, ed)
    a, b = raise_cr(client, ed, w["v10"]), raise_cr(client, ed, w["v10"], title="Second")
    seeds(client, ed, a, [(w["keep"], "MODIFY")])
    r = seeds(client, ed, b, [(w["keep"], "MODIFY")], expect=409)
    assert "FR-0001 is already a seed of CR-0001" in r["detail"]


# ---- trace (criterion 4) ---------------------------------------------------------------------------------------------
def test_analyse_traces_frs_solutions_apps_entities_waves_and_benefits(client, ed):
    w = cr_world(client, ed)
    owner = role(client, ed)
    b = benefit(client, ed, owner, unit="THB")
    put_link(client, ed, b, w["sol"], 50)
    erp = app(client, ed, code="ERP", name="ERP", lifecycle="TO_BE")
    r = client.post(f"{API}/solutions/{w['sol']['solution_id']}/applications", headers=ed["h"],
                    json={"application_id": erp["application_id"]})
    assert r.status_code == 201, r.text
    cr = raise_cr(client, ed, w["v10"])
    seeds(client, ed, cr, [(w["br1"], "MODIFY")])
    out = analyse(client, ed, cr)
    kinds = {(i["kind"], i["number"], i["reached_via"]) for i in out["impacts"]}
    assert {("FR", "FR-0001", "BR_FR"), ("FR", "FR-0003", "BR_FR"), ("SOLUTION", "SOL-0001", "BR_SOLUTION"),
            ("APPLICATION", "ERP", "SOLUTION_APP"), ("BENEFIT", b["benefit_number"], "SOLUTION_BENEFIT")} <= kinds
    assert {k for k, _, via in kinds if via == "BR_ENTITY"} == {"DATA_ENTITY"}
    # unlinking the solution retires its rows; relinking restores them (same rows)
    links = client.get(f"{API}/business-requirements/{w['br1']['br_id']}/solutions", headers=ed["h"]).json()
    before = {i["number"]: i["cr_impact_id"] for i in out["impacts"]}
    for ln in links:
        client.delete(f"{API}/business-requirements/{w['br1']['br_id']}/solutions/{ln['br_solution_id']}",
                      headers=ed["h"], params={"row_version": ln["row_version"]})
    for f in (w["keep"], w["gone"], w["traced"]):                       # FR → solution reaches it too
        cur = client.get(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"]).json()
        assert client.patch(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"],
                            json={"row_version": cur["row_version"], "solution_id": None}).status_code == 200
    again = analyse(client, ed, cr)
    assert "SOL-0001" not in {i["number"] for i in again["impacts"]}
    assert link_solution(client, ed, w["br1"]["br_id"], w["sol"]["solution_id"]).status_code in (200, 201)
    third = analyse(client, ed, cr)
    assert {i["number"]: i["cr_impact_id"] for i in third["impacts"]}["SOL-0001"] == before["SOL-0001"]


# ---- price (criterion 5) ---------------------------------------------------------------------------------------------
def test_price_is_working_set_minus_agreed_over_seed_frs_with_exposure_beside(client, ed, db):
    w, new, out = priced_cr_world(client, ed)
    assert (out["status_code"], out["effort_delta_days"], out["effort_exposed_days"]) == ("PRICED", "4.00", "10.00")
    by = {s["number"]: s for s in out["seeds"]}
    assert (by["FR-0001"]["effort_delta_days"], by["FR-0002"]["effort_delta_days"],
            by["FR-0004"]["effort_delta_days"]) == ("2.00", "-3.00", "5.00")
    assert by["FR-0001"]["agreed_effort_days"] == "2.00" and by["FR-0004"]["agreed_effort_days"] is None
    traced = next(i for i in out["impacts"] if i["number"] == "FR-0003")
    assert traced["agreed_effort_days"] == "10.00" and traced["effort_delta_days"] is None
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "CR_PRICED")).one()
    assert ev.detail["effort_delta_days"] == "4.00"


def test_an_unrated_add_leaves_the_change_analysed_with_it_named(client, ed):
    w = cr_world(client, ed)
    new = fr(client, ed, "Credit check", "BATCH", solution_id=w["sol"]["solution_id"])
    cr = raise_cr(client, ed, w["v10"])
    seeds(client, ed, cr, [(new, "ADD")])
    out = analyse(client, ed, cr)
    assert (out["status_code"], out["unrated_fr_count"], out["effort_delta_days"]) == ("ANALYSED", 1, "0.00")
    assert "not priced" in decide(client, ed, out, expect=409)["detail"]


def test_price_columns_are_all_or_none_and_derived_values_never_come_in(client, ed, db):
    w = cr_world(client, ed)
    cr = raise_cr(client, ed, w["v10"], effort_delta_days="99", budget_increase_days="5")
    assert cr["effort_delta_days"] is None and cr["budget_increase_days"] is None
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE change_request SET effort_delta_days = 1 WHERE change_request_id = :i"),
                   {"i": cr["change_request_id"]})
    db.rollback()


# ---- benefit value (criterion 6) -------------------------------------------------------------------------------------
def test_benefit_value_is_per_unit_never_one_total(client, ed):
    w = cr_world(client, ed, approved=False)
    owner = role(client, ed)
    thb = benefit(client, ed, owner, name="Lower DSO", unit="THB", base="100", target="160")
    hrs = benefit(client, ed, owner, name="Save time", unit="hours", base="10", target="4")
    put_link(client, ed, thb, w["sol"], 50)
    put_link(client, ed, hrs, w["sol"], 100)
    v11 = bid(freeze(client, ed))
    cr = raise_cr(client, ed, v11)
    seeds(client, ed, cr, [(w["keep"], "MODIFY")])
    out = analyse(client, ed, cr)
    assert out["value_measured"] is True
    assert [(u["unit"], u["value_at_stake"], u["value_change"]) for u in out["value_by_unit"]] == [
        ("hours", "6.00", "0.00"), ("THB", "30.00", "0.00")]


def test_a_spec_6_target_measures_value_at_stake_but_not_value_change(client, ed, monkeypatch):
    from tests.test_process_volume import freeze_at_spec
    w_scope = scope(client, ed)
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    keep = rated(client, ed, "Order form", "FORM", "SIMPLE", s)
    link_fr(client, ed, w_scope["br1"], keep)
    v6 = freeze_at_spec(client, ed, monkeypatch, 6)
    b = benefit(client, ed, role(client, ed), unit="THB")
    put_link(client, ed, b, s, 50)
    cr = raise_cr(client, ed, v6)
    seeds(client, ed, cr, [(keep, "MODIFY")])
    out = analyse(client, ed, cr)
    assert out["value_measured"] is False
    assert [(u["unit"], u["value_at_stake"], u["value_change"]) for u in out["value_by_unit"]] == [("THB", "30.00", None)]


# ---- decide and cover (criteria 7, 8) --------------------------------------------------------------------------------
def test_an_uncovered_increase_is_422_and_writes_nothing(client, ed, db):
    w, new, cr = priced_cr_world(client, ed)
    r = decide(client, ed, cr, expect=422)
    assert "4.00 days need a budget record" in r["detail"]
    assert db.scalar(select(Decision.decision_id)) is None


def test_cut_and_budget_cover_an_increase(client, ed, db):
    w = cr_world(client, ed)
    cut = decrease(client, ed, w, w["gone"])                # −3.00, approved, needs no cover
    assert (cut["status_code"], cut["effort_delta_days"]) == ("APPROVED", "-3.00")
    new = rated(client, ed, "Credit check", "BATCH", "MEDIUM", w["sol"])
    inc = raise_cr(client, ed, w["v10"])
    seeds(client, ed, inc, [(new, "ADD")])
    inc = analyse(client, ed, inc)                         # +5.00
    r = decide(client, ed, inc, expect=422, displaces_cr_id=cut["change_request_id"])
    assert "CR-0001 covers 3.00 days; 2.00 days need a budget record" in r["detail"]
    out = decide(client, ed, inc, displaces_cr_id=cut["change_request_id"], budget_reference="PO-77",
                 budget_approved_by="Client CFO")
    assert (out["status_code"], out["displaces_cr_number"], out["budget_increase_days"]) == ("APPROVED", "CR-0001",
                                                                                              "2.00")
    # the same cut on a second increase → 409
    new2 = rated(client, ed, "Credit report", "FORM", "SIMPLE", w["sol"])
    inc2 = raise_cr(client, ed, w["v10"], title="Report")
    seeds(client, ed, inc2, [(new2, "ADD")])
    inc2 = analyse(client, ed, inc2)
    assert "already covers CR-0002" in decide(client, ed, inc2, expect=409,
                                              displaces_cr_id=cut["change_request_id"])["detail"]


def test_a_cut_that_covers_the_whole_increase_needs_no_budget_and_rejection_needs_neither(client, ed):
    w = cr_world(client, ed)
    cut = decrease(client, ed, w, w["traced"])             # −10.00
    new = rated(client, ed, "Credit check", "BATCH", "MEDIUM", w["sol"])
    inc = raise_cr(client, ed, w["v10"])
    seeds(client, ed, inc, [(new, "ADD")])
    inc = analyse(client, ed, inc)
    assert "no budget record is needed" in decide(client, ed, inc, expect=422, displaces_cr_id=cut["change_request_id"],
                                                  budget_reference="X", budget_approved_by="Y")["detail"]
    out = decide(client, ed, inc, displaces_cr_id=cut["change_request_id"])
    assert out["budget_increase_days"] is None and out["displaces_cr_number"] == "CR-0001"
    rej = raise_cr(client, ed, w["v10"], title="Rejected one")
    new2 = rated(client, ed, "Other", "FORM", "SIMPLE", w["sol"])
    seeds(client, ed, rej, [(new2, "ADD")])
    rej = analyse(client, ed, rej)
    assert decide(client, ed, rej, "REJECTED")["status_code"] == "REJECTED"


def test_a_cut_on_another_target_is_422(client, ed):
    w = cr_world(client, ed)
    v11 = bid(freeze(client, ed))
    cut = raise_cr(client, ed, v11, title="Drop")
    seeds(client, ed, cut, [(w["gone"], "REMOVE")])
    cut = decide(client, ed, analyse(client, ed, cut))
    new = rated(client, ed, "Credit check", "BATCH", "MEDIUM", w["sol"])
    inc = raise_cr(client, ed, w["v10"])
    seeds(client, ed, inc, [(new, "ADD")])
    inc = analyse(client, ed, inc)
    assert "same baseline" in decide(client, ed, inc, expect=422, displaces_cr_id=cut["change_request_id"])["detail"]


def test_the_database_refuses_a_cut_used_twice(client, ed, db):
    w = cr_world(client, ed)
    cut = decrease(client, ed, w, w["gone"])
    with pytest.raises(IntegrityError) as exc:
        db.execute(text("UPDATE change_request SET displaces_cr_id = :c WHERE change_request_id = :c"),
                   {"c": cut["change_request_id"]})
    db.rollback()
    assert "ck_cr_displaces" in str(exc.value)


def test_every_decision_writes_one_decision_and_deferred_then_approved_supersedes(client, ed, db):
    w = cr_world(client, ed)
    cr = decrease(client, ed, w, w["gone"], approved=False)
    d1 = decide(client, ed, cr, "DEFERRED", decided_on="2026-11-01")
    assert d1["status_code"] == "DEFERRED" and d1["decision_number"] == "DEC-0001"
    assert "already deferred" in decide(client, ed, cr, "DEFERRED", expect=409)["detail"]
    d2 = decide(client, ed, cr, "APPROVED")
    assert d2["decision_number"] == "DEC-0002"
    decs = db.scalars(select(Decision).order_by(Decision.decision_id)).all()
    assert [(d.decision_number, d.supersedes_decision_id) for d in decs] == [("DEC-0001", None),
                                                                            ("DEC-0002", decs[0].decision_id)]
    assert decs[1].dimension_code == "SCOPE" and decs[1].analysis_code == "priced_diff"
    assert decs[1].alternative_rejected == "Defer to wave 2" and decs[1].title.startswith("CR-0001 Approved:")
    # final: no more decisions, seeds or analyse
    assert "final" in decide(client, ed, cr, "REJECTED", expect=409)["detail"]
    assert "final" in seeds(client, ed, cr, [], expect=409)["detail"]
    assert "final" in analyse(client, ed, cr, expect=409)["detail"]


def test_a_crs_decision_is_corrected_only_through_the_cr(client, ed, db):
    w = cr_world(client, ed)
    cr = decide(client, ed, decrease(client, ed, w, w["gone"], approved=False), "REJECTED")
    r = client.post(f"{API}/projects/{ed['p']}/decisions", headers=ed["h"],
                    json={"title": "Fix", "decision_text": "x", "alternative_rejected": "y", "dimension_code": "SCOPE",
                          "supersedes_decision_id": cr["decision_id"]})
    assert r.status_code == 409 and "correct it on CR-0001" in r.json()["detail"]
    fixed = client.post(f"{API}/change-requests/{cr['change_request_id']}/decision-correction", headers=ed["h"],
                        json={"row_version": get(client, ed, cr)["row_version"], "rationale": "Corrected text",
                              "alternative_rejected": "Defer", "decided_on": "2026-11-02"})
    assert fixed.status_code == 200, fixed.text
    out = fixed.json()
    assert out["decision_number"] == "DEC-0002" and out["status_code"] == "REJECTED"
    new = db.scalars(select(Decision).where(Decision.decision_number == "DEC-0002")).one()
    assert new.supersedes_decision_id == cr["decision_id"] and new.title.startswith("CR-0001 Rejected:")


# ---- stale price (criterion 9) ---------------------------------------------------------------------------------------
def test_a_seed_rerated_after_pricing_blocks_approval_and_writes_nothing(client, ed, db):
    w, new, cr = priced_cr_world(client, ed)
    assert rate(client, ed, new, "COMPLEX").status_code == 200        # 5 → 10
    r = decide(client, ed, cr, expect=409, budget_reference="PO-1", budget_approved_by="CFO")
    assert "has moved (4.00 → 9.00 days)" in r["detail"]
    assert db.scalar(select(Decision.decision_id)) is None
    assert "PRICE" in get(client, ed, cr)["moved_since_pricing"]


def test_a_traced_fr_rerated_is_shown_as_moved_but_does_not_block(client, ed):
    w, new, cr = priced_cr_world(client, ed)
    assert rate(client, ed, w["traced"], "MEDIUM").status_code == 200
    moved = get(client, ed, cr)["moved_since_pricing"]
    assert "PRICE" not in moved and any(m.startswith("EDITED:") and "FR-0003" in m for m in moved)
    out = decide(client, ed, cr, budget_reference="PO-1", budget_approved_by="CFO")
    assert out["status_code"] == "APPROVED" and out["budget_increase_days"] == "4.00"


def test_a_seed_retired_after_pricing_refuses_approval(client, ed):
    w, new, cr = priced_cr_world(client, ed)
    cur = client.get(f"{API}/function-requirements/{new['fr_id']}", headers=ed["h"]).json()
    assert client.delete(f"{API}/function-requirements/{new['fr_id']}", headers=ed["h"],
                         params={"row_version": cur["row_version"]}).status_code == 204   # cr_impact never blocks
    r = decide(client, ed, cr, expect=409, budget_reference="PO-1", budget_approved_by="CFO")
    assert "FR-0004 retired since pricing" in r["detail"]


def test_a_deferred_cr_reseeded_keeps_its_decision_and_the_next_one_supersedes(client, ed, db):
    w = cr_world(client, ed)
    cr = decide(client, ed, decrease(client, ed, w, w["gone"], approved=False), "DEFERRED")
    out = seeds(client, ed, cr, [(w["gone"], "REMOVE")])
    assert (out["status_code"], out["decision_number"]) == ("DRAFT", "DEC-0001")
    out = decide(client, ed, analyse(client, ed, cr), "REJECTED")
    assert out["decision_number"] == "DEC-0002"
    later = db.scalars(select(Decision).where(Decision.decision_number == "DEC-0002")).one()
    assert later.supersedes_decision_id == cr["decision_id"]


# ---- access (criterion 10) -------------------------------------------------------------------------------------------
def test_an_editor_decides_a_viewer_is_403_and_an_outsider_404(client, ed):
    w = cr_world(client, ed)
    cr = decrease(client, ed, w, w["gone"], approved=False)
    decide(client, ed, cr, headers=ed["rv"], expect=403)
    assert client.get(f"{API}/change-requests/{cr['change_request_id']}", headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/projects/{ed['p']}/change-requests", headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/change-requests/{cr['change_request_id']}", headers=ed["rv"]).status_code == 200
    decide(client, ed, cr)


# ---- retire / restore (criterion 11) ---------------------------------------------------------------------------------
def test_an_open_cr_retires_and_restores_a_decided_one_stays(client, ed):
    w = cr_world(client, ed)
    cr = raise_cr(client, ed, w["v10"])
    cid = cr["change_request_id"]
    assert client.delete(f"{API}/change-requests/{cid}", headers=ed["h"],
                         params={"row_version": get(client, ed, cr)["row_version"]}).status_code == 204
    assert client.get(f"{API}/projects/{ed['p']}/change-requests", headers=ed["h"]).json() == []
    assert client.patch(f"{API}/change-requests/{cid}/restore", headers=ed["h"]).json()["is_active"] is True
    done = decrease(client, ed, w, w["gone"])
    r = client.delete(f"{API}/change-requests/{done['change_request_id']}", headers=ed["h"],
                      params={"row_version": get(client, ed, done)["row_version"]})
    assert r.status_code == 409 and "decision on record" in r.json()["detail"]


# ---- unagreed edits (criterion 12) -----------------------------------------------------------------------------------
def test_a_rejected_edit_still_in_the_working_set_is_warned_at_freeze(client, ed):
    w = cr_world(client, ed)
    assert rate(client, ed, w["keep"], "MEDIUM").status_code == 200        # the drafted change: 2 → 4 d
    new = rated(client, ed, "Credit check", "BATCH", "MEDIUM", w["sol"])
    cr = raise_cr(client, ed, w["v10"])
    seeds(client, ed, cr, [(w["keep"], "MODIFY"), (new, "ADD"), (w["br1"], "MODIFY")])
    decide(client, ed, analyse(client, ed, cr), "REJECTED")
    lines = client.get(f"{API}/projects/{ed['p']}/change-requests/unagreed-edits", headers=ed["h"]).json()
    assert sorted(ln["number"] for ln in lines) == ["FR-0001", "FR-0004"]       # BR1 itself was not edited
    assert lines[0]["message"].startswith("CR-0001 is rejected;")
    p = preview(client, ed)
    assert {x["number"] for x in p["warnings"]["unagreed_cr_edits"]} == {"FR-0001", "FR-0004"}
    assert rate(client, ed, w["keep"], "SIMPLE").status_code == 200        # the team undoes the modify
    left = client.get(f"{API}/projects/{ed['p']}/change-requests/unagreed-edits", headers=ed["h"]).json()
    assert [ln["number"] for ln in left] == ["FR-0004"]
