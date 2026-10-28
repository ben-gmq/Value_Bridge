"""Applications: catalogue, to-be allocation, as-is support (docs/slice6b1_spec.md §8). Grade 2: a
wrong allocation or as-is link misstates the landscape and the migration backlog in a client
deliverable. The riskiest concerns — a link across projects or onto a retired end, and the AS_IS rule
slipping between its two write paths — are proven directly. Since slice 7c (Q-23, D-47) as-is support
sits on as-is process steps only: a to-be step's systems come from its requirement's solutions.

Deliberately uncovered (spec §8): a lifecycle change racing an allocation for real (the lock order is
reasoned; `as_is_allocated` is the proof), and phone width."""
from sqlalchemy import select, text

from models import AuditEvent
from services import consistency
from tests.test_dfd_api import as_is_root
from tests.test_scope_api import API, ed, node  # noqa: F401 — ed is a fixture
from tests.test_solution_api import sol, two_brs
from tests.test_step_retire import restore, retire


def as_is_steps(client, ed):
    """Two process steps of the as-is chart (D-47): the root names the chart, children take it."""
    desk = node(client, ed, "Order desk", as_is_root(client, ed)["bfc_node_id"])
    a = node(client, ed, "Key in order", desk["bfc_node_id"], is_process=True)
    b = node(client, ed, "Print order", desk["bfc_node_id"], is_process=True)
    assert (a["bfc_set_code"], b["bfc_set_code"]) == ("AS_IS", "AS_IS")
    return a, b


def app(client, ed, code="SAP-ECC", name="SAP ECC", lifecycle="BOTH", headers=None, project=None, expect=201, **kw):
    r = client.post(f"{API}/projects/{project or ed['p']}/applications", headers=headers or ed["h"],
                    json={"application_code": code, "application_name": name, "lifecycle_code": lifecycle, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def patch(client, ed, a, headers=None, **body):
    cur = client.get(f"{API}/applications/{a['application_id']}", headers=ed["h"]).json()
    return client.patch(f"{API}/applications/{a['application_id']}", headers=headers or ed["h"],
                        json={"row_version": cur["row_version"], **body})


def allocate(client, ed, s, a, note=None, headers=None):
    return client.post(f"{API}/solutions/{s['solution_id']}/applications", headers=headers or ed["h"],
                       json={"application_id": a["application_id"], "note": note})


def support(client, ed, node_id, a, note=None, headers=None):
    return client.post(f"{API}/bfc-nodes/{node_id}/applications", headers=headers or ed["h"],
                       json={"application_id": a["application_id"], "note": note})


def retire_app(client, ed, a, headers=None):
    cur = client.get(f"{API}/applications/{a['application_id']}", headers=headers or ed["h"]).json()
    return client.delete(f"{API}/applications/{a['application_id']}", headers=headers or ed["h"],
                         params={"row_version": cur["row_version"]})


# ---- the catalogue ------------------------------------------------------------------------

def test_code_is_upper_cased_unique_and_charset_checked(client, ed):
    a = app(client, ed, code=" sap-ecc ", name="SAP ECC", kind_code="PACKAGE", vendor="SAP")
    assert (a["application_code"], a["lifecycle_code"], a["app_kind_code"], a["vendor"]) == \
        ("SAP-ECC", "BOTH", "PACKAGE", "SAP")
    r = client.post(f"{API}/projects/{ed['p']}/applications", headers=ed["h"],
                    json={"application_code": "SAP-ECC", "application_name": "Other", "lifecycle_code": "AS_IS"})
    assert r.status_code == 409 and "SAP ECC" in r.json()["detail"]
    app(client, ed, code="SAP ECC!", name="Bad", expect=422)
    app(client, ed, code="CRM", name="  sap ecc ", expect=409)                  # live name taken
    app(client, ed, code="X", name="No lifecycle", lifecycle="NOPE", expect=400)


def test_a_retired_code_is_never_reused(client, ed):
    a = app(client, ed)
    assert retire_app(client, ed, a).status_code == 204
    r = client.post(f"{API}/projects/{ed['p']}/applications", headers=ed["h"],
                    json={"application_code": "SAP-ECC", "application_name": "New", "lifecycle_code": "TO_BE"})
    assert r.status_code == 409 and "retired" in r.json()["detail"]


def test_kind_is_optional_and_can_be_cleared(client, ed):
    """DR6b-P3: absent = unchanged, explicit null = clear."""
    a = app(client, ed, kind_code="SAAS")
    assert patch(client, ed, a, vendor="v").json()["app_kind_code"] == "SAAS"
    assert patch(client, ed, a, kind_code=None).json()["app_kind_code"] is None


def test_code_and_lifecycle_changes_are_audited_with_the_previous_value(client, ed, db):
    """S6b-6, DR6b-D1."""
    a = app(client, ed, code="SAP-ECX")
    r = patch(client, ed, a, application_code="sap-ecc", lifecycle_code="AS_IS")
    assert r.status_code == 200 and r.json()["application_code"] == "SAP-ECC"
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "RECORD_UPDATED",
                                             AuditEvent.target_table == "application")).one()
    assert (ev.detail["previous_application_code"], ev.detail["previous_lifecycle_code"]) == ("SAP-ECX", "BOTH")


def test_patch_never_moves_tenancy(client, ed, world):
    a = app(client, ed)
    r = patch(client, ed, a, project_id=world["p_beta"], description="d")
    assert r.status_code == 200 and r.json()["project_id"] == ed["p"]


def test_restore_is_refused_when_the_name_was_taken_meanwhile(client, ed):
    """DR6b-D2."""
    a = app(client, ed, code="SAP-ECC", name="SAP ECC")
    retire_app(client, ed, a)
    app(client, ed, code="SAP-ECC6", name="SAP ECC")
    r = client.patch(f"{API}/applications/{a['application_id']}/restore", headers=ed["h"])
    assert r.status_code == 409 and "SAP-ECC6" in r.json()["detail"]


def test_reviewer_is_refused_and_outsider_sees_nothing(client, ed):
    a = app(client, ed)
    app(client, ed, code="Z", name="Z", headers=ed["rv"], expect=403)
    assert patch(client, ed, a, headers=ed["rv"], vendor="x").status_code == 403
    assert client.get(f"{API}/applications/{a['application_id']}", headers=ed["out"]).status_code == 404
    assert client.get(f"{API}/projects/{ed['p']}/applications", headers=ed["out"]).status_code == 404


# ---- to-be allocation (R2-D11, criterion 10c) ---------------------------------------------

def test_as_is_cannot_deliver_a_solution_and_both_can(client, ed):
    """Criterion 10c."""
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    old = app(client, ed, code="LEGACY", name="Legacy", lifecycle="AS_IS")
    both = app(client, ed, code="SAP-ECC", name="SAP ECC", lifecycle="BOTH")
    r = allocate(client, ed, s, old)
    assert r.status_code == 422 and "LEGACY" in r.json()["detail"]
    ok = allocate(client, ed, s, both, "Order capture only")
    assert ok.status_code == 201 and ok.json()["note"] == "Order capture only"
    assert allocate(client, ed, s, both).status_code == 409                     # duplicate
    listed = client.get(f"{API}/solutions/{s['solution_id']}/applications", headers=ed["rv"]).json()
    assert [x["application_code"] for x in listed] == ["SAP-ECC"]
    reg = client.get(f"{API}/projects/{ed['p']}/applications", headers=ed["h"]).json()
    assert {x["application_code"]: x["live_solution_count"] for x in reg} == {"LEGACY": 0, "SAP-ECC": 1}


def test_an_allocated_application_cannot_move_to_as_is(client, ed):
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    a = app(client, ed, lifecycle="TO_BE")
    allocate(client, ed, s, a)
    r = patch(client, ed, a, lifecycle_code="AS_IS")
    assert r.status_code == 409 and "SOL-0001" in r.json()["detail"]


def test_relinking_a_removed_pair_under_an_as_is_application_is_refused_and_stays_removed(client, ed, db):
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    a = app(client, ed, lifecycle="TO_BE")
    row = allocate(client, ed, s, a).json()
    client.delete(f"{API}/solutions/{s['solution_id']}/applications/{row['application_solution_id']}",
                  headers=ed["h"], params={"row_version": row["row_version"]})
    assert patch(client, ed, a, lifecycle_code="AS_IS").status_code == 200
    assert allocate(client, ed, s, a).status_code == 422
    assert db.scalar(text("SELECT is_active FROM application_solution WHERE application_solution_id = :i"),
                     {"i": row["application_solution_id"]}) is False


def test_allocation_note_is_edited_in_place_and_relink_restores_the_row(client, ed, db):
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    a = app(client, ed)
    row = allocate(client, ed, s, a, "first").json()
    url = f"{API}/solutions/{s['solution_id']}/applications/{row['application_solution_id']}"
    r = client.patch(url, headers=ed["h"], json={"row_version": row["row_version"], "note": "second"})
    assert r.status_code == 200 and r.json()["note"] == "second"
    client.delete(url, headers=ed["h"], params={"row_version": r.json()["row_version"]})
    again = allocate(client, ed, s, a, "third").json()
    assert again["application_solution_id"] == row["application_solution_id"]
    notes = [e.detail for e in db.scalars(select(AuditEvent).where(AuditEvent.target_table == "application_solution",
                                                                     AuditEvent.event_type.in_(["RECORD_UPDATED",
                                                                                                "RECORD_RESTORED"]))
                                                         .order_by(AuditEvent.audit_event_id))]
    assert {"previous_allocation_note": "first"}.items() <= notes[0].items()
    assert notes[1]["previous_allocation_note"] == "second"


def test_cross_project_and_retired_ends(client, ed, world):
    """Live or retired, another project's application answers like a missing one; a retired end is 409."""
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    admin = world["admin"]
    live = app(client, ed, code="BETA-CRM", name="Beta CRM", headers=admin, project=world["p_beta"])
    gone = app(client, ed, code="BETA-OLD", name="Beta Old", headers=admin, project=world["p_beta"])
    assert retire_app(client, ed, gone, headers=admin).status_code == 204
    missing = allocate(client, ed, s, {"application_id": 10 ** 9})
    assert missing.status_code == 404
    step_a, _ = as_is_steps(client, ed)
    for foreign in (live, gone):
        r = allocate(client, ed, s, foreign)
        p = support(client, ed, step_a["bfc_node_id"], foreign)
        assert (r.status_code, p.status_code) == (404, 404) and r.json() == missing.json() == p.json()
        assert "Beta" not in r.text + p.text
    mine = app(client, ed, code="OLD", name="Old", lifecycle="TO_BE")
    assert retire_app(client, ed, mine).status_code == 204
    assert allocate(client, ed, s, mine).status_code == 409
    assert support(client, ed, step_a["bfc_node_id"], mine).status_code == 409


# ---- as-is support on a step ---------------------------------------------------------------

def test_as_is_support_on_a_step_and_the_to_be_warning(client, ed):
    step_a, _ = as_is_steps(client, ed)
    legacy = app(client, ed, code="LEGACY", name="Legacy", lifecycle="AS_IS")
    future = app(client, ed, code="NEW-CRM", name="New CRM", lifecycle="TO_BE")
    r = support(client, ed, step_a["bfc_node_id"], legacy, "Order entry screens")
    assert r.status_code == 201 and r.json()["warnings"] == [] and r.json()["hier_code"] == step_a["hier_code"]
    w = support(client, ed, step_a["bfc_node_id"], future)
    assert w.status_code == 201 and w.json()["warnings"][0]["code"] == "to_be_as_is"           # S6b-4
    listed = client.get(f"{API}/bfc-nodes/{step_a['bfc_node_id']}/applications", headers=ed["rv"]).json()
    assert [x["application_code"] for x in listed] == ["LEGACY", "NEW-CRM"]


def test_a_to_be_step_takes_no_as_is_support_and_the_line_names_old_links(client, ed, db):
    """Q-23: refused on a to-be step (422); a link made before 7c, when there was one chart, is
    named by the INFORMATIONAL line as_is_support_on_to_be until it is moved and removed."""
    _, _, to_be = two_brs(client, ed)
    a = app(client, ed, code="LEGACY", name="Legacy", lifecycle="AS_IS")
    r = support(client, ed, to_be["bfc_node_id"], a)
    assert r.status_code == 422 and "as-is steps" in r.json()["detail"]
    assert consistency.consistency_check(ed["p"], db)["as_is_support_on_to_be"] == []
    db.execute(text("INSERT INTO application_bfc_node (project_id, application_id, bfc_node_id, created_by) "
                    "SELECT project_id, :a, bfc_node_id, created_by FROM bfc_node WHERE bfc_node_id = :n"),
               {"a": a["application_id"], "n": to_be["bfc_node_id"]})
    db.commit()                                                     # a pre-7c link
    out = consistency.consistency_check(ed["p"], db)["as_is_support_on_to_be"]
    assert [(x["application_code"], x["hier_code"]) for x in out] == [("LEGACY", to_be["hier_code"])]
    assert "as_is_support_on_to_be" in consistency.INFORMATIONAL
    as_is, _ = as_is_steps(client, ed)
    assert support(client, ed, as_is["bfc_node_id"], a).status_code == 201
    assert len(consistency.consistency_check(ed["p"], db)["as_is_support_on_to_be"]) == 1   # only the old one


def test_a_summary_node_cannot_carry_as_is_support(client, ed):
    step_a, _ = as_is_steps(client, ed)
    a = app(client, ed)
    assert support(client, ed, step_a["parent_bfc_node_id"], a).status_code == 422


def test_moving_to_to_be_with_as_is_links_warns_and_the_line_lists_them(client, ed, db):
    """S6b-5, DR6b-P1: never silent."""
    step_a, _ = as_is_steps(client, ed)
    a = app(client, ed, lifecycle="BOTH")
    support(client, ed, step_a["bfc_node_id"], a)
    assert consistency.consistency_check(ed["p"], db)["as_is_support_by_to_be"] == []
    r = patch(client, ed, a, lifecycle_code="TO_BE")
    assert r.status_code == 200
    assert r.json()["warnings"] == [{"code": "to_be_supports_steps", "items": [step_a["hier_code"]]}]
    assert len(consistency.consistency_check(ed["p"], db)["as_is_support_by_to_be"]) == 1
    assert "as_is_support_by_to_be" in consistency.INFORMATIONAL


def test_as_is_links_retire_and_restore_with_their_step(client, ed):
    """S6b-1: owned by the step, named in the preview."""
    step_a, _ = as_is_steps(client, ed)
    a = app(client, ed, code="LEGACY", name="Legacy", lifecycle="AS_IS")
    support(client, ed, step_a["bfc_node_id"], a, "kept")
    pv = client.get(f"{API}/bfc-nodes/{step_a['bfc_node_id']}/retire-preview", headers=ed["h"]).json()
    assert "LEGACY Legacy" in str(pv)
    assert retire(client, ed, step_a["bfc_node_id"]).status_code == 204
    assert client.get(f"{API}/applications/{a['application_id']}/bfc-nodes", headers=ed["h"]).json() == []
    assert restore(client, ed, step_a["bfc_node_id"]).status_code == 200
    back = client.get(f"{API}/applications/{a['application_id']}/bfc-nodes", headers=ed["h"]).json()
    assert [(x["hier_code"], x["note"]) for x in back] == [(step_a["hier_code"], "kept")]


def test_step_restore_is_refused_while_its_application_is_retired(client, ed):
    step_a, _ = as_is_steps(client, ed)
    a = app(client, ed, lifecycle="AS_IS")
    support(client, ed, step_a["bfc_node_id"], a)
    assert retire(client, ed, step_a["bfc_node_id"]).status_code == 204
    assert retire_app(client, ed, a).status_code == 204
    r = restore(client, ed, step_a["bfc_node_id"])
    assert r.status_code == 409 and "SAP-ECC" in r.json()["detail"]


def test_demotion_and_retire_blockers_name_the_links(client, ed):
    step_a, _ = as_is_steps(client, ed)
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    a = app(client, ed, lifecycle="BOTH")
    support(client, ed, step_a["bfc_node_id"], a)
    allocate(client, ed, s, a)
    r = retire_app(client, ed, a)
    assert r.status_code == 409 and "SAP-ECC ↔ SOL-0001" in r.json()["detail"] \
        and f"SAP-ECC ↔ {step_a['hier_code']}" in r.json()["detail"]
    cur = client.get(f"{API}/solutions/{s['solution_id']}", headers=ed["h"]).json()
    rs = client.delete(f"{API}/solutions/{s['solution_id']}", headers=ed["h"], params={"row_version": cur["row_version"]})
    assert rs.status_code == 409 and "SAP-ECC" in rs.json()["detail"]
    node = client.get(f"{API}/bfc-nodes/{step_a['bfc_node_id']}", headers=ed["h"]).json()
    d = client.patch(f"{API}/bfc-nodes/{step_a['bfc_node_id']}/process", headers=ed["h"],
                     json={"is_process": False, "row_version": node["row_version"]})
    assert d.status_code == 409 and "as-is applications" in d.json()["detail"]


# ---- consistency_check --------------------------------------------------------------------

def test_the_must_be_empty_lines_find_planted_orphans(client, ed, db):
    step_a, _ = as_is_steps(client, ed)
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    a = app(client, ed, lifecycle="TO_BE")
    allocate(client, ed, s, a)
    support(client, ed, step_a["bfc_node_id"], a)
    out = consistency.consistency_check(ed["p"], db)
    assert (out["appsol_under_inactive"], out["appnode_under_inactive"], out["as_is_allocated"]) == ([], [], [])
    db.execute(text("UPDATE application SET is_active = false, "
                    "lifecycle_code_id = (SELECT code_id FROM code_master WHERE category = 'APP_LIFECYCLE' "
                    "AND code = 'AS_IS' AND project_id IS NULL) WHERE application_id = :i"),
               {"i": a["application_id"]})
    db.commit()
    out = consistency.consistency_check(ed["p"], db)
    assert (len(out["appsol_under_inactive"]), len(out["appnode_under_inactive"]), len(out["as_is_allocated"])) == (1, 1, 1)


def test_link_ids_are_addressed_only_under_their_owner_and_reviewers_cannot_link(client, ed):
    """sara L3: child_of against the owner on every link route."""
    s1 = sol(client, ed, "Order portal", "TECHNOLOGY")
    s2 = sol(client, ed, "Billing hub", "DATA")
    a = app(client, ed)
    row = allocate(client, ed, s1, a, "kept").json()
    wrong = f"{API}/solutions/{s2['solution_id']}/applications/{row['application_solution_id']}"
    assert client.patch(wrong, headers=ed["h"], json={"row_version": row["row_version"], "note": "x"}).status_code == 404
    assert client.delete(wrong, headers=ed["h"], params={"row_version": row["row_version"]}).status_code == 404
    assert client.get(f"{API}/solutions/{s1['solution_id']}/applications", headers=ed["h"]).json()[0]["note"] == "kept"
    step_a, step_b = as_is_steps(client, ed)
    link = support(client, ed, step_a["bfc_node_id"], a).json()
    other = f"{API}/bfc-nodes/{step_b['bfc_node_id']}/applications/{link['application_bfc_node_id']}"
    assert client.delete(other, headers=ed["h"], params={"row_version": link["row_version"]}).status_code == 404
    assert allocate(client, ed, s2, a, headers=ed["rv"]).status_code == 403
    assert support(client, ed, step_a["bfc_node_id"], a, headers=ed["rv"]).status_code == 403


def test_a_code_that_upper_cases_past_30_characters_is_422(client, ed):
    """sara L1: "ß".upper() == "SS"."""
    app(client, ed, code="ß" * 16, name="Long", expect=422)
