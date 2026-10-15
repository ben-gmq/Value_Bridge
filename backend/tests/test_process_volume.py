"""Slice 13c-1 — process volume and FTE (D-67; docs/slice13_schema.md §3, slice13_spec §10 C1–C6, C8, C10).

Grade 1 for the freeze half: hash spec 3, the new shadow columns and the cross-spec diff, proved against a spec-2
baseline frozen by the pre-13c code path (CURRENT_HASH_SPEC monkeypatched, as test_hash_spec does for spec 1).
"""
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.test_baseline import bid, diff, freeze, owner_exec, scope
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture


def vol(client, ed, node_id, expect=200, **body):
    cur = client.get(f"{API}/bfc-nodes/{node_id}/volume", headers=ed["h"]).json()
    r = client.patch(f"{API}/bfc-nodes/{node_id}/volume", headers=ed["h"],
                     json={"row_version": cur["row_version"], **body})
    assert r.status_code == expect, r.text
    return r.json()


def freeze_at_spec(client, ed, monkeypatch, spec):
    """A freeze as the code before 13c made it (spec 2): bfc_node hashed on its spec-1 list."""
    from services import freeze_set
    monkeypatch.setattr(freeze_set, "CURRENT_HASH_SPEC", spec)
    monkeypatch.setattr("services.baseline.CURRENT_HASH_SPEC", spec)
    try:
        return bid(freeze(client, ed))
    finally:
        monkeypatch.undo()


MANUAL = {"runs_per_period": 3, "volume_period_code": "WEEK", "transactions_per_run": 40,
          "seconds_per_transaction": 360}


# ---- derivation (C1, C3, C10; slice13_schema §3.2) -------------------------------------------------------

def test_the_worked_cases_derive_in_decimal(client, ed):
    w = scope(client, ed)
    s = w["s1"]["bfc_node_id"]
    v = vol(client, ed, s, **MANUAL, transaction_unit_code="INVOICE")
    assert Decimal(v["annual_hours"]) == Decimal(624)                              # C1: 3 × 52 × 40 × 360 / 3600
    assert Decimal(v["fte"]) == Decimal("0.325")                                   # 624 / 1,920 (0.33 on screen)
    assert v["incomplete"] == [] and v["transaction_unit_code"] == "INVOICE"
    v = vol(client, ed, s, runs_per_period=1, volume_period_code="DAY", transactions_per_run=8000,
            seconds_per_transaction="0.3")                                         # automated to-be
    assert Decimal(v["seconds_per_transaction"]) == Decimal("0.300")               # stored, not rounded to zero
    assert Decimal(v["annual_hours"]) == Decimal(160)                              # DAY = the 240 working days [Q-27]
    v = vol(client, ed, s, runs_per_period=2000, volume_period_code="DAY", transactions_per_run=1,
            seconds_per_transaction="0.05")                                        # real-time
    assert round(Decimal(v["annual_hours"]), 2) == Decimal("6.67")


def test_a_missing_figure_gives_no_fte_and_names_it(client, ed):
    s = scope(client, ed)["s1"]["bfc_node_id"]
    v = vol(client, ed, s, runs_per_period=3, volume_period_code="WEEK")
    assert v["annual_hours"] is None and v["fte"] is None
    assert v["incomplete"] == ["transactions_per_run", "seconds_per_transaction"]  # C3: never guessed


def test_a_figure_left_out_keeps_its_value_and_null_clears_it(client, ed):
    s = scope(client, ed)["s1"]["bfc_node_id"]
    vol(client, ed, s, **MANUAL)
    v = vol(client, ed, s, seconds_per_transaction=180)
    assert Decimal(v["runs_per_period"]) == 3 and Decimal(v["annual_hours"]) == 312
    v = vol(client, ed, s, seconds_per_transaction=None)
    assert v["seconds_per_transaction"] is None and v["incomplete"] == ["seconds_per_transaction"]


# ---- refusals (C2, C10, law 6) ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    {"annual_hours": 10}, {"fte": 0.5},                                            # derived, never sent (law 6)
    {"runs_per_period": -1, "volume_period_code": "WEEK"},                        # negative
    {"seconds_per_transaction": "0.0005"},                                         # more decimals than stored
    {"runs_per_period": "1.005", "volume_period_code": "WEEK"},
    {"runs_per_period": 1_000_001, "volume_period_code": "DAY"},                  # over a cap
    {"transactions_per_run": 100_000_001}, {"seconds_per_transaction": 86_401},
    {"runs_per_period": 3},                                                        # a number without its period
    {"volume_period_code": "FORTNIGHT", "runs_per_period": 1},                    # not a period
    {"transaction_unit_code": "INVOICE"},                                          # a unit without a count
])
def test_refused_bodies_are_422_and_change_nothing(client, ed, body):
    s = scope(client, ed)["s1"]["bfc_node_id"]
    before = client.get(f"{API}/bfc-nodes/{s}/volume", headers=ed["h"]).json()
    vol(client, ed, s, expect=422, **body)
    assert client.get(f"{API}/bfc-nodes/{s}/volume", headers=ed["h"]).json() == before


def test_the_caps_and_zero_are_accepted(client, ed):
    s = scope(client, ed)["s1"]["bfc_node_id"]
    v = vol(client, ed, s, runs_per_period=1_000_000, volume_period_code="YEAR", transactions_per_run=100_000_000,
            seconds_per_transaction=86_400)
    assert v["incomplete"] == []
    v = vol(client, ed, s, runs_per_period=0, transactions_per_run=0, seconds_per_transaction=0)
    assert Decimal(v["annual_hours"]) == 0


def test_a_function_heading_has_no_volume(client, ed):
    w = scope(client, ed)
    vol(client, ed, w["group"]["bfc_node_id"], expect=422, **MANUAL)
    with pytest.raises(IntegrityError):                       # and the database says so to the owner role too
        owner_exec("UPDATE bfc_node SET seconds_per_transaction = 1 WHERE bfc_node_id = :b", b=w["group"]["bfc_node_id"])


def test_an_unknown_unit_is_refused_and_a_viewer_cannot_write(client, ed):
    s = scope(client, ed)["s1"]["bfc_node_id"]
    vol(client, ed, s, expect=400, transactions_per_run=5, transaction_unit_code="WIDGET")
    cur = client.get(f"{API}/bfc-nodes/{s}/volume", headers=ed["rv"]).json()        # a reviewer reads ...
    r = client.patch(f"{API}/bfc-nodes/{s}/volume", headers=ed["rv"], json={"row_version": cur["row_version"], **MANUAL})
    assert r.status_code == 403                                                    # ... and cannot write
    assert client.get(f"{API}/bfc-nodes/{s}/volume", headers=ed["out"]).status_code == 404   # 404, never 403


def test_the_write_is_audited_from_and_to(client, ed, db):
    s = scope(client, ed)["s1"]["bfc_node_id"]
    vol(client, ed, s, **MANUAL)
    row = db.execute(text("SELECT detail FROM audit_event WHERE event_type = 'PROCESS_VOLUME_SET' "
                          "AND target_id = :s ORDER BY audit_event_id DESC LIMIT 1"), {"s": s}).scalar()
    assert row["from"]["runs_per_period"] is None and row["to"]["runs_per_period"] == "3.00"


# ---- the basis (C4) ----------------------------------------------------------------------------------------

def test_a_basis_change_moves_every_fte_and_touches_no_process(client, ed):
    s = scope(client, ed)["s1"]["bfc_node_id"]
    before = vol(client, ed, s, **MANUAL)
    owner_exec(f"UPDATE project SET working_days_per_year = 200, hours_per_working_day = 7.5 "
               f"WHERE project_id = {ed['p']}")
    after = client.get(f"{API}/bfc-nodes/{s}/volume", headers=ed["h"]).json()
    assert after["row_version"] == before["row_version"]                          # no process row changed
    assert Decimal(after["annual_hours"]) == 624                                   # WEEK does not read the basis
    assert Decimal(after["fte"]) == Decimal(624) / Decimal(1500)


# ---- freeze, verify and diff across specs (C5, C6; law 2) -------------------------------------------------

def test_a_spec_2_baseline_still_verifies_and_shows_no_process_changed(client, ed, db, monkeypatch):
    w = scope(client, ed)
    v2 = freeze_at_spec(client, ed, monkeypatch, 2)
    assert db.execute(text("SELECT hash_spec_version FROM baseline WHERE baseline_id = :b"), {"b": v2}).scalar() == 2
    assert client.get(f"{API}/baselines/{v2}", headers=ed["h"]).json()["intact"] is True
    d = diff(client, ed, v2, "live")                                               # C5: no CHANGED for new columns
    bfc = d["entities"]["bfc_node"]
    assert bfc["status"] == "OK" and bfc["rows"] == []
    assert bfc["compared_on_spec"] == 2 and "seconds_per_transaction" in bfc["not_compared"]
    # an edit to a spec-1 field still shows; a volume edit alone does not (not frozen in v1.x)
    vol(client, ed, w["s1"]["bfc_node_id"], **MANUAL)
    assert diff(client, ed, v2, "live")["entities"]["bfc_node"]["rows"] == []
    v3 = bid(freeze(client, ed))
    d = diff(client, ed, v2, v3)
    assert d["entities"]["bfc_node"]["rows"] == [] and d["entities"]["bfc_node"]["compared_on_spec"] == 2
    for b in (v2, v3):
        assert client.get(f"{API}/baselines/{b}", headers=ed["h"]).json()["intact"] is True


def test_a_spec_3_freeze_holds_the_figures_and_a_later_edit_reads_changed(client, ed, db):
    w = scope(client, ed)
    s = w["s1"]["bfc_node_id"]
    vol(client, ed, s, **MANUAL, transaction_unit_code="INVOICE")
    v1 = bid(freeze(client, ed))
    row = db.execute(text("SELECT runs_per_period, volume_period_code, seconds_per_transaction, transaction_unit_code "
                          "FROM baseline_bfc_node WHERE baseline_id = :b AND source_id = :s"), {"b": v1, "s": s}).one()
    assert (row[0], row[1], row[2], row[3]) == (Decimal("3.00"), "WEEK", Decimal("360.000"), "INVOICE")
    vol(client, ed, s, seconds_per_transaction=300)
    d = diff(client, ed, v1, "live")
    (r,) = d["entities"]["bfc_node"]["rows"]
    assert r["change"] == "CHANGED" and r["fields"] == ["seconds_per_transaction"]
    assert "compared_on_spec" not in d["entities"]["bfc_node"]


def test_a_baseline_keeps_the_basis_it_was_frozen_with(client, ed, db):
    scope(client, ed)
    v1 = bid(freeze(client, ed))
    owner_exec(f"UPDATE project SET working_days_per_year = 200 WHERE project_id = {ed['p']}")
    h = client.get(f"{API}/baselines/{v1}", headers=ed["h"]).json()
    assert (h["fte_working_days"], h["fte_hours_per_day"]) == (240, 8.0)          # C6: re-derives as frozen
    with pytest.raises(Exception, match="frozen baseline column"):                 # the guard, for the owner role
        owner_exec("UPDATE baseline SET fte_working_days = 1 WHERE baseline_id = :b", b=v1)


def test_tampering_with_a_frozen_volume_fails_the_check(client, ed):
    w = scope(client, ed)
    vol(client, ed, w["s1"]["bfc_node_id"], **MANUAL)
    v1 = bid(freeze(client, ed))
    owner_exec("ALTER TABLE baseline_bfc_node DISABLE TRIGGER trg_baseline_bfc_node_immutable;"
               "UPDATE baseline_bfc_node SET seconds_per_transaction = 1 WHERE baseline_id = :b;"
               "ALTER TABLE baseline_bfc_node ENABLE TRIGGER trg_baseline_bfc_node_immutable", b=v1)
    assert client.get(f"{API}/baselines/{v1}", headers=ed["h"]).json()["intact"] is False


# ---- other writers of the node (F7, Q-23, Q-24) -------------------------------------------------------------

def test_a_process_with_volume_cannot_go_back_to_a_plain_box(client, ed, db):
    w = scope(client, ed)
    s = w["s1"]["bfc_node_id"]
    vol(client, ed, s, **MANUAL)
    from models import BfcNode
    from services import bfc
    node = db.get(BfcNode, s)
    assert "the volume figures" in bfc._step_blockers(db, node)


# ---- 13c-2: the FTE basis (Q-7, C4) and as-is beside to-be (Q-9, Q-28, C7, C9) ------------------------------

from tests.test_scope_api import node  # noqa: E402


def basis(client, headers, p, expect=200, **body):
    cur = client.get(f"{API}/projects/{p}", headers=headers).json()
    r = client.put(f"{API}/projects/{p}/fte-basis", headers=headers, json={"row_version": cur["row_version"], **body})
    assert r.status_code == expect, r.text
    return r.json()


def test_only_an_admin_sets_the_basis_and_it_is_audited(client, ed, world, db):
    s = scope(client, ed)["s1"]["bfc_node_id"]
    vol(client, ed, s, **MANUAL)
    basis(client, ed["h"], ed["p"], expect=403, working_days_per_year=200, hours_per_working_day="7.5")
    basis(client, world["admin"], ed["p"], expect=422, working_days_per_year=0, hours_per_working_day=8)
    basis(client, world["admin"], ed["p"], expect=422, working_days_per_year=200, hours_per_working_day="7.555")
    out = basis(client, world["admin"], ed["p"], working_days_per_year=200, hours_per_working_day="7.5")
    assert (out["working_days_per_year"], Decimal(out["hours_per_working_day"])) == (200, Decimal("7.5"))
    v = client.get(f"{API}/bfc-nodes/{s}/volume", headers=ed["h"]).json()
    assert Decimal(v["fte"]) == Decimal(624) / Decimal(1500)                       # C4, through the route
    ev = db.execute(text("SELECT detail FROM audit_event WHERE event_type = 'PROJECT_FTE_BASIS_CHANGED' "
                         "ORDER BY audit_event_id DESC LIMIT 1")).scalar()
    assert ev["from"]["working_days_per_year"] == 240 and ev["to"]["hours_per_working_day"] == "7.50"
    p = client.get(f"{API}/projects/{ed['p']}", headers=ed["h"]).json()
    assert (p["working_days_per_year"], p["hours_per_working_day"]) == (200, 7.5)


def _two_charts(client, ed):
    """Sales (one complete process) and Finance (one incomplete), copied to the as-is chart with their volume."""
    sales = node(client, ed, "Sales")
    orders = node(client, ed, "Orders", sales["bfc_node_id"])
    take = node(client, ed, "Take order", orders["bfc_node_id"], is_process=True)
    fin = node(client, ed, "Finance")
    billing = node(client, ed, "Billing", fin["bfc_node_id"])
    bill = node(client, ed, "Bill order", billing["bfc_node_id"], is_process=True)
    vol(client, ed, take["bfc_node_id"], **MANUAL)                                  # 624 h
    vol(client, ed, bill["bfc_node_id"], runs_per_period=1, volume_period_code="DAY")    # incomplete
    url = f"{API}/projects/{ed['p']}/bfc-sets/AS_IS/copy-from/TO_BE"
    prev = client.post(url, headers=ed["h"], json={}).json()
    assert client.post(url, headers=ed["h"], json={"confirm_hash": prev["confirm_hash"]}).status_code == 200
    vol(client, ed, take["bfc_node_id"], seconds_per_transaction=180)              # the change halves the time: 312 h
    return {"sales": sales, "fin": fin, "take": take}


def summary(client, ed):
    r = client.get(f"{API}/projects/{ed['p']}/volume-summary", headers=ed["rv"])     # a reviewer reads it
    assert r.status_code == 200, r.text
    return r.json()


def test_the_summary_pairs_areas_and_lists_incomplete_processes(client, ed):
    _two_charts(client, ed)
    s = summary(client, ed)
    assert s["has_as_is"] is True
    l1 = {m["hier_code"]: m for m in s["levels"][0]["matched"]}
    assert set(l1) == {"01", "02"} and s["levels"][0]["unmatched"] == []
    sales = l1["01"]
    assert (Decimal(sales["as_is"]["annual_hours"]), Decimal(sales["to_be"]["annual_hours"])) == (624, 312)
    assert Decimal(sales["saved_hours"]) == 312                                       # C7: the time saved per area
    fin = l1["02"]
    assert fin["to_be"]["complete"] == 0 and len(fin["to_be"]["incomplete"]) == 1     # counted and listed, not guessed
    assert fin["to_be"]["incomplete"][0]["missing"] == ["transactions_per_run", "seconds_per_transaction"]
    assert Decimal(fin["saved_hours"]) == 0
    assert {m["hier_code"] for m in s["levels"][1]["matched"]} == {"01.01", "02.01"}


def test_a_reordered_area_is_listed_never_summed(client, ed):
    c = _two_charts(client, ed)
    fin = client.get(f"{API}/bfc-nodes/{c['fin']['bfc_node_id']}", headers=ed["h"]).json()
    r = client.patch(f"{API}/bfc-nodes/{fin['bfc_node_id']}/reorder", headers=ed["h"],
                     json={"row_version": fin["row_version"], "new_seq_no": 1})                # to-be: Finance 01, Sales 02
    assert r.status_code == 200, r.text
    lvl = summary(client, ed)["levels"][0]
    assert lvl["matched"] == []                                                       # C9: codes agree, names do not
    got = {(u["chart"], u["hier_code"], u["name"], u["reason"], u["other_code"]) for u in lvl["unmatched"]}
    assert got == {("AS_IS", "01", "Sales", "NAME_ELSEWHERE", "02"), ("TO_BE", "01", "Finance", "NAME_ELSEWHERE", "02"),
                   ("AS_IS", "02", "Finance", "NAME_ELSEWHERE", "01"), ("TO_BE", "02", "Sales", "NAME_ELSEWHERE", "01")}


def test_a_renamed_area_reads_code_same_name_differs(client, ed):
    c = _two_charts(client, ed)
    sales = client.get(f"{API}/bfc-nodes/{c['sales']['bfc_node_id']}", headers=ed["h"]).json()
    r = client.patch(f"{API}/bfc-nodes/{sales['bfc_node_id']}", headers=ed["h"],
                     json={"row_version": sales["row_version"], "node_name": "Commercial"})
    assert r.status_code == 200, r.text
    lvl = summary(client, ed)["levels"][0]
    assert [m["hier_code"] for m in lvl["matched"]] == ["02"]
    assert {(u["chart"], u["reason"]) for u in lvl["unmatched"]} == {("AS_IS", "CODE_SAME_NAME_DIFFERS"),
                                                                     ("TO_BE", "CODE_SAME_NAME_DIFFERS")}


def test_a_chart_copy_carries_the_volume(client, ed):
    c = _two_charts(client, ed)
    as_is = client.get(f"{API}/projects/{ed['p']}/bfc-tree", headers=ed["h"], params={"bfc_set": "AS_IS"}).json()
    copied = next(n for n in as_is if n["is_process"] and n["node_name"] == "Take order")
    v = client.get(f"{API}/bfc-nodes/{copied['bfc_node_id']}/volume", headers=ed["h"]).json()
    assert Decimal(v["seconds_per_transaction"]) == 360 and Decimal(v["annual_hours"]) == 624   # Q-23
    assert c["take"]["bfc_node_id"] != copied["bfc_node_id"]
