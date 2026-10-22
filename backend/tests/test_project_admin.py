"""Access slice A — the project admin (D-71, D-73; docs/slice_access_a_plan.md). Grade 1: a silent failure gives
someone admin or edit rights on client data, or lets a project admin reach an FTC-only setting.

Covered: the FTC-only routes and the project-admin routes are both taken from the route table, so a route moved
between them, or a new one, cannot slip past; every refusal is checked as a real user against the real guards; the
level table is checked through the API against literal expectations, not against the code that computes it.
Left uncovered on purpose (plan §Grade): two platform admins changing one user's kind at the same moment — the row
version already refuses the second."""
import pytest
from fastapi.routing import APIRoute
from sqlalchemy import text

from routers.guards import GUARD_KEY
from tests.conftest import login, restrict

API = "/api/v1"
PLATFORM_ROUTES = {("PUT", "/api/v1/projects/{project_id}/components"),
                   ("PUT", "/api/v1/projects/{project_id}/data-model-depth"),
                   ("PUT", "/api/v1/projects/{project_id}/fte-basis"),
                   ("POST", "/api/v1/projects/{project_id}/dfd-rule/preview"),
                   ("PUT", "/api/v1/projects/{project_id}/dfd-rule"),
                   ("PUT", "/api/v1/projects/{project_id}/restriction"),
                   ("POST", "/api/v1/projects/{project_id}/purge-requests")}       # slice 16 (spec §9)
ADMIN_ROUTES = {("GET", "/api/v1/projects/{project_id}/access"),
                ("GET", "/api/v1/projects/{project_id}/members"),
                ("GET", "/api/v1/projects/{project_id}/member-candidates"),
                ("POST", "/api/v1/projects/{project_id}/members"),
                ("PATCH", "/api/v1/project-members/{id}"),
                ("DELETE", "/api/v1/project-members/{id}")}
# wave 1g: a project's code lists are its admin's (G-5); their guards are proven in tests/test_code_lists.py
CODE_LIST_ADMIN_ROUTES = {("POST", "/api/v1/projects/{project_id}/code-lists/{category}"),
                          ("POST", "/api/v1/projects/{project_id}/code-lists/hidden"),
                          ("DELETE", "/api/v1/projects/{project_id}/code-lists/hidden"),
                          ("PATCH", "/api/v1/code-master/{code_id}"),
                          ("PATCH", "/api/v1/code-master/{code_id}/restore"),
                          ("DELETE", "/api/v1/code-master/{code_id}")}
# access slice B: a program's members are its admins' (D-71 (5)); their guards are proven in tests/test_program_members.py
PROGRAM_ADMIN_ROUTES = {("GET", "/api/v1/programs/{program_id}/members"),
                        ("GET", "/api/v1/programs/{program_id}/member-candidates"),
                        ("POST", "/api/v1/programs/{program_id}/members"),
                        ("PATCH", "/api/v1/program-members/{id}"),
                        ("DELETE", "/api/v1/program-members/{id}")}


def _routes(level: str) -> set[tuple[str, str]]:
    from main import app
    return {(m, r.path) for r in app.routes if isinstance(r, APIRoute)
            for m in r.methods if r.openapi_extra[GUARD_KEY]["min_level"] == level}


def _call(client, h, method, path, pid, member_id):
    url = path.replace("{project_id}", str(pid)).replace("{id}", str(member_id))
    return client.request(method, url, headers=h, json={} if method != "GET" else None,
                          params={"row_version": 1} if method == "DELETE" else None)


def add(client, h, pid, uid, level, note=None):
    return client.post(f"{API}/projects/{pid}/members", headers=h,
                       json={"user_id": uid, "access_level": level, "member_note": note})


@pytest.fixture
def pa(client, world):
    """Owner is the admin of SOLO (open) and of nothing else; editor is a plain USER."""
    w = world
    r = add(client, w["admin"], w["p_solo"], w["users"]["owner"], "ADMIN")
    assert r.status_code == 201, r.text
    return {**w, "pa": login(client, "owner@example.test"), "ed": login(client, "editor@example.test"),
            "out": login(client, "outsider@example.test"), "pa_member": r.json()}


# ---- 1, 2: the route table --------------------------------------------------------------------------------
def test_the_ftc_only_and_project_admin_route_sets_are_exactly_these():
    assert _routes("PLATFORM") == PLATFORM_ROUTES
    assert _routes("ADMIN") == ADMIN_ROUTES | CODE_LIST_ADMIN_ROUTES | PROGRAM_ADMIN_ROUTES


def test_every_ftc_only_route_refuses_a_project_admin_and_a_plain_editor(client, pa):
    for method, path in sorted(PLATFORM_ROUTES):
        for who in ("pa", "ed"):
            r = _call(client, pa[who], method, path, pa["p_solo"], pa["pa_member"]["project_member_id"])
            assert r.status_code == 403, (who, method, path, r.status_code)
        r = _call(client, pa["admin"], method, path, pa["p_solo"], pa["pa_member"]["project_member_id"])
        assert r.status_code not in (403, 404), (method, path, r.status_code)       # positive control


def test_every_project_admin_route_refuses_editors_other_projects_admins_and_outsiders(client, pa):
    w = pa
    m_id = pa["pa_member"]["project_member_id"]
    for method, path in sorted(ADMIN_ROUTES):
        # a plain USER on an open project: 403
        assert _call(client, w["ed"], method, path, w["p_solo"], m_id).status_code == 403, (method, path)
        # SOLO's admin on another open project: 403
        if "{project_id}" in path:
            assert _call(client, w["pa"], method, path, w["p_fin"], m_id).status_code == 403, (method, path)
    # SOLO's admin, and a non-member, on a restricted project: 404, never 403
    restrict(client, w["admin"], w["p_sales"], {w["users"]["editor"]: "ADMIN"})
    sales_member = client.get(f"{API}/projects/{w['p_sales']}/members", headers=w["admin"]).json()[0]
    for method, path in sorted(ADMIN_ROUTES):
        for who in ("pa", "out"):
            r = _call(client, w[who], method, path, w["p_sales"], sales_member["project_member_id"])
            assert r.status_code == 404, (who, method, path, r.status_code)
    # and the project admin's own project: allowed
    assert client.get(f"{API}/projects/{w['p_solo']}/access", headers=w["pa"]).status_code == 200
    # sara L5: SOLO's admin on a member row of another OPEN project — 403 (the restricted case is 404 above)
    fin = add(client, w["admin"], w["p_fin"], w["users"]["outsider"], "EDIT").json()
    for method in ("PATCH", "DELETE"):
        r = _call(client, w["pa"], method, "/api/v1/project-members/{id}", w["p_fin"], fin["project_member_id"])
        assert r.status_code == 403, method


def test_every_ftc_only_route_is_404_to_an_outsider_on_a_restricted_project(client, pa):
    restrict(client, pa["admin"], pa["p_sales"])
    for method, path in sorted(PLATFORM_ROUTES):
        for who in ("pa", "out"):
            assert _call(client, pa[who], method, path, pa["p_sales"], 0).status_code == 404, (who, method, path)


# ---- 3: the level table, through the API ----------------------------------------------------------------
# (kind, restricted, membership) → my_access_level, or None for 404. Literal: never computed by the code under test.
LEVELS = [
    ("USER", False, None, "EDIT"), ("USER", False, "VIEW", "EDIT"), ("USER", False, "EDIT", "EDIT"),
    ("USER", False, "ADMIN", "ADMIN"),
    ("USER", True, None, None), ("USER", True, "VIEW", "VIEW"), ("USER", True, "EDIT", "EDIT"),
    ("USER", True, "ADMIN", "ADMIN"),
    ("VIEWER", False, None, "VIEW"), ("VIEWER", False, "VIEW", "VIEW"),
    ("VIEWER", False, "EDIT", "VIEW"), ("VIEWER", False, "ADMIN", "VIEW"),      # rows stored before D-71 (7): capped
    ("VIEWER", True, None, None), ("VIEWER", True, "VIEW", "VIEW"),
    ("VIEWER", True, "EDIT", "VIEW"), ("VIEWER", True, "ADMIN", "VIEW"),
]


@pytest.mark.parametrize("kind,restricted,level,expected", LEVELS)
def test_the_level_table(client, world, db, kind, restricted, level, expected):
    w = world
    who = "reviewer" if kind == "VIEWER" else "outsider"
    uid, pid = w["users"][who], w["p_solo"]
    if level is not None:      # written as a stored row, so a VIEWER's old EDIT / ADMIN row is tested too
        db.execute(text("INSERT INTO project_member (project_id, app_user_id, access_level, created_by) "
                        "VALUES (:p, :u, :l, :u)"), {"p": pid, "u": uid, "l": level})
        db.commit()
    if restricted:
        restrict(client, w["admin"], pid)
    r = client.get(f"{API}/projects/{pid}", headers=login(client, f"{who}@example.test"))
    if expected is None:
        assert r.status_code == 404
    else:
        assert r.status_code == 200 and r.json()["my_access_level"] == expected


def test_a_platform_admin_holds_platform_on_every_project(client, world):
    assert client.get(f"{API}/projects/{world['p_solo']}", headers=world["admin"]).json()["my_access_level"] == "PLATFORM"


# ---- 4: a viewer is refused above VIEW, on add and on change ----------------------------------------------
def test_a_viewer_is_refused_editor_or_admin_on_add_and_on_change(client, pa):
    w = pa
    rid = w["users"]["reviewer"]
    for level in ("EDIT", "ADMIN"):
        assert add(client, w["pa"], w["p_solo"], rid, level).status_code == 422
    m = add(client, w["pa"], w["p_solo"], rid, "VIEW").json()
    for level in ("EDIT", "ADMIN"):
        r = client.patch(f"{API}/project-members/{m['project_member_id']}", headers=w["pa"],
                         json={"access_level": level, "row_version": m["row_version"]})
        assert r.status_code == 422
    assert client.get(f"{API}/projects/{w['p_solo']}/members", headers=w["admin"]).json()[-1]["access_level"] == "VIEW"


# ---- 5: a project admin manages members, other admins included (D-73) -------------------------------------
def test_a_project_admin_appoints_demotes_and_removes_admins_including_one_the_ftc_appointed(client, pa):
    w = pa
    ed_id = w["users"]["editor"]
    m = add(client, w["pa"], w["p_solo"], ed_id, "ADMIN").json()                  # appoints a second admin
    assert m["effective_level"] == "ADMIN" and m["via"] == "MEMBER"
    ed = w["ed"]
    assert client.get(f"{API}/projects/{w['p_solo']}/access", headers=ed).status_code == 200
    # the new admin demotes the one the FTC admin appointed, then removes them
    own = w["pa_member"]
    r = client.patch(f"{API}/project-members/{own['project_member_id']}", headers=ed,
                     json={"access_level": "EDIT", "row_version": own["row_version"]})
    assert r.status_code == 200 and r.json()["access_level"] == "EDIT"
    assert client.get(f"{API}/projects/{w['p_solo']}/access", headers=w["pa"]).status_code == 403
    r = client.delete(f"{API}/project-members/{own['project_member_id']}", headers=ed,
                      params={"row_version": r.json()["row_version"]})
    assert r.status_code == 204
    # the platform admin can always put it back
    assert add(client, w["admin"], w["p_solo"], w["users"]["owner"], "ADMIN").status_code == 201


def test_a_project_admin_picks_from_active_non_admin_staff_who_are_not_members(client, pa):
    w = pa
    names = [p["display_name"] for p in client.get(f"{API}/projects/{w['p_solo']}/member-candidates",
                                                   headers=w["pa"]).json()]
    assert names == ["Editor", "Outsider", "Reviewer"]                    # not Owner (a member), not the admin
    assert client.get(f"{API}/users", headers=w["pa"]).status_code == 403   # the full user list stays FTC-only


def test_a_project_admin_gains_nothing_ftc_only_by_appointing_themselves_elsewhere(client, pa):
    w = pa
    r = add(client, w["pa"], w["p_fin"], w["users"]["owner"], "ADMIN")
    assert r.status_code == 403


# ---- 6: who can open it — the Access list and the restriction preview ------------------------------------
def test_the_access_list_and_restriction_preview_show_project_admins(client, pa):
    w = pa
    acc = client.get(f"{API}/projects/{w['p_solo']}/access", headers=w["pa"]).json()
    assert [(m["display_name"], m["effective_level"], m["via"]) for m in acc["members"]] == [("Owner", "ADMIN", "MEMBER")]
    prev = client.put(f"{API}/projects/{w['p_solo']}/restriction", headers=w["admin"], json={"is_restricted": True}).json()
    assert [(k["display_name"], k["effective_level"], k["level_drops"]) for k in prev["keeps"]] == [("Owner", "ADMIN", False)]
    # a level change after the preview changes who keeps what: the confirm is refused
    m = w["pa_member"]
    client.patch(f"{API}/project-members/{m['project_member_id']}", headers=w["admin"],
                 json={"access_level": "EDIT", "row_version": m["row_version"]})
    r = client.put(f"{API}/projects/{w['p_solo']}/restriction", headers=w["admin"],
                   json={"is_restricted": True, "confirm_hash": prev["confirm_hash"]})
    assert r.status_code == 409


# ---- 7: a change of kind or admin flag shows what comes back, and is confirmed against exactly that -----
def _user(client, w, uid):
    return next(u for u in client.get(f"{API}/users", headers=w["admin"]).json() if u["app_user_id"] == uid)


def _preview(client, w, uid, kind, admin):
    r = client.post(f"{API}/users/{uid}/access-change-preview", headers=w["admin"],
                    json={"user_kind": kind, "is_platform_admin": admin})
    assert r.status_code == 200, r.text
    return r.json()


def _store(db, pid, uid, level):
    """A stored membership the API would refuse today (a VIEWER's ADMIN row from before D-71 (7), or one held while
    the user is a platform admin)."""
    db.execute(text("INSERT INTO project_member (project_id, app_user_id, access_level, created_by) "
                    "VALUES (:p, :u, :l, :u)"), {"p": pid, "u": uid, "l": level})
    db.commit()


def test_a_kind_change_that_lifts_a_stored_membership_needs_its_preview(client, world, db):
    w = world
    rid, pid = w["users"]["reviewer"], w["p_solo"]
    _store(db, pid, rid, "ADMIN")
    restrict(client, w["admin"], pid)
    pv = _preview(client, w, rid, "USER", False)
    assert [(r["project_code"], r["level_before"], r["level_after"]) for r in pv["comes_back"]] == [
        ("SOLO", "VIEW", "ADMIN")]
    url, rv = f"{API}/users/{rid}/kind", _user(client, w, rid)["row_version"]
    assert client.patch(url, headers=w["admin"], json={"user_kind": "USER", "row_version": rv}).json()["detail"].startswith("This change gives back")
    rh = login(client, "reviewer@example.test")
    assert client.get(f"{API}/projects/{pid}", headers=rh).json()["my_access_level"] == "VIEW"   # nothing written
    rv = _user(client, w, rid)["row_version"]                     # signing in touched the user row
    r = client.patch(url, headers=w["admin"], json={"user_kind": "USER", "row_version": rv,
                                                     "confirm_hash": pv["confirm_hash"]})
    assert r.status_code == 200
    assert client.get(f"{API}/projects/{pid}", headers=rh).json()["my_access_level"] == "ADMIN"
    ev = db.execute(text("SELECT detail FROM audit_event WHERE event_type = 'USER_KIND_CHANGED'")).scalar_one()
    assert ev["comes_back"] == [pid]


def test_removing_admin_rights_shows_every_membership_that_comes_back_and_a_late_one_makes_it_stale(client, world, db):
    w = world
    oid, url = w["users"]["outsider"], f"{API}/users/{w['users']['outsider']}/platform-admin"
    restrict(client, w["admin"], w["p_solo"], {oid: "ADMIN"})
    assert _preview(client, w, oid, "USER", True)["comes_back"] == []        # granting admin revives nothing
    from sqlalchemy import create_engine
    from tests.conftest import OWNER_URL
    from tests.test_project_purge_record import promote
    owner = create_engine(OWNER_URL)
    try:
        promote(owner, oid)                                                   # slice 17: granted by an IS grant
    finally:
        owner.dispose()
    pv = _preview(client, w, oid, "USER", False)
    assert [(r["project_code"], r["level_before"], r["level_after"]) for r in pv["comes_back"]] == [
        ("SOLO", None, "ADMIN")]
    body = {"is_platform_admin": False, "rationale": "moved on", "user_kind": "USER",
            "row_version": _user(client, w, oid)["row_version"]}
    assert client.patch(url, headers=w["admin"], json=body).json()["detail"].startswith("This change gives back")            # no hash
    _store(db, w["p_fin"], oid, "ADMIN")                                                     # appears after the preview
    assert client.patch(url, headers=w["admin"], json={**body, "confirm_hash": pv["confirm_hash"]}).json()["detail"].startswith("This change gives back")
    oh = login(client, "outsider@example.test")
    assert client.get(f"{API}/projects/{w['p_solo']}", headers=oh).json()["my_access_level"] == "PLATFORM"
    pv = _preview(client, w, oid, "USER", False)
    assert [r["project_code"] for r in pv["comes_back"]] == ["FIN", "SOLO"]
    body["row_version"] = _user(client, w, oid)["row_version"]   # signing in touched the user row
    r = client.patch(url, headers=w["admin"], json={**body, "confirm_hash": pv["confirm_hash"]})
    assert r.status_code == 200
    assert client.get(f"{API}/projects/{w['p_fin']}", headers=oh).json()["my_access_level"] == "ADMIN"


def test_a_change_that_lifts_nothing_needs_no_preview(client, world):
    w = world
    eid = w["users"]["editor"]
    r = client.patch(f"{API}/users/{eid}/kind", headers=w["admin"],
                     json={"user_kind": "VIEWER", "row_version": _user(client, w, eid)["row_version"]})
    assert r.status_code == 200 and r.json()["user_kind"] == "VIEWER"
