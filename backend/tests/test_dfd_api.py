"""The DFD — the one process diagram (slice 3a, reworked by slice 7c: D-38, D-46, D-47, D-49;
slice7_schema §9.7–§9.8). Grade 2 — a client reads the picture.

The DFD is the step I/O drawn without stored sequence: one flow per active I/O row, except a row an
active external flow covers on (step, DE, direction), which is drawn from/to the party while the
store is still listed; plus one TRIGGER flow per live trigger link. The swimlane is the performer.
Order is derived (B follows A when B reads a DE A writes), ranked loop-safely. Stores read or written
by a process of the same chart outside the frame are boundary stubs. Cross-area is counted over the
whole chart (A-S3-2). The process-flow arrows (bfc_node_flow) were retired by 0045 and are SELECT-only.

Not covered here: the canvas itself (the table view is seen in a browser)."""
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from database import SessionLocal
from models import AppUser, BfcNode
from services import consistency, process_flow
from tests.conftest import OWNER_URL, PW
from tests.test_scope_api import API, _org_role, ed, entity, node, tree  # noqa: F401 — ed is a fixture


def dfd(client, ed, node_id, headers=None):
    return client.get(f"{API}/bfc-nodes/{node_id}/dfd", headers=headers or ed["h"])


def graph(client, ed, n, headers=None):
    r = dfd(client, ed, n["bfc_node_id"], headers)
    assert r.status_code == 200, r.text
    return r.json()


def io(client, ed, step, de, direction, expect=201):
    r = client.post(f"{API}/bfc-nodes/{step['bfc_node_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": de["data_entity_id"], "direction": direction})
    assert r.status_code == expect, r.text
    return r.json()


def party(client, ed, name):
    r = client.post(f"{API}/projects/{ed['p']}/external-entities", headers=ed["h"], json={"ext_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def ext_flow(client, ed, step, who, direction, de=None, label=None):
    r = client.post(f"{API}/bfc-nodes/{step['bfc_node_id']}/external-flows", headers=ed["h"],
                    json={"external_entity_id": who["external_entity_id"], "direction": direction,
                          "data_entity_id": de and de["data_entity_id"], "flow_label": label})
    assert r.status_code == 201, r.text
    return r.json()


def performer(client, ed, step, kind, code=None, label=None, headers=None, expect=200):
    """PUT the step's performer (D-46): a department, a position or a system by code, or an AI by label."""
    cur = client.get(f"{API}/bfc-nodes/{step['bfc_node_id']}", headers=ed["h"]).json()
    r = client.put(f"{API}/bfc-nodes/{step['bfc_node_id']}/performer", headers=headers or ed["h"],
                   json={"row_version": cur["row_version"], "performer_kind": kind, "code": code,
                         "performer_label": label})
    assert r.status_code == expect, r.text
    return r.json()


def trigger(client, ed, name, kind="TIME", schedule_note=None):
    r = client.post(f"{API}/projects/{ed['p']}/process-triggers", headers=ed["h"],
                    json={"trigger_name": name, "trigger_kind": kind, "schedule_note": schedule_note})
    assert r.status_code == 201, r.text
    return r.json()


def starts(client, ed, step, trig, expect=201):
    """Link a trigger to the step it starts (D-49)."""
    r = client.post(f"{API}/bfc-nodes/{step['bfc_node_id']}/triggers", headers=ed["h"],
                    json={"process_trigger_id": trig["process_trigger_id"]})
    assert r.status_code == expect, r.text
    return r.json()


def as_is_root(client, ed, name="Sales (as is)"):
    """A root of the as-is chart (D-47): the body names its chart; children take their parent's."""
    r = client.post(f"{API}/projects/{ed['p']}/bfc-nodes", headers=ed["h"],
                    json={"node_name": name, "bfc_set": "AS_IS"})
    assert r.status_code == 201, r.text
    assert r.json()["bfc_set_code"] == "AS_IS"
    return r.json()


def completeness(client, ed, bfc_set="TO_BE", headers=None):
    r = client.get(f"{API}/projects/{ed['p']}/process-completeness", headers=headers or ed["h"],
                   params={"bfc_set": bfc_set})
    assert r.status_code == 200, r.text
    return r.json()


def layout_url(ed, scope, kind="DFD"):
    return f"{API}/projects/{ed['p']}/diagram-layouts/{kind}/{scope}"


def names(rows):
    return [r["node_name"] for r in rows]


@pytest.fixture
def area(client, ed):
    """L1 01 Sales › 01.01 Order capture with two steps."""
    a = node(client, ed, "Sales")
    b = node(client, ed, "Order capture", a["bfc_node_id"])
    return {"l1": a, "parent": b,
            "s1": node(client, ed, "Receive order", b["bfc_node_id"], is_process=True),
            "s2": node(client, ed, "Check credit", b["bfc_node_id"], is_process=True)}


def _flows(g):
    return {(f["kind"], f["bfc_node_id"], f["direction"], f["data_entity_id"], f["external_entity_id"]): f
            for f in g["flows"]}


# ---- stores and external parties: a covered I/O row draws from the party ------------------------

def test_an_external_flow_covers_its_io_row_and_the_store_is_still_drawn(client, ed, area):
    s1 = area["s1"]
    order, cust = entity(client, ed, "Sales order"), party(client, ed, "Customer")
    ext_flow(client, ed, s1, cust, "I", order)                  # creates the (s1, order, I) I/O row
    g = graph(client, ed, area["parent"], headers=ed["rv"])
    assert [f["kind"] for f in g["flows"]] == ["EXTERNAL"]      # no second store → step flow
    f = g["flows"][0]
    assert (f["external_entity_id"], f["bfc_node_id"], f["direction"], f["label"]) == \
        (cust["external_entity_id"], s1["bfc_node_id"], "I", "Sales order")
    assert [s["de_name"] for s in g["stores"]] == ["Sales order"]
    assert [x["ext_name"] for x in g["externals"]] == ["Customer"]
    assert names(g["processes"]) == ["Receive order", "Check credit"]
    assert g["scope"]["bfc_node_id"] == area["parent"]["bfc_node_id"] and g["scope"]["bfc_set_code"] == "TO_BE"


def test_the_cover_is_exact_on_step_de_and_direction(client, ed, area):
    s1, s2 = area["s1"], area["s2"]
    order, cust = entity(client, ed, "Sales order"), party(client, ed, "Customer")
    ext_flow(client, ed, s1, cust, "I", order)
    io(client, ed, s1, order, "O")                              # same step and DE, other direction
    io(client, ed, s2, order, "I")                              # same DE and direction, other step
    ext_flow(client, ed, s2, cust, "O", label="phones back")    # no DE: covers nothing
    got = _flows(graph(client, ed, area["parent"]))
    d, c = order["data_entity_id"], cust["external_entity_id"]
    assert set(got) == {("EXTERNAL", s1["bfc_node_id"], "I", d, c), ("STORE", s1["bfc_node_id"], "O", d, None),
                        ("STORE", s2["bfc_node_id"], "I", d, None), ("EXTERNAL", s2["bfc_node_id"], "O", None, c)}
    assert got[("EXTERNAL", s2["bfc_node_id"], "O", None, c)]["label"] == "phones back"


def test_external_label_is_the_de_name_first_then_flow_label_else_blank(client, ed, area):
    s1, s2 = area["s1"], area["s2"]
    order, bank = entity(client, ed, "Sales order"), party(client, ed, "Bank")
    ext_flow(client, ed, s1, bank, "O", order, "emailed PO")
    ext_flow(client, ed, s2, bank, "I")
    labels = {f["bfc_node_id"]: f["label"] for f in graph(client, ed, area["parent"])["flows"]}
    assert labels == {s1["bfc_node_id"]: "Sales order", s2["bfc_node_id"]: None}


def test_two_inputs_and_one_output_draw_three_flows_and_a_retired_row_draws_nothing(client, ed, area):
    s1 = area["s1"]
    cust, order, stock = entity(client, ed, "Customer"), entity(client, ed, "Sales order"), entity(client, ed, "Stock")
    io(client, ed, s1, cust, "I")
    io(client, ed, s1, stock, "I")
    io(client, ed, s1, order, "O")
    gone = io(client, ed, area["s2"], stock, "O")
    r = client.delete(f"{API}/bfc-nodes/{area['s2']['bfc_node_id']}/data-entities/{gone['bfc_node_data_entity_id']}",
                      headers=ed["h"], params={"row_version": gone["row_version"]})
    assert r.status_code == 204
    g = graph(client, ed, area["parent"])
    assert sorted((f["kind"], f["bfc_node_id"], f["data_entity_id"], f["direction"], f["label"]) for f in g["flows"]) == \
        sorted([("STORE", s1["bfc_node_id"], cust["data_entity_id"], "I", "Customer"),
                ("STORE", s1["bfc_node_id"], stock["data_entity_id"], "I", "Stock"),
                ("STORE", s1["bfc_node_id"], order["data_entity_id"], "O", "Sales order")])
    assert all(f["external_entity_id"] is None and f["process_trigger_id"] is None for f in g["flows"])
    assert g["order"] == []                                     # the retired writer orders nothing


# ---- lanes are performers (D-46, §9.8) -----------------------------------------------------------

def test_lanes_are_the_performers_in_kind_order_with_unassigned_last(client, ed, area):
    parent, s1, s2 = area["parent"], area["s1"], area["s2"]
    s3 = node(client, ed, "Post order", parent["bfc_node_id"], is_process=True)
    s4 = node(client, ed, "Score risk", parent["bfc_node_id"], is_process=True)
    s5 = node(client, ed, "File order", parent["bfc_node_id"], is_process=True)
    clerk = _org_role(client, ed, "CLERK")                      # creates org unit FIN "Finance"
    unit = client.get(f"{API}/projects/{ed['p']}/org-units", headers=ed["h"]).json()[0]
    sap = client.post(f"{API}/projects/{ed['p']}/applications", headers=ed["h"],
                      json={"application_code": "SAP-ECC", "application_name": "SAP ECC",
                            "lifecycle_code": "BOTH"}).json()
    out = performer(client, ed, s1, "ORG_ROLE", "clerk")       # a code, any case
    assert (out["performer_kind"], out["performer_org_role_id"]) == ("ORG_ROLE", clerk["org_role_id"])
    performer(client, ed, s2, "AI", label="  Credit bot ")
    performer(client, ed, s3, "ORG_UNIT", "FIN")
    performer(client, ed, s4, "APPLICATION", "SAP-ECC")
    g = graph(client, ed, parent, headers=ed["rv"])
    keys = [f"ORG_UNIT:{unit['org_unit_id']}", f"ORG_ROLE:{clerk['org_role_id']}",
            f"APPLICATION:{sap['application_id']}", "AI:Credit bot", "UNASSIGNED"]
    assert [ln["lane_key"] for ln in g["lanes"]] == keys
    assert [(ln["kind"], ln["code"], ln["name"]) for ln in g["lanes"]] == [
        ("ORG_UNIT", "FIN", "Finance"), ("ORG_ROLE", "CLERK", "CLERK"), ("APPLICATION", "SAP-ECC", "SAP ECC"),
        ("AI", None, "Credit bot"), ("UNASSIGNED", None, None)]
    assert g["lanes"][1]["unit_name"] == "Finance"             # a position names its department
    lane_of = {p["bfc_node_id"]: p["lane_key"] for p in g["processes"]}
    assert [lane_of[s["bfc_node_id"]] for s in (s3, s1, s4, s2, s5)] == keys
    assert names(g["completeness"]["no_performer"]) == ["File order"]

    performer(client, ed, s2, None)                             # cleared: back to the unassigned lane
    g = graph(client, ed, parent)
    assert "AI:Credit bot" not in [ln["lane_key"] for ln in g["lanes"]]
    assert {p["lane_key"] for p in g["processes"] if p["bfc_node_id"] == s2["bfc_node_id"]} == {"UNASSIGNED"}
    assert names(completeness(client, ed)["no_performer"]) == ["Check credit", "File order"]


def test_a_performer_is_validated_and_closed_to_reviewers(client, ed, area):
    s1 = area["s1"]
    performer(client, ed, s1, "ORG_ROLE", "NOBODY", expect=422)
    performer(client, ed, s1, "AI", label="   ", expect=422)
    performer(client, ed, s1, "ORG_UNIT", None, expect=422)
    performer(client, ed, area["parent"], "AI", label="Bot", expect=422)        # a parent has no performer
    performer(client, ed, s1, "AI", label="Bot", headers=ed["rv"], expect=403)
    performer(client, ed, s1, "AI", label="Bot", headers=ed["out"], expect=404)
    one = performer(client, ed, s1, "AI", label="Bot")
    stale = client.put(f"{API}/bfc-nodes/{s1['bfc_node_id']}/performer", headers=ed["h"],
                       json={"row_version": one["row_version"] - 1, "performer_kind": None})
    assert stale.status_code == 409


# ---- triggers start processes (D-49) ---------------------------------------------------------------

def test_a_trigger_is_a_flow_into_each_step_it_starts(client, ed, area):
    s1, s2 = area["s1"], area["s2"]
    month = trigger(client, ed, "Month-end close", "TIME", "last working day")
    calls = trigger(client, ed, "customer calls", "EVENT")
    starts(client, ed, s1, month)
    link = starts(client, ed, s1, calls)
    starts(client, ed, s2, month)
    starts(client, ed, s1, month, expect=409)                   # once per step
    starts(client, ed, area["parent"], month, expect=422)       # a trigger starts a process step only
    g = graph(client, ed, area["parent"])
    assert [(t["trigger_name"], t["trigger_kind"], t["schedule_note"]) for t in g["triggers"]] == [
        ("customer calls", "EVENT", None), ("Month-end close", "TIME", "last working day")]   # by name, any case
    trig = sorted((f["bfc_node_id"], f["process_trigger_id"], f["direction"], f["label"])
                  for f in g["flows"] if f["kind"] == "TRIGGER")
    assert trig == sorted([(s1["bfc_node_id"], month["process_trigger_id"], "I", "Month-end close"),
                           (s1["bfc_node_id"], calls["process_trigger_id"], "I", "customer calls"),
                           (s2["bfc_node_id"], month["process_trigger_id"], "I", "Month-end close")])
    assert all(f["data_entity_id"] is None and f["external_entity_id"] is None
               for f in g["flows"] if f["kind"] == "TRIGGER")
    # a trigger is an input: neither step is missing one now
    assert g["completeness"]["missing_input"] == []
    assert names(g["completeness"]["missing_output"]) == ["Receive order", "Check credit"]

    r = client.delete(f"{API}/bfc-nodes/{s1['bfc_node_id']}/triggers/{link['bfc_node_trigger_id']}",
                      headers=ed["h"], params={"row_version": link["row_version"]})
    assert r.status_code == 204
    g = graph(client, ed, area["parent"])
    assert [t["trigger_name"] for t in g["triggers"]] == ["Month-end close"]
    # a trigger a live step names cannot be retired (R2-D2)
    r = client.delete(f"{API}/process-triggers/{month['process_trigger_id']}", headers=ed["h"],
                      params={"row_version": month["row_version"]})
    assert r.status_code == 409


# ---- derived order and a loop-safe rank (D-38, Q-33) ----------------------------------------------

def test_order_is_derived_from_data_and_a_loop_shares_a_rank(client, ed, area):
    parent, s1, s2 = area["parent"], area["s1"], area["s2"]
    s3 = node(client, ed, "Approve order", parent["bfc_node_id"], is_process=True)
    s4 = node(client, ed, "Ship order", parent["bfc_node_id"], is_process=True)
    order, credit, note = entity(client, ed, "Sales order"), entity(client, ed, "Credit check"), entity(client, ed, "Note")
    io(client, ed, s1, order, "O")
    io(client, ed, s1, note, "O")
    io(client, ed, s1, note, "I")                               # reads what it writes: no self-order
    io(client, ed, s2, order, "I")
    io(client, ed, s2, credit, "O")
    io(client, ed, s3, credit, "I")
    io(client, ed, s3, order, "O")                              # a rework loop: s3 feeds s2 again
    io(client, ed, s4, order, "I")
    g = graph(client, ed, parent)
    a, b, c, d = (s["bfc_node_id"] for s in (s1, s2, s3, s4))
    o, cr = order["data_entity_id"], credit["data_entity_id"]
    assert [(x["from_bfc_node_id"], x["to_bfc_node_id"], x["data_entity_ids"]) for x in g["order"]] == sorted([
        (a, b, [o]), (a, d, [o]), (b, c, [cr]), (c, b, [o]), (c, d, [o])])
    rank = {p["bfc_node_id"]: p["rank"] for p in g["processes"]}
    assert rank == {a: 0, b: 1, c: 1, d: 2}                     # the loop {s2, s3} is one component


def test_rank_terminates_on_cycles_and_isolated_steps():
    def o(x, y):
        return {"from_bfc_node_id": x, "to_bfc_node_id": y, "data_entity_ids": [1]}
    assert process_flow.rank([1, 2, 3, 4, 5], [o(1, 2), o(2, 3), o(3, 1), o(3, 4)]) == {1: 0, 2: 0, 3: 0, 4: 1, 5: 0}
    assert process_flow.rank([7], [o(7, 7)]) == {7: 0}
    chain = list(range(1, 2001))                               # A-35: 2,000 steps, no recursion limit
    got = process_flow.rank(chain, [o(i, i + 1) for i in chain[:-1]])
    assert got[1] == 0 and got[2000] == 1999


# ---- boundary stubs: the same chart outside the frame, never the other chart ----------------------

def test_boundary_stubs_name_outside_writers_and_readers_of_the_same_chart(client, ed, area):
    s1, s2 = area["s1"], area["s2"]
    fin = node(client, ed, "Finance")
    billing = node(client, ed, "Billing", fin["bfc_node_id"])
    r2 = node(client, ed, "Raise invoice", billing["bfc_node_id"], is_process=True)
    order, invoice = entity(client, ed, "Sales order"), entity(client, ed, "Invoice")
    io(client, ed, s1, order, "O")
    io(client, ed, r2, order, "I")                              # an outside reader → out
    io(client, ed, r2, invoice, "O")
    io(client, ed, s2, invoice, "I")                            # an outside writer → in
    old = node(client, ed, "Old order desk", node(client, ed, "Desk", as_is_root(client, ed)["bfc_node_id"])
               ["bfc_node_id"], is_process=True)
    assert old["bfc_set_code"] == "AS_IS"
    io(client, ed, old, order, "I")                             # the other chart: never a stub
    io(client, ed, old, invoice, "O")
    g = graph(client, ed, area["parent"])
    assert [(x["data_entity_id"], x["bfc_node_id"]) for x in g["boundary"]["in"]] == \
        [(invoice["data_entity_id"], r2["bfc_node_id"])]
    assert [(x["data_entity_id"], x["bfc_node_id"], x["hier_code"]) for x in g["boundary"]["out"]] == \
        [(order["data_entity_id"], r2["bfc_node_id"], "02.01.01")]
    assert {(x["from_bfc_node_id"], x["to_bfc_node_id"]) for x in g["order"]} == set()   # order stays in the frame
    other = graph(client, ed, billing)                          # and the reverse from the other side
    assert [(x["data_entity_id"], x["bfc_node_id"]) for x in other["boundary"]["in"]] == \
        [(order["data_entity_id"], s1["bfc_node_id"])]
    assert [(x["data_entity_id"], x["bfc_node_id"]) for x in other["boundary"]["out"]] == \
        [(invoice["data_entity_id"], s2["bfc_node_id"])]


# ---- completeness (D-38, §9.7) — the report that replaced flow-completeness ------------------------

def test_process_completeness_names_the_missing_input_and_output(client, ed, area, db):
    s1, s2 = area["s1"], area["s2"]
    first = completeness(client, ed, headers=ed["rv"])
    assert first["bfc_set_code"] == "TO_BE" and first["rule_applies"] is True
    assert names(first["missing_input"]) == names(first["missing_output"]) == ["Receive order", "Check credit"]
    assert names(first["no_performer"]) == ["Receive order", "Check credit"]
    assert first["step_without_br"] == [] and first["live_link_on_retired_step"] == []
    order = entity(client, ed, "Sales order")
    io(client, ed, s1, entity(client, ed, "Customer"), "I")
    io(client, ed, s1, order, "O")
    starts(client, ed, s2, trigger(client, ed, "Month-end close"))
    mid = completeness(client, ed)
    assert mid["missing_input"] == [] and names(mid["missing_output"]) == ["Check credit"]
    out = consistency.consistency_check(ed["p"], db)            # the same gaps feed the freeze gate
    assert names(out["process_missing_input"]) == [] and names(out["process_missing_output"]) == ["Check credit"]
    assert {"process_missing_input", "process_missing_output"} == consistency.FREEZE_BLOCKING_WARNINGS


def test_io_licence_checks_are_empty_in_normal_use(client, ed, area):
    """Criterion 148 (moved from the retired process-flow tests): the licence FKs hold these at 0;
    the report proves it, and a BR's C makes the step's output."""
    de = entity(client, ed, "Sales order")
    br = next(b for b in client.get(f"{API}/projects/{ed['p']}/business-requirements",
                                    headers=ed["h"]).json() if b["bfc_node_id"] == area["s1"]["bfc_node_id"])
    r = client.post(f"{API}/business-requirements/{br['br_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": de["data_entity_id"], "crud_code": "C"})
    assert r.status_code == 201, r.text
    ext_flow(client, ed, area["s2"], party(client, ed, "Customer"), "I", de)
    got = completeness(client, ed)
    assert got["crud_without_io"] == [] and got["ext_without_io"] == []
    assert "Receive order" not in names(got["missing_output"])          # C made step output
    assert "Check credit" not in names(got["missing_input"])            # the party's data is an input


def test_the_as_is_chart_has_its_own_completeness_and_no_requirements(client, ed, area):
    root = as_is_root(client, ed)
    assert root["hier_code"] == "01"                            # each chart numbers its own roots
    desk = node(client, ed, "Order desk", root["bfc_node_id"])
    old = node(client, ed, "Key in order", desk["bfc_node_id"], is_process=True)
    assert old["bfc_set_code"] == "AS_IS"                       # a child takes its parent's chart
    as_is = tree(client, ed, bfc_set="AS_IS")
    assert [(n["hier_code"], n["br_number"]) for n in as_is] == [("01", None), ("01.01", None), ("01.01.01", None)]
    assert old["bfc_node_id"] not in {n["bfc_node_id"] for n in tree(client, ed)}       # to-be by default
    got = completeness(client, ed, "AS_IS")
    assert got["bfc_set_code"] == "AS_IS" and names(got["missing_input"]) == ["Key in order"]
    assert got["step_without_br"] == []                         # as-is processes carry no BR (S7-2)
    assert names(completeness(client, ed)["missing_input"]) == ["Receive order", "Check credit"]
    g = graph(client, ed, desk)
    assert names(g["processes"]) == ["Key in order"] and g["scope"]["bfc_set_code"] == "AS_IS"
    r = client.get(f"{API}/projects/{ed['p']}/process-completeness", headers=ed["h"], params={"bfc_set": "BEST"})
    assert r.status_code == 400
    assert client.get(f"{API}/projects/{ed['p']}/process-completeness", headers=ed["out"]).status_code == 404


# ---- cross-area is chart-wide (A-S3-2) ------------------------------------------------------------

def test_cross_area_counts_writers_and_readers_across_the_whole_project(client, ed, area):
    s1, s2 = area["s1"], area["s2"]
    fin = node(client, ed, "Finance")
    billing = node(client, ed, "Billing", fin["bfc_node_id"])
    r2 = node(client, ed, "Raise invoice", billing["bfc_node_id"], is_process=True)
    assert (area["l1"]["hier_code"], fin["hier_code"]) == ("01", "02")
    x, inside, lonely, both = (entity(client, ed, n) for n in ("Sales order", "Credit check", "Draft", "Customer"))
    io(client, ed, s1, x, "O")
    io(client, ed, r2, x, "I")                      # written under 01, read under 02 → cross-area
    io(client, ed, s1, inside, "O")
    io(client, ed, s2, inside, "I")                 # read and written only inside 01 → not
    io(client, ed, s2, lonely, "O")                 # written, read nowhere → not
    for s in (s1, r2):
        io(client, ed, s, both, "O")
        io(client, ed, s, both, "I")                # written and read in both 01 and 02 → cross-area
    g = graph(client, ed, area["parent"])
    assert {p["bfc_node_id"] for p in g["processes"]} == {s1["bfc_node_id"], s2["bfc_node_id"]}   # no 02 step in frame
    assert len(g["stores"]) == 4
    assert set(g["cross_area"]) == {x["data_entity_id"], both["data_entity_id"]}
    assert set(graph(client, ed, billing)["cross_area"]) == {x["data_entity_id"], both["data_entity_id"]}


def test_a_retired_reader_no_longer_makes_a_store_cross_area(client, ed, area):
    fin = node(client, ed, "Finance")
    r2 = node(client, ed, "Raise invoice", node(client, ed, "Billing", fin["bfc_node_id"])["bfc_node_id"],
              is_process=True)
    x = entity(client, ed, "Sales order")
    io(client, ed, area["s1"], x, "O")
    read = io(client, ed, r2, x, "I")
    assert graph(client, ed, area["parent"])["cross_area"] == [x["data_entity_id"]]
    client.delete(f"{API}/bfc-nodes/{r2['bfc_node_id']}/data-entities/{read['bfc_node_data_entity_id']}",
                  headers=ed["h"], params={"row_version": read["row_version"]})
    assert graph(client, ed, area["parent"])["cross_area"] == []


# ---- scope rules -------------------------------------------------------------------------------

def test_a_step_is_422_a_retired_node_is_409_an_invisible_project_is_404(client, ed, area):
    assert dfd(client, ed, area["s1"]["bfc_node_id"]).status_code == 422
    empty = node(client, ed, "Returns", area["l1"]["bfc_node_id"])
    r = client.delete(f"{API}/bfc-nodes/{empty['bfc_node_id']}", headers=ed["h"],
                      params={"row_version": empty["row_version"]})
    assert r.status_code == 204, r.text
    assert dfd(client, ed, empty["bfc_node_id"]).status_code == 409
    assert dfd(client, ed, area["parent"]["bfc_node_id"], headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/bfc-nodes/99999999/dfd", headers=ed["h"]).status_code == 404


def test_an_l1_dfd_draws_every_step_below_it(client, ed, area):
    """A-S3-1: the scope is every process descendant, any depth."""
    g = graph(client, ed, area["l1"])
    assert names(g["processes"]) == ["Receive order", "Check credit"]
    assert g["flows"] == [] and g["stores"] == [] and g["cross_area"] == [] and g["layout"] == []
    assert g["order"] == [] and g["boundary"] == {"in": [], "out": []} and g["triggers"] == []
    assert [p["rank"] for p in g["processes"]] == [0, 0]
    assert all(p["br_number"] and p["systems"] == [] for p in g["processes"])         # to-be steps carry a BR


# ---- positions persist, separate from the retired process flow -----------------------------------

def test_dfd_positions_persist_and_the_process_flow_positions_are_history(client, ed, area):
    scope, s1 = area["parent"]["bfc_node_id"], area["s1"]
    order, cust = entity(client, ed, "Sales order"), party(client, ed, "Customer")
    ext_flow(client, ed, s1, cust, "I", order)
    month = trigger(client, ed, "Month-end close")
    starts(client, ed, s1, month)
    items = [{"object_type": "STEP", "object_id": s1["bfc_node_id"], "x": 10, "y": 20},
             {"object_type": "ENTITY", "object_id": order["data_entity_id"], "x": 300, "y": 40},
             {"object_type": "EXTERNAL", "object_id": cust["external_entity_id"], "x": -200, "y": 0},
             {"object_type": "TRIGGER", "object_id": month["process_trigger_id"], "x": -400, "y": 0}]
    r = client.put(layout_url(ed, scope), headers=ed["h"], json=items)
    assert r.status_code == 200, r.text
    r = client.put(layout_url(ed, scope, "PROCESS_FLOW"), headers=ed["h"],
                   json=[{"object_type": "STEP", "object_id": s1["bfc_node_id"], "x": 999, "y": 999}])
    assert r.status_code == 409                                  # S7-5: never written again
    got = {(p["object_type"], p["object_id"]): (p["x"], p["y"]) for p in graph(client, ed, area["parent"], ed["rv"])["layout"]}
    assert got == {("STEP", s1["bfc_node_id"]): (10, 20), ("ENTITY", order["data_entity_id"]): (300, 40),
                   ("EXTERNAL", cust["external_entity_id"]): (-200, 0),
                   ("TRIGGER", month["process_trigger_id"]): (-400, 0)}
    assert client.get(layout_url(ed, scope, "PROCESS_FLOW"), headers=ed["h"]).json() == []
    assert client.delete(layout_url(ed, scope), headers=ed["rv"]).status_code == 403
    assert client.delete(layout_url(ed, scope), headers=ed["h"]).status_code == 204
    assert graph(client, ed, area["parent"])["layout"] == []


def test_dfd_layout_refuses_events_and_collapse(client, ed, area):
    scope = area["parent"]["bfc_node_id"]
    r = client.put(layout_url(ed, scope), headers=ed["h"],
                   json=[{"object_type": "EVENT", "object_id": 1, "x": 0, "y": 0}])
    assert r.status_code == 422                                  # EVENT: read-only history of the arrows
    r = client.put(layout_url(ed, scope), headers=ed["h"], json=[
        {"object_type": "STEP", "object_id": area["s1"]["bfc_node_id"], "x": 0, "y": 0, "collapsed": True}])
    assert r.status_code == 422


# ---- the arrows are retired: no routes, and the app role may only read them (0045) ------------------

def test_the_arrow_routes_are_gone(client, ed, area):
    p, s1 = area["parent"]["bfc_node_id"], area["s1"]["bfc_node_id"]
    for method, path in (("get", f"/projects/{ed['p']}/process-flows"), ("post", f"/projects/{ed['p']}/process-flows"),
                         ("get", f"/projects/{ed['p']}/flow-completeness"), ("get", f"/bfc-nodes/{p}/process-flow"),
                         ("get", f"/bfc-nodes/{p}/process-flow/export"),
                         ("get", f"/bfc-nodes/{p}/process-flow/suggest"),
                         ("post", f"/bfc-nodes/{p}/process-flow/suggest/keep"),
                         ("patch", f"/process-flows/{s1}"), ("delete", f"/process-flows/{s1}")):
        kw = {"json": {}} if method in ("post", "patch") else {}
        r = getattr(client, method)(f"{API}{path}", headers=ed["h"], **kw)
        assert r.status_code in (404, 405), (method, path, r.status_code)
    assert not hasattr(process_flow, "generate_process_flow")
    from services import render
    assert not hasattr(render, "export_process_flow")


def test_the_arrow_table_is_select_only_for_the_app_role():
    app_user = make_url(SessionLocal.kw["bind"].url).username
    eng = create_engine(OWNER_URL)
    with eng.begin() as c:
        privs = {p for (p,) in c.execute(text(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = :u AND table_name = 'bfc_node_flow'"), {"u": app_user})}
    eng.dispose()
    assert privs == {"SELECT"}
    with SessionLocal() as s:
        assert s.execute(text("SELECT count(*) FROM bfc_node_flow WHERE is_active")).scalar() == 0
        for stmt in ("UPDATE bfc_node_flow SET note = 'x'",
                     "INSERT INTO bfc_node_flow (project_id, flow_type, created_by) VALUES (1, 'SEQUENCE', 1)",
                     "DELETE FROM bfc_node_flow"):
            with pytest.raises(DBAPIError, match="permission denied"):
                s.execute(text(stmt))
            s.rollback()


# ---- the invariant, over the seeded demo project (both charts) -------------------------------------

def test_every_in_scope_io_row_appears_exactly_once_over_the_demo_project(client, world, db):
    from seeds.seed_demo import build_project
    admin = db.scalar(select(AppUser).where(AppUser.email == "admin@example.test"))
    pid = build_project(db, admin, "example.test", PW)
    h = world["admin"]
    parents = db.scalars(select(BfcNode).where(BfcNode.project_id == pid, BfcNode.is_active,
                                               ~BfcNode.is_process)).all()
    assert {p.bfc_set_code for p in parents} == {"TO_BE", "AS_IS"}
    checked = labelled = triggered = 0
    for parent in parents:
        g = client.get(f"{API}/bfc-nodes/{parent.bfc_node_id}/dfd", headers=h).json()
        steps = {p["bfc_node_id"] for p in g["processes"]}
        rows = [r for s in steps for r in
                client.get(f"{API}/bfc-nodes/{s}/data-entities", headers=h).json()]  # live rows only
        exts = [x for s in steps for x in
                client.get(f"{API}/bfc-nodes/{s}/external-flows", headers=h).json()]
        links = [t for s in steps for t in client.get(f"{API}/bfc-nodes/{s}/triggers", headers=h).json()]
        stores = [(f["bfc_node_id"], f["data_entity_id"], f["direction"]) for f in g["flows"] if f["kind"] == "STORE"]
        covered = {(x["bfc_node_id"], x["data_entity_id"], x["direction"]) for x in exts if x["data_entity_id"]}
        for r in rows:
            key = (r["bfc_node_id"], r["data_entity_id"], r["direction"])
            assert stores.count(key) + (key in covered) == 1, (parent.node_name, r)
        assert len(stores) == len(rows) - len([r for r in rows if (r["bfc_node_id"], r["data_entity_id"],
                                                                   r["direction"]) in covered])
        assert len([f for f in g["flows"] if f["kind"] == "EXTERNAL"]) == len(exts)
        assert sorted((f["bfc_node_id"], f["process_trigger_id"]) for f in g["flows"] if f["kind"] == "TRIGGER") == \
            sorted((t["bfc_node_id"], t["process_trigger_id"]) for t in links)
        assert {s["data_entity_id"] for s in g["stores"]} == {r["data_entity_id"] for r in rows}
        assert {p["lane_key"] for p in g["processes"]} == {ln["lane_key"] for ln in g["lanes"]}
        for x in exts:
            if x["data_entity_id"] and x["flow_label"]:
                f = next(f for f in g["flows"] if f["kind"] == "EXTERNAL" and f["bfc_node_id"] == x["bfc_node_id"]
                         and f["external_entity_id"] == x["external_entity_id"]
                         and f["data_entity_id"] == x["data_entity_id"] and f["direction"] == x["direction"])
                store = next(s for s in g["stores"] if s["data_entity_id"] == x["data_entity_id"])
                assert f["label"] == store["de_name"] != x["flow_label"]
                labelled += 1
        checked += len(rows)
        triggered += len(links)
    assert checked > 0 and labelled > 0 and triggered > 0
    capture = next(p for p in parents if p.node_name == "Order capture" and p.bfc_set_code == "TO_BE")
    g = client.get(f"{API}/bfc-nodes/{capture.bfc_node_id}/dfd", headers=h).json()
    order = next(s for s in g["stores"] if s["de_name"] == "Sales order")
    assert order["data_entity_id"] in g["cross_area"]                 # written under 01, read under 02
