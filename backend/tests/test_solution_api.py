"""Solutions and BR → Solution links (docs/slice5_spec.md §8). Grade 2: a wrong link misstates
traceability to a client and is correctable once noticed. The riskiest concern — a link across
projects, or by someone who may only read — is proven directly here.

Deliberately uncovered (spec §8): two users linking the same pair at the same instant (the full
UK decides), and layout below tablet width."""
from sqlalchemy import select, text

from models import AuditEvent
from services import consistency
from tests.test_scope_api import API, ed, step  # noqa: F401 — ed is a fixture
from tests.test_step_retire import _br, restore, retire


def sol(client, ed, name="Approval matrix", category="PEOPLE", headers=None, project=None, expect=201, **kw):
    r = client.post(f"{API}/projects/{project or ed['p']}/solutions", headers=headers or ed["h"],
                    json={"solution_name": name, "category_code": category, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def link(client, ed, br_id, solution_id, note=None, headers=None):
    return client.post(f"{API}/business-requirements/{br_id}/solutions", headers=headers or ed["h"],
                       json={"solution_id": solution_id, "coverage_note": note})


def links(client, ed, br_id):
    return client.get(f"{API}/business-requirements/{br_id}/solutions", headers=ed["h"]).json()


def two_brs(client, ed):
    a = step(client, ed, "Take order")
    b = client.post(f"{API}/projects/{ed['p']}/bfc-nodes", headers=ed["h"], json={
        "node_name": "Approve order", "parent_bfc_node_id": a["parent_bfc_node_id"], "is_process": True}).json()
    return _br(client, ed, a["bfc_node_id"]), _br(client, ed, b["bfc_node_id"]), a


# ---- the register -------------------------------------------------------------------------

def test_create_mints_numbers_defaults_proposed_and_lists_counts(client, ed):
    a = sol(client, ed, "Approval matrix", "PEOPLE", description="Who signs what")
    b = sol(client, ed, "Order portal", "TECHNOLOGY")
    assert (a["solution_number"], b["solution_number"]) == ("SOL-0001", "SOL-0002")
    assert a["status_code"] == "PROPOSED" and a["category_code"] == "PEOPLE"
    assert a["description"] == "Who signs what"
    rows = client.get(f"{API}/projects/{ed['p']}/solutions", headers=ed["rv"]).json()
    assert [(r["solution_number"], r["live_br_count"]) for r in rows] == [("SOL-0001", 0), ("SOL-0002", 0)]


def test_category_must_resolve_and_status_cannot_be_sent_on_create(client, ed):
    sol(client, ed, category="NOT_A_CATEGORY", expect=400)      # the house code-validation status
    s = sol(client, ed, status_code="DELIVERED", solution_number="SOL-9999")   # ignored: derived (law 6)
    assert (s["status_code"], s["solution_number"]) == ("PROPOSED", "SOL-0001")


def test_live_name_is_unique_and_names_the_clash(client, ed):
    sol(client, ed, "Approval matrix")
    r = client.post(f"{API}/projects/{ed['p']}/solutions", headers=ed["h"],
                    json={"solution_name": "  approval MATRIX ", "category_code": "PROCESS"})
    assert r.status_code == 409 and "SOL-0001" in r.json()["detail"]


def test_blank_name_is_422(client, ed):
    sol(client, ed, "   ", expect=422)


def test_patch_changes_allowed_fields_and_refuses_stale(client, ed):
    s = sol(client, ed)
    r = client.patch(f"{API}/solutions/{s['solution_id']}", headers=ed["h"], json={
        "row_version": s["row_version"], "status_code": "AGREED", "category_code": "PROCESS",
        "benefit_note": "Fewer escalations"})
    assert r.status_code == 200, r.text
    assert (r.json()["status_code"], r.json()["category_code"], r.json()["benefit_note"]) == \
        ("AGREED", "PROCESS", "Fewer escalations")
    stale = client.patch(f"{API}/solutions/{s['solution_id']}", headers=ed["h"],
                         json={"row_version": s["row_version"], "solution_name": "X"})
    assert stale.status_code == 409


def test_patch_never_moves_derived_or_tenancy_columns(client, ed, world):
    """DR1-S2: project_id, the number, created_by and row_version are not request fields."""
    s = sol(client, ed)
    r = client.patch(f"{API}/solutions/{s['solution_id']}", headers=ed["h"], json={
        "row_version": s["row_version"], "project_id": world["p_beta"], "solution_number": "SOL-0099",
        "created_by": 1, "description": "d"})
    assert r.status_code == 200, r.text
    after = r.json()
    assert (after["project_id"], after["solution_number"], after["row_version"]) == \
        (ed["p"], "SOL-0001", s["row_version"] + 1)


def test_reviewer_is_refused_and_outsider_sees_nothing(client, ed):
    s = sol(client, ed)
    assert client.post(f"{API}/projects/{ed['p']}/solutions", headers=ed["rv"],
                       json={"solution_name": "X", "category_code": "DATA"}).status_code == 403
    assert client.patch(f"{API}/solutions/{s['solution_id']}", headers=ed["rv"],
                        json={"row_version": 1, "description": "x"}).status_code == 403
    assert client.get(f"{API}/solutions/{s['solution_id']}", headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/projects/{ed['p']}/solutions", headers=ed["out"]).status_code == 404


# ---- links --------------------------------------------------------------------------------

def test_a_people_solution_answers_two_brs_from_both_sides(client, ed):
    """Acceptance 1 and 3 (criterion 10, first half)."""
    br1, br2, _ = two_brs(client, ed)
    s = sol(client, ed, "Approval matrix", "PEOPLE")
    r = link(client, ed, br1["br_id"], s["solution_id"], "Approval half only")
    assert r.status_code == 201, r.text
    assert (r.json()["solution_number"], r.json()["coverage_note"], r.json()["status_code"]) == \
        ("SOL-0001", "Approval half only", "PROPOSED")
    assert link(client, ed, br2["br_id"], s["solution_id"]).status_code == 201
    from_sol = client.get(f"{API}/solutions/{s['solution_id']}/business-requirements", headers=ed["rv"]).json()
    assert [x["br_number"] for x in from_sol] == [br1["br_number"], br2["br_number"]]
    assert from_sol[0]["node_name"] == "Take order"
    assert [x["solution_number"] for x in links(client, ed, br1["br_id"])] == ["SOL-0001"]
    listed = client.get(f"{API}/projects/{ed['p']}/solutions", headers=ed["h"]).json()
    assert listed[0]["live_br_count"] == 2


def test_duplicate_live_link_is_409(client, ed):
    br1, _, _ = two_brs(client, ed)
    s = sol(client, ed)
    assert link(client, ed, br1["br_id"], s["solution_id"]).status_code == 201
    r = link(client, ed, br1["br_id"], s["solution_id"])
    assert r.status_code == 409 and "already linked" in r.json()["detail"]


def test_unlink_then_relink_restores_the_same_row_and_keeps_the_old_note(client, ed, db):
    br1, _, _ = two_brs(client, ed)
    s = sol(client, ed)
    first = link(client, ed, br1["br_id"], s["solution_id"], "old statement").json()
    r = client.delete(f"{API}/business-requirements/{br1['br_id']}/solutions/{first['br_solution_id']}",
                      headers=ed["h"], params={"row_version": first["row_version"]})
    assert r.status_code == 204
    assert links(client, ed, br1["br_id"]) == []
    again = link(client, ed, br1["br_id"], s["solution_id"], "new statement").json()
    assert again["br_solution_id"] == first["br_solution_id"]
    assert again["coverage_note"] == "new statement"
    ev = db.scalars(select(AuditEvent).where(AuditEvent.target_table == "br_solution",
                                             AuditEvent.event_type == "RECORD_RESTORED")).one()
    assert ev.detail["previous_coverage_note"] == "old statement"            # DR1-D2


def test_note_is_edited_in_place_with_the_old_one_audited(client, ed, db):
    """S5-3."""
    br1, _, _ = two_brs(client, ed)
    s = sol(client, ed)
    row = link(client, ed, br1["br_id"], s["solution_id"], "first").json()
    url = f"{API}/business-requirements/{br1['br_id']}/solutions/{row['br_solution_id']}"
    r = client.patch(url, headers=ed["h"], json={"row_version": row["row_version"], "coverage_note": "second"})
    assert r.status_code == 200, r.text
    assert r.json()["coverage_note"] == "second"
    assert client.patch(url, headers=ed["h"], json={"row_version": row["row_version"],
                                                    "coverage_note": "third"}).status_code == 409
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "RECORD_UPDATED",
                                             AuditEvent.target_table == "br_solution")).one()
    assert ev.detail["previous_coverage_note"] == "first"
    assert client.patch(url, headers=ed["rv"], json={"row_version": r.json()["row_version"],
                                                     "coverage_note": "x"}).status_code == 403


def test_a_link_cannot_be_addressed_under_another_br(client, ed):
    br1, br2, _ = two_brs(client, ed)
    s = sol(client, ed)
    row = link(client, ed, br1["br_id"], s["solution_id"]).json()
    r = client.delete(f"{API}/business-requirements/{br2['br_id']}/solutions/{row['br_solution_id']}",
                      headers=ed["h"], params={"row_version": row["row_version"]})
    assert r.status_code == 404


def test_reviewer_cannot_link(client, ed):
    br1, _, _ = two_brs(client, ed)
    s = sol(client, ed)
    assert link(client, ed, br1["br_id"], s["solution_id"], headers=ed["rv"]).status_code == 403


def test_another_projects_solution_is_404_and_nothing_of_it_leaks(client, ed, world):
    """DR1-S1: live or retired, a solution in another project answers exactly like a missing one."""
    br1, _, _ = two_brs(client, ed)
    admin = world["admin"]
    live = sol(client, ed, "Beta secret plan", "TECHNOLOGY", headers=admin, project=world["p_beta"])
    gone = sol(client, ed, "Beta retired plan", "DATA", headers=admin, project=world["p_beta"])
    assert client.delete(f"{API}/solutions/{gone['solution_id']}", headers=admin,
                         params={"row_version": gone["row_version"]}).status_code == 204
    for foreign in (live, gone):
        r = link(client, ed, br1["br_id"], foreign["solution_id"])
        assert r.status_code == 404, r.text
        assert "Beta" not in r.text and foreign["solution_number"] not in r.text
    assert link(client, ed, br1["br_id"], 10 ** 9).json() == r.json()        # same as a missing id


def test_linking_a_retired_solution_is_refused(client, ed):
    br1, _, _ = two_brs(client, ed)
    s = sol(client, ed)
    client.delete(f"{API}/solutions/{s['solution_id']}", headers=ed["h"], params={"row_version": s["row_version"]})
    r = link(client, ed, br1["br_id"], s["solution_id"])
    assert r.status_code == 409 and "Restore it first" in r.json()["detail"]


def test_a_rejected_solution_can_be_linked_and_shows_its_status(client, ed):
    """S5-2: allowed; the link carries the status so the screen can flag it."""
    br1, _, _ = two_brs(client, ed)
    s = sol(client, ed)
    client.patch(f"{API}/solutions/{s['solution_id']}", headers=ed["h"],
                 json={"row_version": s["row_version"], "status_code": "REJECTED"})
    r = link(client, ed, br1["br_id"], s["solution_id"])
    assert r.status_code == 201 and r.json()["status_code"] == "REJECTED"


# ---- retire and restore -------------------------------------------------------------------

def test_retiring_a_linked_solution_is_refused_naming_the_brs(client, ed):
    """Acceptance 5, DR1-P1: the 409 names the BRs, not the solution three times."""
    br1, br2, _ = two_brs(client, ed)
    s = sol(client, ed)
    link(client, ed, br1["br_id"], s["solution_id"])
    link(client, ed, br2["br_id"], s["solution_id"])
    r = client.delete(f"{API}/solutions/{s['solution_id']}", headers=ed["h"], params={"row_version": s["row_version"]})
    assert r.status_code == 409
    assert br1["br_number"] in r.json()["detail"] and br2["br_number"] in r.json()["detail"]


def test_retire_and_restore_a_solution(client, ed):
    s = sol(client, ed)
    assert client.delete(f"{API}/solutions/{s['solution_id']}", headers=ed["h"],
                         params={"row_version": s["row_version"]}).status_code == 204
    assert client.get(f"{API}/projects/{ed['p']}/solutions", headers=ed["h"]).json() == []
    r = client.patch(f"{API}/solutions/{s['solution_id']}/restore", headers=ed["h"])
    assert r.status_code == 200 and r.json()["is_active"] is True


def test_restore_is_refused_when_the_name_was_taken_meanwhile(client, ed):
    s = sol(client, ed, "Approval matrix")
    client.delete(f"{API}/solutions/{s['solution_id']}", headers=ed["h"], params={"row_version": s["row_version"]})
    sol(client, ed, "Approval matrix")
    r = client.patch(f"{API}/solutions/{s['solution_id']}/restore", headers=ed["h"])
    assert r.status_code == 409 and "SOL-0002" in r.json()["detail"]


def test_step_retire_takes_the_links_and_restore_brings_them_back(client, ed):
    """S5-1: the pairing is owned by the BR and shown in the step's retire preview."""
    br1, _, a = two_brs(client, ed)
    s = sol(client, ed, "Approval matrix")
    link(client, ed, br1["br_id"], s["solution_id"], "kept")
    pv = client.get(f"{API}/bfc-nodes/{a['bfc_node_id']}/retire-preview", headers=ed["h"]).json()
    assert "SOL-0001 Approval matrix" in str(pv)
    assert retire(client, ed, a["bfc_node_id"]).status_code == 204
    assert client.get(f"{API}/solutions/{s['solution_id']}/business-requirements", headers=ed["h"]).json() == []
    assert client.get(f"{API}/solutions/{s['solution_id']}", headers=ed["h"]).json()["is_active"] is True
    assert restore(client, ed, a["bfc_node_id"]).status_code == 200
    back = links(client, ed, br1["br_id"])
    assert [(x["solution_number"], x["coverage_note"]) for x in back] == [("SOL-0001", "kept")]


def test_step_restore_is_refused_while_its_linked_solution_is_retired(client, ed):
    """DR1-P3 / A-SR-5: all-or-nothing, and the message names the solution."""
    br1, _, a = two_brs(client, ed)
    s = sol(client, ed)
    link(client, ed, br1["br_id"], s["solution_id"])
    assert retire(client, ed, a["bfc_node_id"]).status_code == 204
    assert client.delete(f"{API}/solutions/{s['solution_id']}", headers=ed["h"],
                         params={"row_version": s["row_version"]}).status_code == 204
    r = restore(client, ed, a["bfc_node_id"])
    assert r.status_code == 409 and "SOL-0001" in r.json()["detail"]


# ---- consistency_check --------------------------------------------------------------------

def test_brsol_under_inactive_finds_a_planted_orphan(client, ed, db):
    br1, _, _ = two_brs(client, ed)
    s = sol(client, ed)
    link(client, ed, br1["br_id"], s["solution_id"])
    assert consistency.consistency_check(ed["p"], db)["brsol_under_inactive"] == []
    db.execute(text("UPDATE solution SET is_active = false WHERE solution_id = :i"), {"i": s["solution_id"]})
    db.commit()
    found = consistency.consistency_check(ed["p"], db)["brsol_under_inactive"]
    assert [(f["br_number"], f["solution_number"]) for f in found] == [(br1["br_number"], "SOL-0001")]
