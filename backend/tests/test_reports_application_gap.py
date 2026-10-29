"""System gap (docs/slice1f_spec.md §3.4, function 67; D-8, RP-1, criterion 10d). Grade 2: the report is the
migration backlog a client plans from; a system missing from it is a system nobody plans to replace, noticed when
someone checks a step. Proven on one built fixture: 10d, RP-1 (two systems on one area, only one allocated — the other
is still listed), the net-new line, retiring (A7), a TO_BE system as today's support kept apart (S6b-5), a REJECTED
answer not counted as allocation, an unmatched area with its reason, the input counts on an empty project (D3), a
component off (A1), level 2 and its bound, an outsider's 404, and the print stamp now accepting the report (N4).

Deliberately uncovered (spec §5): very large charts; NAME_ELSEWHERE and CODE_SAME_NAME_DIFFERS here (the pairing is
area_match, proven by test_process_volume)."""
from sqlalchemy import select

from models import BfcNode
from tests.test_application_api import allocate, app, support
from tests.test_br_fr import set_components
from tests.test_reports_print_stamp import stamp
from tests.test_reports_traceability import _set_status
from tests.test_scope_api import API, ed, node  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol
from tests.test_step_retire import _br


def gap(client, ed, headers=None, expect=200, **q):
    r = client.get(f"{API}/projects/{ed['p']}/application-gap", headers=headers or ed["rv"], params=q)
    assert r.status_code == expect, r.text
    return r.json()


def as_is_node(db, ed, name):
    db.expire_all()
    return db.scalar(select(BfcNode).where(BfcNode.project_id == ed["p"], BfcNode.bfc_set_code == "AS_IS",
                                           BfcNode.node_name == name, BfcNode.is_active))


def world_(client, ed, db):
    """Sales and Finance copied to the as-is chart, then Procurement added to the to-be chart only."""
    sales = node(client, ed, "Sales")
    take = node(client, ed, "Take order", node(client, ed, "Orders", sales["bfc_node_id"])["bfc_node_id"], is_process=True)
    fin = node(client, ed, "Finance")
    bill = node(client, ed, "Bill order", node(client, ed, "Billing", fin["bfc_node_id"])["bfc_node_id"], is_process=True)
    url = f"{API}/projects/{ed['p']}/bfc-sets/AS_IS/copy-from/TO_BE"
    prev = client.post(url, headers=ed["h"], json={}).json()
    assert client.post(url, headers=ed["h"], json={"confirm_hash": prev["confirm_hash"]}).status_code == 200
    node(client, ed, "Procurement")
    apps = {c: app(client, ed, c, f"{c} app", lc) for c, lc in
            (("ECC", "BOTH"), ("CRM", "BOTH"), ("LEGACY", "AS_IS"), ("NEWAPP", "TO_BE"))}
    old_take, old_bill = as_is_node(db, ed, "Take order").bfc_node_id, as_is_node(db, ed, "Bill order").bfc_node_id
    for step_id, c in ((old_take, "ECC"), (old_take, "LEGACY"), (old_take, "NEWAPP"), (old_bill, "CRM")):
        assert support(client, ed, step_id, apps[c]).status_code == 201
    portal = sol(client, ed, "Order portal", "TECHNOLOGY")
    assert link(client, ed, _br(client, ed, take["bfc_node_id"])["br_id"], portal["solution_id"]).status_code == 201
    for c in ("ECC", "NEWAPP"):
        assert allocate(client, ed, portal, apps[c]).status_code == 201
    dropped = sol(client, ed, "Billing engine", "TECHNOLOGY")                   # answers Billing, but REJECTED
    assert link(client, ed, _br(client, ed, bill["bfc_node_id"])["br_id"], dropped["solution_id"]).status_code == 201
    assert allocate(client, ed, dropped, apps["CRM"]).status_code == 201
    _set_status(client, ed, dropped, "REJECTED")
    return {"take": take, "bill": bill, "old_take": old_take}


def pairs(rows):
    return {(r["area_name"], r["step"]["node_name"], r["application"]["application_code"]) for r in rows}


def test_per_system_gaps_retiring_and_the_to_be_support_line(client, ed, db):
    world_(client, ed, db)
    g = gap(client, ed)
    assert g["level"] == 1 and g["counts"] == {"as_is_processes": 2, "support_links": 3, "to_be_allocations": 2}
    # 10d (Bill order: CRM's only answer is REJECTED) and RP-1 (Sales: ECC is allocated, LEGACY still listed)
    assert pairs(g["unallocated"]) == {("Sales", "Take order", "LEGACY"), ("Finance", "Bill order", "CRM")}
    assert pairs(g["unsupported"]) == {("Sales", "Take order", "NEWAPP")}            # net-new: no as-is support
    assert [a["application_code"] for a in g["retiring"]] == ["CRM", "LEGACY"]       # A7: ECC is allocated
    assert [(r["step"]["node_name"], r["application"]["application_code"])
            for r in g["as_is_support_by_to_be"]] == [("Take order", "NEWAPP")]       # never counted as support
    assert [(u["chart"], u["name"], u["reason"]) for u in g["unmatched"]] == [("TO_BE", "Procurement", "ONLY_TO_BE")]


def test_level_two_pairs_the_sub_areas(client, ed, db):
    world_(client, ed, db)
    g = gap(client, ed, level=2)
    assert pairs(g["unallocated"]) == {("Orders", "Take order", "LEGACY"), ("Billing", "Bill order", "CRM")}
    assert g["unmatched"] == []                                                      # Procurement has no L2
    gap(client, ed, level=3, expect=422)


def test_an_empty_project_returns_zero_inputs_and_an_outsider_gets_404(client, ed):
    g = gap(client, ed)
    assert g["counts"] == {"as_is_processes": 0, "support_links": 0, "to_be_allocations": 0}     # D3
    assert g["unallocated"] == [] and g["retiring"] == []
    gap(client, ed, headers=ed["out"], expect=404)
    stamp(client, ed, report="application_gap")                                      # N4: printable once built


def test_a_component_off_makes_every_part_null(client, ed, world):
    set_components(client, world, ed["p"], ["FUNCTION_REQUIREMENT", "APPLICATION", "SOLUTION"])     # AS_IS off
    g = gap(client, ed)
    assert g["counts"] is None and g["unallocated"] is None and g["unmatched"] is None
