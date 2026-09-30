"""Slice 2b through the API: the process flow graph and saved diagram positions (§7.2a,
D-21, D-30, S2-6). Grade 2 for the graph (a client reads it); Grade 3 for positions, except
the one hard delete the app role may run, which is proven to stay inside its scope.

Not covered: concurrent first saves of one object (the ON CONFLICT arbiter is the design's
answer and is not raced here), and the TO_BE variant's systems, which wait for APPLICATION."""
from sqlalchemy import text

from tests.test_process_flow_api import edge, steps  # noqa: F401 — steps is a fixture
from tests.test_scope_api import API, _org_role, ed, node  # noqa: F401 — ed is a fixture


def graph(client, ed, node_id, headers=None, **q):
    return client.get(f"{API}/bfc-nodes/{node_id}/process-flow", headers=headers or ed["h"], params=q)


def layout_url(ed, scope, kind="PROCESS_FLOW"):
    return f"{API}/projects/{ed['p']}/diagram-layouts/{kind}/{scope}"


def test_graph_is_the_steps_under_the_node_with_edges_lanes_stores_and_parties(client, ed, steps):
    s1, s2, s3, parent = steps["s1"], steps["s2"], steps["s3"], steps["parent"]
    area = node(client, ed, "Fulfilment")
    far = node(client, ed, "Ship", node(client, ed, "Dispatch", area["bfc_node_id"])["bfc_node_id"],
               is_process=True)
    edge(client, ed, None, s1)
    edge(client, ed, s1, s2, "CONDITIONAL", "Credit OK")
    edge(client, ed, s2, far, "HANDOFF")
    clerk = _org_role(client, ed, "CLERK")
    client.post(f"{API}/bfc-nodes/{s1['bfc_node_id']}/org-roles", headers=ed["h"],
                json={"org_role_id": clerk["org_role_id"], "raci_code": "R"})
    de = client.post(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"],
                     json={"de_name": "Sales order"}).json()
    client.post(f"{API}/bfc-nodes/{s1['bfc_node_id']}/data-entities", headers=ed["h"],
                json={"data_entity_id": de["data_entity_id"], "direction": "O"})
    client.post(f"{API}/bfc-nodes/{s2['bfc_node_id']}/data-entities", headers=ed["h"],
                json={"data_entity_id": de["data_entity_id"], "direction": "I"})
    cust = client.post(f"{API}/projects/{ed['p']}/external-entities", headers=ed["h"],
                       json={"ext_name": "Customer"}).json()
    client.post(f"{API}/bfc-nodes/{s1['bfc_node_id']}/external-flows", headers=ed["h"],
                json={"external_entity_id": cust["external_entity_id"], "direction": "I"})

    r = graph(client, ed, parent["bfc_node_id"], headers=ed["rv"])
    assert r.status_code == 200, r.text
    g = r.json()
    assert [n["node_name"] for n in g["nodes"]] == ["Receive order", "Check credit", "Confirm order"]
    assert g["nodes"][0]["br_number"] and g["nodes"][0]["lane_org_role_id"] == clerk["org_role_id"]
    assert g["nodes"][1]["lane_org_role_id"] is None                          # the unassigned lane
    assert [ln["org_role_code"] for ln in g["lanes"]] == ["CLERK"]
    kinds = {(e["from_bfc_node_id"], e["to_bfc_node_id"]): e for e in g["edges"]}
    assert kinds[(s2["bfc_node_id"], far["bfc_node_id"])]["is_external"] is True
    assert kinds[(None, s1["bfc_node_id"])]["is_external"] is False
    assert [o["node_name"] for o in g["outside"]] == ["Ship"]                 # the hand-off leaves the frame
    assert g["stores"] == [{"data_entity_id": de["data_entity_id"], "de_number": de["de_number"],
                            "de_name": "Sales order", "reads": [s2["bfc_node_id"]],
                            "writes": [s1["bfc_node_id"]]}]
    assert g["externals"][0]["ext_name"] == "Customer" and g["externals"][0]["flows"][0]["direction"] == "I"
    assert g["layout"] == []
    far_graph = graph(client, ed, area["bfc_node_id"]).json()                 # the other area sees it too
    assert [n["node_name"] for n in far_graph["nodes"]] == ["Ship"]
    assert far_graph["edges"][0]["is_external"] is True


def test_graph_refuses_a_step_a_bad_variant_and_outsiders(client, ed, steps):
    assert graph(client, ed, steps["s1"]["bfc_node_id"]).status_code == 422
    assert graph(client, ed, steps["parent"]["bfc_node_id"], variant="BEST").status_code == 422
    assert graph(client, ed, steps["parent"]["bfc_node_id"], variant="TO_BE").status_code == 200
    assert graph(client, ed, steps["parent"]["bfc_node_id"], headers=ed["out"]).status_code == 404


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
    g = graph(client, ed, scope).json()
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
    ev = db.execute(text("SELECT detail FROM audit_event WHERE event_type = 'LAYOUT_RESET'")).scalars().all()
    assert ev == [{"diagram_type": "PROCESS_FLOW", "scope_key": str(scope), "positions": 1}]


def test_positions_are_validated_against_scope_type_and_project(client, ed, steps, world):
    scope, s1, s2 = steps["parent"]["bfc_node_id"], steps["s1"], steps["s2"]
    start = edge(client, ed, None, s1)
    middle = edge(client, ed, s1, s2)
    other = client.post(f"{API}/projects/{world['p_fin']}/bfc-nodes", headers=world["admin"],
                        json={"node_name": "Elsewhere"}).json()
    de = client.post(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"], json={"de_name": "Order"}).json()

    def put(scope_key, items, kind="PROCESS_FLOW", headers=None):
        return client.put(layout_url(ed, scope_key, kind), headers=headers or ed["h"], json=items)

    def one(**kw):
        return [{"x": 0, "y": 0, **kw}]

    assert put(scope, one(object_type="EVENT", object_id=start["bfc_node_flow_id"])).status_code == 200
    assert put(scope, one(object_type="EVENT", object_id=middle["bfc_node_flow_id"])).status_code == 422
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
