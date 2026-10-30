"""Control-B1: requirement volatility and the data migration map, their panel rows, and switched-off rules
(docs/slice_control_b_spec.md §7 tests 1, 4, 5, 6; CB-1, CB-4, CB-5). Grade 2: a silent GREEN reaches a steering
decision and is corrected once noticed.

Deliberately uncovered (spec §7): volatility's speed with many baselines (measured once, not tested); a half-done as-is
mapping under-counting "no source" (visible through not_seen_on_as_is, closed by a later "confirmed new data" marker)."""
from decimal import Decimal

from sqlalchemy import select, text

from models import BfcNode, ControlRule
from services import control, control_reports
from tests.conftest import owner_engine
from tests.test_application_api import app, support
from tests.test_baseline import freeze, patch_br, scope
from tests.test_br_fr import set_components
from tests.test_control import edit, panel, role, row
from tests.test_dfd_api import io
from tests.test_scope_api import API, ed, entity, node  # noqa: F401 — ed is a fixture


def vol(client, ed, headers=None, expect=200):
    r = client.get(f"{API}/projects/{ed['p']}/requirement-volatility", headers=headers or ed["rv"])
    assert r.status_code == expect, r.text
    return r.json()


def mig(client, ed, headers=None, expect=200):
    r = client.get(f"{API}/projects/{ed['p']}/data-migration", headers=headers or ed["rv"])
    assert r.status_code == expect, r.text
    return r.json()


def area(out, name):
    return next(a for a in out["areas"] if a["area_name"] == name)


# ---- 1. requirement volatility ---------------------------------------------------------------------------------------
def test_an_area_changed_at_two_freezes_running_flags_and_three_escalates(client, ed):
    s = scope(client, ed)
    assert vol(client, ed)["headline"]["reason"] == "NO_BASELINE_PAIR"
    freeze(client, ed)
    for n, stmt in enumerate(("Take the order by phone", "Take the order online", "Take it anywhere"), 1):
        patch_br(client, ed, s["br1"], br_statement=stmt)
        freeze(client, ed)
        assert vol(client, ed)["headline"]["measured"] == str(Decimal(n))
    r = row(panel(client, ed), "requirement_volatility")
    assert (r["measured"], r["verdict"]) == ("3.00", "ESCALATE")
    assert area(vol(client, ed), "Sales")["churned"] == [True, True, True]
    freeze(client, ed)                                          # a quiet generation resets the current run
    out = vol(client, ed)
    assert (out["headline"]["measured"], area(out, "Sales")["current_run"]) == ("0", 0)
    assert row(panel(client, ed), "requirement_volatility")["verdict"] == "GREEN"
    vol(client, ed, headers=ed["out"], expect=404)


def test_two_freezes_running_is_flag_and_the_area_keeps_its_run_when_renumbered(client, ed):
    """CB-1 at its boundary; R1-D1: an area inserted above Sales renumbers it and is new (all ADDED): not churn."""
    s = scope(client, ed)
    freeze(client, ed)
    patch_br(client, ed, s["br1"], br_statement="Take the order by phone")
    freeze(client, ed)
    patch_br(client, ed, s["br2"], br_statement="Bill the order monthly")
    first = node(client, ed, "Strategy")
    r = client.patch(f"{API}/bfc-nodes/{first['bfc_node_id']}/reorder", headers=ed["h"],
                     json={"row_version": first["row_version"], "new_seq_no": 1})
    assert r.status_code == 200, r.text
    freeze(client, ed)
    out = vol(client, ed)
    sales = area(out, "Sales")
    assert (sales["hier_code"], sales["churned"], sales["current_run"]) == ("02", [True, True], 2)
    assert area(out, "Strategy")["churned"] == [False, False]
    assert row(panel(client, ed), "requirement_volatility")["verdict"] == "FLAG"


def test_a_reorder_is_not_churn_and_a_requirement_line_change_is(client, ed):
    s = scope(client, ed)
    freeze(client, ed)
    step = client.get(f"{API}/bfc-nodes/{s['s2']['bfc_node_id']}", headers=ed["h"]).json()
    r = client.patch(f"{API}/bfc-nodes/{step['bfc_node_id']}/reorder", headers=ed["h"],
                     json={"row_version": step["row_version"], "new_seq_no": 1})
    assert r.status_code == 200, r.text
    freeze(client, ed)
    assert area(vol(client, ed), "Sales")["churned"] == [False]
    r = client.post(f"{API}/business-requirements/{s['br1']['br_id']}/lines", headers=ed["h"],
                    json={"line_kind_code": "RULE", "line_text": "Orders over 10,000 need approval"})
    assert r.status_code == 201, r.text
    freeze(client, ed)
    assert area(vol(client, ed), "Sales")["churned"] == [False, True]


def test_a_damaged_baseline_anywhere_in_the_chain_is_not_measured_on_tab_and_panel(client, ed, monkeypatch):
    scope(client, ed)
    first = freeze(client, ed)["baseline"]
    freeze(client, ed)
    freeze(client, ed)
    monkeypatch.setattr(control_reports.baseline, "verify", lambda db, b: b.baseline_id != first["baseline_id"])
    h = vol(client, ed)["headline"]
    assert (h["reason"], h["baseline_label"]) == ("BASELINE_DAMAGED", first["version_label"])
    assert row(panel(client, ed), "requirement_volatility")["reason"] == "BASELINE_DAMAGED"


def _side(nodes, brs):
    """A hand-built frozen side: nodes {id: parent}, brs {br_id: node id}."""
    n = {i: {"parent_bfc_node_id": p} for i, p in nodes.items()}
    b = {i: {"bfc_node_id": s} for i, s in brs.items()}
    members = {}
    for br, step in brs.items():
        members.setdefault(control_reports._l1_of(n, step), set()).add(br)
    return {"nodes": n, "brs": b, "members": members}


def test_a_moved_sub_tree_churns_both_areas_and_a_brand_new_one_does_not():
    """Round 2 N1 and R1-D2: no BR row changed, only the set of BRs under each area."""
    a = _side({1: None, 2: None, 10: 1, 11: 1, 20: 2}, {100: 10, 101: 11, 200: 20})
    b = _side({1: None, 2: None, 3: None, 10: 1, 11: 3, 20: 2}, {100: 10, 101: 11, 200: 20})
    assert control_reports._churning(a, b, touched=set()) == {1, 3}       # 3 is new but its BR moved in
    c = _side({1: None, 2: None, 4: None, 10: 1, 20: 2, 40: 4}, {100: 10, 200: 20, 400: 40})
    a2 = _side({1: None, 2: None, 10: 1, 20: 2}, {100: 10, 200: 20})
    assert control_reports._churning(a2, c, touched={400}) == set()        # a new area, every BR ADDED
    assert control_reports._churning(a2, c, touched={100}) == {1}


# ---- 4. data migration map -------------------------------------------------------------------------------------------
def _as_is(db, ed, name):
    db.expire_all()
    n = db.scalar(select(BfcNode).where(BfcNode.project_id == ed["p"], BfcNode.bfc_set_code == "AS_IS",
                                        BfcNode.node_name == name, BfcNode.is_active))
    return {"bfc_node_id": n.bfc_node_id}


def _migration_world(client, ed, db):
    sales, fin = node(client, ed, "Sales"), node(client, ed, "Finance")
    take = node(client, ed, "Take order", node(client, ed, "Orders", sales["bfc_node_id"])["bfc_node_id"],
                is_process=True)
    bill = node(client, ed, "Bill order", node(client, ed, "Billing", fin["bfc_node_id"])["bfc_node_id"],
                is_process=True)
    url = f"{API}/projects/{ed['p']}/bfc-sets/AS_IS/copy-from/TO_BE"
    prev = client.post(url, headers=ed["h"], json={}).json()
    assert client.post(url, headers=ed["h"], json={"confirm_hash": prev["confirm_hash"]}).status_code == 200
    ents = {n: entity(client, ed, n) for n in ("Customer", "Sales order", "Invoice", "Promotion", "Ledger")}
    brs = {b["bfc_node_id"]: b for b in client.get(f"{API}/projects/{ed['p']}/business-requirements",
                                                   headers=ed["h"]).json()}
    for step, name, crud in ((take, "Customer", "R"), (take, "Sales order", "C"), (take, "Promotion", "C"),
                             (bill, "Sales order", "R"), (bill, "Invoice", "C")):
        r = client.post(f"{API}/business-requirements/{brs[step['bfc_node_id']]['br_id']}/data-entities",
                        headers=ed["h"], json={"data_entity_id": ents[name]["data_entity_id"], "crud_code": crud})
        assert r.status_code == 201, r.text
    return {"ents": ents, "old_take": _as_is(db, ed, "Take order"), "old_bill": _as_is(db, ed, "Bill order")}


def test_sources_conflicts_new_data_and_retiring(client, ed, db):
    w = _migration_world(client, ed, db)
    h = mig(client, ed)["headline"]
    assert (h["reason"], h["not_seen_on_as_is"], h["in_scope"]) == ("AS_IS_NOT_MAPPED", 4, 4)   # R1-S2
    assert row(panel(client, ed), "data_migration_map")["verdict"] == "NOT_MEASURED"
    for step, name, d in (("old_take", "Customer", "I"), ("old_take", "Sales order", "O"),
                          ("old_bill", "Invoice", "O"), ("old_bill", "Ledger", "O")):
        io(client, ed, w[step], w["ents"][name], d)
    ecc, crm = app(client, ed, "ECC", "SAP ECC", "BOTH"), app(client, ed, "CRM", "Old CRM", "AS_IS")
    new = app(client, ed, "NEW", "New platform", "TO_BE")
    for a in (ecc, crm, new):
        assert support(client, ed, w["old_take"]["bfc_node_id"], a).status_code == 201
    out = mig(client, ed)
    assert {e["de_name"]: (e["state"], [s["application_code"] for s in e["sources"]]) for e in out["entities"]} == {
        "Customer": ("CONFLICTING", ["CRM", "ECC"]), "Sales order": ("CONFLICTING", ["CRM", "ECC"]),
        "Invoice": ("NO_SOURCE", [])}                       # a TO_BE system is never today's source
    assert [e["de_name"] for e in out["new_data"]] == ["Promotion"]
    assert [e["de_name"] for e in out["retiring"]] == ["Ledger"]
    assert out["headline"] == {"measured": "3", "reason": None, "in_scope": 4, "no_source": 1, "conflicting": 2,
                               "not_seen_on_as_is": 1}
    r = row(panel(client, ed), "data_migration_map")
    assert (r["measured"], r["verdict"], r["figures"]["not_seen_on_as_is"]) == ("3.00", "FLAG", 1)
    edit(client, ed, "data_migration_map", escalate_value="2")
    assert row(panel(client, ed), "data_migration_map")["verdict"] == "ESCALATE"


def test_data_migration_needs_as_is_and_applications(client, ed, world):
    set_components(client, world, ed["p"], ["SOLUTION"])
    assert mig(client, ed)["headline"]["reason"] == "AS_IS_OFF" and mig(client, ed)["entities"] is None
    mig(client, ed, headers=ed["out"], expect=404)


# ---- 5. switched-off rules (CB-5) ------------------------------------------------------------------------------------
def test_a_backfilled_rule_arrives_off_measured_and_not_yet_agreed_until_switched_on(client, ed, db):
    with owner_engine().begin() as c:                            # the app role cannot delete: stage a running project
        c.execute(text(f"DELETE FROM control_rule WHERE project_id = {ed['p']} "
                       "AND analysis_code = 'requirement_volatility'"))
    control.backfill(db, "admin@example.test")
    r = row(panel(client, ed), "requirement_volatility")
    assert (r["is_enabled"], r["verdict"], r["reason"], r["off_state"]) == (False, None, "NO_BASELINE_PAIR",
                                                                            "NOT_YET_AGREED")
    assert row(panel(client, ed), "coverage")["off_state"] is None
    pmo = role(client, ed)
    edit(client, ed, "requirement_volatility", owner_org_role_id=pmo["org_role_id"])   # round 2 N2
    assert row(panel(client, ed), "requirement_volatility")["off_state"] == "NOT_YET_AGREED"
    edit(client, ed, "requirement_volatility", is_enabled=True, change_rationale="Client agreed at steering")
    on = row(panel(client, ed), "requirement_volatility")
    assert (on["off_state"], on["verdict"]) == (None, "NOT_MEASURED")
    edit(client, ed, "requirement_volatility", is_enabled=False, change_rationale="Paused for the wave")
    assert row(panel(client, ed), "requirement_volatility")["off_state"] == "SWITCHED_OFF"


def test_a_new_project_gets_every_house_rule_switched_on(client, ed, db):
    got = db.scalars(select(ControlRule).where(ControlRule.project_id == ed["p"])).all()
    assert {r.analysis_code for r in got} == set(control.ORDER) and all(r.is_enabled for r in got)
