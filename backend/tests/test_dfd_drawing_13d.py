"""Slice 13d (D-65; slice13_spec §4.4, §7.4, §10 D1–D7): connections drawn on the DFD canvas.

Drawing writes through the writers the panel already uses — step I/O (`step_io.ensure_step_io`), the
external-flow route and the trigger-link route — plus ONE new route, the process-to-process hand-off,
which writes A's output and B's input in one transaction. Order stays derived (D-38). Drawing never
writes BR CRUD (Q-11). Every drawn flow carries the one row behind it, so the canvas removes STORE,
EXTERNAL and TRIGGER flows by that row's existing unlink route; a derived order arrow has no row and
cannot be removed (DR13-P3). The canvas itself is seen in a browser."""
from sqlalchemy import select

from models import BfcNodeDataEntity, BrDataEntity
from services import step_io
from tests.test_charts_7c import switch
from tests.test_dfd_api import area, ext_flow, graph, io, party, starts, trigger  # noqa: F401 — area is a fixture
from tests.test_scope_api import API, ed, entity, node  # noqa: F401 — ed is a fixture

ALL_BUT_TO_BE_DFD = ["SOLUTION", "FUNCTION_REQUIREMENT", "EFFORT", "APPLICATION", "AS_IS"]


def hand_off(client, h, a, b, de, expect=201):
    r = client.post(f"{API}/bfc-nodes/{a['bfc_node_id']}/hand-offs", headers=h,
                    json={"to_bfc_node_id": b["bfc_node_id"], "data_entity_id": de["data_entity_id"]})
    assert r.status_code == expect, r.text
    return r.json()


def live_io(db, step_ids, de_id):
    db.expire_all()
    return {(r.bfc_node_id, r.direction): r for r in db.scalars(select(BfcNodeDataEntity).where(
        BfcNodeDataEntity.bfc_node_id.in_(step_ids), BfcNodeDataEntity.data_entity_id == de_id,
        BfcNodeDataEntity.is_active))}


# ---- D2: the hand-off ------------------------------------------------------------------------------

def test_a_hand_off_writes_a_output_and_b_input_and_the_order_arrow_appears(client, ed, area, db):
    s1, s2 = area["s1"], area["s2"]
    de = entity(client, ed, "Customer order")
    out = hand_off(client, ed["h"], s1, s2, de)
    assert out["already"] is False
    assert (out["output"]["bfc_node_id"], out["output"]["direction"]) == (s1["bfc_node_id"], "O")
    assert (out["input"]["bfc_node_id"], out["input"]["direction"]) == (s2["bfc_node_id"], "I")
    rows = live_io(db, [s1["bfc_node_id"], s2["bfc_node_id"]], de["data_entity_id"])
    assert set(rows) == {(s1["bfc_node_id"], "O"), (s2["bfc_node_id"], "I")}
    g = graph(client, ed, area["parent"])
    assert g["order"] == [{"from_bfc_node_id": s1["bfc_node_id"], "to_bfc_node_id": s2["bfc_node_id"],
                           "data_entity_ids": [de["data_entity_id"]]}]


def test_the_same_hand_off_again_writes_nothing(client, ed, area, db):
    """D1/D2: already on the diagram → 200, `already`, no row touched (row_version unchanged)."""
    de = entity(client, ed)
    first = hand_off(client, ed["h"], area["s1"], area["s2"], de)
    again = hand_off(client, ed["h"], area["s1"], area["s2"], de, expect=200)
    assert again["already"] is True
    assert again["output"] == first["output"] and again["input"] == first["input"]
    assert len(live_io(db, [area["s1"]["bfc_node_id"], area["s2"]["bfc_node_id"]], de["data_entity_id"])) == 2


def test_a_hand_off_completes_a_half_and_restores_a_removed_row(client, ed, area, db):
    """A already writes the entity: only B's input is new. A removed row comes back (S1-7), never twice."""
    de = entity(client, ed)
    a_out = io(client, ed, area["s1"], de, "O")
    out = hand_off(client, ed["h"], area["s1"], area["s2"], de)
    assert out["already"] is False and out["output"]["bfc_node_data_entity_id"] == a_out["bfc_node_data_entity_id"]
    b_in = out["input"]
    r = client.delete(f"{API}/bfc-nodes/{area['s2']['bfc_node_id']}/data-entities/{b_in['bfc_node_data_entity_id']}",
                      headers=ed["h"], params={"row_version": b_in["row_version"]})
    assert r.status_code == 204, r.text
    back = hand_off(client, ed["h"], area["s1"], area["s2"], de)
    assert back["input"]["bfc_node_data_entity_id"] == b_in["bfc_node_data_entity_id"]
    db.expire_all()
    assert len(db.scalars(select(BfcNodeDataEntity).where(
        BfcNodeDataEntity.bfc_node_id == area["s2"]["bfc_node_id"])).all()) == 1


def test_if_b_input_fails_a_output_is_not_written(client, ed, area, db, monkeypatch):
    """D2: one transaction. A failure on B's side rolls A's output back."""
    de = entity(client, ed)
    real = step_io.ensure_step_io

    def fail_on_input(db_, actor_id, n, de_id, direction):
        if direction == "I":
            raise step_io.HTTPException(422, "simulated failure on B")
        return real(db_, actor_id, n, de_id, direction)

    monkeypatch.setattr(step_io, "ensure_step_io", fail_on_input)
    hand_off(client, ed["h"], area["s1"], area["s2"], de, expect=422)
    monkeypatch.undo()
    assert live_io(db, [area["s1"]["bfc_node_id"], area["s2"]["bfc_node_id"]], de["data_entity_id"]) == {}


def test_a_retired_or_non_process_target_writes_nothing(client, ed, area, db):
    de = entity(client, ed)
    hand_off(client, ed["h"], area["s1"], area["parent"], de, expect=422)             # not a process
    hand_off(client, ed["h"], area["s1"], area["s1"], de, expect=422)                 # to itself
    s2 = area["s2"]["bfc_node_id"]
    pv = client.get(f"{API}/bfc-nodes/{s2}/retire-preview", headers=ed["h"]).json()
    r = client.post(f"{API}/bfc-nodes/{s2}/retire-with-dependents", headers=ed["h"],
                    json={"confirm_hash": pv["confirm_hash"]})
    assert r.status_code == 204, r.text
    hand_off(client, ed["h"], area["s1"], area["s2"], de, expect=422)                 # B retired
    other = entity(client, ed, "Gone")
    r = client.delete(f"{API}/data-entities/{other['data_entity_id']}", headers=ed["h"],
                      params={"row_version": other["row_version"]})
    assert r.status_code == 204, r.text
    s3 = node(client, ed, "Ship", area["parent"]["bfc_node_id"], is_process=True)
    hand_off(client, ed["h"], area["s1"], s3, other, expect=422)                      # retired entity
    assert live_io(db, [area["s1"]["bfc_node_id"], s3["bfc_node_id"]], de["data_entity_id"]) == {}
    assert live_io(db, [area["s1"]["bfc_node_id"], s3["bfc_node_id"]], other["data_entity_id"]) == {}


# ---- D5: charts, projects, levels, components ---------------------------------------------------------

def test_a_hand_off_across_charts_is_422(client, ed, area, db):
    a = node(client, ed, "Sales (as is)")
    r = client.post(f"{API}/projects/{ed['p']}/bfc-nodes", headers=ed["h"],
                    json={"node_name": "Old sales", "bfc_set": "AS_IS"})
    assert r.status_code == 201, r.text
    b = node(client, ed, "Old order capture", r.json()["bfc_node_id"])
    old = node(client, ed, "Take order by fax", b["bfc_node_id"], is_process=True)
    assert old["bfc_set_code"] == "AS_IS" and a["bfc_set_code"] == "TO_BE"
    de = entity(client, ed)
    r = client.post(f"{API}/bfc-nodes/{area['s1']['bfc_node_id']}/hand-offs", headers=ed["h"],
                    json={"to_bfc_node_id": old["bfc_node_id"], "data_entity_id": de["data_entity_id"]})
    assert r.status_code == 422 and "cross charts" in r.json()["detail"]
    hand_off(client, ed["h"], old, area["s1"], de, expect=422)
    assert live_io(db, [area["s1"]["bfc_node_id"], old["bfc_node_id"]], de["data_entity_id"]) == {}


def test_a_target_in_another_project_is_404_seen_or_unseen(client, world, ed, area, db):
    """A step of another project — even one the editor can see — is never a hand-off target, and is not named."""
    adm = world["admin"]

    def step_in(pid):
        def mk(name, parent=None, proc=False):
            r = client.post(f"{API}/projects/{pid}/bfc-nodes", headers=adm,
                            json={"node_name": name, "parent_bfc_node_id": parent, "is_process": proc})
            assert r.status_code == 201, r.text
            return r.json()
        x = mk("Area")
        return mk("Step", mk("Func", x["bfc_node_id"])["bfc_node_id"], True)

    seen = step_in(world["p_sales"])                       # not restricted: the editor sees it
    assert client.get(f"{API}/bfc-nodes/{seen['bfc_node_id']}", headers=ed["h"]).status_code == 200
    de = entity(client, ed)
    r = client.post(f"{API}/bfc-nodes/{area['s1']['bfc_node_id']}/hand-offs", headers=ed["h"],
                    json={"to_bfc_node_id": seen["bfc_node_id"], "data_entity_id": de["data_entity_id"]})
    assert r.status_code == 404 and seen["node_name"] not in r.text
    hand_off(client, ed["h"], area["s1"], {"bfc_node_id": 99999999}, de, expect=404)
    hand_off(client, ed["out"], area["s1"], area["s2"], de, expect=404)                # outsider: A unseen
    assert live_io(db, [area["s1"]["bfc_node_id"], area["s2"]["bfc_node_id"], seen["bfc_node_id"]],
                   de["data_entity_id"]) == {}


def test_a_viewer_is_403_and_a_chart_with_its_dfd_off_is_409(client, world, ed, area):
    de = entity(client, ed)
    hand_off(client, ed["rv"], area["s1"], area["s2"], de, expect=403)
    switch(client, world, ed["p"], ALL_BUT_TO_BE_DFD)
    r = client.post(f"{API}/bfc-nodes/{area['s1']['bfc_node_id']}/hand-offs", headers=ed["h"],
                    json={"to_bfc_node_id": area["s2"]["bfc_node_id"], "data_entity_id": de["data_entity_id"]})
    assert r.status_code == 409 and r.headers["X-VB-Error"] == "COMPONENT_OFF"


# ---- D6, Q-11, Q-12: the same rows as the panel; no CRUD; a new entity numbered on save ------------------

def test_a_drawn_row_is_the_row_the_panel_writes_and_no_crud_is_written(client, ed, area, db):
    s3 = node(client, ed, "Invoice", area["parent"]["bfc_node_id"], is_process=True)
    de = entity(client, ed)
    panel = io(client, ed, s3, de, "I")                                      # the panel's route
    drawn = hand_off(client, ed["h"], area["s1"], area["s2"], de)["input"]   # the canvas's
    strip = lambda r: {k: v for k, v in r.items() if k not in ("bfc_node_data_entity_id", "bfc_node_id")}  # noqa: E731
    assert strip(panel) == strip(drawn)
    db.expire_all()
    a, p = db.get(BfcNodeDataEntity, drawn["bfc_node_data_entity_id"]), db.get(BfcNodeDataEntity, panel["bfc_node_data_entity_id"])
    assert (a.created_by, a.project_id, a.is_active, a.row_version) == (p.created_by, p.project_id, p.is_active, p.row_version)
    assert db.scalars(select(BrDataEntity).where(BrDataEntity.data_entity_id == de["data_entity_id"])).all() == []


def test_drawing_to_an_empty_spot_may_create_a_numbered_entity(client, ed, area, db):
    """Q-12: the canvas creates the entity through the data-entity route (numbered on save), then links it."""
    before = entity(client, ed, "Existing")
    r = client.post(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"],
                    json={"de_name": "Credit decision", "de_number": "DE-9999"})
    new = r.json()
    assert r.status_code == 201 and new["de_number"] != "DE-9999"
    assert int(new["de_number"].split("-")[1]) == int(before["de_number"].split("-")[1]) + 1
    io(client, ed, area["s2"], new, "O")
    assert any(s["data_entity_id"] == new["data_entity_id"] for s in graph(client, ed, area["parent"])["stores"])


# ---- D1: store → process by the existing route -------------------------------------------------------

def test_store_to_process_writes_one_input_and_again_writes_nothing(client, ed, area, db):
    de = entity(client, ed)
    io(client, ed, area["s1"], de, "I")
    r = client.post(f"{API}/bfc-nodes/{area['s1']['bfc_node_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": de["data_entity_id"], "direction": "I"})
    assert r.status_code == 409
    assert len(live_io(db, [area["s1"]["bfc_node_id"]], de["data_entity_id"])) == 1


# ---- D3, D7: removing a flow ---------------------------------------------------------------------

def test_every_drawn_flow_names_its_one_row_and_order_arrows_name_none(client, ed, area, db):
    de = entity(client, ed)
    hand_off(client, ed["h"], area["s1"], area["s2"], de)
    who = party(client, ed, "Bank")
    ext_flow(client, ed, area["s1"], who, "I", label="Payment advice")
    starts(client, ed, area["s1"], trigger(client, ed, "Month end"))
    g = graph(client, ed, area["parent"])
    by_kind = {}
    for f in g["flows"]:
        by_kind.setdefault(f["kind"], []).append(f)
        assert isinstance(f["link_id"], int) and f["row_version"] >= 1
    assert {k: len(v) for k, v in by_kind.items()} == {"STORE": 2, "EXTERNAL": 1, "TRIGGER": 1}
    assert all("link_id" not in o for o in g["order"])


def test_removing_a_store_external_or_trigger_flow_soft_deletes_exactly_one_row(client, ed, area, db):
    de = entity(client, ed)
    hand_off(client, ed["h"], area["s1"], area["s2"], de)
    who = party(client, ed, "Bank")
    ext_flow(client, ed, area["s1"], who, "I", label="Payment advice")
    starts(client, ed, area["s2"], trigger(client, ed, "Month end"))
    route = {"STORE": "data-entities", "EXTERNAL": "external-flows", "TRIGGER": "triggers"}
    for kind in ("STORE", "EXTERNAL", "TRIGGER"):
        g = graph(client, ed, area["parent"])
        f = next(x for x in g["flows"] if x["kind"] == kind)
        r = client.delete(f"{API}/bfc-nodes/{f['bfc_node_id']}/{route[kind]}/{f['link_id']}", headers=ed["h"],
                          params={"row_version": f["row_version"]})
        assert r.status_code == 204, r.text
        after = graph(client, ed, area["parent"])
        assert len(after["flows"]) == len(g["flows"]) - 1
        assert all(x["link_id"] != f["link_id"] or x["kind"] != kind for x in after["flows"])
    # The STORE removed was one end of the hand-off: the derived order arrow went with its data.
    assert graph(client, ed, area["parent"])["order"] == []


def test_removing_a_flow_a_requirement_depends_on_is_409_naming_it(client, ed, area, db):
    """D3: a step I/O a BR's CRUD needs stays; the message names the BR."""
    de = entity(client, ed)
    br = next(n for n in client.get(f"{API}/projects/{ed['p']}/bfc-tree", headers=ed["h"]).json()
              if n["bfc_node_id"] == area["s1"]["bfc_node_id"])
    brs = client.get(f"{API}/projects/{ed['p']}/business-requirements", headers=ed["h"]).json()
    br_id = next(b["br_id"] for b in brs if b["br_number"] == br["br_number"])
    r = client.post(f"{API}/business-requirements/{br_id}/data-entities", headers=ed["h"],
                    json={"data_entity_id": de["data_entity_id"], "crud_code": "C"})
    assert r.status_code == 201, r.text
    f = next(x for x in graph(client, ed, area["parent"])["flows"]
             if x["kind"] == "STORE" and x["bfc_node_id"] == area["s1"]["bfc_node_id"])
    r = client.delete(f"{API}/bfc-nodes/{f['bfc_node_id']}/data-entities/{f['link_id']}", headers=ed["h"],
                      params={"row_version": f["row_version"]})
    assert r.status_code == 409 and br["br_number"] in r.json()["detail"]
    assert len(live_io(db, [area["s1"]["bfc_node_id"]], de["data_entity_id"])) == 1
