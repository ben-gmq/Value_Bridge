"""Slice 3b through the API: the logical ERD (§7.4 generate_erd, D-29, §5.4.17; slice 3 spec
§7 3b, criteria 10–15). Grade 2: a client reads the diagram, so every derived value is
asserted against the rule that produces it.

Not covered here: the browser-only halves of 14a and 16 (edge landing and collapse on the
canvas, seen by ui-verifier) and criterion 17 (the 200-entity load, scripts/seed_erd_load.py)."""
from sqlalchemy import text

from tests.test_scope_api import API, ed, entity, node  # noqa: F401 — ed is a fixture


def erd(client, ed, area=None, headers=None):
    params = {"subject_area": area} if area is not None else {}
    return client.get(f"{API}/projects/{ed['p']}/erd", headers=headers or ed["h"], params=params)


def field(client, ed, de, name, **spec):
    r = client.post(f"{API}/data-entities/{de['data_entity_id']}/fields", headers=ed["h"],
                    json={"field_name": name, **spec})
    assert r.status_code == 201, r.text
    return r.json()


def pk(client, ed, de, name, n=1, **spec):
    return field(client, ed, de, name, is_primary_key=True, pk_ordinal=n, **spec)


def fk(client, ed, de, name, parent, ref=None, **spec):
    return field(client, ed, de, name, ref_data_entity_id=parent["data_entity_id"],
                 ref_data_field_id=ref["data_field_id"] if ref else None, **spec)


def io(client, ed, step, de, direction="I"):
    r = client.post(f"{API}/bfc-nodes/{step['bfc_node_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": de["data_entity_id"], "direction": direction})
    assert r.status_code == 201, r.text


def rels(g, child=None):
    return [r for r in g["relationships"] if child is None or r["child_data_entity_id"] == child["data_entity_id"]]


def ent(g, de):
    return next(e for e in g["entities"] if e["data_entity_id"] == de["data_entity_id"])


# ---- criterion 10: a composite FK is one relationship -------------------------------------

def test_composite_fk_is_one_relationship_landing_on_each_parent_key_row(client, ed):
    line, ship = entity(client, ed, "Order line"), entity(client, ed, "Shipment line")
    order_id = pk(client, ed, line, "order_id", 1, is_mandatory=True)
    line_no = pk(client, ed, line, "line_no", 2, is_mandatory=True)
    pk(client, ed, ship, "shipment_line_id")
    a = fk(client, ed, ship, "order_id", line, order_id, is_mandatory=True)
    b = fk(client, ed, ship, "line_no", line, line_no, is_mandatory=True, fk_group=1)

    r = erd(client, ed, headers=ed["rv"])
    assert r.status_code == 200, r.text
    [rel] = rels(r.json(), ship)
    assert rel["parent_data_entity_id"] == line["data_entity_id"] and rel["fk_group_no"] == 1
    assert [(v["data_field_id"], v["ref_data_field_id"], v["ref_is_key"]) for v in rel["via_fields"]] == [
        (a["data_field_id"], order_id["data_field_id"], True), (b["data_field_id"], line_no["data_field_id"], True)]
    assert rel["parent_cardinality"] == "1" and rel["label"] == "order_id, line_no"
    assert rel["child_cardinality"] == "many" and rel["identifying"] is False      # not the child's key

    for optional in (False, None):                        # optional or unknown → 0..1 (A-53)
        client.patch(f"{API}/data-fields/{b['data_field_id']}", headers=ed["h"],
                     json={"row_version": b["row_version"], "is_mandatory": optional})
        b = client.get(f"{API}/data-entities/{ship['data_entity_id']}/fields", headers=ed["h"]).json()[-1]
        assert b["is_mandatory"] is optional
        [rel] = rels(erd(client, ed).json(), ship)
        assert rel["parent_cardinality"] == "0..1"


# ---- criterion 11: two relationships to one parent ----------------------------------------

def test_two_fk_groups_to_one_parent_are_two_relationships_labelled_by_field(client, ed):
    order, addr = entity(client, ed, "Order"), entity(client, ed, "Address")
    address_id = pk(client, ed, addr, "address_id")
    pk(client, ed, order, "order_id")
    fk(client, ed, order, "ship_to_address_id", addr, address_id)
    fk(client, ed, order, "bill_to_address_id", addr, address_id)
    got = sorted((r["fk_group_no"], r["label"]) for r in rels(erd(client, ed).json(), order))
    assert got == [(1, "ship_to_address_id"), (2, "bill_to_address_id")]


# ---- criterion 12: identifying vs not -------------------------------------------------------

def test_fk_equal_to_the_child_key_is_one_to_one_identifying_and_a_plain_fk_is_many(client, ed):
    order, detail, cust = entity(client, ed, "Order"), entity(client, ed, "Order detail"), entity(client, ed, "Customer")
    order_id = pk(client, ed, order, "order_id")
    cust_id = pk(client, ed, cust, "customer_id")
    pk(client, ed, detail, "order_id", ref_data_entity_id=order["data_entity_id"],
       ref_data_field_id=order_id["data_field_id"])                           # both PK and FK
    fk(client, ed, order, "customer_id", cust, cust_id)
    g = erd(client, ed).json()
    [one] = rels(g, detail)
    assert (one["child_cardinality"], one["identifying"]) == ("1", True)
    [many] = rels(g, order)
    assert (many["child_cardinality"], many["identifying"]) == ("many", False)


def test_a_key_fk_that_is_only_part_of_the_child_key_is_identifying_but_many(client, ed):
    order, line = entity(client, ed, "Order"), entity(client, ed, "Order line")
    order_id = pk(client, ed, order, "order_id")
    pk(client, ed, line, "order_id", 1, ref_data_entity_id=order["data_entity_id"],
       ref_data_field_id=order_id["data_field_id"])
    pk(client, ed, line, "line_no", 2)
    [rel] = rels(erd(client, ed).json(), line)
    assert (rel["child_cardinality"], rel["identifying"]) == ("many", True)


# ---- field order, 14 (NO_KEY), 14a (landing data) ----------------------------------------

def test_fields_order_pk_then_fk_then_attributes_and_a_keyless_entity_is_drawn_badged(client, ed):
    cust, pay = entity(client, ed, "Customer"), entity(client, ed, "Payment")
    note = field(client, ed, cust, "note")
    region = fk(client, ed, cust, "region_id", pay)                           # no parent field named
    k2 = pk(client, ed, cust, "branch", 2)
    k1 = pk(client, ed, cust, "customer_no", 1)
    name = field(client, ed, cust, "注文番号", data_type_code="STRING", is_mandatory=True,
                 description="Order number")
    g = erd(client, ed).json()
    c = ent(g, cust)
    assert [f["data_field_id"] for f in c["fields"]] == [k1["data_field_id"], k2["data_field_id"],
                                                         region["data_field_id"], note["data_field_id"],
                                                         name["data_field_id"]]
    assert c["warnings"] == [] and c["field_count"] == 5
    assert c["fields"][2]["ref_de_name"] == "Payment"
    assert c["fields"][4]["field_name"] == "注文番号" and c["fields"][4]["data_type_code"] == "STRING"
    assert ent(g, pay)["warnings"] == ["NO_KEY"] and ent(g, pay)["fields"] == []
    [rel] = rels(g, cust)
    assert rel["via_fields"][0]["ref_data_field_id"] is None and rel["via_fields"][0]["ref_is_key"] is False
    assert rel["child_cardinality"] == "many"


def test_an_fk_naming_a_non_key_parent_attribute_is_kept_and_flagged_off_key(client, ed):
    order, cust = entity(client, ed, "Order"), entity(client, ed, "Customer")
    pk(client, ed, cust, "customer_id")
    email = field(client, ed, cust, "email")
    fk(client, ed, order, "customer_email", cust, email)
    [rel] = rels(erd(client, ed).json(), order)
    assert rel["via_fields"][0]["ref_data_field_id"] == email["data_field_id"]
    assert rel["via_fields"][0]["ref_is_key"] is False                          # lands on t-L-entity


def test_retired_fields_and_entities_are_not_drawn(client, ed):
    order, gone = entity(client, ed, "Order"), entity(client, ed, "Gone")
    f = field(client, ed, order, "old")
    assert client.delete(f"{API}/data-fields/{f['data_field_id']}", headers=ed["h"],
                         params={"row_version": f["row_version"]}).status_code == 204
    assert client.delete(f"{API}/data-entities/{gone['data_entity_id']}", headers=ed["h"],
                         params={"row_version": gone["row_version"]}).status_code == 204
    g = erd(client, ed).json()
    assert [e["de_name"] for e in g["entities"]] == ["Order"] and ent(g, order)["fields"] == []


def test_a_retired_parent_comes_back_as_a_retired_stub_not_a_crash(client, ed, db):
    """A-S3-4: the retire route refuses this, so the state is forced in the database."""
    order, cust = entity(client, ed, "Order"), entity(client, ed, "Customer")
    fk(client, ed, order, "customer_id", cust)
    db.execute(text("UPDATE data_entity SET is_active = false WHERE data_entity_id = :i"),
               {"i": cust["data_entity_id"]})
    db.commit()
    g = erd(client, ed).json()
    assert rels(g) == []
    [stub] = g["outside_refs"]
    assert (stub["parent_de_name"], stub["retired"]) == ("Customer", True)


# ---- criterion 13, 14b: subject areas -------------------------------------------------------

def _two_areas(client, ed):
    l1a, l1b = node(client, ed, "Sales"), node(client, ed, "Finance")
    l2a = node(client, ed, "Order to cash", l1a["bfc_node_id"])
    take = node(client, ed, "Take order", l2a["bfc_node_id"], is_process=True)
    ship = node(client, ed, "Ship order", l2a["bfc_node_id"], is_process=True)
    bill = node(client, ed, "Bill", node(client, ed, "Billing", l1b["bfc_node_id"])["bfc_node_id"],
                is_process=True)
    order, cust, invoice, line = (entity(client, ed, n) for n in ("Order", "Customer", "Invoice", "Order line"))
    cust_id, order_id = pk(client, ed, cust, "customer_id"), pk(client, ed, order, "order_id")
    fk(client, ed, order, "customer_id", cust, cust_id)             # Customer is outside Sales
    fk(client, ed, invoice, "order_id", order, order_id)
    fk(client, ed, line, "order_id", order, order_id)
    io(client, ed, take, order, "O")
    io(client, ed, ship, line, "O")
    io(client, ed, ship, order, "I")
    io(client, ed, bill, invoice, "O")
    io(client, ed, bill, cust, "I")
    return {"l1a": l1a, "l1b": l1b, "take": take, "order": order, "cust": cust, "invoice": invoice, "line": line}


def test_a_subject_area_shows_only_its_entities_and_stubs_the_fks_that_leave_it(client, ed):
    w = _two_areas(client, ed)
    g = erd(client, ed, w["l1a"]["bfc_node_id"]).json()
    assert g["scope_key"] == str(w["l1a"]["bfc_node_id"])
    assert {e["de_name"] for e in g["entities"]} == {"Order", "Order line"}
    assert [(r["child_data_entity_id"], r["parent_data_entity_id"]) for r in g["relationships"]] == [
        (w["line"]["data_entity_id"], w["order"]["data_entity_id"])]
    [stub] = g["outside_refs"]
    assert (stub["child_data_entity_id"], stub["parent_de_number"], stub["parent_de_name"], stub["retired"]) == (
        w["order"]["data_entity_id"], w["cust"]["de_number"], "Customer", False)
    whole = erd(client, ed).json()
    assert whole["scope_key"] == "project" and len(whole["entities"]) == 4
    assert len(whole["relationships"]) == 3 and whole["outside_refs"] == []


def test_a_single_step_area_gives_exactly_that_steps_entities(client, ed):
    w = _two_areas(client, ed)
    g = erd(client, ed, w["take"]["bfc_node_id"]).json()
    assert [e["de_name"] for e in g["entities"]] == ["Order"]
    assert [s["parent_de_name"] for s in g["outside_refs"]] == ["Customer"]


def test_an_unknown_other_project_or_retired_area_is_404(client, ed, world):
    w = _two_areas(client, ed)
    other = client.post(f"{API}/projects/{world['p_fin']}/bfc-nodes", headers=world["admin"],
                        json={"node_name": "Elsewhere"}).json()
    empty = node(client, ed, "Empty")
    assert client.delete(f"{API}/bfc-nodes/{empty['bfc_node_id']}", headers=ed["h"],
                         params={"row_version": empty["row_version"]}).status_code == 204
    for area in (999999, other["bfc_node_id"], empty["bfc_node_id"]):
        assert erd(client, ed, area).status_code == 404
    assert erd(client, ed, w["l1a"]["bfc_node_id"], headers=ed["out"]).status_code == 404
    assert erd(client, ed, headers=ed["out"]).status_code == 404


# ---- criterion 15: positions per scope, collapse, no baseline reference -------------------

def test_positions_per_scope_are_independent_and_collapse_persists_both_ways(client, ed, db):
    w = _two_areas(client, ed)
    order_id, area = w["order"]["data_entity_id"], w["l1a"]["bfc_node_id"]

    def put(scope, x, collapsed, headers=None):
        return client.put(f"{API}/projects/{ed['p']}/diagram-layouts/ERD/{scope}", headers=headers or ed["h"],
                          json=[{"object_type": "ENTITY", "object_id": order_id, "x": x, "y": 5,
                                 "collapsed": collapsed}])

    assert put("project", 100, True).status_code == 200
    assert put(area, 700, False).status_code == 200
    assert put("project", 1, True, headers=ed["rv"]).status_code == 403         # a reviewer places nothing
    whole = {p["object_id"]: p for p in erd(client, ed, headers=ed["rv"]).json()["layout"]}
    sub = {p["object_id"]: p for p in erd(client, ed, area).json()["layout"]}
    assert (whole[order_id]["x"], whole[order_id]["collapsed"]) == (100, True)
    assert (sub[order_id]["x"], sub[order_id]["collapsed"]) == (700, False)     # a stored false is kept (R2-NEW-1)
    assert put("project", 150, False).status_code == 200                          # expand is saved, not reset
    again = erd(client, ed).json()["layout"]
    assert [(p["x"], p["collapsed"]) for p in again] == [(150, False)]
    refs = db.execute(text(
        "SELECT count(*) FROM information_schema.constraint_column_usage u "
        "JOIN information_schema.table_constraints c ON c.constraint_name = u.constraint_name "
        "WHERE u.table_name = 'diagram_layout' AND c.constraint_type = 'FOREIGN KEY' "
        "AND c.table_name LIKE 'baseline%'")).scalar()
    assert refs == 0                                                               # never baselined (A-52)


def test_an_fk_naming_a_parent_fk_row_lands_on_that_row(client, ed):
    """A parent FK row stays drawn when its card collapses, so it counts as a key row (sara Q)."""
    cust, order, line = entity(client, ed, "Customer"), entity(client, ed, "Order"), entity(client, ed, "Line")
    cid = pk(client, ed, cust, "customer_id")
    pk(client, ed, order, "order_id")
    order_cust = fk(client, ed, order, "customer_id", cust, cid)
    fk(client, ed, line, "order_customer_id", order, order_cust)
    [rel] = rels(erd(client, ed).json(), line)
    assert rel["via_fields"][0]["ref_is_key"] is True
