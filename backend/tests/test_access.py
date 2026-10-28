"""Slice 7b access (D-40, OR-5, OR-6; slice7_schema §8): admin / USER / VIEWER, restricted projects
and their members. Grade 1: who can see a client's data. Replaces the D-32 grant tests."""
import re

from fastapi.routing import APIRoute
from sqlalchemy import create_engine, select

from models import AuditEvent
from tests.conftest import ALL_COMPONENTS, OWNER_URL, PW, login, restrict

API = "/api/v1"


def visible(client, headers):
    return sorted(p["project_code"] for p in client.get(f"{API}/projects", headers=headers).json())


def preview_restrict(client, w, pid, value=True):
    return client.put(f"{API}/projects/{pid}/restriction", headers=w["admin"], json={"is_restricted": value})


# ---- visibility ---------------------------------------------------------------------------------
def test_staff_see_every_unrestricted_project_and_a_restricted_one_only_as_members(client, world):
    w = world
    every = ["BETA1", "FIN", "SALES", "SOLO"]
    ed, rv, out = (login(client, f"{n}@example.test") for n in ("editor", "reviewer", "outsider"))
    assert visible(client, ed) == every and visible(client, rv) == every          # D-40, OR-5
    restrict(client, w["admin"], w["p_solo"], {w["users"]["editor"]: "EDIT"})
    assert visible(client, ed) == every
    assert visible(client, out) == ["BETA1", "FIN", "SALES"]
    assert client.get(f"{API}/projects/{w['p_solo']}", headers=out).status_code == 404   # never 403
    assert visible(client, w["admin"]) == every                                      # admins always


def test_levels_user_edits_viewer_reads_and_membership_caps(client, world):
    w = world
    body = {"node_name": "Sales", "parent_bfc_node_id": None}
    ed, rv, owner = (login(client, f"{n}@example.test") for n in ("editor", "reviewer", "owner"))
    url = f"{API}/projects/{w['p_fin']}/bfc-nodes"
    assert client.post(url, headers=ed, json=body).status_code == 201
    assert client.post(url, headers=rv, json={**body, "node_name": "X"}).status_code == 403
    r = client.get(f"{API}/projects/{w['p_fin']}", headers=rv).json()
    assert r["my_access_level"] == "VIEW"
    # restricted: a USER member at VIEW reads only; a VIEWER is refused above VIEW, never quietly capped (D-71 (7))
    url = f"{API}/projects/{w['p_sales']}/members"
    for level in ("EDIT", "ADMIN"):
        r = client.post(url, headers=w["admin"], json={"user_id": w["users"]["reviewer"], "access_level": level})
        assert r.status_code == 422 and "viewer" in r.json()["detail"]
    r = client.post(url, headers=w["admin"], json={"user_id": w["users"]["reviewer"], "access_level": "VIEW"})
    assert r.status_code == 201 and r.json()["effective_level"] == "VIEW"
    restrict(client, w["admin"], w["p_sales"], {w["users"]["owner"]: "VIEW"})
    url = f"{API}/projects/{w['p_sales']}/bfc-nodes"
    assert client.post(url, headers=owner, json=body).status_code == 403
    assert client.post(url, headers=rv, json=body).status_code == 403
    assert client.get(f"{API}/projects/{w['p_sales']}", headers=owner).json()["my_access_level"] == "VIEW"


def test_me_reports_scope_and_kind(client, world):
    me = client.get("/auth/me", headers=login(client, "reviewer@example.test")).json()
    assert me["scope"] == "STAFF" and me["user_kind"] == "VIEWER"
    assert client.get("/auth/me", headers=world["admin"]).json()["scope"] == "PLATFORM_ADMIN"


# ---- restriction ----------------------------------------------------------------------------------
def test_restricting_previews_loses_and_keeps_then_applies_and_audits(client, world, db):
    w = world
    client.post(f"{API}/projects/{w['p_solo']}/members", headers=w["admin"],
                json={"user_id": w["users"]["editor"], "access_level": "EDIT", "member_note": "NDA signatory"})
    prev = preview_restrict(client, w, w["p_solo"]).json()
    assert prev["applied"] is False and prev["changed"] is True
    assert sorted(x["display_name"] for x in prev["loses"]) == ["Outsider", "Owner", "Reviewer"]
    assert [(k["display_name"], k["member_note"]) for k in prev["keeps"]] == [("Editor", "NDA signatory")]
    out = login(client, "outsider@example.test")
    assert "SOLO" in visible(client, out)                                     # nothing written yet
    url = f"{API}/projects/{w['p_solo']}/restriction"
    r = client.put(url, headers=w["admin"], json={"is_restricted": True, "confirm_hash": prev["confirm_hash"]})
    assert r.json()["applied"] is True and "SOLO" not in visible(client, out)
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PROJECT_RESTRICTED")).one()
    assert ev.detail["members"] == [{"user_id": w["users"]["editor"], "access_level": "EDIT"}]
    back = preview_restrict(client, w, w["p_solo"], False).json()
    assert sorted(x["display_name"] for x in back["gains"]) == ["Outsider", "Owner", "Reviewer"]


def test_the_restrict_preview_flags_a_kept_member_whose_level_drops(client, world):
    """DR10c-S1 (D-62): restricting an open project keeps a USER copied at VIEW — flagged; an EDIT member and a
    VIEWER (read-only either way) are not. Unrestricting flags nobody."""
    w = world
    for name, level in (("editor", "VIEW"), ("owner", "EDIT"), ("reviewer", "VIEW")):
        client.post(f"{API}/projects/{w['p_solo']}/members", headers=w["admin"],
                    json={"user_id": w["users"][name], "access_level": level})
    prev = preview_restrict(client, w, w["p_solo"]).json()
    assert {k["display_name"]: k["level_drops"] for k in prev["keeps"]} == {
        "Editor": True, "Owner": False, "Reviewer": False}
    client.put(f"{API}/projects/{w['p_solo']}/restriction", headers=w["admin"],
               json={"is_restricted": True, "confirm_hash": prev["confirm_hash"]})
    back = preview_restrict(client, w, w["p_solo"], False).json()
    assert not any(k["level_drops"] for k in back["keeps"])


def test_a_stale_restriction_preview_is_refused(client, world):
    w = world
    prev = preview_restrict(client, w, w["p_solo"]).json()
    client.post(f"{API}/projects/{w['p_solo']}/members", headers=w["admin"],
                json={"user_id": w["users"]["editor"], "access_level": "EDIT"})
    r = client.put(f"{API}/projects/{w['p_solo']}/restriction", headers=w["admin"],
                   json={"is_restricted": True, "confirm_hash": prev["confirm_hash"]})
    assert r.status_code == 409


def test_only_an_admin_manages_members_restriction_and_the_access_list(client, world):
    w = world
    ed = login(client, "editor@example.test")
    pid = w["p_solo"]
    assert client.get(f"{API}/projects/{pid}/access", headers=ed).status_code == 403
    assert client.post(f"{API}/projects/{pid}/members", headers=ed,
                       json={"user_id": w["users"]["owner"], "access_level": "EDIT"}).status_code == 403
    assert client.put(f"{API}/projects/{pid}/restriction", headers=ed, json={"is_restricted": True}).status_code == 403
    acc = client.get(f"{API}/projects/{pid}/access", headers=w["admin"]).json()
    assert acc["is_restricted"] is False and acc["staff"] == {"USER": 3, "VIEWER": 1}


# ---- members --------------------------------------------------------------------------------------
def test_member_lifecycle_add_change_remove_and_readd_as_a_new_row(client, world, db):
    w = world
    pid, uid = w["p_solo"], w["users"]["editor"]
    restrict(client, w["admin"], pid, {uid: "VIEW"})
    ed = login(client, "editor@example.test")
    m = client.get(f"{API}/projects/{pid}/members", headers=w["admin"]).json()[0]
    assert client.post(f"{API}/projects/{pid}/members", headers=w["admin"],
                       json={"user_id": uid, "access_level": "EDIT"}).status_code == 409
    r = client.patch(f"{API}/project-members/{m['project_member_id']}", headers=w["admin"],
                     json={"access_level": "EDIT", "row_version": m["row_version"]})
    assert r.status_code == 200 and r.json()["effective_level"] == "EDIT"
    assert client.get(f"{API}/projects/{pid}", headers=ed).json()["my_access_level"] == "EDIT"
    r = client.delete(f"{API}/project-members/{m['project_member_id']}", headers=w["admin"],
                      params={"row_version": r.json()["row_version"]})
    assert r.status_code == 204
    assert client.get(f"{API}/projects/{pid}", headers=ed).status_code == 404     # next request
    r = client.post(f"{API}/projects/{pid}/members", headers=w["admin"], json={"user_id": uid, "access_level": "VIEW"})
    assert r.json()["project_member_id"] != m["project_member_id"]                  # a new period
    types = [e.event_type for e in db.scalars(select(AuditEvent).where(AuditEvent.event_type.like("MEMBER_%"))
                                               .order_by(AuditEvent.audit_event_id))]
    assert types == ["MEMBER_ADDED", "MEMBER_LEVEL_CHANGED", "MEMBER_REMOVED", "MEMBER_ADDED"]


def test_admins_need_no_membership(client, world):
    admin_id = client.get("/auth/me", headers=world["admin"]).json()["user"]["app_user_id"]
    r = client.post(f"{API}/projects/{world['p_solo']}/members", headers=world["admin"],
                    json={"user_id": admin_id, "access_level": "EDIT"})
    assert r.status_code == 422


# ---- programs -------------------------------------------------------------------------------------
def test_programs_roll_up_visible_projects_and_hide_when_none_is_visible(client, world):
    w = world
    out = login(client, "outsider@example.test")
    assert [g["program_code"] for g in client.get(f"{API}/programs", headers=out).json()] == ["CSR27"]
    restrict(client, w["admin"], w["p_sales"])
    url = f"{API}/programs/{w['program_id']}/projects"
    assert [p["project_code"] for p in client.get(url, headers=out).json()] == ["FIN"]   # silently omitted
    restrict(client, w["admin"], w["p_fin"])
    assert client.get(f"{API}/programs", headers=out).json() == []                       # auditor Q2
    assert client.get(url, headers=out).status_code == 404


def test_move_project_needs_preview_then_confirm_and_changes_no_access(client, world):
    """R2-S3 kept; since D-40 a move changes roll-ups, never access."""
    w = world
    url = f"{API}/programs/{w['program_id']}/projects"
    pre = client.post(url, headers=w["admin"], json={"project_id": w["p_solo"]}).json()
    assert pre["applied"] is False and pre["preview"]["gains"] == [] and pre["preview"]["loses"] == []
    r = client.post(url, headers=w["admin"], json={"project_id": w["p_solo"], "confirm_hash": pre["preview_hash"]})
    assert r.json()["applied"] is True
    assert client.post(url, headers=w["admin"], json={"project_id": w["p_beta"]}).status_code == 422


def test_non_admin_cannot_create_projects_or_move(client, world):
    w = world
    owner = login(client, "owner@example.test")
    r = client.post(f"{API}/projects", headers=owner, json={
        "client_id": w["client_id"], "project_code": "X", "project_name": "X",
        "component_codes": ALL_COMPONENTS, "is_restricted": False})
    assert r.status_code == 403
    r = client.post(f"{API}/programs/{w['program_id']}/projects", headers=owner, json={"project_id": w["p_solo"]})
    assert r.status_code == 403


def test_admin_gets_404_for_missing_program_and_wrong_program_detach(client, world):
    """sara M2, M1."""
    w = world
    assert client.get(f"{API}/programs/9999", headers=w["admin"]).status_code == 404
    assert client.get(f"{API}/programs/9999/projects", headers=w["admin"]).status_code == 404
    other = client.post(f"{API}/programs", headers=w["admin"], json={
        "client_id": w["client_id"], "program_code": "OTHER", "program_name": "Other"}).json()
    r = client.delete(f"{API}/programs/{other['program_id']}/projects/{w['p_sales']}", headers=w["admin"])
    assert r.status_code == 404


def test_create_project_asks_whether_it_is_restricted(client, world, db):
    w = world
    body = {"client_id": w["client_id"], "project_code": "NDA", "project_name": "NDA",
            "component_codes": ["ISSUE"]}
    assert client.post(f"{API}/projects", headers=w["admin"], json=body).status_code == 422   # no default
    r = client.post(f"{API}/projects", headers=w["admin"], json={**body, "is_restricted": True})
    assert r.status_code == 201 and r.json()["is_restricted"] is True
    assert "NDA" not in visible(client, login(client, "editor@example.test"))
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PROJECT_CREATED",
                                             AuditEvent.project_id == r.json()["project_id"])).one()
    assert ev.detail["is_restricted"] is True


# ---- users and kinds --------------------------------------------------------------------------------
def test_user_kind_is_required_changed_by_an_admin_and_audited(client, world, db):
    w = world
    r = client.post(f"{API}/users", headers=w["admin"], json={
        "email": "new@example.test", "display_name": "New", "initial_password": PW})
    assert r.status_code == 422                                                  # no API default
    rv = login(client, "reviewer@example.test")
    url = f"{API}/projects/{w['p_fin']}/bfc-nodes"
    assert client.post(url, headers=rv, json={"node_name": "A", "parent_bfc_node_id": None}).status_code == 403
    u = next(x for x in client.get(f"{API}/users", headers=w["admin"]).json() if x["app_user_id"] == w["users"]["reviewer"])
    r = client.patch(f"{API}/users/{u['app_user_id']}/kind", headers=w["admin"],
                     json={"user_kind": "USER", "row_version": u["row_version"]})
    assert r.status_code == 200 and r.json()["user_kind"] == "USER"
    assert client.post(url, headers=rv, json={"node_name": "A", "parent_bfc_node_id": None}).status_code == 201
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "USER_KIND_CHANGED")).one()
    assert ev.detail == {"from": "VIEWER", "to": "USER", "comes_back": []}
    assert client.patch(f"{API}/users/{u['app_user_id']}/kind", headers=login(client, "editor@example.test"),
                        json={"user_kind": "USER", "row_version": 1}).status_code == 403


def test_deactivation_takes_effect_on_next_request(client, world):
    w = world
    editor = login(client, "editor@example.test")
    assert client.get(f"{API}/projects", headers=editor).status_code == 200
    assert client.patch(f"{API}/users/{w['users']['editor']}/deactivate", headers=w["admin"]).status_code == 200
    assert client.get(f"{API}/projects", headers=editor).status_code == 401


def test_platform_admin_is_a_separate_audited_act_and_removal_names_the_kind(client, world, db):
    """sara M7 kept; DR7-S6: removing admin rights says what the user becomes."""
    w = world
    r = client.post(f"{API}/users", headers=w["admin"], json={
        "email": "sneaky@example.test", "display_name": "Sneaky", "initial_password": PW,
        "user_kind": "VIEWER", "is_platform_admin": True})
    assert r.status_code == 201 and r.json()["is_platform_admin"] is False
    uid, rv = r.json()["app_user_id"], r.json()["row_version"]
    url = f"{API}/users/{uid}/platform-admin"
    no = client.patch(url, headers=w["admin"], json={
        "is_platform_admin": True, "rationale": "Second admin for cover", "row_version": rv})
    assert no.status_code == 422 and "request" in no.json()["detail"]                   # slice 17 (AR-13), criterion 7
    from tests.test_project_purge_record import promote
    owner = create_engine(OWNER_URL)
    try:
        promote(owner, uid)                                                             # an IS grant (AR-19)
    finally:
        owner.dispose()
    rv = next(u for u in client.get(f"{API}/users", headers=w["admin"]).json() if u["app_user_id"] == uid)["row_version"]
    assert client.patch(url, headers=w["admin"], json={
        "is_platform_admin": False, "rationale": "Moved on", "row_version": rv}).status_code == 422
    r = client.patch(url, headers=w["admin"], json={
        "is_platform_admin": False, "rationale": "Moved on", "row_version": rv, "user_kind": "VIEWER"})
    assert r.status_code == 200 and r.json()["user_kind"] == "VIEWER"
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PLATFORM_ADMIN_REMOVED")).one()
    assert ev.detail["user_kind"] == "VIEWER"


# ---- DR7-S2: no GET route leaks a restricted project to a non-member ----------------------------------
def _seed_restricted(client, w) -> tuple[int, dict, set[int]]:
    """A restricted project in the program, with one marked row of every model a GET route serves:
    chart nodes and a process with its BR, data entity and field, solution, FR, application, org unit
    and role, external party (sara 7b M2a/b). Returns (project id, marks, every id it uses)."""
    h = w["admin"]
    marks = {"code": "ZQXCODE", "name": "Zqx secret project", "node": "Zqx hidden L1", "step": "Zqx hidden step",
             "de": "Zqx ledger", "field": "zqx_field", "sol": "Zqx solution", "fr": "Zqx form",
             "app": "ZQXAPP", "unit": "ZQXU", "role": "ZQXR", "ext": "Zqx bank", "baseline": "Zqx frozen note",
             "stk": "Zqx stakeholder", "issue": "Zqx issue", "br": "Zqx statement", "wave": "Zqx wave"}
    p = client.post(f"{API}/projects", headers=h, json={
        "client_id": w["client_id"], "project_code": marks["code"], "project_name": marks["name"],
        "program_id": w["program_id"], "component_codes": ALL_COMPONENTS, "is_restricted": True}).json()
    pid, ids = p["project_id"], {p["project_id"]}

    def post(path, body, key):
        r = client.post(f"{API}{path}", headers=h, json=body)
        assert r.status_code == 201, (path, r.text)
        ids.add(r.json()[key])
        return r.json()
    l1 = post(f"/projects/{pid}/bfc-nodes", {"node_name": marks["node"], "parent_bfc_node_id": None}, "bfc_node_id")
    l2 = post(f"/projects/{pid}/bfc-nodes", {"node_name": "Zqx L2", "parent_bfc_node_id": l1["bfc_node_id"]}, "bfc_node_id")
    step = post(f"/projects/{pid}/bfc-nodes", {"node_name": marks["step"], "parent_bfc_node_id": l2["bfc_node_id"],
                                               "is_process": True}, "bfc_node_id")
    brs = client.get(f"{API}/projects/{pid}/business-requirements", headers=h).json()
    ids.update(b["br_id"] for b in brs)
    de = post(f"/projects/{pid}/data-entities", {"de_name": marks["de"]}, "data_entity_id")
    post(f"/data-entities/{de['data_entity_id']}/fields", {"field_name": marks["field"]}, "data_field_id")
    sol = post(f"/projects/{pid}/solutions", {"solution_name": marks["sol"], "category_code": "PROCESS"}, "solution_id")
    post(f"/projects/{pid}/function-requirements", {"fr_name": marks["fr"], "fr_type_code": "FORM",
                                                    "solution_id": sol["solution_id"]}, "fr_id")
    post(f"/projects/{pid}/applications", {"application_code": marks["app"], "application_name": "Zqx app",
                                           "lifecycle_code": "AS_IS"}, "application_id")
    unit = post(f"/projects/{pid}/org-units", {"org_unit_code": marks["unit"], "org_unit_name": "Zqx unit"}, "org_unit_id")
    post(f"/projects/{pid}/org-roles", {"org_unit_id": unit["org_unit_id"], "org_role_code": marks["role"],
                                        "org_role_name": "Zqx role"}, "org_role_id")
    post(f"/projects/{pid}/external-entities", {"ext_name": marks["ext"]}, "external_entity_id")
    stk = post(f"/projects/{pid}/stakeholders", {"stakeholder_name": marks["stk"], "org_unit_id": unit["org_unit_id"]},
               "stakeholder_id")                                                         # slice 14 (sara A M-1)
    iss = post(f"/projects/{pid}/issues", {"title": marks["issue"], "severity_code": "HIGH", "issue_type_code": "DATA",
                                           "raised_by_stakeholder_id": stk["stakeholder_id"]}, "issue_id")
    # slice 15: a marked wave, the marked solution split into it, and a dependency on the marked solution
    wv = post(f"/projects/{pid}/phases", {"phase_code": "ZQXW", "phase_name": marks["wave"],
                                          "status_code": "PLANNED"}, "phase_id")
    r = client.put(f"{API}/solutions/{sol['solution_id']}/phase-split", headers=h,
                   json={"based_on": [], "rows": [{"phase_id": wv["phase_id"], "portion_pct": "100"}]})
    assert r.status_code == 200, r.text
    needs = post(f"/projects/{pid}/solutions", {"solution_name": "Zqx later", "category_code": "PROCESS"}, "solution_id")
    post(f"/solutions/{needs['solution_id']}/dependencies", {"depends_on_solution_id": sol["solution_id"]},
         "solution_dependency_id")
    assert step["is_process"]
    # slice 8: a frozen baseline, marked by its note — its step reads and writes data so the freeze passes
    de2 = post(f"/projects/{pid}/data-entities", {"de_name": "Zqx journal"}, "data_entity_id")
    br = next(b for b in brs if b["bfc_node_id"] == step["bfc_node_id"])
    for d, crud in ((de, "R"), (de2, "C")):
        post(f"/business-requirements/{br['br_id']}/data-entities",
             {"data_entity_id": d["data_entity_id"], "crud_code": crud}, "br_data_entity_id")
    # slice 14 (sara C L1): an issue link to the hidden BR, whose statement is marked
    r = client.patch(f"{API}/business-requirements/{br['br_id']}", headers=h,
                     json={"row_version": br["row_version"], "br_statement": marks["br"]})
    assert r.status_code == 200, r.text
    post(f"/issues/{iss['issue_id']}/brs", {"br_id": br["br_id"]}, "issue_br_id")
    pv = client.get(f"{API}/projects/{pid}/baselines/next", headers=h).json()
    fz = client.post(f"{API}/projects/{pid}/baselines/freeze", headers=h, json={
        "note": marks["baseline"], "bump": "MINOR", "confirm_text": pv["confirm_text"],
        "preview_digest": pv["preview_digest"]})
    assert fz.status_code == 201, fz.text
    ids.add(fz.json()["baseline"]["baseline_id"])
    return pid, marks, ids


def _sweep(client, headers, pid, ids) -> tuple[list[str], int, list[str]]:
    """Call every GET route with every id; return (paths whose body carries a mark, calls, bodies)."""
    from main import app
    hits, bodies, called = [], [], 0
    for r in app.routes:
        if not isinstance(r, APIRoute) or "GET" not in r.methods:
            continue
        params = re.findall(r"\{(\w+)\}", r.path)
        for i in sorted(ids | {1, 2, 3}) if params else [None]:
            path = r.path
            for prm in params:
                path = path.replace(f"{{{prm}}}", str(pid if prm == "project_id" else i) if prm.endswith("id")
                                    else "BFC_NODE")
            resp = client.get(path, headers=headers)
            called += 1
            hits.append((r.path, path, resp.status_code, resp.text))
    return hits, called, bodies


def test_no_get_route_leaks_a_restricted_project(client, world):
    """DR7-S2, strengthened (sara 7b M2): marked rows of every model, the project inside a program, a
    sweep of every GET route as a non-member USER and as a non-member VIEWER, and a positive control —
    the same sweep as the admin must find the marks, so the test cannot pass by finding nothing."""
    w = world
    pid, marks, ids = _seed_restricted(client, w)
    found = lambda hits: {p for p, _, _, body in hits if any(v in body for v in marks.values())}  # noqa: E731
    admin_hits, called, _ = _sweep(client, w["admin"], pid, ids)
    seen_by_admin = found(admin_hits)
    for must in ("/api/v1/projects", "/api/v1/projects/{project_id}", "/api/v1/projects/{project_id}/bfc-tree",
                 "/api/v1/projects/{project_id}/data-entities", "/api/v1/projects/{project_id}/solutions",
                 "/api/v1/projects/{project_id}/function-requirements", "/api/v1/projects/{project_id}/applications",
                 "/api/v1/programs/{program_id}/projects", "/api/v1/projects/{project_id}/baselines",
                 "/api/v1/baselines/{id}", "/api/v1/projects/{project_id}/stakeholders",
                 "/api/v1/stakeholders/{id}", "/api/v1/projects/{project_id}/issues", "/api/v1/issues/{id}",
                 "/api/v1/projects/{project_id}/issue-dashboard",                  # names the raiser (slice 14)
                 "/api/v1/issues/{id}/brs",                                        # the linked BR's statement
                 "/api/v1/projects/{project_id}/phases", "/api/v1/phases/{id}",    # slice 15: the wave's name
                 "/api/v1/projects/{project_id}/phase-plan", "/api/v1/solutions/{id}/phase-split",
                 "/api/v1/solutions/{id}/dependencies",                            # the prerequisite's name
                 "/api/v1/projects/{project_id}/traceability",                     # slice 1f: the FR name
                 "/api/v1/projects/{project_id}/coverage",                         # slice 1f: the BR statement
                 "/api/v1/projects/{project_id}/solution-matrix"):                 # slice 1f: the area name
        assert must in seen_by_admin, must                                              # positive control
    assert called > 200
    # slice 8 (sara L6): the parameterised baseline reads, as admin (positive) and as each non-member
    bl = max(i for i in ids if client.get(f"{API}/baselines/{i}", headers=w["admin"]).status_code == 200)
    extra = [f"{API}/baselines/{bl}/rows/business_requirement",
             f"{API}/projects/{pid}/baselines/diff?from={bl}&to=live"]
    assert all(client.get(u, headers=w["admin"]).status_code == 200 for u in extra)
    assert any(marks["baseline"] in client.get(f"{API}/baselines/{bl}", headers=w["admin"]).text for _ in [0])
    # D-71: the admin of another project in the same program is a non-member here like anyone else
    r = client.post(f"{API}/projects/{w['p_fin']}/members", headers=w["admin"],
                    json={"user_id": w["users"]["owner"], "access_level": "ADMIN"})
    assert r.status_code == 201
    for who in ("outsider", "reviewer", "owner"):
        hh = login(client, f"{who}@example.test")
        assert all(client.get(u, headers=hh).status_code == 404 for u in extra + [f"{API}/baselines/{bl}"]), who
    for who in ("outsider", "reviewer", "owner"):                 # a non-member USER, VIEWER and project admin
        hits, _, _ = _sweep(client, login(client, f"{who}@example.test"), pid, ids)
        assert found(hits) == set(), who
        on_pid = [(p, path, code) for p, path, code, _ in hits if f"/projects/{pid}" in path and code != 404]
        assert on_pid == [], (who, on_pid)                         # the project itself: never 403, always 404
