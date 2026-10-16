"""Slice 11b — the attributes a BR uses, C / R / U per attribute, saved with the entity ticks in one request
(D-60b, docs/slice11_schema.md §2, §4, §5; criterion 187).

Grade 2 (wrong figures reach a client's spec and are correctable once seen), except the one concern shared with
slice 11a: a frozen baseline holds every live tick, hashed on the agreed columns — Grade 1, proven below against an
independent hash. Left uncovered on purpose: concurrency beyond the `known` check (the licence FK is the database's
own guard behind it)."""
import pytest
from sqlalchemy import text

from tests.test_baseline import bid, diff, freeze, owner_exec, scope
from tests.test_br_lines import expected_hash
from tests.test_erd_api import field
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture


def grid(client, ed, br, headers=None):
    r = client.get(f"{API}/business-requirements/{br['br_id']}/data-grid", headers=headers or ed["h"])
    assert r.status_code == 200, r.text
    return r.json()


def known_of(g):
    return [{"table": "br_data_entity", "id": e["br_data_entity_id"], "row_version": e["row_version"]}
            for e in g["entities"]] + \
           [{"table": "br_data_field", "id": a["br_data_field_id"], "row_version": a["row_version"]}
            for a in g["attributes"]]


def save(client, ed, br, entities, attributes, known=None, expect=200, headers=None):
    """entities: [(de, crud)], attributes: [(field, crud)] or [(field, crud, note)]."""
    k = known if known is not None else known_of(grid(client, ed, br))
    body = {"entity_ticks": [{"data_entity_id": de["data_entity_id"], "crud_code": c} for de, c in entities],
            "attribute_ticks": [{"data_field_id": a[0]["data_field_id"], "crud_code": a[1],
                                 "usage_note": a[2] if len(a) > 2 else None} for a in attributes],
            "known": k}
    r = client.put(f"{API}/business-requirements/{br['br_id']}/data-grid", headers=headers or ed["h"], json=body)
    assert r.status_code == expect, r.text
    return r.json()


def ticks(g):
    return sorted((a["data_field_id"], a["crud_code"]) for a in g["attributes"])


@pytest.fixture
def w(client, ed):
    s = scope(client, ed)
    s["oid"] = field(client, ed, s["order"], "order_id", is_primary_key=True, pk_ordinal=1)
    s["amt"] = field(client, ed, s["order"], "amount")
    s["inv_no"] = field(client, ed, s["invoice"], "invoice_no", is_primary_key=True, pk_ordinal=1)
    return s


def current_entities(client, ed, br):
    return [({"data_entity_id": e["data_entity_id"]}, e["crud_code"]) for e in grid(client, ed, br)["entities"]]


# ---- one save ------------------------------------------------------------------------------------------------

def test_entity_and_attribute_ticks_save_together_and_attributes_need_their_entity_action(client, ed, w):
    br = w["br1"]                                       # scope(): br1 reads invoice (R) and creates order (C)
    ents = current_entities(client, ed, br)
    g = save(client, ed, br, ents + [(w["order"], "U")],
             [(w["oid"], "C"), (w["amt"], "U", "set when the order is priced")])
    assert ticks(g) == sorted([(w["oid"]["data_field_id"], "C"), (w["amt"]["data_field_id"], "U")])
    assert {(e["data_entity_id"], e["crud_code"]) for e in g["entities"]} >= {(w["order"]["data_entity_id"], "U")}
    note = next(a for a in g["attributes"] if a["crud_code"] == "U")["usage_note"]
    assert note == "set when the order is priced"
    # an attribute action the entity does not have is refused, and nothing is saved
    save(client, ed, br, ents, [(w["inv_no"], "U")], expect=422)
    save(client, ed, br, ents + [(w["order"], "D")], [(w["oid"], "D")], expect=422)   # Delete stays entity-level
    assert ticks(grid(client, ed, br)) == ticks(g)


def test_unticking_an_entity_action_removes_its_attribute_ticks_in_the_same_save(client, ed, w):
    br = w["br1"]
    ents = current_entities(client, ed, br)
    save(client, ed, br, ents + [(w["order"], "U")], [(w["oid"], "C"), (w["amt"], "U")])
    g = save(client, ed, br, ents, [(w["oid"], "C")])     # U on the order unticked, with its attribute
    assert ticks(g) == [(w["oid"]["data_field_id"], "C")]
    assert (w["order"]["data_entity_id"], "U") not in {(e["data_entity_id"], e["crud_code"]) for e in g["entities"]}


def test_the_one_tick_unlink_refuses_while_attributes_hold_the_action(client, ed, w):
    br = w["br1"]
    g = save(client, ed, br, current_entities(client, ed, br), [(w["oid"], "C")])
    link = next(e for e in g["entities"] if (e["data_entity_id"], e["crud_code"]) == (w["order"]["data_entity_id"], "C"))
    r = client.delete(f"{API}/business-requirements/{br['br_id']}/data-entities/{link['br_data_entity_id']}",
                      headers=ed["h"], params={"row_version": link["row_version"]})
    assert r.status_code == 409 and "order_id" in r.json()["detail"]


def test_a_save_from_a_stale_screen_is_409_and_changes_nothing(client, ed, w):
    br = w["br1"]
    stale = known_of(grid(client, ed, br))
    save(client, ed, br, current_entities(client, ed, br), [(w["oid"], "C")])
    save(client, ed, br, current_entities(client, ed, br), [], known=stale, expect=409)
    assert ticks(grid(client, ed, br)) == [(w["oid"]["data_field_id"], "C")]


def test_reticking_restores_the_same_row(client, ed, w):
    br = w["br1"]
    ents = current_entities(client, ed, br)
    first = save(client, ed, br, ents, [(w["oid"], "C")])["attributes"][0]["br_data_field_id"]
    save(client, ed, br, ents, [])
    again = save(client, ed, br, ents, [(w["oid"], "C")])["attributes"][0]["br_data_field_id"]
    assert again == first


def test_a_field_of_another_project_is_404_and_viewers_cannot_save(client, ed, w, world):
    br = w["br1"]
    ents = current_entities(client, ed, br)
    r = client.put(f"{API}/business-requirements/{br['br_id']}/data-grid", headers=ed["h"],
                   json={"entity_ticks": [], "attribute_ticks": [{"data_field_id": 999999, "crud_code": "C", "usage_note": None}],
                         "known": known_of(grid(client, ed, br))})
    assert r.status_code == 404
    save(client, ed, br, ents, [], headers=ed["rv"], expect=403)
    assert client.get(f"{API}/business-requirements/{br['br_id']}/data-grid", headers=ed["out"]).status_code == 404


# ---- liveness ------------------------------------------------------------------------------------------------

def test_retiring_a_field_a_requirement_uses_is_refused_naming_it(client, ed, w):
    br = w["br1"]
    save(client, ed, br, current_entities(client, ed, br), [(w["amt"], "C")])
    cur = client.get(f"{API}/data-entities/{w['order']['data_entity_id']}/fields", headers=ed["h"]).json()
    amt = next(f for f in cur if f["data_field_id"] == w["amt"]["data_field_id"])
    r = client.delete(f"{API}/data-fields/{amt['data_field_id']}", headers=ed["h"], params={"row_version": amt["row_version"]})
    assert r.status_code == 409 and br["br_number"] in r.json()["detail"]


def test_the_database_refuses_an_attribute_tick_without_its_live_entity_action(client, ed, w):
    """Criterion 187, at the database: even the owner cannot insert a tick whose entity action is missing."""
    br = w["br1"]
    sql = (f"INSERT INTO br_data_field (project_id, br_id, data_entity_id, crud_code, data_field_id, created_by) "
           f"SELECT {ed['p']}, {br['br_id']}, {w['order']['data_entity_id']}, 'U', {w['oid']['data_field_id']}, "
           f"min(app_user_id) FROM app_user")
    with pytest.raises(Exception, match="fk_brdf_licence"):
        owner_exec(sql)                                  # the order has C on br1, never U


def test_ticks_retire_and_restore_with_their_process(client, ed, w):
    br, s = w["br1"], w["s1"]
    save(client, ed, br, current_entities(client, ed, br), [(w["oid"], "C")])
    prev = client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}/retire-preview", headers=ed["h"]).json()
    assert "order_id (C)" in str(prev)
    r = client.post(f"{API}/bfc-nodes/{s['bfc_node_id']}/retire-with-dependents", headers=ed["h"],
                    json={"confirm_hash": prev["confirm_hash"]})
    assert r.status_code == 204, r.text
    assert client.post(f"{API}/bfc-nodes/{s['bfc_node_id']}/restore-with-dependents", headers=ed["h"]).status_code == 200
    assert ticks(grid(client, ed, br)) == [(w["oid"]["data_field_id"], "C")]


def test_an_entity_action_with_no_attribute_is_information_under_full_only(client, ed, w, world):
    br = w["br1"]
    info = grid(client, ed, br)["info"]
    assert {(i["data_entity_id"], i["crud_code"]) for i in info} == {
        (w["order"]["data_entity_id"], "C"), (w["invoice"]["data_entity_id"], "R")}
    save(client, ed, br, current_entities(client, ed, br), [(w["oid"], "C")])
    assert {(i["data_entity_id"], i["crud_code"]) for i in grid(client, ed, br)["info"]} == {
        (w["invoice"]["data_entity_id"], "R")}
    proj = client.get(f"{API}/projects/{ed['p']}", headers=world["admin"]).json()
    r = client.put(f"{API}/projects/{ed['p']}/data-model-depth", headers=world["admin"],
                   json={"row_version": proj["row_version"], "data_model_depth": "KEYS_ONLY"})
    assert r.status_code == 200, r.text
    assert grid(client, ed, br)["info"] == []


# ---- baselines (grade 1, with 11a) ---------------------------------------------------------------------------

def test_a_frozen_baseline_holds_every_live_tick_hashed_on_the_agreed_columns(client, ed, w, db):
    br = w["br1"]
    ents = current_entities(client, ed, br)
    save(client, ed, br, ents + [(w["order"], "U")], [(w["oid"], "C"), (w["amt"], "U", "priced")])
    save(client, ed, br, ents + [(w["order"], "U")], [(w["amt"], "U", "priced")])   # oid's tick retired before
    v = bid(freeze(client, ed))
    rows = db.execute(text("SELECT source_id, br_id, data_entity_id, data_field_id, crud_code, usage_note, content_hash "
                           "FROM baseline_br_data_field WHERE baseline_id = :b"), {"b": v}).mappings().all()
    assert [(r["data_field_id"], r["crud_code"]) for r in rows] == [(w["amt"]["data_field_id"], "U")]
    r = rows[0]
    assert r["content_hash"] == expected_hash((r["br_id"], r["data_entity_id"], r["data_field_id"], r["crud_code"],
                                               r["usage_note"]))
    assert client.get(f"{API}/baselines/{v}", headers=ed["h"]).json()["intact"] is True
    save(client, ed, br, ents + [(w["order"], "U")], [(w["amt"], "U", "priced at entry")])
    d = diff(client, ed, v, "live")
    changed = d["entities"]["br_data_field"]["rows"]
    assert [(x["change"], x["fields"]) for x in changed] == [("CHANGED", ["usage_note"])]
    with pytest.raises(Exception):
        owner_exec("UPDATE baseline_br_data_field SET usage_note = 'x' WHERE baseline_id = :b", b=v)


# ---- sara's 11b review ---------------------------------------------------------------------------------------

def test_a_field_retired_while_a_save_waits_is_refused_not_ticked(client, ed, w):
    """sara M1: a save locks each field it newly ticks (SR-5). A retire holding the field's lock in another session
    makes the save wait; once the retire commits, the save sees the field retired and refuses with 409."""
    import threading
    from sqlalchemy import create_engine
    from tests.conftest import OWNER_URL
    br = w["br1"]
    ents = current_entities(client, ed, br)
    known = known_of(grid(client, ed, br))
    eng = create_engine(OWNER_URL)
    conn = eng.connect()
    tx = conn.begin()
    conn.execute(text("SELECT 1 FROM data_field WHERE data_field_id = :f FOR UPDATE"), {"f": w["amt"]["data_field_id"]})
    conn.execute(text("UPDATE data_field SET is_active = false, deleted_at = now() WHERE data_field_id = :f"),
                 {"f": w["amt"]["data_field_id"]})
    out = {}
    t = threading.Thread(target=lambda: out.update(r=client.put(
        f"{API}/business-requirements/{br['br_id']}/data-grid", headers=ed["h"],
        json={"entity_ticks": [{"data_entity_id": e["data_entity_id"], "crud_code": c} for e, c in ents],
              "attribute_ticks": [{"data_field_id": w["amt"]["data_field_id"], "crud_code": "C", "usage_note": None}],
              "known": known})))
    t.start()
    t.join(timeout=2)
    assert t.is_alive(), "the save must wait for the field's lock"
    tx.commit()
    conn.close()
    eng.dispose()
    t.join(timeout=30)
    assert out["r"].status_code == 409 and "retired" in out["r"].json()["detail"]
    assert ticks(grid(client, ed, br)) == []


def test_reticking_an_entity_action_keeps_its_note(client, ed, w):
    """sara L1: unticking and re-ticking an entity action through the grid restores the row with the note it had."""
    br = w["br1"]
    r = client.post(f"{API}/business-requirements/{br['br_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": w["order"]["data_entity_id"], "crud_code": "U", "usage_note": "on pricing"})
    assert r.status_code == 201, r.text
    ents = current_entities(client, ed, br)
    without = [x for x in ents if (x[0]["data_entity_id"], x[1]) != (w["order"]["data_entity_id"], "U")]
    save(client, ed, br, without, [])
    g = save(client, ed, br, ents, [])
    row = next(e for e in g["entities"] if (e["data_entity_id"], e["crud_code"]) == (w["order"]["data_entity_id"], "U"))
    assert row["usage_note"] == "on pricing"


def test_the_grid_body_is_the_whole_state(client, ed, w):
    """sara L2, L3: an attribute tick must carry its note (null allowed) and no tick may appear twice."""
    br = w["br1"]
    ents = [{"data_entity_id": e["data_entity_id"], "crud_code": c} for e, c in current_entities(client, ed, br)]
    known = known_of(grid(client, ed, br))
    url = f"{API}/business-requirements/{br['br_id']}/data-grid"
    oid = w["oid"]["data_field_id"]
    r = client.put(url, headers=ed["h"], json={"entity_ticks": ents, "known": known,
                                               "attribute_ticks": [{"data_field_id": oid, "crud_code": "C"}]})
    assert r.status_code == 422
    twice = [{"data_field_id": oid, "crud_code": "C", "usage_note": "a"},
             {"data_field_id": oid, "crud_code": "C", "usage_note": "b"}]
    r = client.put(url, headers=ed["h"], json={"entity_ticks": ents, "known": known, "attribute_ticks": twice})
    assert r.status_code == 422 and "once" in r.text
    r = client.put(url, headers=ed["h"], json={"entity_ticks": ents + ents[:1], "known": known, "attribute_ticks": []})
    assert r.status_code == 422
