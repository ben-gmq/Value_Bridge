"""Slice 3a through the API: the generated DFD (design §7.2a generate_dfd, D-31; spec
docs/slice3_spec.md §7 3a, criteria 4–8 and 5a). Grade 2 — a client reads the picture.

The DFD is the step I/O drawn without sequence: one flow per active I/O row, except a row an
active external flow covers on (step, DE, direction), which is drawn from/to the party while the
store is still listed. Cross-area is counted over the whole project (A-S3-2).

Not covered here: the canvas itself (criterion 9, the table view, is seen in a browser)."""
import pytest
from sqlalchemy import select

from models import AppUser, BfcNode
from tests.conftest import PW
from tests.test_scope_api import API, ed, entity, node  # noqa: F401 — ed is a fixture


def dfd(client, ed, node_id, headers=None):
    return client.get(f"{API}/bfc-nodes/{node_id}/dfd", headers=headers or ed["h"])


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


def layout_url(ed, scope, kind="DFD"):
    return f"{API}/projects/{ed['p']}/diagram-layouts/{kind}/{scope}"


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


# ---- criterion 4 (design 94): a covered I/O row draws from the party --------------------------

def test_an_external_flow_covers_its_io_row_and_the_store_is_still_drawn(client, ed, area):
    s1 = area["s1"]
    order, cust = entity(client, ed, "Sales order"), party(client, ed, "Customer")
    ext_flow(client, ed, s1, cust, "I", order)                  # creates the (s1, order, I) I/O row
    g = dfd(client, ed, area["parent"]["bfc_node_id"], headers=ed["rv"]).json()
    assert [f["kind"] for f in g["flows"]] == ["EXTERNAL"]      # no second store → step flow
    f = g["flows"][0]
    assert (f["external_entity_id"], f["bfc_node_id"], f["direction"], f["label"]) == \
        (cust["external_entity_id"], s1["bfc_node_id"], "I", "Sales order")
    assert [s["de_name"] for s in g["stores"]] == ["Sales order"]
    assert [x["ext_name"] for x in g["externals"]] == ["Customer"]
    assert [p["node_name"] for p in g["processes"]] == ["Receive order", "Check credit"]


def test_the_cover_is_exact_on_step_de_and_direction(client, ed, area):
    s1, s2 = area["s1"], area["s2"]
    order, cust = entity(client, ed, "Sales order"), party(client, ed, "Customer")
    ext_flow(client, ed, s1, cust, "I", order)
    io(client, ed, s1, order, "O")                              # same step and DE, other direction
    io(client, ed, s2, order, "I")                              # same DE and direction, other step
    ext_flow(client, ed, s2, cust, "O", label="phones back")    # no DE: covers nothing
    got = _flows(dfd(client, ed, area["parent"]["bfc_node_id"]).json())
    d, c = order["data_entity_id"], cust["external_entity_id"]
    assert set(got) == {("EXTERNAL", s1["bfc_node_id"], "I", d, c), ("STORE", s1["bfc_node_id"], "O", d, None),
                        ("STORE", s2["bfc_node_id"], "I", d, None), ("EXTERNAL", s2["bfc_node_id"], "O", None, c)}
    assert got[("EXTERNAL", s2["bfc_node_id"], "O", None, c)]["label"] == "phones back"


def test_external_label_is_the_de_name_first_then_flow_label_else_blank(client, ed, area):
    s1, s2 = area["s1"], area["s2"]
    order, bank = entity(client, ed, "Sales order"), party(client, ed, "Bank")
    ext_flow(client, ed, s1, bank, "O", order, "emailed PO")
    ext_flow(client, ed, s2, bank, "I")
    labels = {f["bfc_node_id"]: f["label"] for f in dfd(client, ed, area["parent"]["bfc_node_id"]).json()["flows"]}
    assert labels == {s1["bfc_node_id"]: "Sales order", s2["bfc_node_id"]: None}


# ---- criterion 5 --------------------------------------------------------------------------------

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
    g = dfd(client, ed, area["parent"]["bfc_node_id"]).json()
    assert sorted((f["kind"], f["bfc_node_id"], f["data_entity_id"], f["direction"], f["label"]) for f in g["flows"]) == \
        sorted([("STORE", s1["bfc_node_id"], cust["data_entity_id"], "I", "Customer"),
                ("STORE", s1["bfc_node_id"], stock["data_entity_id"], "I", "Stock"),
                ("STORE", s1["bfc_node_id"], order["data_entity_id"], "O", "Sales order")])
    assert all(f["bfc_node_data_entity_id"] and f["bfc_node_external_flow_id"] is None for f in g["flows"])


def test_a_dfd_reads_no_sequence_edges(client, ed, area):
    """D-31: an edge between the steps changes nothing on the DFD."""
    order = entity(client, ed, "Sales order")
    io(client, ed, area["s1"], order, "O")
    before = dfd(client, ed, area["parent"]["bfc_node_id"]).json()
    r = client.post(f"{API}/projects/{ed['p']}/process-flows", headers=ed["h"], json={
        "from_bfc_node_id": area["s1"]["bfc_node_id"], "to_bfc_node_id": area["s2"]["bfc_node_id"],
        "flow_type": "SEQUENCE"})
    assert r.status_code == 201
    assert dfd(client, ed, area["parent"]["bfc_node_id"]).json() == before


# ---- criterion 6: cross-area is project-wide (A-S3-2) ----------------------------------------

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
    g = dfd(client, ed, area["parent"]["bfc_node_id"]).json()
    assert {p["bfc_node_id"] for p in g["processes"]} == {s1["bfc_node_id"], s2["bfc_node_id"]}   # no 02 step in frame
    assert len(g["stores"]) == 4
    assert set(g["cross_area"]) == {x["data_entity_id"], both["data_entity_id"]}
    assert set(dfd(client, ed, billing["bfc_node_id"]).json()["cross_area"]) == \
        {x["data_entity_id"], both["data_entity_id"]}


def test_a_retired_reader_no_longer_makes_a_store_cross_area(client, ed, area):
    fin = node(client, ed, "Finance")
    r2 = node(client, ed, "Raise invoice", node(client, ed, "Billing", fin["bfc_node_id"])["bfc_node_id"],
              is_process=True)
    x = entity(client, ed, "Sales order")
    io(client, ed, area["s1"], x, "O")
    read = io(client, ed, r2, x, "I")
    assert dfd(client, ed, area["parent"]["bfc_node_id"]).json()["cross_area"] == [x["data_entity_id"]]
    client.delete(f"{API}/bfc-nodes/{r2['bfc_node_id']}/data-entities/{read['bfc_node_data_entity_id']}",
                  headers=ed["h"], params={"row_version": read["row_version"]})
    assert dfd(client, ed, area["parent"]["bfc_node_id"]).json()["cross_area"] == []


# ---- criterion 7 -------------------------------------------------------------------------------

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
    """A-S3-1: the scope is the process-flow scope — every process descendant, any depth."""
    g = dfd(client, ed, area["l1"]["bfc_node_id"]).json()
    assert [p["node_name"] for p in g["processes"]] == ["Receive order", "Check credit"]
    assert g["flows"] == [] and g["stores"] == [] and g["cross_area"] == [] and g["layout"] == []


# ---- criterion 8: positions persist, separate from the process flow ---------------------------

def test_dfd_positions_persist_and_are_independent_of_the_process_flow(client, ed, area):
    scope, s1 = area["parent"]["bfc_node_id"], area["s1"]
    order, cust = entity(client, ed, "Sales order"), party(client, ed, "Customer")
    ext_flow(client, ed, s1, cust, "I", order)
    items = [{"object_type": "STEP", "object_id": s1["bfc_node_id"], "x": 10, "y": 20},
             {"object_type": "ENTITY", "object_id": order["data_entity_id"], "x": 300, "y": 40},
             {"object_type": "EXTERNAL", "object_id": cust["external_entity_id"], "x": -200, "y": 0}]
    r = client.put(layout_url(ed, scope), headers=ed["h"], json=items)
    assert r.status_code == 200, r.text
    client.put(layout_url(ed, scope, "PROCESS_FLOW"), headers=ed["h"],
               json=[{"object_type": "STEP", "object_id": s1["bfc_node_id"], "x": 999, "y": 999}])
    got = {(p["object_type"], p["object_id"]): (p["x"], p["y"])
           for p in dfd(client, ed, scope, headers=ed["rv"]).json()["layout"]}
    assert got == {("STEP", s1["bfc_node_id"]): (10, 20), ("ENTITY", order["data_entity_id"]): (300, 40),
                   ("EXTERNAL", cust["external_entity_id"]): (-200, 0)}
    flow = client.get(f"{API}/bfc-nodes/{scope}/process-flow", headers=ed["h"]).json()
    assert [(p["object_type"], p["x"]) for p in flow["layout"]] == [("STEP", 999)]
    assert client.delete(layout_url(ed, scope), headers=ed["rv"]).status_code == 403
    assert client.delete(layout_url(ed, scope), headers=ed["h"]).status_code == 204
    assert dfd(client, ed, scope).json()["layout"] == []
    assert len(client.get(f"{API}/bfc-nodes/{scope}/process-flow", headers=ed["h"]).json()["layout"]) == 1


def test_dfd_layout_refuses_events_and_collapse(client, ed, area):
    scope = area["parent"]["bfc_node_id"]
    start = client.post(f"{API}/projects/{ed['p']}/process-flows", headers=ed["h"], json={
        "to_bfc_node_id": area["s1"]["bfc_node_id"], "flow_type": "SEQUENCE"}).json()
    r = client.put(layout_url(ed, scope), headers=ed["h"],
                   json=[{"object_type": "EVENT", "object_id": start["bfc_node_flow_id"], "x": 0, "y": 0}])
    assert r.status_code == 422
    r = client.put(layout_url(ed, scope), headers=ed["h"], json=[
        {"object_type": "STEP", "object_id": area["s1"]["bfc_node_id"], "x": 0, "y": 0, "collapsed": True}])
    assert r.status_code == 422


# ---- criterion 5a: the invariant, over the seeded demo project --------------------------------

def test_every_in_scope_io_row_appears_exactly_once_over_the_demo_project(client, world, db):
    from seeds.seed_demo import build_project
    admin = db.scalar(select(AppUser).where(AppUser.email == "admin@example.test"))
    pid = build_project(db, admin, "example.test", PW)
    h = world["admin"]
    parents = db.scalars(select(BfcNode).where(BfcNode.project_id == pid, BfcNode.is_active,
                                               ~BfcNode.is_process)).all()
    checked = labelled = 0
    for parent in parents:
        g = client.get(f"{API}/bfc-nodes/{parent.bfc_node_id}/dfd", headers=h).json()
        steps = {p["bfc_node_id"] for p in g["processes"]}
        rows = [r for s in steps for r in
                client.get(f"{API}/bfc-nodes/{s}/data-entities", headers=h).json()]  # live rows only
        exts = [x for s in steps for x in
                client.get(f"{API}/bfc-nodes/{s}/external-flows", headers=h).json()]
        store_ids = [f["bfc_node_data_entity_id"] for f in g["flows"] if f["kind"] == "STORE"]
        covered = {(x["bfc_node_id"], x["data_entity_id"], x["direction"]) for x in exts if x["data_entity_id"]}
        for r in rows:
            as_store = store_ids.count(r["bfc_node_data_entity_id"])
            is_covered = (r["bfc_node_id"], r["data_entity_id"], r["direction"]) in covered
            assert as_store + is_covered == 1, (parent.node_name, r)
        assert len(store_ids) == len(set(store_ids))
        assert sorted(f["bfc_node_external_flow_id"] for f in g["flows"] if f["kind"] == "EXTERNAL") == \
            sorted(x["bfc_node_external_flow_id"] for x in exts)
        assert {s["data_entity_id"] for s in g["stores"]} == {r["data_entity_id"] for r in rows}
        for x in exts:
            if x["data_entity_id"] and x["flow_label"]:
                f = next(f for f in g["flows"] if f["bfc_node_external_flow_id"] == x["bfc_node_external_flow_id"])
                store = next(s for s in g["stores"] if s["data_entity_id"] == x["data_entity_id"])
                assert f["label"] == store["de_name"] != x["flow_label"]
                labelled += 1
        checked += len(rows)
    assert checked > 0 and labelled > 0                  # the seed holds a covered row with a label
    capture = next(p for p in parents if p.node_name == "Order capture")
    g = client.get(f"{API}/bfc-nodes/{capture.bfc_node_id}/dfd", headers=h).json()
    order = next(s for s in g["stores"] if s["de_name"] == "Sales order")
    assert order["data_entity_id"] in g["cross_area"]                 # written under 01, read under 02
