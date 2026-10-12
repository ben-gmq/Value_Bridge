"""BR ↔ FR direct links (D-52; docs/slice10b_schema.md §1.2, §2, §4, §6). Grade 2 for the routes: a wrong mapping
reaches a client but is correctable once seen. The tag rule, the drift warnings, component gating, the
cross-project 404 and the step retire / restore of links are proven directly."""
from sqlalchemy import select, text

from models import AuditEvent
from services import consistency
from tests.conftest import restrict  # noqa: F401
from tests.test_function_requirement_api import fr
from tests.test_scope_api import API, ed, node  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol
from tests.test_step_retire import _br, preview, restore, retire


def two_brs(client, ed):
    a = node(client, ed, "Sales")
    g = node(client, ed, "Order to cash", a["bfc_node_id"])
    s1 = node(client, ed, "Take order", g["bfc_node_id"], is_process=True)
    s2 = node(client, ed, "Approve order", g["bfc_node_id"], is_process=True)
    return _br(client, ed, s1["bfc_node_id"]), _br(client, ed, s2["bfc_node_id"]), s1, s2


def lnk(client, ed, br, f, note=None, expect=201, headers=None):
    r = client.post(f"{API}/business-requirements/{br['br_id']}/function-requirements", headers=headers or ed["h"],
                    json={"fr_id": f["fr_id"], "coverage_note": note})
    assert r.status_code == expect, r.text
    return r.json()


def rows(client, ed, br):
    r = client.get(f"{API}/business-requirements/{br['br_id']}/function-requirements", headers=ed["h"])
    assert r.status_code == 200, r.text
    return r.json()


def unlnk(client, ed, br, row, expect=200):
    r = client.delete(f"{API}/business-requirements/{br['br_id']}/function-requirements/"
                      f"{row['br_function_requirement_id']}", headers=ed["h"], params={"row_version": row["row_version"]})
    assert r.status_code == expect, r.text
    return r.json()


def tag(client, ed, br, row, solution_id, fr_row_version=None, expect=200):
    r = client.put(f"{API}/business-requirements/{br['br_id']}/function-requirements/"
                   f"{row['br_function_requirement_id']}/solution", headers=ed["h"],
                   json={"solution_id": solution_id,
                         "fr_row_version": fr_row_version if fr_row_version is not None else row["fr_row_version"]})
    assert r.status_code == expect, r.text
    return r.json()


def get_fr(client, ed, f):
    return client.get(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"]).json()


def set_components(client, world, project_id, codes):
    url = f"{API}/projects/{project_id}/components"
    prev = client.put(url, headers=world["admin"], json={"component_codes": codes})
    assert prev.status_code == 200, prev.text
    r = client.put(url, headers=world["admin"], json={"component_codes": codes,
                                                      "confirm_hash": prev.json()["confirm_hash"]})
    assert r.status_code == 200, r.text


# ---- link, note, unlink, relink -----------------------------------------------------------------

def test_link_returns_the_row_and_relink_keeps_one_id(client, ed, db):
    br, _, _, _ = two_brs(client, ed)
    f = fr(client, ed)
    assert f["warnings"] == ["no_br"] and f["br_count"] == 0
    row = lnk(client, ed, br, f, note="validation half")
    assert (row["fr_number"], row["coverage_note"], row["solution_id"], row["tag_answers_this_br"]) == \
        (f["fr_number"], "validation half", None, False)
    assert row["fr_row_version"] == f["row_version"] and row["warnings"] == []
    assert get_fr(client, ed, f)["br_count"] == 1
    lnk(client, ed, br, f, expect=409)
    gone = unlnk(client, ed, br, row)
    assert gone["warnings"] == [{"code": "no_br", "frs": [f["fr_number"]]}]
    assert rows(client, ed, br) == []
    again = lnk(client, ed, br, f, note="all of it")
    assert again["br_function_requirement_id"] == row["br_function_requirement_id"]       # S1-7
    assert again["coverage_note"] == "all of it"
    r = client.patch(f"{API}/business-requirements/{br['br_id']}/function-requirements/"
                     f"{again['br_function_requirement_id']}", headers=ed["h"],
                     json={"row_version": again["row_version"], "coverage_note": "the validation half"})
    assert r.status_code == 200 and r.json()["coverage_note"] == "the validation half"
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "RECORD_UPDATED",
                                             AuditEvent.target_table == "br_function_requirement")).one()
    assert ev.detail["previous_coverage_note"] == "all of it"
    stale = client.patch(f"{API}/business-requirements/{br['br_id']}/function-requirements/"
                         f"{again['br_function_requirement_id']}", headers=ed["h"],
                         json={"row_version": again["row_version"], "coverage_note": "x"})
    assert stale.status_code == 409
    assert unlnk(client, ed, br, again, expect=409)                    # stale row_version


def test_another_projects_fr_is_404_and_a_link_is_addressed_under_its_br(client, ed, world):
    br, other_br, _, _ = two_brs(client, ed)
    foreign = fr(client, ed, headers=world["admin"], project=world["p_fin"])
    r = client.post(f"{API}/business-requirements/{br['br_id']}/function-requirements", headers=ed["h"],
                    json={"fr_id": foreign["fr_id"]})
    missing = client.post(f"{API}/business-requirements/{br['br_id']}/function-requirements", headers=ed["h"],
                          json={"fr_id": 999999})
    assert r.status_code == missing.status_code == 404 and r.json() == missing.json()
    row = lnk(client, ed, br, fr(client, ed))
    r = client.delete(f"{API}/business-requirements/{other_br['br_id']}/function-requirements/"
                      f"{row['br_function_requirement_id']}", headers=ed["h"], params={"row_version": 1})
    assert r.status_code == 404


def test_who_may_link(client, ed):
    br, _, _, _ = two_brs(client, ed)
    f = fr(client, ed)
    lnk(client, ed, br, f, expect=403, headers=ed["rv"])
    lnk(client, ed, br, f, expect=404, headers=ed["out"])
    assert client.get(f"{API}/business-requirements/{br['br_id']}/function-requirements",
                      headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/business-requirements/{br['br_id']}/function-requirements",
                      headers=ed["rv"]).status_code == 200


def test_retired_ends_refuse_and_an_fr_with_links_cannot_be_retired(client, ed):
    br, _, _, _ = two_brs(client, ed)
    f = fr(client, ed)
    lnk(client, ed, br, f)
    cur = get_fr(client, ed, f)
    r = client.delete(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"],
                      params={"row_version": cur["row_version"]})
    assert r.status_code == 409 and br["br_number"] in r.json()["detail"]                 # Q-13, S10b-2
    other = fr(client, ed, name="Other form")
    cur = get_fr(client, ed, other)
    assert client.delete(f"{API}/function-requirements/{other['fr_id']}", headers=ed["h"],
                         params={"row_version": cur["row_version"]}).status_code == 204
    r = client.post(f"{API}/business-requirements/{br['br_id']}/function-requirements", headers=ed["h"],
                    json={"fr_id": other["fr_id"]})
    assert r.status_code == 409 and "retired" in r.json()["detail"]


# ---- the solution tag ---------------------------------------------------------------------------

def test_the_tag_from_a_br_row_must_be_that_brs_solution(client, ed, db):
    br, other_br, _, _ = two_brs(client, ed)
    s_mine, s_other = sol(client, ed, "Approval matrix"), sol(client, ed, "Credit check")
    assert link(client, ed, br["br_id"], s_mine["solution_id"]).status_code == 201
    assert link(client, ed, other_br["br_id"], s_other["solution_id"]).status_code == 201
    f = fr(client, ed)
    row = lnk(client, ed, br, f)
    r = client.put(f"{API}/business-requirements/{br['br_id']}/function-requirements/"
                   f"{row['br_function_requirement_id']}/solution", headers=ed["h"],
                   json={"solution_id": s_other["solution_id"], "fr_row_version": row["fr_row_version"]})
    assert r.status_code == 422
    assert r.json()["detail"] == (f"{s_other['solution_number']} does not answer {br['br_number']}. "
                                  "Add it to this requirement's solutions first.")
    assert get_fr(client, ed, f)["solution_id"] is None                                     # nothing written
    out = tag(client, ed, br, row, s_mine["solution_id"])
    assert out["solution_id"] == s_mine["solution_id"] and out["tag_answers_this_br"] is True
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "RECORD_UPDATED",
                                             AuditEvent.target_table == "function_requirement")).one()
    assert ev.detail["previous_solution_number"] is None
    tag(client, ed, br, row, None, fr_row_version=row["fr_row_version"], expect=409)        # stale FR version
    cleared = tag(client, ed, br, row, None, fr_row_version=out["fr_row_version"])
    assert cleared["solution_id"] is None


def test_the_register_tag_must_answer_at_least_one_br(client, ed):
    br, other_br, _, _ = two_brs(client, ed)
    s1, s2, s3 = (sol(client, ed, n) for n in ("Approval matrix", "Credit check", "Courier"))
    link(client, ed, br["br_id"], s1["solution_id"])
    link(client, ed, other_br["br_id"], s2["solution_id"])
    f = fr(client, ed)
    lnk(client, ed, br, f)
    lnk(client, ed, other_br, f)
    cur = get_fr(client, ed, f)
    r = client.patch(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"],
                     json={"row_version": cur["row_version"], "solution_id": s3["solution_id"]})
    assert r.status_code == 422 and s3["solution_number"] in r.json()["detail"]
    r = client.patch(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"],
                     json={"row_version": cur["row_version"], "solution_id": s2["solution_id"]})
    assert r.status_code == 200 and r.json()["br_count"] == 2
    loose = fr(client, ed, name="Loose form", solution_id=s3["solution_id"])          # no BR: any solution
    assert "no_br" in loose["warnings"]


def test_solution_off_maps_but_cannot_tag(client, ed, world):
    br, _, _, _ = two_brs(client, ed)
    f = fr(client, ed)
    set_components(client, world, ed["p"], ["FUNCTION_REQUIREMENT", "TO_BE_DFD"])
    row = lnk(client, ed, br, f)
    r = client.put(f"{API}/business-requirements/{br['br_id']}/function-requirements/"
                   f"{row['br_function_requirement_id']}/solution", headers=ed["h"],
                   json={"solution_id": 1, "fr_row_version": row["fr_row_version"]})
    assert r.status_code == 409 and r.headers.get("X-VB-Error") == "COMPONENT_OFF"
    assert tag(client, ed, br, row, None)["solution_id"] is None                            # clearing needs FR only


# ---- drift: warn, never block, never clear -----------------------------------------------------

def test_drift_is_named_on_each_action_and_reported_as_a_warning_line(client, ed, db):
    br, other_br, _, _ = two_brs(client, ed)
    s = sol(client, ed)
    pairing = link(client, ed, br["br_id"], s["solution_id"]).json()
    f = fr(client, ed, solution_id=s["solution_id"])
    row = lnk(client, ed, br, f)
    assert row["warnings"] == [] and row["tag_answers_this_br"]
    # linking it to a BR the tag does not answer is allowed; it still answers BR-1, so no drift
    other = lnk(client, ed, other_br, f)
    assert other["tag_answers_this_br"] is False and other["warnings"] == []
    # unlinking the pairing leaves the tag answering none of its BRs: named, never cleared
    r = client.delete(f"{API}/business-requirements/{br['br_id']}/solutions/{pairing['br_solution_id']}",
                      headers=ed["h"], params={"row_version": pairing["row_version"]})
    assert r.status_code == 200 and r.json()["warnings"] == [
        {"code": "fr_solution_outside_its_brs", "frs": [f["fr_number"]]}]
    assert get_fr(client, ed, f)["solution_id"] == s["solution_id"]
    report = consistency.consistency_check(ed["p"], db)
    assert [x["fr_number"] for x in report["fr_solution_outside_its_brs"]] == [f["fr_number"]]
    assert report["brfr_under_inactive"] == []
    # unlinking the last answering link: same warning from the BR↔FR side
    link(client, ed, br["br_id"], s["solution_id"])
    assert unlnk(client, ed, br, rows(client, ed, br)[0])["warnings"] == [
        {"code": "fr_solution_outside_its_brs", "frs": [f["fr_number"]]}]


def test_a_freeze_with_a_drifted_tag_succeeds_and_records_which_rows(client, ed, db):
    from tests.test_baseline import freeze, scope
    w = scope(client, ed)
    s = sol(client, ed)
    pairing = link(client, ed, w["br1"]["br_id"], s["solution_id"]).json()
    f = fr(client, ed, solution_id=s["solution_id"])
    lnk(client, ed, w["br1"], f)
    client.delete(f"{API}/business-requirements/{w['br1']['br_id']}/solutions/{pairing['br_solution_id']}",
                  headers=ed["h"], params={"row_version": pairing["row_version"]})
    out = freeze(client, ed)                                                # DR10b-S3: a warning, not a refusal
    assert "fr_solution_outside_its_brs" in out["warnings"]
    assert out["counts"]["br_function_requirement"] == 1
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "BASELINE_FROZEN")).one()
    assert "fr_solution_outside_its_brs" in ev.detail["warnings"]
    assert ev.detail["warning_detail"]["fr_solution_outside_its_brs"] == {"count": 1, "numbers": [f["fr_number"]]}


def test_warning_detail_is_capped_and_carries_numbers_only():
    from services.baseline import WARNING_DETAIL_CAP, warning_detail
    lines = {"entities_without_fields": [{"data_entity_id": i, "de_number": f"DE-{i:04d}", "de_name": "Secret name"}
                                         for i in range(250)]}
    d = warning_detail(lines)["entities_without_fields"]
    assert d["count"] == 250 and len(d["numbers"]) == WARNING_DETAIL_CAP and d["numbers"][0] == "DE-0000"
    assert "Secret name" not in str(d)


# ---- create from the BR -----------------------------------------------------------------------

def test_create_with_br_id_links_in_one_step_and_applies_the_br_rule(client, ed, world):
    br, other_br, _, _ = two_brs(client, ed)
    s, s_other = sol(client, ed, "Approval matrix"), sol(client, ed, "Credit check")
    link(client, ed, br["br_id"], s["solution_id"])
    link(client, ed, other_br["br_id"], s_other["solution_id"])
    made = fr(client, ed, br_id=br["br_id"], solution_id=s["solution_id"])
    assert made["br_count"] == 1 and "no_br" not in made["warnings"]
    assert [r["fr_id"] for r in rows(client, ed, br)] == [made["fr_id"]]
    fr(client, ed, name="Wrong one", br_id=br["br_id"], solution_id=s_other["solution_id"], expect=422)
    other_project_br = client.get(f"{API}/projects/{world['p_fin']}/business-requirements",
                                  headers=world["admin"]).json()
    foreign = other_project_br[0]["br_id"] if other_project_br else 999999
    fr(client, ed, name="Foreign", br_id=foreign, expect=404)
    names = [x["fr_name"] for x in client.get(f"{API}/projects/{ed['p']}/function-requirements",
                                              headers=ed["h"]).json()]
    assert names == ["Order entry form"]                                     # nothing half-made


# ---- lists, effort -----------------------------------------------------------------------------

def test_register_filters_and_counts(client, ed):
    br, _, _, _ = two_brs(client, ed)
    s = sol(client, ed)
    traced = fr(client, ed, name="Traced")
    loose = fr(client, ed, name="Loose", solution_id=s["solution_id"])
    lnk(client, ed, br, traced)
    url = f"{API}/projects/{ed['p']}/function-requirements"
    assert [x["fr_name"] for x in client.get(url, headers=ed["h"], params={"unlinked": True}).json()] == ["Loose"]
    assert [x["fr_name"] for x in client.get(url, headers=ed["h"], params={"unassigned": True}).json()] == ["Traced"]
    counts = {x["fr_name"]: x["br_count"] for x in client.get(url, headers=ed["h"]).json()}
    assert counts == {"Traced": 1, "Loose": 0}
    brs = client.get(f"{API}/function-requirements/{traced['fr_id']}/business-requirements", headers=ed["h"]).json()
    assert [b["br_number"] for b in brs] == [br["br_number"]]
    assert loose


def test_effort_summary_untraced_line_is_information(client, ed):
    from tests.test_effort_api import rate
    br, _, _, _ = two_brs(client, ed)
    a, b = fr(client, ed, name="Traced"), fr(client, ed, name="Loose")
    for f in (a, b):
        assert rate(client, ed, f, "SIMPLE").status_code == 200
    lnk(client, ed, br, a)
    s = client.get(f"{API}/projects/{ed['p']}/effort-summary", headers=ed["h"]).json()
    assert s["untraced"]["count"] == 1
    assert float(s["total_days"]) == 2 * float(s["untraced"]["days"])        # in the total once, never added again


# ---- step retire / restore ----------------------------------------------------------------------

def test_a_step_retire_takes_the_links_and_restore_brings_them_back(client, ed, db):
    br, other_br, s1, _ = two_brs(client, ed)
    s = sol(client, ed)
    link(client, ed, br["br_id"], s["solution_id"])
    f = fr(client, ed, solution_id=s["solution_id"])
    lnk(client, ed, br, f)
    lnk(client, ed, other_br, f)
    p = preview(client, ed, s1["bfc_node_id"]).json()
    assert any(o["table"] == "br_function_requirement" and o["label"].startswith(f["fr_number"]) for o in p["owned"])
    assert p["tag_drift"] == [f["fr_number"]]
    assert retire(client, ed, s1["bfc_node_id"]).status_code == 204
    assert consistency.consistency_check(ed["p"], db)["brfr_under_inactive"] == []
    assert get_fr(client, ed, f)["br_count"] == 1
    assert restore(client, ed, s1["bfc_node_id"]).status_code == 200
    assert [r["fr_id"] for r in rows(client, ed, br)] == [f["fr_id"]]


def test_a_step_restore_refuses_while_a_linked_fr_is_retired(client, ed):
    """DR10b-P2: the links join the restore set before the parent check, so a retired FR blocks it."""
    br, _, s1, _ = two_brs(client, ed)
    f = fr(client, ed)
    lnk(client, ed, br, f)
    assert retire(client, ed, s1["bfc_node_id"]).status_code == 204
    cur = get_fr(client, ed, f)
    assert client.delete(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"],
                         params={"row_version": cur["row_version"]}).status_code == 204
    r = restore(client, ed, s1["bfc_node_id"])
    assert r.status_code == 409 and f["fr_number"] in r.json()["detail"]


def test_a_backfilled_same_stamp_link_restores_and_is_checked_like_the_rest(client, ed, db):
    """§3.2 [Q-8], DR10b-P2: a retired link carrying the event's stamp but not listed in it (a pre-10b retire,
    as the 0051 backfill writes it) is restored with the step — and blocks it while its FR is retired."""
    from tests.test_baseline import owner_exec
    br, _, s1, _ = two_brs(client, ed)
    f = fr(client, ed)
    assert retire(client, ed, s1["bfc_node_id"]).status_code == 204
    owner_exec("INSERT INTO br_function_requirement (project_id, br_id, fr_id, created_by, is_active, deleted_at, "
               "deleted_by) SELECT project_id, br_id, :b, created_by, false, deleted_at, deleted_by "
               "FROM business_requirement WHERE br_id = " + str(br["br_id"]), b=f["fr_id"])
    cur = get_fr(client, ed, f)
    assert client.delete(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"],
                         params={"row_version": cur["row_version"]}).status_code == 204
    r = restore(client, ed, s1["bfc_node_id"])
    assert r.status_code == 409 and f["fr_number"] in r.json()["detail"]
    assert client.patch(f"{API}/function-requirements/{f['fr_id']}/restore", headers=ed["h"]).status_code == 200
    assert restore(client, ed, s1["bfc_node_id"]).status_code == 200
    assert [x["fr_id"] for x in rows(client, ed, br)] == [f["fr_id"]]
    n = db.execute(text("SELECT count(*) FROM br_function_requirement WHERE is_active")).scalar()
    assert n == 1
