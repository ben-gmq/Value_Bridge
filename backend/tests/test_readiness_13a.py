"""Slice 13a (D-68, D-69; slice13_spec §4.1, §7.1, §10 A3–A11): the DFD readiness light, here on projects that keep
today's D-38 rule — something starts the process (a data input, an inbound external party or a trigger), and it
outputs a data entity. Since 13b (Q-13, S13-2) red = a rule element is missing (blocks the freeze) and yellow = the
rule is met but a recommended element (to-be: DATA_IN, ORDER) is missing. The reader is proven to agree with the
freeze gate's own report (A4); the as-is gap still refuses (B8). Per-project rules: tests/test_dfd_rule.py."""
import random

from services import consistency, process_flow
from tests.test_baseline import freeze, preview, scope
from tests.test_charts_7c import switch
from tests.test_dfd_api import as_is_root, completeness, ext_flow, io, party, starts, trigger
from tests.test_scope_api import API, ed, entity, node, tree  # noqa: F401 — ed is a fixture
from tests.test_step_retire import restore, retire


def lights(client, ed, bfc_set="TO_BE", **q):
    return {n["bfc_node_id"]: (n["dfd_light"], n["dfd_missing"]) for n in tree(client, ed, bfc_set=bfc_set, **q)}


def ready_of(client, ed, bfc_set="TO_BE"):
    return completeness(client, ed, bfc_set)["readiness"]


def parent(client, ed):
    a = node(client, ed, "Sales")
    return node(client, ed, "Order to cash", a["bfc_node_id"])


# ---- each light, to-be (A3, A10) ---------------------------------------------------------------

def test_each_light_on_a_to_be_process(client, ed):
    b = parent(client, ed)
    bare, trig_only, out_only, done = (node(client, ed, n, b["bfc_node_id"], is_process=True)
                                       for n in ("Bare", "Trigger only", "Output only", "Done"))
    order = entity(client, ed, "Sales order")
    month_end = trigger(client, ed, "Month end")
    starts(client, ed, trig_only, month_end)
    io(client, ed, out_only, order, "O")
    starts(client, ed, done, month_end)
    io(client, ed, done, order, "O")
    got = lights(client, ed)
    assert got[bare["bfc_node_id"]] == ("NOT_READY", ["STARTED", "DATA_OUT"])
    assert got[trig_only["bfc_node_id"]] == ("NOT_READY", ["DATA_OUT"])           # Q-13: a rule gap is red
    assert got[out_only["bfc_node_id"]] == ("NOT_READY", ["STARTED"])
    assert got[done["bfc_node_id"]] == ("PARTIAL", [])                            # rule met, recommended not
    assert got[b["bfc_node_id"]] == (None, None)                     # a non-process row carries no light
    r = ready_of(client, ed)
    assert r["rule_applies"] is True and r["rule"] == ["STARTED", "DATA_OUT"]
    assert r["processes"][str(done["bfc_node_id"])] == {"light": "PARTIAL", "missing": [],
                                                         "advised": ["DATA_IN", "ORDER"]}


def test_an_inbound_party_or_a_data_input_meets_started_and_no_data_in_element_exists(client, ed):
    """A10 (DR13-D1): STARTED is any one of a trigger, a data input, or an inbound external party."""
    b = parent(client, ed)
    by_party, by_input, outbound = (node(client, ed, n, b["bfc_node_id"], is_process=True)
                                    for n in ("Party starts it", "Data starts it", "Outbound only"))
    cust = party(client, ed, "Customer")
    ext_flow(client, ed, by_party, cust, "I", label="Phone call")      # no data entity, no trigger
    io(client, ed, by_input, entity(client, ed, "Customer"), "I")
    ext_flow(client, ed, outbound, cust, "O", label="Confirmation")    # outbound does not start it
    got = lights(client, ed)
    assert got[by_party["bfc_node_id"]] == ("NOT_READY", ["DATA_OUT"])
    assert got[by_input["bfc_node_id"]] == ("NOT_READY", ["DATA_OUT"])
    assert got[outbound["bfc_node_id"]] == ("NOT_READY", ["STARTED", "DATA_OUT"])
    assert ready_of(client, ed)["rule"] == ["STARTED", "DATA_OUT"]   # no DATA_IN under the fixed rule


# ---- as-is, retired, and a chart whose DFD is off (A5) ---------------------------------------------

def test_the_as_is_chart_has_its_own_lights(client, ed):
    root = as_is_root(client, ed)
    desk = node(client, ed, "Order desk", root["bfc_node_id"])
    old = node(client, ed, "Key in order", desk["bfc_node_id"], is_process=True)
    assert lights(client, ed, "AS_IS")[old["bfc_node_id"]] == ("NOT_READY", ["STARTED", "DATA_OUT"])
    io(client, ed, old, entity(client, ed, "Paper order"), "O")
    assert lights(client, ed, "AS_IS")[old["bfc_node_id"]] == ("NOT_READY", ["STARTED"])
    assert old["bfc_node_id"] not in ready_of(client, ed)["processes"]           # the to-be read never lists it
    assert list(ready_of(client, ed, "AS_IS")["processes"]) == [str(old["bfc_node_id"])]


def test_a_retired_process_has_no_light_and_comes_back_with_its_own(client, ed):
    b = parent(client, ed)
    s = node(client, ed, "Ship", b["bfc_node_id"], is_process=True)
    starts(client, ed, s, trigger(client, ed, "Order paid"))
    assert lights(client, ed)[s["bfc_node_id"]] == ("NOT_READY", ["DATA_OUT"])
    assert retire(client, ed, s["bfc_node_id"]).status_code == 204
    assert s["bfc_node_id"] not in ready_of(client, ed)["processes"]
    assert lights(client, ed, include_retired=True)[s["bfc_node_id"]] == (None, None)
    assert restore(client, ed, s["bfc_node_id"]).status_code == 200
    assert lights(client, ed)[s["bfc_node_id"]] == ("NOT_READY", ["DATA_OUT"])   # the trigger came back with it


def test_no_light_while_the_charts_dfd_is_off(client, world, ed):
    b = parent(client, ed)
    s = node(client, ed, "Ship", b["bfc_node_id"], is_process=True)
    switch(client, world, ed["p"], ["SOLUTION", "FUNCTION_REQUIREMENT", "EFFORT", "APPLICATION", "AS_IS"])
    assert lights(client, ed)[s["bfc_node_id"]] == (None, None)
    r = ready_of(client, ed)
    assert r["rule_applies"] is False and r["processes"] == {}


# ---- one source: the light agrees with the freeze gate's report (A4) ------------------------------

def test_the_light_agrees_with_process_completeness_on_fifty_processes(client, ed, db):
    rng = random.Random(1368)
    b = parent(client, ed)
    des = [entity(client, ed, f"Entity {i}") for i in range(4)]
    trig = trigger(client, ed, "Daily")
    cust = party(client, ed, "Customer")
    steps = [node(client, ed, f"Step {i:02d}", b["bfc_node_id"], is_process=True) for i in range(52)]
    for s in steps:
        how = rng.randrange(4)                                       # 0: nothing starts it
        if how == 1:
            starts(client, ed, s, trig)
        elif how == 2:
            io(client, ed, s, rng.choice(des), "I")
        elif how == 3:
            ext_flow(client, ed, s, cust, "I", label="Call")
        if rng.random() < 0.5:
            io(client, ed, s, rng.choice(des), "O")
    rep = completeness(client, ed)
    no_in = {r["bfc_node_id"] for r in rep["missing_input"]}
    no_out = {r["bfc_node_id"] for r in rep["missing_output"]}
    got = lights(client, ed)
    seen = set()
    for s in steps:
        sid = s["bfc_node_id"]
        light, missing = got[sid]
        assert (light == "NOT_READY") == (sid in no_in or sid in no_out), s["node_name"]     # red = blocks (Q-13)
        assert ("STARTED" in missing) == (sid in no_in) and ("DATA_OUT" in missing) == (sid in no_out)
        seen.add(light)
    assert seen == {"READY", "PARTIAL", "NOT_READY"}                 # the sample covers every light
    assert {k: (v["light"], v["missing"]) for k, v in rep["readiness"]["processes"].items()} == {
        str(k): v for k, v in got.items() if v[0] is not None}
    gate = consistency.consistency_check(ed["p"], db)                  # and the freeze gate reads the same gaps
    assert {r["bfc_node_id"] for r in gate["process_missing_input"]} == no_in
    assert {r["bfc_node_id"] for r in gate["process_missing_output"]} == no_out
    direct = process_flow.readiness(db, ed["p"], "TO_BE", [steps[0]["bfc_node_id"]])["processes"]
    assert list(direct) == [steps[0]["bfc_node_id"]]                   # node_ids narrows the read


# ---- the freeze is unchanged in 13a (A8, DR13-P1) ----------------------------------------------------

def test_an_as_is_gap_still_refuses_the_freeze(client, ed):
    scope(client, ed)                                                  # a clean to-be chart
    root = as_is_root(client, ed)
    desk = node(client, ed, "Order desk", root["bfc_node_id"])
    old = node(client, ed, "Key in order", desk["bfc_node_id"], is_process=True)
    assert lights(client, ed, "AS_IS")[old["bfc_node_id"]][0] == "NOT_READY"
    p = preview(client, ed)
    assert [r["bfc_node_id"] for r in p["freeze_blocking"]["process_missing_input"]] == [old["bfc_node_id"]]
    out = freeze(client, ed, expect=409)
    assert [r["bfc_node_id"] for r in out["detail"]["freeze_blocking"]["process_missing_output"]] == [old["bfc_node_id"]]
    assert client.get(f"{API}/projects/{ed['p']}/baselines", headers=ed["h"]).json() == []


def test_red_refuses_the_freeze_and_yellow_freezes(client, ed):
    """Q-13 (S13-2, ending DR13-P2's interim rule): red = a rule element missing, refused; yellow = the rule met but a
    recommended element missing, frozen; green = nothing missing."""
    w = scope(client, ed)
    s = node(client, ed, "Ship order", w["group"]["bfc_node_id"], is_process=True)
    starts(client, ed, s, trigger(client, ed, "Order paid"))
    assert lights(client, ed)[s["bfc_node_id"]] == ("NOT_READY", ["DATA_OUT"])
    freeze(client, ed, expect=409)
    io(client, ed, s, entity(client, ed, "Shipment"), "O")              # nobody reads it: no order, no data in
    assert lights(client, ed)[s["bfc_node_id"]] == ("PARTIAL", [])
    assert freeze(client, ed)["baseline"]["version_label"] == "v1.0"
    io(client, ed, s, w["invoice"], "I")                                # reads what s2 writes: data in and order
    assert lights(client, ed)[s["bfc_node_id"]] == ("READY", [])
