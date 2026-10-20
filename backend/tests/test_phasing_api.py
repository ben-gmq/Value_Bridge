"""Slice 15 — waves, a solution's split, dependencies and the wave plan (docs/slice15_phasing_spec.md §6).

Grade 2 (spec §2): the split and the plan are figures a client decides from, and the no-cycle rule rests on one
advisory lock, so criterion 3 is proven with a second session holding that lock. Criteria covered here: 1 (the split
rule, T1–T3), 2 (waves + UNPHASED + UNASSIGNED = the headline, exact and as displayed, R3 / R6), 3 (cycles, the
concurrent pair), 4 (self-dependency refused by the database), 5 (order warnings, Q-61), 6 (retire refusals, Q-60),
8 (component off), 9 (outsiders and cross-solution ids, T2, R7), 10 (statuses company-only, W-4). Criterion 7 is in
test_baseline_phasing.py; 11 (no "phase" on screen) is the frontend's.

Left uncovered on purpose: relabelling a wave status (the existing code-list suite covers relabels; one assertion
here proves PHASE_STATUS is company-only)."""
import threading
from decimal import Decimal

from sqlalchemy import create_engine, text

from tests.conftest import OWNER_URL
from tests.test_effort_api import rate
from tests.test_function_requirement_api import fr
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import sol


def wave(client, ed, code="W1", name="Finance + Procurement", status="PLANNED", expect=201, headers=None, **kw):
    r = client.post(f"{API}/projects/{ed['p']}/phases", headers=headers or ed["h"],
                    json={"phase_code": code, "phase_name": name, "status_code": status, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def get_split(client, ed, s):
    return client.get(f"{API}/solutions/{s['solution_id']}/phase-split", headers=ed["h"]).json()


def put_split(client, ed, s, rows, based_on=None, headers=None):
    """rows: [(wave, pct)]. based_on defaults to the live split as it reads now."""
    if based_on is None:
        based_on = [{"solution_phase_id": r["solution_phase_id"], "row_version": r["row_version"]}
                    for r in get_split(client, ed, s)["rows"]]
    return client.put(f"{API}/solutions/{s['solution_id']}/phase-split", headers=headers or ed["h"],
                      json={"based_on": based_on,
                            "rows": [{"phase_id": w["phase_id"], "portion_pct": str(p)} for w, p in rows]})


def depend(client, ed, s, on, headers=None):
    return client.post(f"{API}/solutions/{s['solution_id']}/dependencies", headers=headers or ed["h"],
                       json={"depends_on_solution_id": on["solution_id"]})


def plan(client, ed):
    r = client.get(f"{API}/projects/{ed['p']}/phase-plan", headers=ed["h"])
    assert r.status_code == 200, r.text
    return r.json()


def rated_fr(client, ed, s, cx="MEDIUM", name="Order entry form"):
    f = fr(client, ed, name, solution_id=s["solution_id"] if s else None)
    assert rate(client, ed, f, cx).status_code == 200
    return f


# ---- waves -----------------------------------------------------------------------------------------------------------
def test_waves_take_the_next_place_codes_are_unique_and_a_reorder_sends_every_wave(client, ed):
    a, b = wave(client, ed, "W1"), wave(client, ed, "W2", "Manufacturing")
    assert (a["seq_no"], b["seq_no"], a["status_code"]) == (1, 2, "PLANNED")
    wave(client, ed, " w1 ", expect=409)                                     # the live index normalises the code
    wave(client, ed, "W3", start_date="2027-03-01", end_date="2027-01-01", expect=422)
    r = client.post(f"{API}/projects/{ed['p']}/phases/reorder", headers=ed["h"],
                    json={"order": [{"id": b["phase_id"], "row_version": b["row_version"]}]})
    assert r.status_code == 422                                              # not every live wave
    r = client.post(f"{API}/projects/{ed['p']}/phases/reorder", headers=ed["h"],
                    json={"order": [{"id": b["phase_id"], "row_version": b["row_version"]},
                                    {"id": a["phase_id"], "row_version": a["row_version"]}]})
    assert r.status_code == 200 and [w["phase_code"] for w in r.json()] == ["W2", "W1"]
    assert [w["seq_no"] for w in r.json()] == [1, 2]


def test_a_retired_wave_restores_to_the_end_unless_its_code_is_taken(client, ed):
    a, b = wave(client, ed, "W1"), wave(client, ed, "W2")
    assert client.delete(f"{API}/phases/{a['phase_id']}", headers=ed["h"],
                         params={"row_version": a["row_version"]}).status_code == 204
    wave(client, ed, "W3")
    r = client.patch(f"{API}/phases/{a['phase_id']}/restore", headers=ed["h"])
    assert r.status_code == 200 and r.json()["seq_no"] == 4                   # after W2 (2) and W3 (3)
    assert client.delete(f"{API}/phases/{b['phase_id']}", headers=ed["h"],
                         params={"row_version": b["row_version"]}).status_code == 204
    wave(client, ed, "w2")
    assert client.patch(f"{API}/phases/{b['phase_id']}/restore", headers=ed["h"]).status_code == 409


def test_wave_statuses_are_company_only(client, ed, db):
    """Criterion 10 (W-4): a project cannot add, override or hide a wave status."""
    from services import code_lists
    assert "PHASE_STATUS" in code_lists.COMPANY_ONLY
    assert {("PHASE_STATUS", "IN_DELIVERY"), ("PHASE_STATUS", "CANCELLED")} <= code_lists.PINNED
    wave(client, ed, "W1", status="NOT_A_STATUS", expect=400)               # an unknown code, as everywhere


# ---- criterion 1: the split rule -------------------------------------------------------------------------------------
def test_a_split_is_exactly_100_or_empty_and_saved_whole(client, ed):
    s = sol(client, ed)
    w1, w2 = wave(client, ed, "W1"), wave(client, ed, "W2")
    assert put_split(client, ed, s, [(w1, 60), (w2, 30)]).status_code == 422          # 90
    assert put_split(client, ed, s, [(w1, 60), (w2, 40.5)]).status_code == 422        # 100.5
    assert put_split(client, ed, s, [(w1, "33.333"), (w2, "66.667")]).status_code == 422   # T3: three decimals
    assert put_split(client, ed, s, [(w1, 0), (w2, 100)]).status_code == 422          # a 0 % row
    assert put_split(client, ed, s, [(w1, 50), (w1, 50)]).status_code == 422          # T1: a wave named twice
    r = put_split(client, ed, s, [(w1, "33.33"), (w2, "66.67")])
    assert r.status_code == 200, r.text
    assert [(x["phase_code"], Decimal(x["portion_pct"])) for x in r.json()["rows"]] == \
        [("W1", Decimal("33.33")), ("W2", Decimal("66.67"))]
    assert put_split(client, ed, s, []).status_code == 200                           # empty: wholly unphased
    assert get_split(client, ed, s)["rows"] == []


def test_a_stale_or_partial_basis_is_409_and_a_named_wave_restores_its_row(client, ed):
    s = sol(client, ed)
    w1, w2 = wave(client, ed, "W1"), wave(client, ed, "W2")
    first = put_split(client, ed, s, [(w1, 40), (w2, 60)]).json()["rows"]
    stale = [{"solution_phase_id": r["solution_phase_id"], "row_version": r["row_version"]} for r in first]
    assert put_split(client, ed, s, [(w1, 50), (w2, 50)]).status_code == 200        # someone else saved
    assert put_split(client, ed, s, [(w1, 100)], based_on=stale).status_code == 409  # built from stale rows
    assert put_split(client, ed, s, [(w1, 100)], based_on=stale[:1]).status_code == 409   # a live row missing
    assert put_split(client, ed, s, [(w1, 100)]).status_code == 200                 # W2's row retires
    again = put_split(client, ed, s, [(w1, 70), (w2, 30)]).json()["rows"]
    assert {r["phase_code"]: r["solution_phase_id"] for r in again} == \
        {r["phase_code"]: r["solution_phase_id"] for r in first}                    # S1-7: the same rows


def test_a_cancelled_wave_keeps_or_lowers_its_share_and_takes_no_new_one(client, ed):
    """T4: a row in a CANCELLED wave may stay at the same or a lower percent; it is never inserted or raised."""
    s, other = sol(client, ed), sol(client, ed, "Workflow")
    w1, w2 = wave(client, ed, "W1"), wave(client, ed, "W2")
    assert put_split(client, ed, s, [(w1, 40), (w2, 60)]).status_code == 200
    cur = client.get(f"{API}/phases/{w1['phase_id']}", headers=ed["h"]).json()
    assert client.patch(f"{API}/phases/{w1['phase_id']}", headers=ed["h"],
                        json={"row_version": cur["row_version"], "status_code": "CANCELLED"}).status_code == 200
    assert put_split(client, ed, s, [(w1, 50), (w2, 50)]).status_code == 422          # raised
    assert put_split(client, ed, s, [(w1, 40), (w2, 60)]).status_code == 200          # kept
    assert put_split(client, ed, s, [(w1, 10), (w2, 90)]).status_code == 200          # lowered
    assert put_split(client, ed, other, [(w1, 50), (w2, 50)]).status_code == 422      # inserted


# ---- criterion 2: the plan adds up -----------------------------------------------------------------------------------
def test_waves_unphased_and_unassigned_add_up_to_the_headline(client, ed):
    """R3 / R6: a rejected-but-split solution and an unrated FR are in the world; the displayed lines add up to the
    displayed headline, each wave's solutions to the wave, and the exact figures to the headline."""
    a, b, c, rej = sol(client, ed, "ERP"), sol(client, ed, "Workflow"), sol(client, ed, "Portal"), sol(client, ed, "Old")
    w1, w2, w3 = wave(client, ed, "W1"), wave(client, ed, "W2"), wave(client, ed, "W3")
    rated_fr(client, ed, a, "MEDIUM", "A1")                                   # 4 days
    rated_fr(client, ed, a, "SIMPLE", "A2")                                   # 2 days → ERP 6
    rated_fr(client, ed, b, "COMPLEX", "B1")                                  # 8 → Workflow 8
    rated_fr(client, ed, c, "SIMPLE", "C1")                                   # 2 → Portal 2, unphased
    rated_fr(client, ed, None, "MEDIUM", "U1")                                # 4 → unassigned
    fr(client, ed, "Unrated", solution_id=a["solution_id"])                   # counted, never given days
    rated_fr(client, ed, rej, "VERY_COMPLEX", "R1")                           # outside the headline
    assert put_split(client, ed, a, [(w1, "33.33"), (w2, "33.33"), (w3, "33.34")]).status_code == 200
    assert put_split(client, ed, b, [(w2, 100)]).status_code == 200
    assert put_split(client, ed, rej, [(w3, 100)]).status_code == 200
    cur = client.get(f"{API}/solutions/{rej['solution_id']}", headers=ed["h"]).json()
    assert client.patch(f"{API}/solutions/{rej['solution_id']}", headers=ed["h"],
                        json={"row_version": cur["row_version"], "status_code": "REJECTED"}).status_code == 200
    headline = Decimal(client.get(f"{API}/projects/{ed['p']}/effort-summary", headers=ed["h"]).json()["total_days"])
    p = plan(client, ed)
    assert Decimal(p["total_days"]) == headline == Decimal("20")
    lines = {(x["kind"], x.get("phase_code")): x for x in p["lines"]}
    assert sum(Decimal(x["days"]) for x in p["lines"]) == Decimal(p["total_shown"]) == headline
    for x in p["lines"]:
        if x["solutions"]:
            assert sum(Decimal(s["days"]) for s in x["solutions"]) == Decimal(x["days"])
    assert Decimal(lines[("WAVE", "W1")]["days"]) == Decimal("2.00")          # 6 × 33.33 % = 1.9998
    assert Decimal(lines[("WAVE", "W2")]["days"]) == Decimal("10.00")         # 1.9998 + 8
    assert Decimal(lines[("WAVE", "W3")]["days"]) == Decimal("2.00")          # 2.0004, the rejected one left out
    assert [s["solution_number"] for s in lines[("UNPHASED", None)]["solutions"]] == [c["solution_number"]]
    assert Decimal(lines[("UNASSIGNED", None)]["days"]) == Decimal("4.00")
    assert p["unrated_count"] == 1
    assert {"kind": "REJECTED_WITH_SPLIT", "solution_number": rej["solution_number"],
            "depends_on_solution_number": None} in p["warnings"]                # Q-65: warns, does not block


# ---- criteria 3 and 4: no cycles -------------------------------------------------------------------------------------
def test_a_dependency_cycle_is_refused_naming_the_path(client, ed):
    a, b, c = sol(client, ed, "A"), sol(client, ed, "B"), sol(client, ed, "C")
    assert depend(client, ed, a, b).status_code == 201
    assert depend(client, ed, b, c).status_code == 201
    r = depend(client, ed, c, a)
    assert r.status_code == 422
    assert r.json()["detail"] == (f"Dependency cycle: {c['solution_number']} → {a['solution_number']} → "
                                  f"{b['solution_number']} → {c['solution_number']}")
    assert depend(client, ed, a, b).status_code == 409                        # already linked
    assert depend(client, ed, a, a).status_code == 422


def test_the_database_refuses_a_self_dependency(client, ed):
    """Criterion 4: the CHECK holds even if the service were bypassed."""
    import pytest
    a = sol(client, ed, "A")
    eng = create_engine(OWNER_URL)
    try:
        with pytest.raises(Exception, match="ck_soldep_not_self"):
            with eng.begin() as conn:
                conn.execute(text("INSERT INTO solution_dependency (project_id, solution_id, depends_on_solution_id, "
                                  "created_by) SELECT project_id, solution_id, solution_id, created_by FROM solution "
                                  "WHERE solution_id = :s"), {"s": a["solution_id"]})
    finally:
        eng.dispose()


def test_two_links_that_would_close_a_cycle_serialise_and_the_second_is_refused(client, ed):
    """Criterion 3, the concurrent pair: another session holds the project's dependency lock and inserts B → A. The
    link A → B waits on the lock; once B → A commits, its walk (a new snapshot) sees it and refuses."""
    from services.phasing import DEPENDENCY_LOCK
    a, b = sol(client, ed, "A"), sol(client, ed, "B")
    eng = create_engine(OWNER_URL)
    conn = eng.connect()
    out = {}
    t = threading.Thread(target=lambda: out.update(r=depend(client, ed, a, b)))
    try:
        tx = conn.begin()
        conn.execute(text("SELECT pg_advisory_xact_lock(:k, CAST(:p AS int4))"), {"k": DEPENDENCY_LOCK, "p": ed["p"]})
        conn.execute(text("INSERT INTO solution_dependency (project_id, solution_id, depends_on_solution_id, "
                          "created_by) SELECT project_id, :b, :a, created_by FROM solution WHERE solution_id = :a"),
                     {"a": a["solution_id"], "b": b["solution_id"]})
        t.start()
        t.join(timeout=2)
        assert t.is_alive(), "the link must wait for the project's dependency lock"
        tx.commit()
    finally:
        conn.close()
        eng.dispose()
    t.join(timeout=30)
    assert out["r"].status_code == 422 and "Dependency cycle" in out["r"].json()["detail"], out["r"].text


def test_a_long_transitive_chain_links_and_checks_fast(client, ed, db):
    """Sara M1: each of 25 solutions depends on every earlier one (2^23 paths). The walk keeps reached nodes, not
    paths, so the closing link is refused and the freeze proof runs in well under a few seconds."""
    import time
    from services import phasing
    sols = [sol(client, ed, f"S{i:02d}") for i in range(25)]
    eng = create_engine(OWNER_URL)
    try:
        with eng.begin() as conn:
            for i, s in enumerate(sols):
                for p in sols[:i]:
                    conn.execute(text("INSERT INTO solution_dependency (project_id, solution_id, "
                                      "depends_on_solution_id, created_by) SELECT project_id, :s, :p, created_by "
                                      "FROM solution WHERE solution_id = :s"),
                                 {"s": s["solution_id"], "p": p["solution_id"]})
    finally:
        eng.dispose()
    t0 = time.monotonic()
    r = depend(client, ed, sols[0], sols[-1])
    assert r.status_code == 422 and r.json()["detail"].startswith(f"Dependency cycle: {sols[0]['solution_number']}")
    assert phasing.dependency_cycle(db, ed["p"]) == []
    assert time.monotonic() - t0 < 5


def test_the_seed_refuses_while_a_project_holds_its_own_wave_status(client, ed, db):
    """Sara M2 (R8): PHASE_STATUS became company-only; a project row made before that stops the deploy seed."""
    import pytest
    from seeds.seed_code_master import company_only_breaches, seed
    assert company_only_breaches(db) == []
    eng = create_engine(OWNER_URL)
    try:
        with eng.begin() as conn:
            conn.execute(text("INSERT INTO code_master (project_id, category, code, label, sort_order, is_system) "
                              "VALUES (:p, 'PHASE_STATUS', 'PAUSED', 'Paused', 99, false)"), {"p": ed["p"]})
        with pytest.raises(SystemExit, match="PAUSED"):
            seed(db)
    finally:
        with eng.begin() as conn:
            conn.execute(text("UPDATE code_master SET is_active = false WHERE project_id = :p AND code = 'PAUSED'"),
                         {"p": ed["p"]})
        eng.dispose()


def test_a_dependency_can_be_removed_and_relinked_as_the_same_row(client, ed, db):
    a, b = sol(client, ed, "A"), sol(client, ed, "B")
    d = client.post(f"{API}/solutions/{a['solution_id']}/dependencies", headers=ed["h"],
                    json={"depends_on_solution_id": b["solution_id"], "note": "first note"}).json()
    assert client.delete(f"{API}/solutions/{a['solution_id']}/dependencies/{d['solution_dependency_id']}",
                         headers=ed["h"], params={"row_version": d["row_version"]}).status_code == 204
    again = depend(client, ed, a, b).json()
    assert again["solution_dependency_id"] == d["solution_dependency_id"]
    detail = db.execute(text("SELECT detail FROM audit_event WHERE event_type = 'RECORD_RESTORED' AND target_table = "
                             "'solution_dependency' AND target_id = :i"), {"i": d["solution_dependency_id"]}).scalar()
    assert detail["previous_note"] == "first note"                            # sara L3: the old note is kept
    deps = client.get(f"{API}/solutions/{b['solution_id']}/dependencies", headers=ed["h"]).json()
    assert [x["solution_number"] for x in deps["needed_by"]] == [a["solution_number"]]


# ---- criterion 5: order warnings (Q-61) ------------------------------------------------------------------------------
def test_a_prerequisite_in_a_later_or_the_same_wave_or_none_warns(client, ed):
    a, b, c, d = sol(client, ed, "A"), sol(client, ed, "B"), sol(client, ed, "C"), sol(client, ed, "D")
    w1, w2 = wave(client, ed, "W1"), wave(client, ed, "W2")
    put_split(client, ed, a, [(w1, 100)])
    put_split(client, ed, b, [(w2, 100)])
    put_split(client, ed, c, [(w1, 100)])
    for need, pre in ((a, b), (c, a), (a, d)):                                 # later, same, unscheduled
        assert depend(client, ed, need, pre).status_code == 201
    kinds = {(x["solution_number"], x["depends_on_solution_number"]): x["kind"] for x in plan(client, ed)["warnings"]}
    assert kinds == {(a["solution_number"], b["solution_number"]): "PREREQ_LATER",
                     (c["solution_number"], a["solution_number"]): "PREREQ_SAME_WAVE",
                     (a["solution_number"], d["solution_number"]): "PREREQ_UNSCHEDULED"}


# ---- criterion 6: retire refusals (Q-60) -----------------------------------------------------------------------------
def test_a_split_wave_or_a_split_or_linked_solution_cannot_be_retired(client, ed):
    a, b = sol(client, ed, "A"), sol(client, ed, "B")
    w1 = wave(client, ed, "W1")
    put_split(client, ed, a, [(w1, 100)])
    depend(client, ed, b, a)
    w = client.get(f"{API}/phases/{w1['phase_id']}", headers=ed["h"]).json()
    r = client.delete(f"{API}/phases/{w1['phase_id']}", headers=ed["h"], params={"row_version": w["row_version"]})
    assert r.status_code == 409 and f"{a['solution_number']} ↔ W1 (100%)" in r.json()["detail"], r.text
    for s, needle in ((a, "Solution ↔ wave"), (b, f"{b['solution_number']} needs {a['solution_number']}")):
        cur = client.get(f"{API}/solutions/{s['solution_id']}", headers=ed["h"]).json()
        r = client.delete(f"{API}/solutions/{s['solution_id']}", headers=ed["h"],
                          params={"row_version": cur["row_version"]})
        assert r.status_code == 409 and needle in r.json()["detail"], r.text


# ---- criteria 8 and 9: component and visibility ----------------------------------------------------------------------
def test_component_off_refuses_every_write(client, ed, world):
    from tests.conftest import ALL_COMPONENTS
    from tests.test_components import switch
    s = sol(client, ed)
    switch(client, world, ed["p"], [c for c in ALL_COMPONENTS if c != "PHASING"])
    r = client.post(f"{API}/projects/{ed['p']}/phases", headers=ed["h"],
                    json={"phase_code": "W1", "phase_name": "One", "status_code": "PLANNED"})
    assert r.status_code == 409 and r.headers.get("X-VB-Error") == "COMPONENT_OFF"
    assert put_split(client, ed, s, []).status_code == 409
    assert client.get(f"{API}/projects/{ed['p']}/phase-plan", headers=ed["h"]).status_code == 200   # reads stay


def test_outsiders_and_cross_solution_ids_get_404(client, ed):
    a, b = sol(client, ed, "A"), sol(client, ed, "B")
    w1 = wave(client, ed, "W1")
    rows = put_split(client, ed, a, [(w1, 100)]).json()["rows"]
    d = depend(client, ed, a, b).json()
    out = ed["out"]
    for path in (f"/projects/{ed['p']}/phases", f"/phases/{w1['phase_id']}", f"/projects/{ed['p']}/phase-plan",
                 f"/solutions/{a['solution_id']}/phase-split", f"/solutions/{a['solution_id']}/dependencies"):
        assert client.get(f"{API}{path}", headers=out).status_code == 404, path
    wave(client, ed, "W9", headers=out, expect=404)
    # T2: another solution's row in based_on; R7: a wave of no project of ours; another solution's link
    basis = [{"solution_phase_id": rows[0]["solution_phase_id"], "row_version": rows[0]["row_version"]}]
    assert put_split(client, ed, b, [(w1, 100)], based_on=basis).status_code == 404
    assert put_split(client, ed, b, [({"phase_id": 999999}, 100)]).status_code == 404
    assert client.delete(f"{API}/solutions/{b['solution_id']}/dependencies/{d['solution_dependency_id']}",
                         headers=ed["h"], params={"row_version": d["row_version"]}).status_code == 404
    assert client.put(f"{API}/solutions/{a['solution_id']}/phase-split", headers=ed["rv"],
                      json={"based_on": [], "rows": []}).status_code == 403              # a viewer reads only
