"""Saved diagram positions (D-29, D-30, S2-6; slice 7c S7-5). Grade 3 for positions, except the one
hard delete the app role may run, which is proven to stay inside its scope. The process-flow graph
these tests once drew was retired by D-38 (0045): its saved positions stay readable as history and are
refused for writes (409); the DFD places steps, entities, parties and triggers.

Not covered: concurrent first saves of one object (the ON CONFLICT arbiter is the design's
answer and is not raced here)."""
import pytest
from sqlalchemy import text

from tests.test_dfd_api import starts, trigger
from tests.test_scope_api import API, ed, node  # noqa: F401 — ed is a fixture


@pytest.fixture
def steps(client, ed):
    """Three process steps under one L2 parent."""
    a = node(client, ed, "Sales")
    b = node(client, ed, "Order to cash", a["bfc_node_id"])
    return {"parent": b, **{k: node(client, ed, n, b["bfc_node_id"], is_process=True)
                            for k, n in (("s1", "Receive order"), ("s2", "Check credit"),
                                         ("s3", "Confirm order"))}}


def dfd(client, ed, node_id, headers=None):
    return client.get(f"{API}/bfc-nodes/{node_id}/dfd", headers=headers or ed["h"])


def layout_url(ed, scope, kind="DFD"):
    return f"{API}/projects/{ed['p']}/diagram-layouts/{kind}/{scope}"


def test_positions_upsert_per_object_and_keep_the_first_placer(client, ed, steps, world, db):
    scope, s1, s2 = steps["parent"]["bfc_node_id"], steps["s1"], steps["s2"]
    url = layout_url(ed, scope)
    r = client.put(url, headers=ed["h"], json=[
        {"object_type": "STEP", "object_id": s1["bfc_node_id"], "x": 10, "y": 20},
        {"object_type": "STEP", "object_id": s2["bfc_node_id"], "x": 200, "y": 20, "w": 180, "h": 64}])
    assert r.status_code == 200, r.text
    admin_h = world["admin"]
    r = client.put(url, headers=admin_h, json=[{"object_type": "STEP", "object_id": s1["bfc_node_id"],
                                                "x": 15.5, "y": 25}])
    assert r.status_code == 200
    got = {p["object_id"]: p for p in client.get(url, headers=ed["rv"]).json()}
    assert (got[s1["bfc_node_id"]]["x"], got[s1["bfc_node_id"]]["y"]) == (15.5, 25)
    assert (got[s2["bfc_node_id"]]["x"], got[s2["bfc_node_id"]]["w"]) == (200, 180)     # untouched
    who = db.execute(text("SELECT created_by, updated_by FROM diagram_layout WHERE bfc_node_id = :n"),
                     {"n": s1["bfc_node_id"]}).one()
    assert who.created_by == world["users"]["editor"] and who.updated_by != who.created_by
    g = dfd(client, ed, scope).json()
    assert {p["object_id"] for p in g["layout"]} == {s1["bfc_node_id"], s2["bfc_node_id"]}


def test_reset_hard_deletes_only_its_own_diagram_and_is_audited(client, ed, steps, db):
    scope, s1 = steps["parent"]["bfc_node_id"], steps["s1"]
    other = node(client, ed, "Returns", steps["parent"]["parent_bfc_node_id"])
    client.put(layout_url(ed, scope), headers=ed["h"],
               json=[{"object_type": "STEP", "object_id": s1["bfc_node_id"], "x": 1, "y": 2}])
    client.put(layout_url(ed, other["bfc_node_id"]), headers=ed["h"],
               json=[{"object_type": "STEP", "object_id": s1["bfc_node_id"], "x": 3, "y": 4}])
    assert client.delete(layout_url(ed, scope), headers=ed["rv"]).status_code == 403
    assert client.delete(layout_url(ed, scope), headers=ed["h"]).status_code == 204
    assert client.get(layout_url(ed, scope), headers=ed["h"]).json() == []
    assert len(client.get(layout_url(ed, other["bfc_node_id"]), headers=ed["h"]).json()) == 1
    ev = db.execute(text("SELECT target_table, target_id, detail FROM audit_event "
                         "WHERE event_type = 'LAYOUT_RESET'")).all()
    assert [tuple(e) for e in ev] == [("bfc_node", scope,
                                       {"diagram_type": "DFD", "scope_key": str(scope), "positions": 1})]


def test_positions_are_validated_against_scope_type_and_project(client, ed, steps, world):
    scope, s1, s2 = steps["parent"]["bfc_node_id"], steps["s1"], steps["s2"]
    other = client.post(f"{API}/projects/{world['p_fin']}/bfc-nodes", headers=world["admin"],
                        json={"node_name": "Elsewhere"}).json()
    de = client.post(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"], json={"de_name": "Order"}).json()
    month = trigger(client, ed, "Month-end close")
    starts(client, ed, s1, month)

    def put(scope_key, items, kind="DFD", headers=None):
        return client.put(layout_url(ed, scope_key, kind), headers=headers or ed["h"], json=items)

    def one(**kw):
        return [{"x": 0, "y": 0, **kw}]

    assert put(scope, one(object_type="TRIGGER", object_id=month["process_trigger_id"])).status_code == 200
    assert put(scope, one(object_type="TRIGGER", object_id=10 ** 9)).status_code == 422
    assert put(scope, one(object_type="EVENT", object_id=1)).status_code == 422        # history only
    assert put(scope, one(object_type="BOGUS", object_id=1)).status_code == 422
    assert put(scope, one(object_type="STEP", object_id=other["bfc_node_id"])).status_code == 422
    assert put(scope, one(object_type="STEP", object_id=s1["bfc_node_id"], collapsed=True)).status_code == 422
    assert put(s1["bfc_node_id"], one(object_type="STEP", object_id=s2["bfc_node_id"])).status_code == 422
    assert put("project", one(object_type="STEP", object_id=s1["bfc_node_id"])).status_code == 422
    assert put(other["bfc_node_id"], one(object_type="STEP", object_id=s1["bfc_node_id"])).status_code == 404
    assert put(scope, one(object_type="STEP", object_id=s1["bfc_node_id"]) * 2).status_code == 422
    assert put(scope, one(object_type="STEP", object_id=s1["bfc_node_id"]), headers=ed["rv"]).status_code == 403
    assert client.get(layout_url(ed, scope, "GANTT"), headers=ed["h"]).status_code == 404
    erd = put("project", one(object_type="ENTITY", object_id=de["data_entity_id"], collapsed=True), kind="ERD")
    assert erd.status_code == 200 and erd.json()[0]["collapsed"] is True           # Slice 3 needs no change
    assert put("project", one(object_type="STEP", object_id=s1["bfc_node_id"]), kind="ERD").status_code == 422


def test_process_flow_positions_are_history_readable_but_never_written(client, ed, steps, db):
    """S7-5 / D-38: a PROCESS_FLOW layout can still be read; a save or a reset is 409, and nothing moves."""
    scope, s1 = steps["parent"]["bfc_node_id"], steps["s1"]
    url = layout_url(ed, scope, "PROCESS_FLOW")
    db.execute(text("INSERT INTO diagram_layout (project_id, diagram_type, scope_bfc_node_id, bfc_node_id, x, y, "
                    "is_collapsed, created_by) SELECT project_id, 'PROCESS_FLOW', :scope, bfc_node_id, 5, 6, false, "
                    "created_by FROM bfc_node WHERE bfc_node_id = :s"), {"scope": scope, "s": s1["bfc_node_id"]})
    db.commit()                                                     # a position saved before 7c
    before = client.get(url, headers=ed["rv"])
    assert before.status_code == 200
    assert [(p["object_type"], p["object_id"], p["x"]) for p in before.json()] == [("STEP", s1["bfc_node_id"], 5)]
    r = client.put(url, headers=ed["h"], json=[{"object_type": "STEP", "object_id": s1["bfc_node_id"], "x": 9, "y": 9}])
    assert r.status_code == 409 and "D-38" in r.json()["detail"]
    assert client.delete(url, headers=ed["h"]).status_code == 409
    assert client.get(url, headers=ed["h"]).json() == before.json()
    assert dfd(client, ed, scope).json()["layout"] == []              # the DFD never reads them
    assert client.put(url, headers=ed["out"], json=[]).status_code == 404


# ---- sara L6: the remaining proofs -------------------------------------------------------

def test_layout_routes_are_hidden_from_outsiders(client, ed, steps):
    url = layout_url(ed, steps["parent"]["bfc_node_id"])
    item = [{"object_type": "STEP", "object_id": steps["s1"]["bfc_node_id"], "x": 0, "y": 0}]
    assert client.get(url, headers=ed["out"]).status_code == 404
    assert client.put(url, headers=ed["out"], json=item).status_code == 404
    assert client.delete(url, headers=ed["out"]).status_code == 404
    assert client.get(layout_url(ed, "%C2%B9"), headers=ed["h"]).status_code == 404       # sara L1


def test_reset_of_one_diagram_type_leaves_the_others(client, ed, steps):
    scope = steps["parent"]["bfc_node_id"]
    de = client.post(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"], json={"de_name": "Order"}).json()
    client.put(layout_url(ed, "project", "ERD"), headers=ed["h"],
               json=[{"object_type": "ENTITY", "object_id": de["data_entity_id"], "x": 0, "y": 0}])
    client.put(layout_url(ed, scope), headers=ed["h"],
               json=[{"object_type": "STEP", "object_id": steps["s1"]["bfc_node_id"], "x": 0, "y": 0}])
    assert client.delete(layout_url(ed, "project", "ERD"), headers=ed["h"]).status_code == 204
    assert client.get(layout_url(ed, "project", "ERD"), headers=ed["h"]).json() == []
    assert len(client.get(layout_url(ed, scope), headers=ed["h"]).json()) == 1


def test_more_than_2000_positions_are_refused(client, ed, steps):
    item = {"object_type": "STEP", "object_id": steps["s1"]["bfc_node_id"], "x": 0, "y": 0}
    r = client.put(layout_url(ed, steps["parent"]["bfc_node_id"]), headers=ed["h"], json=[item] * 2001)
    assert r.status_code == 422
