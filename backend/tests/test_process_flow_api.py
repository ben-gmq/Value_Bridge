"""Slice 2 through the API: process flow edges and the completeness report (§7.2a, D-20, D-23,
Q2, S2-1…S2-5). Grade 2 — a wrong edge misleads a client's process picture.

Deliberately not covered here: the NFKC-vs-index normaliser gap (S2-5, accepted), concurrent
creates racing the partial index (the shared handler maps the 23505 to 409), and the flow JSON
import, which arrives with the import pipeline."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.test_scope_api import API, _org_role, ed, node, step  # noqa: F401 — ed is a fixture


def flows_url(ed):
    return f"{API}/projects/{ed['p']}/process-flows"


def edge(client, ed, frm, to, flow_type="SEQUENCE", label=None, expect=201, **extra):
    body = {"from_bfc_node_id": frm and frm["bfc_node_id"], "to_bfc_node_id": to and to["bfc_node_id"],
            "flow_type": flow_type, "condition_label": label, **extra}
    r = client.post(flows_url(ed), headers=ed["h"], json=body)
    assert r.status_code == expect, r.text
    return r.json()


@pytest.fixture
def steps(client, ed):
    """Three process steps under one L2 parent."""
    a = node(client, ed, "Sales")
    b = node(client, ed, "Order to cash", a["bfc_node_id"])
    return {"parent": b, **{k: node(client, ed, n, b["bfc_node_id"], is_process=True)
                            for k, n in (("s1", "Receive order"), ("s2", "Check credit"),
                                         ("s3", "Confirm order"))}}


def test_edges_list_in_render_order_and_filter_by_step(client, ed, steps):
    s1, s2, s3 = steps["s1"], steps["s2"], steps["s3"]
    e1 = edge(client, ed, s1, s2, seq_no=2)
    e2 = edge(client, ed, s1, s3, "CONDITIONAL", "Credit NG", seq_no=1)
    e3 = edge(client, ed, None, s1)                                   # a start event
    got = client.get(flows_url(ed), headers=ed["rv"]).json()
    assert [e["bfc_node_flow_id"] for e in got] == [e2["bfc_node_flow_id"], e1["bfc_node_flow_id"],
                                                    e3["bfc_node_flow_id"]]      # seq_no NULLS LAST
    only_s3 = client.get(flows_url(ed), headers=ed["h"], params={"bfc_node_id": s3["bfc_node_id"]}).json()
    assert [e["bfc_node_flow_id"] for e in only_s3] == [e2["bfc_node_flow_id"]]


def test_same_steps_same_condition_is_409_after_normalising(client, ed, steps):
    s1, s2 = steps["s1"], steps["s2"]
    edge(client, ed, s1, s2, "CONDITIONAL", "Credit NG")
    r = client.post(flows_url(ed), headers=ed["h"], json={
        "from_bfc_node_id": s1["bfc_node_id"], "to_bfc_node_id": s2["bfc_node_id"],
        "flow_type": "SEQUENCE", "condition_label": "  credit  ＮＧ "})     # flow_type is not in the key
    assert r.status_code == 409 and "already joined" in r.json()["detail"]
    edge(client, ed, s1, s2, "CONDITIONAL", "Credit OK")                # a different condition is fine
    edge(client, ed, s1, s2)                                            # and so is no condition, once
    edge(client, ed, s1, s2, expect=409)


def test_start_and_end_events_follow_the_same_key(client, ed, steps):
    edge(client, ed, None, steps["s1"])
    edge(client, ed, None, steps["s1"], expect=409)                     # NULLS NOT DISTINCT
    edge(client, ed, steps["s3"], None)
    r = client.post(flows_url(ed), headers=ed["h"], json={"flow_type": "SEQUENCE"})
    assert r.status_code == 422 and "from step" in r.json()["detail"]


def test_conditional_needs_a_label_in_the_service_and_the_database(client, ed, steps, db):
    s1, s2 = steps["s1"], steps["s2"]
    r = client.post(flows_url(ed), headers=ed["h"], json={
        "from_bfc_node_id": s1["bfc_node_id"], "to_bfc_node_id": s2["bfc_node_id"],
        "flow_type": "CONDITIONAL", "condition_label": "   "})
    assert r.status_code == 422 and "condition label" in r.json()["detail"]
    with pytest.raises(IntegrityError, match="ck_bnf_conditional_label"):     # S2-1: a real CHECK
        db.execute(text("INSERT INTO bfc_node_flow (project_id, from_bfc_node_id, to_bfc_node_id, "
                        "flow_type, created_by) SELECT project_id, :a, :b, 'CONDITIONAL', created_by "
                        "FROM bfc_node WHERE bfc_node_id = :a"),
                   {"a": s1["bfc_node_id"], "b": s2["bfc_node_id"]})
    db.rollback()
    bad = client.post(flows_url(ed), headers=ed["h"], json={
        "from_bfc_node_id": s1["bfc_node_id"], "flow_type": "LOOP"})
    assert bad.status_code == 422


def test_ends_must_be_live_process_steps_in_this_project(client, ed, steps, world):
    edge(client, ed, steps["parent"], steps["s1"], expect=422)          # a parent is not a step
    other = client.post(f"{API}/projects/{world['p_fin']}/bfc-nodes", headers=world["admin"],
                        json={"node_name": "Elsewhere"}).json()
    r = client.post(flows_url(ed), headers=ed["h"], json={
        "from_bfc_node_id": steps["s1"]["bfc_node_id"], "to_bfc_node_id": other["bfc_node_id"],
        "flow_type": "HANDOFF"})
    assert r.status_code == 422 and "in this project" in r.json()["detail"]


def test_self_loop_and_cycles_are_legal(client, ed, steps):
    s1, s2 = steps["s1"], steps["s2"]
    edge(client, ed, s1, s1, "CONDITIONAL", "Rework")                  # S2-4
    edge(client, ed, s1, s2)
    edge(client, ed, s2, s1, "CONDITIONAL", "Rejected")               # a rework loop, no cycle check


def test_re_adding_a_removed_edge_restores_the_same_row(client, ed, steps):
    e = edge(client, ed, steps["s1"], steps["s2"], "CONDITIONAL", "Credit NG", note="first")
    r = client.delete(f"{API}/process-flows/{e['bfc_node_flow_id']}", headers=ed["h"],
                      params={"row_version": e["row_version"]})
    assert r.status_code == 204
    assert client.get(flows_url(ed), headers=ed["h"]).json() == []
    again = edge(client, ed, steps["s1"], steps["s2"], "CONDITIONAL", "credit ng", note="second")
    assert again["bfc_node_flow_id"] == e["bfc_node_flow_id"]         # source_id stays stable
    assert (again["condition_label"], again["note"]) == ("credit ng", "second")


def test_patch_edits_but_never_moves_an_edge(client, ed, steps):
    s1, s2, s3 = steps["s1"], steps["s2"], steps["s3"]
    e = edge(client, ed, s1, s2, "CONDITIONAL", "Credit NG")
    edge(client, ed, s1, s2, "CONDITIONAL", "Credit OK")
    url = f"{API}/process-flows/{e['bfc_node_flow_id']}"
    r = client.patch(url, headers=ed["h"], json={"row_version": e["row_version"],
                                                 "to_bfc_node_id": s3["bfc_node_id"], "seq_no": 3})
    assert r.status_code == 200 and r.json()["to_bfc_node_id"] == s2["bfc_node_id"]    # S2-2
    moved = r.json()
    r = client.patch(url, headers=ed["h"], json={"row_version": moved["row_version"],
                                                 "condition_label": "credit ok"})
    assert r.status_code == 409 and "already joined" in r.json()["detail"]
    r = client.patch(url, headers=ed["h"], json={"row_version": moved["row_version"], "flow_type": "SEQUENCE",
                                                 "condition_label": None})
    assert r.status_code == 200 and r.json()["condition_label"] is None
    r = client.patch(url, headers=ed["h"], json={"row_version": moved["row_version"], "note": "stale"})
    assert r.status_code == 409                                         # stale row_version
    r = client.patch(url, headers=ed["h"], json={"row_version": moved["row_version"] + 1,
                                                 "flow_type": "CONDITIONAL"})
    assert r.status_code == 422                                         # a conditional needs its label


def test_a_step_with_edges_cannot_be_demoted_or_retired(client, ed, steps):
    s1, s2 = steps["s1"], steps["s2"]
    e = edge(client, ed, s1, s2, "CONDITIONAL", "Credit NG")
    r = client.patch(f"{API}/bfc-nodes/{s1['bfc_node_id']}/process", headers=ed["h"],
                     json={"row_version": s1["row_version"], "is_process": False})
    assert r.status_code == 409 and "1 flow edges" in r.json()["detail"]
    r = client.delete(f"{API}/bfc-nodes/{s2['bfc_node_id']}", headers=ed["h"],
                      params={"row_version": s2["row_version"]})
    assert r.status_code == 409 and "Flow edge" in r.json()["detail"] and "Credit NG" in r.json()["detail"]
    client.delete(f"{API}/process-flows/{e['bfc_node_flow_id']}", headers=ed["h"],
                  params={"row_version": e["row_version"]})
    r = client.delete(f"{API}/bfc-nodes/{s2['bfc_node_id']}", headers=ed["h"],
                      params={"row_version": s2["row_version"]})
    assert r.status_code == 409 and "Flow edge" not in r.json()["detail"]    # only the BR blocks now


def test_restoring_an_edge_whose_step_is_retired_is_refused(client, ed, steps):
    """S2-2 / Q-8: the twin is found, but its end is checked live before it comes back."""
    s1 = steps["s1"]
    lone = node(client, ed, "Lone step", steps["parent"]["bfc_node_id"], is_process=True)
    e = edge(client, ed, s1, lone)
    client.delete(f"{API}/process-flows/{e['bfc_node_flow_id']}", headers=ed["h"],
                  params={"row_version": e["row_version"]})
    br = next(b for b in client.get(f"{API}/projects/{ed['p']}/business-requirements",
                                    headers=ed["h"]).json() if b["bfc_node_id"] == lone["bfc_node_id"])
    assert client.delete(f"{API}/business-requirements/{br['br_id']}", headers=ed["h"],
                         params={"row_version": br["row_version"]}).status_code == 204
    assert client.delete(f"{API}/bfc-nodes/{lone['bfc_node_id']}", headers=ed["h"],
                         params={"row_version": lone["row_version"]}).status_code == 204
    edge(client, ed, s1, lone, expect=422)


def test_reviewers_read_outsiders_see_nothing(client, ed, steps):
    e = edge(client, ed, steps["s1"], steps["s2"])
    assert client.get(flows_url(ed), headers=ed["rv"]).status_code == 200
    r = client.post(flows_url(ed), headers=ed["rv"], json={
        "from_bfc_node_id": steps["s2"]["bfc_node_id"], "flow_type": "SEQUENCE"})
    assert r.status_code == 403
    url = f"{API}/process-flows/{e['bfc_node_flow_id']}"
    assert client.patch(url, headers=ed["out"], json={"row_version": 1, "note": "x"}).status_code == 404
    assert client.get(flows_url(ed), headers=ed["out"]).status_code == 404


def test_completeness_names_the_gaps(client, ed, steps):
    s1, s2, s3 = steps["s1"], steps["s2"], steps["s3"]
    url = f"{API}/projects/{ed['p']}/flow-completeness"
    first = client.get(url, headers=ed["rv"]).json()
    assert {s["node_name"] for s in first["orphan_steps"]} == {"Receive order", "Check credit", "Confirm order"}
    assert first["no_start"] == [] and first["no_end"] == []            # no flow drawn yet
    edge(client, ed, s1, s2)
    mid = client.get(url, headers=ed["h"]).json()
    assert [s["node_name"] for s in mid["orphan_steps"]] == ["Confirm order"]
    assert [p["node_name"] for p in mid["no_start"]] == ["Order to cash"]
    assert [p["node_name"] for p in mid["no_end"]] == ["Order to cash"]
    edge(client, ed, None, s1)
    edge(client, ed, s2, None)
    done = client.get(url, headers=ed["h"]).json()
    assert done["no_start"] == [] and done["no_end"] == [] and done["edge_count"] == 3
    clerk = _org_role(client, ed, "CLERK")
    client.post(f"{API}/bfc-nodes/{s3['bfc_node_id']}/org-roles", headers=ed["h"],
                json={"org_role_id": clerk["org_role_id"], "raci_code": "R"})
    lanes = client.get(url, headers=ed["h"]).json()["no_lane"]
    assert "Confirm order" not in {s["node_name"] for s in lanes} and len(lanes) == 2


# ---- sara MED-2: the Grade-2 edges -------------------------------------------------------

def test_derived_values_in_the_body_are_ignored(client, ed, steps, world, db):
    """VB law 6: project, author and version come from the route and the JWT, never the body."""
    e = edge(client, ed, steps["s1"], steps["s2"], project_id=world["p_fin"], created_by=1, row_version=7)
    assert (e["project_id"], e["row_version"]) == (ed["p"], 1)
    author = db.execute(text("SELECT created_by FROM bfc_node_flow WHERE bfc_node_flow_id = :i"),
                        {"i": e["bfc_node_flow_id"]}).scalar()
    assert author == world["users"]["editor"]


def test_every_verb_is_hidden_from_outsiders_and_closed_to_reviewers(client, ed, steps):
    e = edge(client, ed, steps["s1"], steps["s2"])
    url = f"{API}/process-flows/{e['bfc_node_flow_id']}"
    rv = {"row_version": e["row_version"]}
    assert client.delete(url, headers=ed["out"], params=rv).status_code == 404
    assert client.get(f"{API}/projects/{ed['p']}/flow-completeness", headers=ed["out"]).status_code == 404
    assert client.patch(url, headers=ed["rv"], json={**rv, "note": "x"}).status_code == 403
    assert client.delete(url, headers=ed["rv"], params=rv).status_code == 403


def test_list_filtered_by_another_projects_step_is_empty(client, ed, steps, world):
    edge(client, ed, steps["s1"], steps["s2"])
    other = client.post(f"{API}/projects/{world['p_fin']}/bfc-nodes", headers=world["admin"],
                        json={"node_name": "Elsewhere"}).json()
    got = client.get(flows_url(ed), headers=ed["h"], params={"bfc_node_id": other["bfc_node_id"]})
    assert got.status_code == 200 and got.json() == []


def test_restoring_an_edge_whose_step_was_demoted_is_refused(client, ed, steps):
    s1 = steps["s1"]
    lone = node(client, ed, "Lone step", steps["parent"]["bfc_node_id"], is_process=True)
    e = edge(client, ed, s1, lone)
    client.delete(f"{API}/process-flows/{e['bfc_node_flow_id']}", headers=ed["h"],
                  params={"row_version": e["row_version"]})
    br = next(b for b in client.get(f"{API}/projects/{ed['p']}/business-requirements",
                                    headers=ed["h"]).json() if b["bfc_node_id"] == lone["bfc_node_id"])
    client.delete(f"{API}/business-requirements/{br['br_id']}", headers=ed["h"],
                  params={"row_version": br["row_version"]})
    r = client.patch(f"{API}/bfc-nodes/{lone['bfc_node_id']}/process", headers=ed["h"],
                     json={"row_version": lone["row_version"], "is_process": False})
    assert r.status_code == 200, r.text
    r = client.post(flows_url(ed), headers=ed["h"], json={
        "from_bfc_node_id": s1["bfc_node_id"], "to_bfc_node_id": lone["bfc_node_id"], "flow_type": "SEQUENCE"})
    assert r.status_code == 422 and "not a process step" in r.json()["detail"]


def test_of_several_removed_twins_the_latest_comes_back(client, ed, steps):
    """S2-5 / Q-9: edit a live edge onto a removed one's condition, remove it too, re-add."""
    s1, s2 = steps["s1"], steps["s2"]
    first = edge(client, ed, s1, s2, "CONDITIONAL", "Credit NG")
    client.delete(f"{API}/process-flows/{first['bfc_node_flow_id']}", headers=ed["h"],
                  params={"row_version": first["row_version"]})
    second = edge(client, ed, s1, s2, "CONDITIONAL", "Credit OK")
    r = client.patch(f"{API}/process-flows/{second['bfc_node_flow_id']}", headers=ed["h"],
                     json={"row_version": second["row_version"], "condition_label": "credit ng"})
    assert r.status_code == 200, r.text
    client.delete(f"{API}/process-flows/{second['bfc_node_flow_id']}", headers=ed["h"],
                  params={"row_version": r.json()["row_version"]})
    back = edge(client, ed, s1, s2, "CONDITIONAL", "Credit NG")
    assert back["bfc_node_flow_id"] == second["bfc_node_flow_id"]


def test_remove_and_edit_refuse_stale_and_removed_edges(client, ed, steps):
    e = edge(client, ed, steps["s1"], steps["s2"], "CONDITIONAL", "Credit NG")
    url = f"{API}/process-flows/{e['bfc_node_flow_id']}"
    r = client.patch(url, headers=ed["h"], json={"row_version": e["row_version"], "condition_label": None})
    assert r.status_code == 422                                          # a conditional keeps its label
    stale = client.delete(url, headers=ed["h"], params={"row_version": e["row_version"] + 5})
    assert stale.status_code == 409 and stale.headers.get("x-vb-error") == "STALE"
    assert client.delete(url, headers=ed["h"], params={"row_version": e["row_version"]}).status_code == 204
    again = client.delete(url, headers=ed["h"], params={"row_version": e["row_version"] + 1})
    assert again.status_code == 409 and "already removed" in again.json()["detail"]
    r = client.patch(url, headers=ed["h"], json={"row_version": e["row_version"] + 1, "note": "x"})
    assert r.status_code == 409 and "Add it again" in r.json()["detail"]


def test_blank_note_is_stored_as_none(client, ed, steps):
    e = edge(client, ed, steps["s1"], steps["s2"], note="   ")
    assert e["note"] is None


def test_io_licence_checks_are_empty_in_normal_use(client, ed, steps):
    """Criterion 148: the licence FKs hold these at 0; the report proves it."""
    de = client.post(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"],
                     json={"de_name": "Sales order"}).json()
    br = next(b for b in client.get(f"{API}/projects/{ed['p']}/business-requirements",
                                    headers=ed["h"]).json() if b["bfc_node_id"] == steps["s1"]["bfc_node_id"])
    r = client.post(f"{API}/business-requirements/{br['br_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": de["data_entity_id"], "crud_code": "C"})
    assert r.status_code == 201, r.text
    got = client.get(f"{API}/projects/{ed['p']}/flow-completeness", headers=ed["h"]).json()
    assert got["crud_without_io"] == [] and got["ext_without_io"] == []
    assert "Receive order" not in {s["node_name"] for s in got["no_output"]}   # C made step output
