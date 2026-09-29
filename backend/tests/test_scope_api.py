"""Slice 1 through the API: the function chart, requirements, step data, roles and retire /
restore (§7.2, §7.3, §7.12, D-2, D-23, D-24, S1-2)."""
import pytest

from tests.conftest import login

API = "/api/v1"


@pytest.fixture
def ed(client, world):
    """An EDITOR on p_solo, a REVIEWER on p_solo, and the project id."""
    for name, role in (("editor", "EDITOR"), ("reviewer", "REVIEWER")):
        r = client.post(f"{API}/projects/{world['p_solo']}/access", headers=world["admin"],
                        json={"user_id": world["users"][name], "project_role_code": role})
        assert r.status_code == 201, r.text
    return {"h": login(client, "editor@example.test"), "rv": login(client, "reviewer@example.test"),
            "out": login(client, "outsider@example.test"), "p": world["p_solo"]}


def node(client, ed, name, parent=None, is_process=False, expect=201):
    r = client.post(f"{API}/projects/{ed['p']}/bfc-nodes", headers=ed["h"],
                    json={"node_name": name, "parent_bfc_node_id": parent, "is_process": is_process})
    assert r.status_code == expect, r.text
    return r.json()


def step(client, ed, name="Take order"):
    a = node(client, ed, "Sales")
    b = node(client, ed, "Order to cash", a["bfc_node_id"])
    return node(client, ed, name, b["bfc_node_id"], is_process=True)


def tree(client, ed, **q):
    return client.get(f"{API}/projects/{ed['p']}/bfc-tree", headers=ed["h"], params=q).json()


def entity(client, ed, name="Sales order"):
    r = client.post(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"], json={"de_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def br_of(client, ed, node_id):
    return next(n["br_number"] for n in tree(client, ed) if n["bfc_node_id"] == node_id)


def brs(client, ed):
    return {b["br_number"]: b for b in
            client.get(f"{API}/projects/{ed['p']}/business-requirements", headers=ed["h"]).json()}


# ---- chart -------------------------------------------------------------------------------

def test_codes_are_derived_and_a_process_step_gets_its_requirement(client, ed):
    s = step(client, ed)
    assert (s["level_no"], s["hier_code"], s["is_process"]) == (3, "01.01.01", True)
    assert br_of(client, ed, s["bfc_node_id"]) == "BR-0001"
    assert brs(client, ed)["BR-0001"]["status_code"] == "DRAFT"


def test_level_5_is_always_a_process_and_a_process_has_no_children(client, ed):
    a = node(client, ed, "A")
    b = node(client, ed, "B", a["bfc_node_id"])
    c = node(client, ed, "C", b["bfc_node_id"])
    d = node(client, ed, "D", c["bfc_node_id"])
    e = node(client, ed, "E", d["bfc_node_id"])
    assert e["is_process"] and e["hier_code"] == "01.01.01.01.01"
    node(client, ed, "F", e["bfc_node_id"], expect=422)


def test_sibling_names_are_unique_after_normalising(client, ed):
    node(client, ed, "Sales")
    r = client.post(f"{API}/projects/{ed['p']}/bfc-nodes", headers=ed["h"], json={"node_name": "  SALES "})
    assert r.status_code == 409 and "already exists" in r.json()["detail"]


def test_reorder_recodes_every_shifted_subtree(client, ed):
    """S1-2: moving the third L1 node first re-codes all three subtrees without a collision."""
    tops = [node(client, ed, n) for n in ("A", "B", "C")]
    for t in tops:
        node(client, ed, f"{t['node_name']} child", t["bfc_node_id"])
    c = tops[2]
    r = client.patch(f"{API}/bfc-nodes/{c['bfc_node_id']}/reorder", headers=ed["h"],
                     json={"row_version": c["row_version"], "new_seq_no": 1})
    assert r.status_code == 200, r.text
    codes = {n["node_name"]: n["hier_code"] for n in tree(client, ed)}
    assert codes == {"C": "01", "C child": "01.01", "A": "02", "A child": "02.01",
                     "B": "03", "B child": "03.01"}


def test_stale_row_version_is_409(client, ed):
    n = node(client, ed, "A")
    ok = client.patch(f"{API}/bfc-nodes/{n['bfc_node_id']}", headers=ed["h"],
                      json={"row_version": n["row_version"], "purpose_desc": "x"})
    assert ok.status_code == 200
    stale = client.patch(f"{API}/bfc-nodes/{n['bfc_node_id']}", headers=ed["h"],
                         json={"row_version": n["row_version"], "purpose_desc": "y"})
    assert stale.status_code == 409


# ---- D-23: promote / demote ---------------------------------------------------------------

def test_demote_is_refused_while_the_requirement_lives_and_names_it(client, ed):
    s = step(client, ed)
    r = client.patch(f"{API}/bfc-nodes/{s['bfc_node_id']}/process", headers=ed["h"],
                     json={"row_version": s["row_version"], "is_process": False})
    assert r.status_code == 409 and "BR-0001" in r.json()["detail"]


def test_retire_requirement_then_demote_then_promote_mints_a_new_one(client, ed):
    s = step(client, ed)
    br = brs(client, ed)["BR-0001"]
    assert client.delete(f"{API}/business-requirements/{br['br_id']}", headers=ed["h"],
                         params={"row_version": br["row_version"]}).status_code == 204
    s = client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}", headers=ed["h"]).json()
    r = client.patch(f"{API}/bfc-nodes/{s['bfc_node_id']}/process", headers=ed["h"],
                     json={"row_version": s["row_version"], "is_process": False})
    assert r.status_code == 200 and r.json()["business_requirement"] is None
    s = r.json()["node"]
    r = client.patch(f"{API}/bfc-nodes/{s['bfc_node_id']}/process", headers=ed["h"],
                     json={"row_version": s["row_version"], "is_process": True})
    assert r.status_code == 200 and r.json()["business_requirement"]["br_number"] == "BR-0002"


# ---- D-24: CRUD creates the step I/O that licenses it ---------------------------------------

def test_crud_creates_step_io_and_step_io_cannot_go_while_crud_needs_it(client, ed):
    s, de = step(client, ed), entity(client, ed)
    br = brs(client, ed)["BR-0001"]
    r = client.post(f"{API}/business-requirements/{br['br_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": de["data_entity_id"], "crud_code": "R"})
    assert r.status_code == 201 and r.json()["direction"] == "I"
    io = client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}/data-entities", headers=ed["h"]).json()
    assert [(x["data_entity_id"], x["direction"]) for x in io] == [(de["data_entity_id"], "I")]
    r = client.delete(f"{API}/bfc-nodes/{s['bfc_node_id']}/data-entities/{io[0]['bfc_node_data_entity_id']}",
                      headers=ed["h"], params={"row_version": io[0]["row_version"]})
    assert r.status_code == 409 and "BR-0001 R" in r.json()["detail"]


def test_direction_is_never_accepted_from_the_body(client, ed):
    step(client, ed)
    de = entity(client, ed)
    br = brs(client, ed)["BR-0001"]
    r = client.post(f"{API}/business-requirements/{br['br_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": de["data_entity_id"], "crud_code": "C", "direction": "I"})
    assert r.status_code == 201 and r.json()["direction"] == "O"


def test_relinking_a_removed_crud_restores_the_same_row(client, ed):
    step(client, ed)
    de = entity(client, ed)
    br = brs(client, ed)["BR-0001"]
    url = f"{API}/business-requirements/{br['br_id']}/data-entities"
    first = client.post(url, headers=ed["h"], json={"data_entity_id": de["data_entity_id"],
                                                    "crud_code": "U"}).json()
    assert client.delete(f"{url}/{first['br_data_entity_id']}", headers=ed["h"],
                         params={"row_version": first["row_version"]}).status_code == 204
    again = client.post(url, headers=ed["h"], json={"data_entity_id": de["data_entity_id"],
                                                    "crud_code": "U"}).json()
    assert again["br_data_entity_id"] == first["br_data_entity_id"]


# ---- external flows, RACI -------------------------------------------------------------------

def test_external_flow_with_data_creates_step_io(client, ed):
    s, de = step(client, ed), entity(client, ed)
    ext = client.post(f"{API}/projects/{ed['p']}/external-entities", headers=ed["h"],
                      json={"ext_name": "Bank"}).json()
    assert ext["ext_number"] == "EXT-0001"
    r = client.post(f"{API}/bfc-nodes/{s['bfc_node_id']}/external-flows", headers=ed["h"],
                    json={"external_entity_id": ext["external_entity_id"], "direction": "O",
                          "data_entity_id": de["data_entity_id"]})
    assert r.status_code == 201, r.text
    io = client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}/data-entities", headers=ed["h"]).json()
    assert [x["direction"] for x in io] == ["O"]


def _org_role(client, ed, code):
    units = client.get(f"{API}/projects/{ed['p']}/org-units", headers=ed["h"]).json()
    unit = units[0] if units else client.post(f"{API}/projects/{ed['p']}/org-units", headers=ed["h"], json={
        "org_unit_code": "FIN", "org_unit_name": "Finance"}).json()
    r = client.post(f"{API}/projects/{ed['p']}/org-roles", headers=ed["h"], json={
        "org_unit_id": unit["org_unit_id"], "org_role_code": code, "org_role_name": code})
    assert r.status_code == 201, r.text
    return r.json()


def test_org_unit_level_code_defaults_from_level(client, ed):
    top = client.post(f"{API}/projects/{ed['p']}/org-units", headers=ed["h"],
                      json={"org_unit_code": "FIN", "org_unit_name": "Finance"}).json()
    sub = client.post(f"{API}/projects/{ed['p']}/org-units", headers=ed["h"], json={
        "org_unit_code": "AP", "org_unit_name": "Payables", "parent_org_unit_id": top["org_unit_id"]}).json()
    assert (top["level_code"], sub["level_code"], sub["level_no"]) == ("DEPARTMENT", "DIVISION", 2)


def test_one_accountable_per_step_named_in_the_409(client, ed):
    s = step(client, ed)
    cfo, clerk = _org_role(client, ed, "CFO"), _org_role(client, ed, "CLERK")
    url = f"{API}/bfc-nodes/{s['bfc_node_id']}/org-roles"
    r = client.post(url, headers=ed["h"], json={"org_role_id": cfo["org_role_id"], "raci_code": "A"})
    assert r.status_code == 201 and r.json()["raci_behaviour"] == "ACCOUNTABLE"
    r = client.post(url, headers=ed["h"], json={"org_role_id": clerk["org_role_id"], "raci_code": "A"})
    assert r.status_code == 409 and "CFO" in r.json()["detail"]


# ---- retire / restore (§7.12) --------------------------------------------------------------

def test_retire_is_refused_with_dependents_named_and_nothing_cascades(client, ed):
    s = step(client, ed)
    parent_id = s["parent_bfc_node_id"]
    parent = client.get(f"{API}/bfc-nodes/{parent_id}", headers=ed["h"]).json()
    r = client.delete(f"{API}/bfc-nodes/{parent_id}", headers=ed["h"],
                      params={"row_version": parent["row_version"]})
    assert r.status_code == 409 and "01.01.01 Take order" in r.json()["detail"]
    r = client.delete(f"{API}/bfc-nodes/{s['bfc_node_id']}", headers=ed["h"],
                      params={"row_version": s["row_version"]})
    assert r.status_code == 409 and "BR-0001" in r.json()["detail"]


def test_restore_is_refused_while_the_parent_is_retired(client, ed):
    a = node(client, ed, "A")
    b = node(client, ed, "B", a["bfc_node_id"])
    assert client.delete(f"{API}/bfc-nodes/{b['bfc_node_id']}", headers=ed["h"],
                         params={"row_version": b["row_version"]}).status_code == 204
    assert client.delete(f"{API}/bfc-nodes/{a['bfc_node_id']}", headers=ed["h"],
                         params={"row_version": a["row_version"]}).status_code == 204
    r = client.patch(f"{API}/bfc-nodes/{b['bfc_node_id']}/restore", headers=ed["h"])
    assert r.status_code == 409 and "Restore BFC node 01 A first" in r.json()["detail"]
    assert client.patch(f"{API}/bfc-nodes/{a['bfc_node_id']}/restore", headers=ed["h"]).status_code == 200
    assert client.patch(f"{API}/bfc-nodes/{b['bfc_node_id']}/restore", headers=ed["h"]).status_code == 200


def test_restored_node_whose_code_is_taken_moves_to_the_end(client, ed):
    a = node(client, ed, "A")
    assert client.delete(f"{API}/bfc-nodes/{a['bfc_node_id']}", headers=ed["h"],
                         params={"row_version": a["row_version"]}).status_code == 204
    node(client, ed, "B")                                  # takes position 1 / code 01
    r = client.patch(f"{API}/bfc-nodes/{a['bfc_node_id']}/restore", headers=ed["h"])
    assert r.status_code == 200 and r.json()["hier_code"] == "02"


# ---- access ------------------------------------------------------------------------------

def test_reviewer_reads_but_cannot_write_and_outsider_sees_nothing(client, ed):
    s = step(client, ed)
    assert client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}", headers=ed["rv"]).status_code == 200
    r = client.patch(f"{API}/bfc-nodes/{s['bfc_node_id']}", headers=ed["rv"],
                     json={"row_version": s["row_version"], "purpose_desc": "x"})
    assert r.status_code == 403
    assert client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}", headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/projects/{ed['p']}/bfc-tree", headers=ed["out"]).status_code == 404


def test_cannot_link_another_projects_entity(client, world, ed):
    s = step(client, ed)
    other = client.post(f"{API}/projects/{world['p_fin']}/data-entities", headers=world["admin"],
                        json={"de_name": "Foreign"}).json()
    br = brs(client, ed)["BR-0001"]
    r = client.post(f"{API}/business-requirements/{br['br_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": other["data_entity_id"], "crud_code": "C"})
    assert r.status_code == 422
    assert s


def test_there_is_no_create_requirement_route(client, ed):
    r = client.post(f"{API}/projects/{ed['p']}/business-requirements", headers=ed["h"], json={})
    assert r.status_code == 405


# ---- data fields --------------------------------------------------------------------------

def test_fk_field_group_is_assigned_not_sent(client, ed):
    order, cust = entity(client, ed, "Order"), entity(client, ed, "Customer")
    pk = client.post(f"{API}/data-entities/{cust['data_entity_id']}/fields", headers=ed["h"], json={
        "field_name": "customer_id", "is_primary_key": True, "pk_ordinal": 1,
        "data_type_code": "INTEGER"}).json()
    url = f"{API}/data-entities/{order['data_entity_id']}/fields"
    bill = client.post(url, headers=ed["h"], json={"field_name": "bill_to", "ref_data_entity_id":
                       cust["data_entity_id"], "ref_data_field_id": pk["data_field_id"]}).json()
    ship = client.post(url, headers=ed["h"], json={"field_name": "ship_to", "ref_data_entity_id":
                       cust["data_entity_id"], "ref_data_field_id": pk["data_field_id"]}).json()
    assert (bill["fk_group_no"], ship["fk_group_no"]) == (1, 2)
    r = client.post(url, headers=ed["h"], json={"field_name": "x", "ref_data_entity_id":
                    cust["data_entity_id"], "fk_group": 7})
    assert r.status_code == 422


# ---- sara round 2: H1, M1, M2, M3, L7, L8 ---------------------------------------------------

def _delete(client, ed, path, obj):
    return client.delete(f"{API}/{path}", headers=ed["h"], params={"row_version": obj["row_version"]})


def test_restored_child_takes_its_parents_current_code(client, ed):
    """H1: retire a child, move its parent, restore the child — the code follows the parent."""
    a = node(client, ed, "A")
    child = node(client, ed, "A child", a["bfc_node_id"])
    node(client, ed, "B")
    assert _delete(client, ed, f"bfc-nodes/{child['bfc_node_id']}", child).status_code == 204
    a = client.get(f"{API}/bfc-nodes/{a['bfc_node_id']}", headers=ed["h"]).json()
    r = client.patch(f"{API}/bfc-nodes/{a['bfc_node_id']}/reorder", headers=ed["h"],
                     json={"row_version": a["row_version"], "new_seq_no": 2})
    assert r.status_code == 200 and r.json()["hier_code"] == "02"
    r = client.patch(f"{API}/bfc-nodes/{child['bfc_node_id']}/restore", headers=ed["h"])
    assert r.status_code == 200 and r.json()["hier_code"] == "02.01"


def test_a_retired_row_cannot_be_edited(client, ed):
    de = entity(client, ed)
    assert _delete(client, ed, f"data-entities/{de['data_entity_id']}", de).status_code == 204
    r = client.patch(f"{API}/data-entities/{de['data_entity_id']}", headers=ed["h"],
                     json={"row_version": de["row_version"] + 1, "de_name": "Renamed"})
    assert r.status_code == 409 and "Restore it first" in r.json()["detail"]


def test_restored_field_whose_position_was_taken_comes_back_at_the_end(client, ed):
    de = entity(client, ed)
    url = f"{API}/data-entities/{de['data_entity_id']}/fields"
    f1 = client.post(url, headers=ed["h"], json={"field_name": "a"}).json()
    assert _delete(client, ed, f"data-fields/{f1['data_field_id']}", f1).status_code == 204
    client.post(url, headers=ed["h"], json={"field_name": "b"})         # takes position 1
    r = client.patch(f"{API}/data-fields/{f1['data_field_id']}/restore", headers=ed["h"])
    assert r.status_code == 200 and r.json()["seq_no"] == 2


def test_a_link_cannot_be_removed_under_another_owner(client, ed):
    s1 = step(client, ed)
    s2 = node(client, ed, "Ship order", s1["parent_bfc_node_id"], is_process=True)
    role = _org_role(client, ed, "CLERK")
    link = client.post(f"{API}/bfc-nodes/{s1['bfc_node_id']}/org-roles", headers=ed["h"],
                       json={"org_role_id": role["org_role_id"], "raci_code": "C"}).json()
    r = client.delete(f"{API}/bfc-nodes/{s2['bfc_node_id']}/org-roles/{link['bfc_node_org_role_id']}",
                      headers=ed["h"], params={"row_version": link["row_version"]})
    assert r.status_code == 404


def test_duplicate_step_data_is_409_and_removal_is_audited(client, ed, db):
    from sqlalchemy import text
    s, de = step(client, ed), entity(client, ed)
    url = f"{API}/bfc-nodes/{s['bfc_node_id']}/data-entities"
    io = client.post(url, headers=ed["h"], json={"data_entity_id": de["data_entity_id"], "direction": "I"})
    assert io.status_code == 201
    assert client.post(url, headers=ed["h"], json={"data_entity_id": de["data_entity_id"],
                                                   "direction": "I"}).status_code == 409
    io = io.json()
    assert _delete(client, ed, f"bfc-nodes/{s['bfc_node_id']}/data-entities/{io['bfc_node_data_entity_id']}",
                   io).status_code == 204
    n = db.execute(text("SELECT count(*) FROM audit_event WHERE event_type = 'RECORD_DELETED' "
                        "AND target_table = 'bfc_node_data_entity'")).scalar()
    assert n == 1


def test_baseline_statuses_are_system_set(client, ed):
    """S1-8: an editor may choose Draft or Confirmed, never Baselined or Superseded."""
    step(client, ed)
    br = brs(client, ed)["BR-0001"]
    url = f"{API}/business-requirements/{br['br_id']}"
    for code in ("BASELINED", "SUPERSEDED"):
        r = client.patch(url, headers=ed["h"], json={"row_version": br["row_version"], "status_code": code})
        assert r.status_code == 422 and "baseline freeze" in r.json()["detail"]
    r = client.patch(url, headers=ed["h"], json={"row_version": br["row_version"], "status_code": "CONFIRMED"})
    assert r.status_code == 200 and r.json()["status_code"] == "CONFIRMED"


def test_changed_lookup_codes_come_back_in_the_response(client, ed):
    top = client.post(f"{API}/projects/{ed['p']}/org-units", headers=ed["h"],
                      json={"org_unit_code": "FIN", "org_unit_name": "Finance"}).json()
    r = client.patch(f"{API}/org-units/{top['org_unit_id']}", headers=ed["h"],
                     json={"row_version": top["row_version"], "level_code": "SECTION"})
    assert r.json()["level_code"] == "SECTION"
    de = entity(client, ed)
    f = client.post(f"{API}/data-entities/{de['data_entity_id']}/fields", headers=ed["h"],
                    json={"field_name": "amount", "data_type_code": "INTEGER"}).json()
    r = client.patch(f"{API}/data-fields/{f['data_field_id']}", headers=ed["h"],
                     json={"row_version": f["row_version"], "data_type_code": "DECIMAL"})
    assert r.json()["data_type_code"] == "DECIMAL"


def test_entity_lists_the_requirements_that_use_it(client, ed):
    step(client, ed)
    de = entity(client, ed)
    br = brs(client, ed)["BR-0001"]
    for c in ("U", "R"):
        client.post(f"{API}/business-requirements/{br['br_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": de["data_entity_id"], "crud_code": c})
    r = client.get(f"{API}/data-entities/{de['data_entity_id']}/business-requirements", headers=ed["rv"])
    assert r.json() == [{"br_id": br["br_id"], "br_number": "BR-0001", "hier_code": "01.01.01",
                         "node_name": "Take order", "crud": "RU"}]


def test_lists_can_include_retired_rows(client, ed):
    """Show retired → Restore needs the retired rows in every list."""
    de = entity(client, ed)
    unit = client.post(f"{API}/projects/{ed['p']}/org-units", headers=ed["h"],
                       json={"org_unit_code": "FIN", "org_unit_name": "Finance"}).json()
    party = client.post(f"{API}/projects/{ed['p']}/external-entities", headers=ed["h"],
                        json={"ext_name": "Bank"}).json()
    for path, obj in ((f"data-entities/{de['data_entity_id']}", de), (f"org-units/{unit['org_unit_id']}", unit),
                      (f"external-entities/{party['external_entity_id']}", party)):
        assert client.delete(f"{API}/{path}", headers=ed["h"],
                             params={"row_version": obj["row_version"]}).status_code == 204
    for coll in ("data-entities", "org-units", "external-entities"):
        url = f"{API}/projects/{ed['p']}/{coll}"
        assert client.get(url, headers=ed["h"]).json() == []
        rows = client.get(url, headers=ed["h"], params={"include_retired": True}).json()
        assert len(rows) == 1 and rows[0]["is_active"] is False


def test_a_stale_save_is_marked_and_other_conflicts_are_not(client, ed):
    n = node(client, ed, "A")
    client.patch(f"{API}/bfc-nodes/{n['bfc_node_id']}", headers=ed["h"],
                 json={"row_version": n["row_version"], "purpose_desc": "x"})
    stale = client.patch(f"{API}/bfc-nodes/{n['bfc_node_id']}", headers=ed["h"],
                         json={"row_version": n["row_version"], "purpose_desc": "y"})
    assert stale.status_code == 409 and stale.headers.get("x-vb-error") == "STALE"
    dup = client.post(f"{API}/projects/{ed['p']}/bfc-nodes", headers=ed["h"], json={"node_name": "a"})
    assert dup.status_code == 409 and "x-vb-error" not in dup.headers


def test_fk_field_keeps_its_own_relationship_number(client, ed):
    """sara (data M2): changing only the target field must not renumber the relationship."""
    order, cust = entity(client, ed, "Order"), entity(client, ed, "Customer")
    url_c = f"{API}/data-entities/{cust['data_entity_id']}/fields"
    a = client.post(url_c, headers=ed["h"], json={"field_name": "id", "is_primary_key": True, "pk_ordinal": 1}).json()
    b = client.post(url_c, headers=ed["h"], json={"field_name": "code"}).json()
    url = f"{API}/data-entities/{order['data_entity_id']}/fields"
    fks = [client.post(url, headers=ed["h"], json={"field_name": n, "ref_data_entity_id": cust["data_entity_id"],
                                                   "ref_data_field_id": a["data_field_id"]}).json()
           for n in ("f1", "f2", "f3")]
    assert [f["fk_group_no"] for f in fks] == [1, 2, 3]
    mid = fks[1]
    for body in ({"fk_group": 2}, {}):                        # keep explicitly, and by default
        r = client.patch(f"{API}/data-fields/{mid['data_field_id']}", headers=ed["h"], json={
            "row_version": mid["row_version"], "ref_data_entity_id": cust["data_entity_id"],
            "ref_data_field_id": b["data_field_id"], **body})
        assert r.status_code == 200 and r.json()["fk_group_no"] == 2, r.text
        mid = r.json()
