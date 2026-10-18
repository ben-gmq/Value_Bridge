"""Slice 11c — system-to-system flows on a BR, their derived coverage, "Create interface FR from these flows" and the
Data migration FR type (D-61, S11-3, S11-5, S11-7; docs/slice11_schema.md §3, §4, §5; criterion 188).

Grade 2 (a wrong flow or coverage reaches a client's scope document and is correctable once seen), except the one
concern Ren named for the slice: before slice 11 merges, a frozen baseline must hold every live requirement line,
attribute tick and flow, hashed on the agreed columns — Grade 1, proven at the end against an independent hash.
Left uncovered on purpose: flows across more than one page of applications (no paging exists)."""
import pytest
from sqlalchemy import text
from services.freeze_set import CURRENT_HASH_SPEC

from tests.test_application_api import app, retire_app
from tests.test_baseline import bid, freeze, owner_exec, scope
from tests.test_br_attributes import current_entities, save
from tests.test_br_lines import add as add_line, expected_hash
from tests.test_components import editor_on, new_project
from tests.test_erd_api import field
from tests.test_function_requirement_api import fr
from tests.test_interface_api import listing, put as put_iface
from tests.test_scope_api import API, ed, node  # noqa: F401 — ed is a fixture


def flow(client, ed, br, de, src, tgt, note=None, expect=201, headers=None):
    r = client.post(f"{API}/business-requirements/{br['br_id']}/flows", headers=headers or ed["h"],
                    json={"data_entity_id": de["data_entity_id"], "source_application_id": src["application_id"],
                          "target_application_id": tgt["application_id"], "flow_note": note})
    assert r.status_code == expect, r.text
    return r.json()


def flows(client, ed, br):
    r = client.get(f"{API}/business-requirements/{br['br_id']}/flows", headers=ed["h"])
    assert r.status_code == 200, r.text
    return r.json()


def to_fr(client, ed, br, ids, fr_type="INTERFACE", name="Credit decision feed", expect=201):
    r = client.post(f"{API}/business-requirements/{br['br_id']}/flows/interface-fr", headers=ed["h"],
                    json={"flow_ids": ids, "fr_type_code": fr_type, "fr_name": name})
    assert r.status_code == expect, r.text
    return r.json()


@pytest.fixture
def w(client, ed):
    s = scope(client, ed)
    s["crm"] = app(client, ed, code="SF-CRM", name="Salesforce", lifecycle="TO_BE")
    s["erp"] = app(client, ed, code="SAP-ECC", name="SAP ECC", lifecycle="BOTH")
    s["old"] = app(client, ed, code="LEGACY", name="Legacy billing", lifecycle="AS_IS")
    return s


# ---- stating flows -------------------------------------------------------------------------------------------

def test_a_flow_names_two_different_systems_from_the_list_and_restating_restores_it(client, ed, w):
    br = w["br1"]
    f = flow(client, ed, br, w["order"], w["crm"], w["erp"], "before every credit check")
    assert (f["covered_by"], f["info"]) == ([], [])          # br1 creates the order: used, nothing to say
    flow(client, ed, br, w["order"], w["crm"], w["crm"], expect=422)
    flow(client, ed, br, w["order"], w["crm"], w["erp"], expect=409)        # the same statement twice
    r = client.delete(f"{API}/business-requirements/{br['br_id']}/flows/{f['br_system_flow_id']}", headers=ed["h"],
                      params={"row_version": f["row_version"]})
    assert r.status_code == 204, r.text
    assert flows(client, ed, br) == []
    again = flow(client, ed, br, w["order"], w["crm"], w["erp"])
    assert again["br_system_flow_id"] == f["br_system_flow_id"] and again["flow_note"] == "before every credit check"


def test_information_lines_never_block(client, ed, w):
    br = w["br2"]                                             # br2 reads the order and creates the invoice
    cust = client.post(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"], json={"de_name": "Customer"}).json()
    f = flow(client, ed, br, cust, w["old"], w["erp"])
    assert set(f["info"]) == {"flow_entity_not_used_by_br", "flow_touches_as_is_only_application"}


def test_another_projects_system_is_refused_and_viewers_cannot_write(client, ed, w, world):
    br = w["br1"]
    other = app(client, ed, code="X-OTHER", project=world["p_sales"], headers=world["admin"])
    flow(client, ed, br, w["order"], w["crm"], other, expect=422)
    flow(client, ed, br, w["order"], w["crm"], w["erp"], headers=ed["rv"], expect=403)
    assert client.get(f"{API}/business-requirements/{br['br_id']}/flows", headers=ed["out"]).status_code == 404


def test_with_applications_off_a_flow_write_is_component_off(client, world):
    """Criterion 188: APPLICATION off → 409 COMPONENT_OFF; reading still works."""
    p = new_project(client, world, "REQ11", ["ISSUE"])["project_id"]
    h = editor_on(client, world, p)
    ed2 = {"h": h, "p": p}
    a = node(client, ed2, "Sales")
    g = node(client, ed2, "Order to cash", a["bfc_node_id"])
    s = node(client, ed2, "Take order", g["bfc_node_id"], is_process=True)
    br = next(b for b in client.get(f"{API}/projects/{p}/business-requirements", headers=h).json()
              if b["bfc_node_id"] == s["bfc_node_id"])
    r = client.post(f"{API}/business-requirements/{br['br_id']}/flows", headers=h,
                    json={"data_entity_id": 1, "source_application_id": 1, "target_application_id": 2})
    assert r.status_code == 409 and r.headers["X-VB-Error"] == "COMPONENT_OFF"
    assert client.get(f"{API}/business-requirements/{br['br_id']}/flows", headers=h).status_code == 200


def test_retiring_a_system_or_entity_a_live_flow_uses_is_refused_naming_the_requirement(client, ed, w):
    br = w["br1"]
    flow(client, ed, br, w["order"], w["crm"], w["erp"])
    r = retire_app(client, ed, w["crm"])
    assert r.status_code == 409 and br["br_number"] in r.json()["detail"]


def test_flows_retire_and_restore_with_their_process(client, ed, w):
    br, s = w["br1"], w["s1"]
    flow(client, ed, br, w["order"], w["crm"], w["erp"])
    prev = client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}/retire-preview", headers=ed["h"]).json()
    assert "SF-CRM → SAP-ECC" in str(prev)
    assert client.post(f"{API}/bfc-nodes/{s['bfc_node_id']}/retire-with-dependents", headers=ed["h"],
                       json={"confirm_hash": prev["confirm_hash"]}).status_code == 204
    assert client.post(f"{API}/bfc-nodes/{s['bfc_node_id']}/restore-with-dependents", headers=ed["h"]).status_code == 200
    assert len(flows(client, ed, br)) == 1


# ---- coverage and the seeding action -------------------------------------------------------------------------

def test_coverage_is_exactly_a_linked_interface_fr_with_the_same_ends_carrying_the_entity(client, ed, w):
    br = w["br1"]
    f = flow(client, ed, br, w["order"], w["crm"], w["erp"])
    i = fr(client, ed, "Order feed", "INTERFACE")
    assert put_iface(client, ed, i, w["crm"], w["erp"], [w["invoice"]]).status_code == 200   # wrong entity
    r = client.post(f"{API}/business-requirements/{br['br_id']}/function-requirements", headers=ed["h"],
                    json={"fr_id": i["fr_id"]})
    assert r.status_code == 201, r.text
    assert flows(client, ed, br)[0]["covered_by"] == []
    cur = client.get(f"{API}/function-requirements/{i['fr_id']}/interface", headers=ed["h"]).json()
    assert put_iface(client, ed, i, w["erp"], w["crm"], [w["order"]], row_version=cur["row_version"]).status_code == 200
    assert flows(client, ed, br)[0]["covered_by"] == []       # the wrong direction
    cur = client.get(f"{API}/function-requirements/{i['fr_id']}/interface", headers=ed["h"]).json()
    assert put_iface(client, ed, i, w["crm"], w["erp"], [w["order"]], row_version=cur["row_version"]).status_code == 200
    assert flows(client, ed, br)[0]["covered_by"] == [i["fr_number"]]
    assert f["br_system_flow_id"] == flows(client, ed, br)[0]["br_system_flow_id"]


def test_create_interface_fr_from_flows_makes_the_fr_interface_carried_set_and_link_in_one_save(client, ed, w):
    br = w["br1"]
    f1 = flow(client, ed, br, w["order"], w["crm"], w["erp"], "the order")
    f2 = flow(client, ed, br, w["invoice"], w["crm"], w["erp"])
    made = to_fr(client, ed, br, [f1["br_system_flow_id"], f2["br_system_flow_id"]])
    assert made["fr_number"].startswith("FR-")
    detail = client.get(f"{API}/function-requirements/{made['fr_id']}/interface", headers=ed["h"]).json()
    assert (detail["source_application_id"], detail["target_application_id"]) == (w["crm"]["application_id"],
                                                                                  w["erp"]["application_id"])
    assert sorted(c["data_entity_id"] for c in detail["carried"]) == sorted([w["order"]["data_entity_id"],
                                                                             w["invoice"]["data_entity_id"]])
    assert {x["covered_by"][0] for x in flows(client, ed, br)} == {made["fr_number"]}
    links = client.get(f"{API}/business-requirements/{br['br_id']}/function-requirements", headers=ed["h"]).json()
    assert made["fr_id"] in [x["fr_id"] for x in links]


def test_seeding_refuses_mixed_pairs_and_non_interface_types_and_writes_nothing(client, ed, w):
    br = w["br1"]
    f1 = flow(client, ed, br, w["order"], w["crm"], w["erp"])
    f2 = flow(client, ed, br, w["invoice"], w["erp"], w["crm"])
    before = client.get(f"{API}/projects/{ed['p']}/function-requirements", headers=ed["h"]).json()
    to_fr(client, ed, br, [f1["br_system_flow_id"], f2["br_system_flow_id"]], expect=422)
    to_fr(client, ed, br, [f1["br_system_flow_id"]], fr_type="FORM", expect=422)
    to_fr(client, ed, br, [999999], expect=404)
    assert client.get(f"{API}/projects/{ed['p']}/function-requirements", headers=ed["h"]).json() == before


def test_a_data_migration_fr_covers_a_flow_and_is_listed_among_interfaces_with_its_type(client, ed, w):
    """S11-5, S11-7: Data migration has interface behaviour, covers a flow as an interface does, and the Interfaces
    register names its type so the two can be told apart."""
    br = w["br1"]
    f = flow(client, ed, br, w["order"], w["old"], w["erp"], "one-off at go-live")
    made = to_fr(client, ed, br, [f["br_system_flow_id"]], fr_type="MIGRATION", name="Migrate open orders")
    assert flows(client, ed, br)[0]["covered_by"] == [made["fr_number"]]
    rows = {r["interface_number"]: r for r in listing(client, ed)["rows"]}
    assert rows[made["fr_number"]]["fr_type_code"] == "MIGRATION"
    assert rows[made["fr_number"]]["fr_type_label"] == "Data migration"


def test_seeding_refuses_a_flow_of_another_requirement_or_project(client, ed, w, world):
    """sara 11c L5: a live flow id from another BR — or another project's BR — is 404, never an FR built from it."""
    mine = flow(client, ed, w["br1"], w["order"], w["crm"], w["erp"])
    theirs = flow(client, ed, w["br2"], w["invoice"], w["crm"], w["erp"])
    to_fr(client, ed, w["br1"], [mine["br_system_flow_id"], theirs["br_system_flow_id"]], expect=404)
    to_fr(client, ed, w["br2"], [mine["br_system_flow_id"]], expect=404)
    # another project: the admin states a flow there; its id is refused on this project's BR
    adm = {"h": world["admin"], "p": world["p_sales"]}
    a = node(client, adm, "Sales")
    g = node(client, adm, "Order to cash", a["bfc_node_id"])
    s = node(client, adm, "Take order", g["bfc_node_id"], is_process=True)
    br_x = next(b for b in client.get(f"{API}/projects/{world['p_sales']}/business-requirements",
                                      headers=world["admin"]).json() if b["bfc_node_id"] == s["bfc_node_id"])
    de_x = client.post(f"{API}/projects/{world['p_sales']}/data-entities", headers=world["admin"],
                       json={"de_name": "Order"}).json()
    src_x = app(client, ed, code="X-ONE", name="Other one", project=world["p_sales"], headers=world["admin"])
    tgt_x = app(client, ed, code="X-TWO", name="Other two", project=world["p_sales"], headers=world["admin"])
    foreign = flow(client, adm, br_x, de_x, src_x, tgt_x)
    to_fr(client, ed, w["br1"], [foreign["br_system_flow_id"]], expect=404)
    assert flows(client, ed, w["br1"])[0]["covered_by"] == []


def test_a_flow_note_edit_is_versioned_and_audited(client, ed, w, db):
    """sara 11c L4: the note route has its API function, a stale version is 409, and the change is audited."""
    br = w["br1"]
    f = flow(client, ed, br, w["order"], w["crm"], w["erp"], "nightly")
    url = f"{API}/business-requirements/{br['br_id']}/flows/{f['br_system_flow_id']}"
    r = client.patch(url, headers=ed["h"], json={"row_version": f["row_version"], "flow_note": "hourly"})
    assert r.status_code == 200 and r.json()["flow_note"] == "hourly"
    assert client.patch(url, headers=ed["h"], json={"row_version": f["row_version"], "flow_note": "x"}).status_code == 409
    ev = db.execute(text("SELECT detail FROM audit_event WHERE target_table = 'br_system_flow' "
                         "AND event_type = 'RECORD_UPDATED'")).scalars().all()
    assert [e["previous_flow_note"] for e in ev] == ["nightly"]


# ---- the slice 11 freeze (grade 1, Ren's condition before slice 11 merges) ------------------------------------

def test_one_baseline_holds_every_live_line_tick_and_flow_hashed_on_the_agreed_columns(client, ed, w, db):
    br = w["br1"]
    line = add_line(client, ed, br, "RULE", "Only active customers may get credit.", "MUST")
    oid = field(client, ed, w["order"], "order_id", is_primary_key=True, pk_ordinal=1)
    save(client, ed, br, current_entities(client, ed, br), [(oid, "C", "minted on save")])
    f = flow(client, ed, br, w["order"], w["crm"], w["erp"], "on every credit decision")
    gone = flow(client, ed, br, w["invoice"], w["crm"], w["erp"])
    assert client.delete(f"{API}/business-requirements/{br['br_id']}/flows/{gone['br_system_flow_id']}",
                         headers=ed["h"], params={"row_version": gone["row_version"]}).status_code == 204
    b = freeze(client, ed)["baseline"]
    v = b["baseline_id"]
    assert b["hash_spec_version"] == CURRENT_HASH_SPEC     # a fresh freeze: the current spec (5 since slice 14)
    q = lambda sql: db.execute(text(sql), {"b": v}).mappings().all()     # noqa: E731
    ln = q("SELECT source_id, br_id, line_no, line_kind_code, priority_code, line_text, content_hash "
           "FROM baseline_br_requirement_line WHERE baseline_id = :b")
    tk = q("SELECT source_id, br_id, data_entity_id, data_field_id, crud_code, usage_note, content_hash "
           "FROM baseline_br_data_field WHERE baseline_id = :b")
    fl = q("SELECT source_id, br_id, data_entity_id, source_application_id, target_application_id, flow_note, "
           "content_hash FROM baseline_br_system_flow WHERE baseline_id = :b")
    assert [r["source_id"] for r in ln] == [line["br_requirement_line_id"]]
    assert [r["data_field_id"] for r in tk] == [oid["data_field_id"]]
    assert [r["source_id"] for r in fl] == [f["br_system_flow_id"]]          # the removed flow is not frozen
    for r, cols in ((ln[0], ("br_id", "line_no", "line_kind_code", "priority_code", "line_text")),
                    (tk[0], ("br_id", "data_entity_id", "data_field_id", "crud_code", "usage_note")),
                    (fl[0], ("br_id", "data_entity_id", "source_application_id", "target_application_id", "flow_note"))):
        assert r["content_hash"] == expected_hash(tuple(r[c] for c in cols))
    assert client.get(f"{API}/baselines/{v}", headers=ed["h"]).json()["intact"] is True
    for t in ("baseline_br_requirement_line", "baseline_br_data_field", "baseline_br_system_flow"):
        with pytest.raises(Exception):
            owner_exec(f"UPDATE {t} SET project_id = project_id WHERE baseline_id = :b", b=v)
    assert bid({"baseline": b}) == v
