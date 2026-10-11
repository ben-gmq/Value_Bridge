"""Interface detail and the generated interface list (docs/slice6b2_spec.md §8). Grade 2: the list
is a vendor-facing scope document; a wrong endpoint or a hidden incomplete interface misleads a build.
The riskiest concerns — detail on a non-interface FR or across projects, a renamed type dropping out
of the list, and a stale tab silently reverting the carried set — are proven directly.

Deliberately uncovered (spec §8): `.xlsx` export; more than 200 carried entities."""
from sqlalchemy import select, text

from models import AuditEvent
from services import consistency, lifecycle
from tests.test_application_api import app, retire_app
from tests.test_function_requirement_api import fr, patch as fr_patch
from tests.test_scope_api import API, ed, entity  # noqa: F401 — ed is a fixture


def put(client, ed, f, src, tgt, carried=(), row_version=None, headers=None, **kw):
    body = {"source_application_id": src["application_id"], "target_application_id": tgt["application_id"],
            "carried": [c if isinstance(c, dict) else {"data_entity_id": c["data_entity_id"]} for c in carried],
            "row_version": row_version, **kw}
    return client.put(f"{API}/function-requirements/{f['fr_id']}/interface", headers=headers or ed["h"], json=body)


def read(client, ed, f):
    return client.get(f"{API}/function-requirements/{f['fr_id']}/interface", headers=ed["h"]).json()


def listing(client, ed, **q):
    return client.get(f"{API}/projects/{ed['p']}/interfaces", headers=ed["rv"], params=q).json()


def world_(client, ed):
    """Two applications, two entities, one interface FR."""
    erp = app(client, ed, code="SAP-ECC", name="SAP ECC", lifecycle="BOTH")
    crm = app(client, ed, code="SF-CRM", name="Salesforce", lifecycle="TO_BE")
    order, cust = entity(client, ed, "Sales order"), entity(client, ed, "Customer")
    f = fr(client, ed, "Order feed", "INTERFACE")
    return erp, crm, order, cust, f


def add_api_type(db, project_id, code="API", label="API", behaviour="INTERFACE"):
    """A project's own FR type with interface behaviour (criterion 101) — no maintenance route yet."""
    db.execute(text("INSERT INTO code_master (project_id, category, code, label, behaviour_code, sort_order, is_system) "
                    "VALUES (:p, 'FR_TYPE', :c, :l, :b, 99, false)"), {"p": project_id, "c": code, "l": label, "b": behaviour})
    db.commit()


# ---- describe -----------------------------------------------------------------------------

def test_describe_read_and_list_a_complete_interface(client, ed):
    erp, crm, order, cust, f = world_(client, ed)
    r = put(client, ed, f, erp, crm, [{"data_entity_id": order["data_entity_id"], "note": "header and lines"}],
            pattern_code="PUSH", method_code="API", frequency_code="DAILY", volume_note="~2k/day")
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["described"], d["source_application_code"], d["target_application_code"], d["method_code"]) == \
        (True, "SAP-ECC", "SF-CRM", "API")
    assert [(c["de_number"], c["note"]) for c in d["carried"]] == [(order["de_number"], "header and lines")]
    row = listing(client, ed)["rows"][0]
    assert (row["interface_number"], row["is_complete"], row["missing"]) == (f["fr_number"], True, [])
    assert row["carried"] == [{"de_number": order["de_number"], "de_name": "Sales order", "note": "header and lines"}]


def test_detail_only_on_an_interface_behaviour_fr(client, ed):
    """Criterion 102 (first half)."""
    erp, crm, *_ = world_(client, ed)
    form = fr(client, ed, "Order form", "FORM")
    r = put(client, ed, form, erp, crm)
    assert r.status_code == 422 and "interface-type" in r.json()["detail"]


def test_type_change_away_with_detail_is_409_and_to_another_interface_type_is_allowed(client, ed, db):
    """Criteria 101 and 102: behaviour decides, never the code."""
    erp, crm, order, _, f = world_(client, ed)
    put(client, ed, f, erp, crm, [order], method_code="API")
    cur = client.get(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"]).json()
    r = fr_patch(client, ed, cur, fr_type_code="FORM")
    assert r.status_code == 409 and "interface detail" in r.json()["detail"]
    add_api_type(db, ed["p"])
    r = fr_patch(client, ed, cur, fr_type_code="API")
    assert r.status_code == 200 and r.json()["fr_type_behaviour"] == "INTERFACE"
    row = listing(client, ed)["rows"][0]
    assert (row["interface_number"], row["fr_type_code"]) == (f["fr_number"], "API")       # still listed (101)


def test_an_fr_of_a_new_interface_type_is_listed_and_describable(client, ed, db):
    """Criterion 101: a renamed or added type with INTERFACE behaviour lists with no code change."""
    add_api_type(db, ed["p"], code="RENKEI", label="連携")
    erp = app(client, ed, code="A", name="A")
    crm = app(client, ed, code="B", name="B")
    f = fr(client, ed, "連携 feed", "RENKEI")
    assert f["fr_type_behaviour"] == "INTERFACE"
    assert put(client, ed, f, erp, crm).status_code == 200
    assert [r["fr_type_label"] for r in listing(client, ed)["rows"]] == ["連携"]


def test_incomplete_interfaces_list_with_what_is_missing(client, ed):
    """Criterion 103 and S6b2-1: complete = endpoints, method and at least one entity."""
    erp, crm, order, _, f = world_(client, ed)
    bare = fr(client, ed, "Not yet described", "INTERFACE")
    put(client, ed, f, erp, crm)                                         # endpoints only
    rows = {r["interface_number"]: r for r in listing(client, ed)["rows"]}
    assert rows[bare["fr_number"]]["missing"] == ["endpoints", "method", "data_entities"]
    assert rows[f["fr_number"]]["missing"] == ["method", "data_entities"]
    assert not any(r["is_complete"] for r in rows.values())


def test_source_and_target_must_differ_and_codes_resolve(client, ed):
    erp, crm, _, _, f = world_(client, ed)
    assert put(client, ed, f, erp, erp).status_code == 422
    assert put(client, ed, f, erp, crm, method_code="TELEPATHY").status_code == 400


# ---- versions, the carried set, and one transaction ---------------------------------------

def test_a_stale_tab_cannot_revert_a_carried_set_change(client, ed):
    """DR6b2-P1: a set-only change moves the detail's version, so the second save is 409."""
    erp, crm, order, cust, f = world_(client, ed)
    v1 = put(client, ed, f, erp, crm, [order, cust]).json()["row_version"]
    b = put(client, ed, f, erp, crm, [order], row_version=v1)                 # editor B drops Customer
    assert b.status_code == 200 and b.json()["row_version"] > v1
    a = put(client, ed, f, erp, crm, [order, cust], row_version=v1, frequency_code="HOURLY")   # editor A, stale
    assert a.status_code == 409
    assert [c["de_number"] for c in read(client, ed, f)["carried"]] == [order["de_number"]]


def test_update_needs_the_version_and_insert_does_not(client, ed):
    erp, crm, order, _, f = world_(client, ed)
    assert put(client, ed, f, erp, crm).status_code == 200                    # insert: no version
    assert put(client, ed, f, erp, crm, [order]).status_code == 409           # update without one


def test_a_retired_entity_in_the_list_changes_nothing(client, ed):
    """DR6b2-P3: all checks before the first write."""
    erp, crm, order, cust, f = world_(client, ed)
    v = put(client, ed, f, erp, crm, [order], method_code="API").json()["row_version"]
    client.delete(f"{API}/data-entities/{cust['data_entity_id']}", headers=ed["h"], params={"row_version": cust["row_version"]})
    r = put(client, ed, f, erp, crm, [cust], row_version=v, method_code="FILE")
    assert r.status_code == 409
    after = read(client, ed, f)
    assert (after["method_code"], [c["de_number"] for c in after["carried"]], after["row_version"]) == \
        ("API", [order["de_number"]], v)


def test_carried_is_required_duplicates_refused_and_untouched_notes_kept(client, ed):
    """DR6b2-D1, DR6b2-D2, S6b2-4."""
    erp, crm, order, cust, f = world_(client, ed)
    body = {"source_application_id": erp["application_id"], "target_application_id": crm["application_id"]}
    assert client.put(f"{API}/function-requirements/{f['fr_id']}/interface", headers=ed["h"], json=body).status_code == 422
    dup = [{"data_entity_id": order["data_entity_id"]}, {"data_entity_id": order["data_entity_id"]}]
    assert put(client, ed, f, erp, crm, dup).status_code == 422
    v = put(client, ed, f, erp, crm, [{"data_entity_id": order["data_entity_id"], "note": "header only"}]).json()["row_version"]
    v = put(client, ed, f, erp, crm, [{"data_entity_id": order["data_entity_id"]}, cust], row_version=v).json()["row_version"]
    assert {c["de_number"]: c["note"] for c in read(client, ed, f)["carried"]} == \
        {order["de_number"]: "header only", cust["de_number"]: None}
    put(client, ed, f, erp, crm, [{"data_entity_id": order["data_entity_id"], "note": None}], row_version=v)
    assert read(client, ed, f)["carried"][0]["note"] is None


def test_remove_then_put_again_restores_the_same_rows_with_the_retired_version(client, ed, db):
    """DR6b2-P2 and S6b Q-5."""
    erp, crm, order, _, f = world_(client, ed)
    v = put(client, ed, f, erp, crm, [order], method_code="API").json()["row_version"]
    assert client.delete(f"{API}/function-requirements/{f['fr_id']}/interface", headers=ed["h"],
                         params={"row_version": v}).status_code == 204
    gone = read(client, ed, f)
    assert (gone["described"], gone["carried"]) == (False, [])
    assert db.scalar(text("SELECT count(*) FROM fr_interface_data_entity WHERE fr_id = :i AND is_active"), {"i": f["fr_id"]}) == 0
    assert listing(client, ed)["rows"][0]["missing"] == ["endpoints", "method", "data_entities"]
    assert put(client, ed, f, erp, crm, [order], row_version=v).status_code == 409             # stale: removal moved it
    back = put(client, ed, f, erp, crm, [order], row_version=gone["row_version"], method_code="API")
    assert back.status_code == 200 and back.json()["described"] is True
    assert db.scalar(text("SELECT count(*) FROM fr_interface_data_entity WHERE fr_id = :i"), {"i": f["fr_id"]}) == 1


def test_endpoint_changes_are_audited_with_the_previous_values(client, ed, db):
    """DR6b2-S1."""
    erp, crm, order, _, f = world_(client, ed)
    wms = app(client, ed, code="LEGACY-WMS", name="Legacy WMS")
    v = put(client, ed, f, erp, crm, [order], method_code="API").json()["row_version"]
    put(client, ed, f, erp, wms, [order], row_version=v, method_code="FILE")
    ev = db.scalars(select(AuditEvent).where(AuditEvent.target_table == "fr_interface",
                                             AuditEvent.event_type == "RECORD_UPDATED")).one()
    assert (ev.detail["previous_target_application_code"], ev.detail["previous_method_code"]) == ("SF-CRM", "API")


# ---- retired FRs, scope, and retire guards ------------------------------------------------

def test_put_and_delete_on_a_retired_fr_are_refused(client, ed):
    """DR6b2-P4."""
    erp, crm, *_, f = world_(client, ed)
    client.delete(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"], params={"row_version": f["row_version"]})
    assert put(client, ed, f, erp, crm).status_code == 409
    assert client.delete(f"{API}/function-requirements/{f['fr_id']}/interface", headers=ed["h"],
                         params={"row_version": 1}).status_code == 409


def test_another_projects_application_or_entity_is_404_and_nothing_leaks(client, ed, world):
    erp, crm, order, _, f = world_(client, ed)
    admin = world["admin"]
    beta = app(client, ed, code="BETA-ERP", name="Beta ERP", headers=admin, project=world["p_beta"])
    gone = app(client, ed, code="BETA-OLD", name="Beta Old", headers=admin, project=world["p_beta"])
    retire_app(client, ed, gone, headers=admin)
    beta_de = client.post(f"{API}/projects/{world['p_beta']}/data-entities", headers=admin, json={"de_name": "Beta secret"}).json()
    missing = put(client, ed, f, erp, {"application_id": 10 ** 9})
    assert missing.status_code == 404
    for r in (put(client, ed, f, erp, beta), put(client, ed, f, gone, crm), put(client, ed, f, erp, crm, [beta_de])):
        assert r.status_code == 404 and r.json() == missing.json() and "Beta" not in r.text


def test_retire_guards_fr_application_entity(client, ed):
    """S6b-3 and the generic FK_LIVENESS blockers."""
    erp, crm, order, _, f = world_(client, ed)
    put(client, ed, f, erp, crm, [order])
    r = client.delete(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"], params={"row_version": f["row_version"]})
    assert r.status_code == 409 and f"Interface {f['fr_number']}" in r.json()["detail"]
    ra = retire_app(client, ed, crm)
    assert ra.status_code == 409 and f["fr_number"] in ra.json()["detail"]
    rd = client.delete(f"{API}/data-entities/{order['data_entity_id']}", headers=ed["h"], params={"row_version": order["row_version"]})
    assert rd.status_code == 409 and f"{f['fr_number']} carries {order['de_number']}" in rd.json()["detail"]


def test_one_link_per_fk_pair_so_blockers_are_not_double_counted(client, ed):
    """GUARD_TARGET_COLUMNS gains fr_type_behaviour (schema §7)."""
    from models import FrInterface, FrInterfaceDataEntity, FunctionRequirement
    fr_links = [ln for ln in lifecycle.dependents_of(FunctionRequirement) if ln.child is FrInterface]
    fide_links = [ln for ln in lifecycle.dependents_of(FrInterface) if ln.child is FrInterfaceDataEntity]
    assert (len(fr_links), len(fide_links)) == (1, 1)


def test_reviewer_is_refused_and_outsider_sees_nothing(client, ed):
    erp, crm, *_, f = world_(client, ed)
    assert put(client, ed, f, erp, crm, headers=ed["rv"]).status_code == 403
    assert client.get(f"{API}/function-requirements/{f['fr_id']}/interface", headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/projects/{ed['p']}/interfaces", headers=ed["out"]).status_code == 404


# ---- the pair filter ----------------------------------------------------------------------

def test_pair_filter_direction_bidirectional_and_the_unfilterable_count(client, ed):
    """S6b2-2, S6b2-3."""
    erp, crm, order, _, f = world_(client, ed)
    back = fr(client, ed, "Customer sync", "INTERFACE")
    other = fr(client, ed, "Reverse feed", "INTERFACE")
    fr(client, ed, "Not yet described", "INTERFACE")
    put(client, ed, f, erp, crm, [order], method_code="API")                     # SAP → SF
    put(client, ed, back, crm, erp, [order], pattern_code="BIDIRECTIONAL")       # SF ↔ SAP
    put(client, ed, other, crm, erp, [order], pattern_code="PUSH")               # SF → SAP only
    got = listing(client, ed, source=erp["application_id"], target=crm["application_id"])
    assert sorted(r["interface_name"] for r in got["rows"]) == ["Customer sync", "Order feed"]
    assert got["unfilterable_incomplete"] == 1
    assert listing(client, ed)["unfilterable_incomplete"] == 0


def test_status_filter(client, ed):
    erp, crm, order, _, f = world_(client, ed)
    put(client, ed, f, erp, crm, [order])
    assert len(listing(client, ed, status="SPECIFIED")["rows"]) == 1
    assert listing(client, ed, status="BUILT")["rows"] == []


# ---- consistency_check and the view -------------------------------------------------------

def test_interface_under_inactive_finds_a_planted_orphan(client, ed, db):
    erp, crm, order, _, f = world_(client, ed)
    put(client, ed, f, erp, crm, [order])
    assert consistency.consistency_check(ed["p"], db)["interface_under_inactive"] == []
    db.execute(text("UPDATE application SET is_active = false WHERE application_id = :i"), {"i": crm["application_id"]})
    db.commit()
    assert len(consistency.consistency_check(ed["p"], db)["interface_under_inactive"]) == 1


def test_the_list_view_is_read_only_to_the_app(db):
    can = db.execute(text("SELECT has_table_privilege('v_interface_list', 'SELECT'), "
                          "has_table_privilege('v_interface_list', 'INSERT'), "
                          "has_table_privilege('v_interface_list', 'UPDATE')")).one()
    assert tuple(can) == (True, False, False)
