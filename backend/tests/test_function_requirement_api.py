"""Function requirements, first cut (docs/slice6a_spec.md §8). Grade 2: a wrong FR or a wrong
Solution link puts a wrong vendor-scope line in front of a client, correctable once noticed.
The riskiest concern — an FR under another project's Solution, or under a retired one — is
proven directly, on create and on PATCH.

Deliberately uncovered (spec §8): two editors relinking one FR at the same instant (row_version
decides), and phone width."""
from sqlalchemy import select, text

from models import AuditEvent
from services import consistency
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol, two_brs


def fr(client, ed, name="Order entry form", fr_type="FORM", solution_id=None, headers=None, project=None,
       expect=201, **kw):
    r = client.post(f"{API}/projects/{project or ed['p']}/function-requirements", headers=headers or ed["h"],
                    json={"fr_name": name, "fr_type_code": fr_type, "solution_id": solution_id, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def patch(client, ed, f, headers=None, **body):
    return client.patch(f"{API}/function-requirements/{f['fr_id']}", headers=headers or ed["h"],
                        json={"row_version": f["row_version"], **body})


def retire_solution(client, ed, s, headers=None):
    cur = client.get(f"{API}/solutions/{s['solution_id']}", headers=headers or ed["h"]).json()
    return client.delete(f"{API}/solutions/{s['solution_id']}", headers=headers or ed["h"],
                         params={"row_version": cur["row_version"]})


# ---- create -------------------------------------------------------------------------------

def test_create_mints_numbers_copies_behaviour_and_starts_specified(client, ed):
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    a = fr(client, ed, "Order entry form", "FORM", s["solution_id"])
    b = fr(client, ed, "Order feed to ERP", "INTERFACE", s["solution_id"])
    assert (a["fr_number"], b["fr_number"]) == ("FR-0001", "FR-0002")
    assert (b["fr_type_code"], b["fr_type_behaviour"]) == ("INTERFACE", "INTERFACE")
    assert a["fulfilment_status_code"] == "SPECIFIED" and a["warnings"] == ["no_br"]     # D-52: untraced
    assert (a["complexity_code"], a["effort_days"]) == (None, None)        # S6a-3


def test_unlinked_fr_saves_with_a_warning_and_shows_in_the_unlinked_filter(client, ed):
    """Criterion 105 (first half), D-28 re-based by D-52 (slice10b Q-17): `unlinked` = no BR link (no_br);
    `unassigned` = no solution, which is information now."""
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    fr(client, ed, "Tagged", solution_id=s["solution_id"])
    loose = fr(client, ed, "Loose")
    assert loose["warnings"] == ["no_br"] and loose["solution_id"] is None
    url = f"{API}/projects/{ed['p']}/function-requirements"
    rows = client.get(url, headers=ed["rv"], params={"unlinked": True}).json()
    assert [r["fr_name"] for r in rows] == ["Tagged", "Loose"]          # by number
    rows = client.get(url, headers=ed["rv"], params={"unassigned": True}).json()
    assert [r["fr_name"] for r in rows] == ["Loose"]


def test_bad_type_is_refused(client, ed):
    """Criterion 9."""
    fr(client, ed, fr_type="NOT_A_TYPE", expect=400)


def test_derived_values_in_the_body_are_ignored(client, ed):
    f = fr(client, ed, fr_number="FR-9999", effort_days=12, complexity_code="COMPLEX",
           fr_type_behaviour="INTERFACE", fulfilment_status_code="BUILT")
    assert (f["fr_number"], f["effort_days"], f["complexity_code"], f["fr_type_behaviour"],
            f["fulfilment_status_code"]) == ("FR-0001", None, None, "FORM", "SPECIFIED")


def test_a_forged_behaviour_copy_is_refused_by_the_database(client, ed, db):
    """D-27: the 3-column FK proves the copy matches the type."""
    f = fr(client, ed)
    try:
        db.execute(text("UPDATE function_requirement SET fr_type_behaviour = 'INTERFACE' WHERE fr_id = :i"),
                   {"i": f["fr_id"]})
        db.commit()
        raise AssertionError("a forged behaviour copy was stored")
    except Exception as e:                                   # noqa: BLE001 — the FK must refuse
        db.rollback()
        assert "fk_fr_type_code" in str(e)


def test_warnings_for_non_technology_rejected_and_duplicate(client, ed):
    people = sol(client, ed, "Approval matrix", "PEOPLE")
    assert "non_technology_solution" in fr(client, ed, "Approve form", solution_id=people["solution_id"])["warnings"]
    again = fr(client, ed, " approve FORM ", solution_id=people["solution_id"])
    assert "duplicate_name" in again["warnings"]                            # DR6a-P2, S6a-2
    tech = sol(client, ed, "Portal", "TECHNOLOGY")
    client.patch(f"{API}/solutions/{tech['solution_id']}", headers=ed["h"],
                 json={"row_version": tech["row_version"], "status_code": "REJECTED"})
    assert fr(client, ed, "Search", solution_id=tech["solution_id"])["warnings"] == ["no_br", "rejected_solution"]
    # the same name under a different solution is not a duplicate
    assert "duplicate_name" not in fr(client, ed, "Approve form", solution_id=tech["solution_id"])["warnings"]


# ---- the solution link: scope and liveness ------------------------------------------------

def test_another_projects_solution_is_404_on_create_and_patch_and_nothing_leaks(client, ed, world):
    """DR6a-S1: live or retired, a foreign solution answers exactly like a missing id."""
    admin = world["admin"]
    live = sol(client, ed, "Beta secret plan", "TECHNOLOGY", headers=admin, project=world["p_beta"])
    gone = sol(client, ed, "Beta retired plan", "DATA", headers=admin, project=world["p_beta"])
    assert retire_solution(client, ed, gone, headers=admin).status_code == 204
    missing = fr(client, ed, solution_id=10 ** 9, expect=404)
    mine = fr(client, ed, "Mine")
    for foreign in (live, gone):
        r = client.post(f"{API}/projects/{ed['p']}/function-requirements", headers=ed["h"],
                        json={"fr_name": "X", "fr_type_code": "FORM", "solution_id": foreign["solution_id"]})
        assert r.status_code == 404 and r.json() == missing
        p = patch(client, ed, mine, solution_id=foreign["solution_id"])
        assert p.status_code == 404 and p.json() == missing
        assert "Beta" not in r.text + p.text


def test_a_retired_solution_in_the_same_project_is_refused_on_create_and_patch(client, ed):
    """DR6a-D1."""
    s = sol(client, ed, "Old portal", "TECHNOLOGY")
    assert retire_solution(client, ed, s).status_code == 204
    r = client.post(f"{API}/projects/{ed['p']}/function-requirements", headers=ed["h"],
                    json={"fr_name": "X", "fr_type_code": "FORM", "solution_id": s["solution_id"]})
    assert r.status_code == 409 and "Restore it first" in r.json()["detail"]
    f = fr(client, ed)
    assert patch(client, ed, f, solution_id=s["solution_id"]).status_code == 409


def test_fr_under_inactive_solution_finds_a_planted_orphan(client, ed, db):
    s = sol(client, ed, "Portal", "TECHNOLOGY")
    f = fr(client, ed, solution_id=s["solution_id"])
    assert consistency.consistency_check(ed["p"], db)["fr_under_inactive_solution"] == []
    db.execute(text("UPDATE solution SET is_active = false WHERE solution_id = :i"), {"i": s["solution_id"]})
    db.commit()
    found = consistency.consistency_check(ed["p"], db)["fr_under_inactive_solution"]
    assert [(x["fr_number"], x["solution_number"]) for x in found] == [(f["fr_number"], "SOL-0001")]


# ---- update -------------------------------------------------------------------------------

def test_patch_edits_retypes_moves_unlinks_and_audits_the_move(client, ed, db):
    a = sol(client, ed, "Portal", "TECHNOLOGY")
    b = sol(client, ed, "Data hub", "DATA")
    f = fr(client, ed, solution_id=a["solution_id"])
    r = patch(client, ed, f, fr_name="Order capture form", fr_type_code="REPORT",
              fulfilment_status_code="ACCEPTED_BY_VENDOR", solution_id=b["solution_id"])
    assert r.status_code == 200, r.text
    g = r.json()
    assert (g["fr_name"], g["fr_type_behaviour"], g["fulfilment_status_code"], g["solution_id"]) == \
        ("Order capture form", "REPORT", "ACCEPTED_BY_VENDOR", b["solution_id"])
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "RECORD_UPDATED",
                                             AuditEvent.target_table == "function_requirement")).one()
    assert (ev.detail["previous_solution_number"], ev.detail["previous_fr_type_code"]) == ("SOL-0001", "FORM")
    u = patch(client, ed, g, solution_id=None)
    assert u.status_code == 200 and u.json()["solution_id"] is None and u.json()["warnings"] == ["no_br"]
    assert patch(client, ed, f, description="stale").status_code == 409     # old row_version


def test_patch_never_moves_derived_or_tenancy_columns(client, ed, world):
    f = fr(client, ed)
    r = patch(client, ed, f, project_id=world["p_beta"], fr_number="FR-0099", effort_days=5,
              complexity_code="COMPLEX", fr_type_behaviour="INTERFACE", description="d")
    assert r.status_code == 200, r.text
    g = r.json()
    assert (g["project_id"], g["fr_number"], g["effort_days"], g["complexity_code"], g["fr_type_behaviour"]) == \
        (ed["p"], "FR-0001", None, None, "FORM")


def test_reviewer_is_refused_and_outsider_sees_nothing(client, ed):
    f = fr(client, ed)
    fr(client, ed, headers=ed["rv"], expect=403)
    assert patch(client, ed, f, headers=ed["rv"], description="x").status_code == 403
    assert client.get(f"{API}/function-requirements/{f['fr_id']}", headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/projects/{ed['p']}/function-requirements", headers=ed["out"]).status_code == 404


# ---- retire, restore, and the derived BR → FR ---------------------------------------------

def test_a_solution_with_live_frs_cannot_be_retired_and_the_refusal_names_them(client, ed):
    """Acceptance 5."""
    s = sol(client, ed, "Portal", "TECHNOLOGY")
    f = fr(client, ed, "Order entry form", solution_id=s["solution_id"])
    r = retire_solution(client, ed, s)
    assert r.status_code == 409 and f["fr_number"] in r.json()["detail"]


def test_an_fr_cannot_be_restored_under_a_retired_solution(client, ed):
    s = sol(client, ed, "Portal", "TECHNOLOGY")
    f = fr(client, ed, solution_id=s["solution_id"])
    assert client.delete(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"],
                         params={"row_version": f["row_version"]}).status_code == 204
    assert retire_solution(client, ed, s).status_code == 204
    r = client.patch(f"{API}/function-requirements/{f['fr_id']}/restore", headers=ed["h"])
    assert r.status_code == 409 and "SOL-0001" in r.json()["detail"]


def test_a_solution_path_alone_is_no_longer_a_mapping(client, ed, db):
    """Criterion 10a superseded by D-52 (slice10b Q-16): BR → FR is the stored link; a BR_SOLUTION → SOL → FR
    path with no link maps nothing, and the view reads the links only."""
    br1, br2, a = two_brs(client, ed)
    s = sol(client, ed, "Portal", "TECHNOLOGY")
    for b in (br1, br2):
        assert link(client, ed, b["br_id"], s["solution_id"]).status_code == 201
    f1 = fr(client, ed, "Order entry form", solution_id=s["solution_id"])
    fr(client, ed, "Order feed", "INTERFACE", solution_id=s["solution_id"])
    n = db.scalar(text("SELECT count(*) FROM v_br_function_requirement WHERE project_id = :p"), {"p": ed["p"]})
    assert n == 0
    url = f"{API}/business-requirements/{br1['br_id']}/function-requirements"
    assert client.post(url, headers=ed["h"], json={"fr_id": f1["fr_id"]}).status_code == 201
    rows = client.get(url, headers=ed["rv"]).json()
    assert [(r["fr_number"], r["solution_number"], r["tag_answers_this_br"]) for r in rows] == \
        [("FR-0001", "SOL-0001", True)]
    under = client.get(f"{API}/solutions/{s['solution_id']}/function-requirements", headers=ed["rv"]).json()
    assert [r["fr_number"] for r in under] == ["FR-0001", "FR-0002"]     # the solution side is unchanged


def test_the_link_stays_when_the_brs_solution_goes(client, ed):
    """D-52 (slice10b §2.2): unlinking the BR_SOLUTION no longer drops the FR from the BR; the tag stays and
    the response names the FR whose tag now answers none of its BRs."""
    br1, _, _ = two_brs(client, ed)
    s = sol(client, ed, "Portal", "TECHNOLOGY")
    row = link(client, ed, br1["br_id"], s["solution_id"]).json()
    f = fr(client, ed, solution_id=s["solution_id"])
    url = f"{API}/business-requirements/{br1['br_id']}/function-requirements"
    assert client.post(url, headers=ed["h"], json={"fr_id": f["fr_id"]}).status_code == 201
    r = client.delete(f"{API}/business-requirements/{br1['br_id']}/solutions/{row['br_solution_id']}",
                      headers=ed["h"], params={"row_version": row["row_version"]})
    assert r.json()["warnings"] == [{"code": "fr_solution_outside_its_brs", "frs": [f["fr_number"]]}]
    rows = client.get(url, headers=ed["h"]).json()
    assert [(r["fr_id"], r["solution_id"], r["tag_answers_this_br"]) for r in rows] == \
        [(f["fr_id"], s["solution_id"], False)]


def test_the_view_is_read_only_to_the_app(db):
    """0024 revokes the INSERT/UPDATE that 0001's default privileges grant on every new relation."""
    can = db.execute(text("SELECT has_table_privilege('v_br_function_requirement', 'SELECT'), "
                          "has_table_privilege('v_br_function_requirement', 'INSERT'), "
                          "has_table_privilege('v_br_function_requirement', 'UPDATE')")).one()
    assert tuple(can) == (True, False, False)
