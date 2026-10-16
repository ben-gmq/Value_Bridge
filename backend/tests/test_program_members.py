"""Access slice B — program members (D-71 (2)–(5), (8), D-72, D-73; docs/slice_access_b_plan.md). Grade 1: a silent
failure shows a restricted client project to someone outside it, or lets them change it.

Personas: the program CSR27 holds SALES and FIN; SOLO sits in a second program OTHER. Every refusal is checked as a
real user against the real guards; the level table is literal; the leak sweep runs as a member of the OTHER program.
Left uncovered on purpose: a two-connection race on the program lock (the lock order carries it, as slice A)."""
import pytest
from sqlalchemy import text

from tests.conftest import login, restrict
from tests.test_access import _seed_restricted, _sweep, preview_restrict

API = "/api/v1"


def padd(client, h, program_id, uid, level, expect=201):
    r = client.post(f"{API}/programs/{program_id}/members", headers=h, json={"user_id": uid, "access_level": level})
    assert r.status_code == expect, r.text
    return r.json()


def my_level(client, h, pid):
    r = client.get(f"{API}/projects/{pid}", headers=h)
    return r.json()["my_access_level"] if r.status_code == 200 else r.status_code


def move(client, w, program_id, pid, confirm=None):
    r = client.post(f"{API}/programs/{program_id}/projects", headers=w["admin"],
                    json={"project_id": pid, "confirm_hash": confirm})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def pg(client, world):
    """OTHER (same client) holds SOLO; SALES restricted; the owner is CSR27's program admin."""
    w = world
    other = client.post(f"{API}/programs", headers=w["admin"], json={
        "client_id": w["client_id"], "program_code": "OTHER", "program_name": "Other"}).json()
    pv = move(client, w, other["program_id"], w["p_solo"])
    move(client, w, other["program_id"], w["p_solo"], pv["preview_hash"])
    restrict(client, w["admin"], w["p_sales"])
    padd(client, w["admin"], w["program_id"], w["users"]["owner"], "ADMIN")
    return {**w, "other": other["program_id"], "ga": login(client, "owner@example.test"),
            "ed": login(client, "editor@example.test"), "rv": login(client, "reviewer@example.test"),
            "out": login(client, "outsider@example.test")}


# ---- the level table, through the API ---------------------------------------------------------------------------
# (kind, restricted, program level, direct level) → my_access_level, or 404. Literal; never computed by the code.
LEVELS = [
    ("USER", True, "VIEW", None, "VIEW"), ("USER", True, "EDIT", None, "EDIT"), ("USER", True, "ADMIN", None, "ADMIN"),
    ("USER", True, None, None, 404), ("USER", True, "VIEW", "EDIT", "EDIT"), ("USER", True, "ADMIN", "VIEW", "ADMIN"),
    ("USER", False, "VIEW", None, "EDIT"), ("USER", False, "ADMIN", None, "ADMIN"),
    ("VIEWER", True, "VIEW", None, "VIEW"), ("VIEWER", True, "ADMIN", None, "VIEW"),     # a stored row: capped
    ("VIEWER", False, "EDIT", None, "VIEW"),
]


@pytest.mark.parametrize("kind,restricted,program_level,direct,expected", LEVELS)
def test_the_level_table_with_a_program_role(client, world, db, kind, restricted, program_level, direct, expected):
    w = world
    who = "reviewer" if kind == "VIEWER" else "outsider"
    uid, pid = w["users"][who], w["p_fin"]
    for table, col, ref, level in (("program_member", "program_id", w["program_id"], program_level),
                                   ("project_member", "project_id", pid, direct)):
        if level:
            db.execute(text(f"INSERT INTO {table} ({col}, app_user_id, access_level, created_by) "
                            "VALUES (:r, :u, :l, :u)"), {"r": ref, "u": uid, "l": level})
    db.commit()
    if restricted:
        restrict(client, w["admin"], pid)
    assert my_level(client, login(client, f"{who}@example.test"), pid) == expected


# ---- reach: a program role opens its own program's restricted projects, never another's -------------------------------
def test_a_program_member_opens_its_restricted_projects_and_nothing_in_another_program(client, pg):
    w = pg
    padd(client, w["admin"], w["program_id"], w["users"]["outsider"], "EDIT")
    assert my_level(client, w["out"], w["p_sales"]) == "EDIT"                     # restricted, via CSR27
    restrict(client, w["admin"], w["p_solo"])
    assert my_level(client, w["out"], w["p_solo"]) == 404                         # OTHER: no role there
    assert w["program_id"] in {g["program_id"] for g in client.get(f"{API}/programs", headers=w["out"]).json()}
    # removing the program role takes it away on the next request
    m = client.get(f"{API}/programs/{w['program_id']}/members", headers=w["admin"]).json()
    row = next(x for x in m if x["user_id"] == w["users"]["outsider"])
    r = client.delete(f"{API}/program-members/{row['program_member_id']}", headers=w["ga"],
                      params={"row_version": row["row_version"]})
    assert r.status_code == 204
    assert my_level(client, w["out"], w["p_sales"]) == 404


def test_no_get_route_leaks_a_restricted_project_to_another_programs_member(client, pg):
    """The DR7-S2 sweep, as an admin of the OTHER program: a restricted project of CSR27 never shows."""
    w = pg
    pid, marks, ids = _seed_restricted(client, w)
    padd(client, w["admin"], w["other"], w["users"]["outsider"], "ADMIN")
    hits, called, _ = _sweep(client, w["out"], pid, ids)
    assert called > 200
    found = {p for p, _, _, body in hits if any(v in body for v in marks.values())}
    assert found == set()
    assert [(p, path, code) for p, path, code, _ in hits if f"/projects/{pid}" in path and code != 404] == []
    # positive control: the same sweep as a CSR27 member finds the project
    padd(client, w["admin"], w["program_id"], w["users"]["editor"], "VIEW")
    assert my_level(client, w["ed"], pid) == "VIEW"


# ---- who manages what ---------------------------------------------------------------------------------------------------
def test_a_program_admin_manages_the_program_and_its_projects_members_never_ftc_settings(client, pg):
    w = pg
    m = padd(client, w["ga"], w["program_id"], w["users"]["editor"], "ADMIN")         # appoints another admin
    assert m["effective_level"] == "ADMIN"
    r = client.post(f"{API}/projects/{w['p_sales']}/members", headers=w["ga"],
                    json={"user_id": w["users"]["outsider"], "access_level": "EDIT"})
    assert r.status_code == 201                                                         # D-71 (5): its projects
    assert client.put(f"{API}/projects/{w['p_sales']}/restriction", headers=w["ga"],
                      json={"is_restricted": False}).status_code == 403                 # FTC-only
    assert client.put(f"{API}/projects/{w['p_sales']}/components", headers=w["ga"],
                      json={"component_codes": []}).status_code == 403
    assert client.post(f"{API}/programs/{w['other']}/projects", headers=w["ga"],
                       json={"project_id": w["p_sales"]}).status_code == 403             # moving stays FTC-only
    # another program's members: a program it cannot see is 404, one it sees through an open project is 403
    restrict(client, w["admin"], w["p_solo"])
    assert client.get(f"{API}/programs/{w['other']}/members", headers=w["ga"]).status_code == 404


def test_plain_staff_and_editors_cannot_manage_program_members(client, pg):
    w = pg
    padd(client, w["admin"], w["program_id"], w["users"]["editor"], "EDIT")
    for who in ("ed", "rv", "out"):
        assert client.get(f"{API}/programs/{w['program_id']}/members", headers=w[who]).status_code == 403, who
        assert client.post(f"{API}/programs/{w['program_id']}/members", headers=w[who],
                           json={"user_id": w["users"]["outsider"], "access_level": "VIEW"}).status_code == 403, who
    row = client.get(f"{API}/programs/{w['program_id']}/members", headers=w["admin"]).json()[0]
    assert client.patch(f"{API}/program-members/{row['program_member_id']}", headers=w["ed"],
                        json={"access_level": "ADMIN", "row_version": row["row_version"]}).status_code == 403


def test_a_viewer_or_a_platform_admin_is_refused_and_a_duplicate_is_409(client, pg):
    w = pg
    for level in ("EDIT", "ADMIN"):
        padd(client, w["ga"], w["program_id"], w["users"]["reviewer"], level, expect=422)
    admin_id = client.get("/auth/me", headers=w["admin"]).json()["user"]["app_user_id"]
    padd(client, w["ga"], w["program_id"], admin_id, "VIEW", expect=422)
    padd(client, w["ga"], w["program_id"], w["users"]["owner"], "VIEW", expect=409)


def test_an_empty_programs_admin_can_open_it(client, world):
    w = world
    g = client.post(f"{API}/programs", headers=w["admin"], json={
        "client_id": w["client_id"], "program_code": "EMPTY", "program_name": "Empty"}).json()
    padd(client, w["admin"], g["program_id"], w["users"]["outsider"], "ADMIN")
    out = login(client, "outsider@example.test")
    r = client.get(f"{API}/programs/{g['program_id']}", headers=out)
    assert r.status_code == 200 and r.json()["my_access_level"] == "ADMIN"


# ---- who can open it: the Access list, restriction and move previews ---------------------------------------------------
def test_the_access_list_shows_program_access_and_a_direct_removal_keeps_it(client, pg):
    w = pg
    padd(client, w["admin"], w["program_id"], w["users"]["outsider"], "EDIT")
    direct = client.post(f"{API}/projects/{w['p_sales']}/members", headers=w["admin"],
                         json={"user_id": w["users"]["outsider"], "access_level": "VIEW"}).json()
    assert direct["also_via_program"] == "CSR27" and direct["effective_level"] == "EDIT" and direct["via"] == "PROGRAM"
    acc = client.get(f"{API}/projects/{w['p_sales']}/access", headers=w["ga"]).json()
    assert [(p["display_name"], p["effective_level"], p["via"]) for p in acc["program_members"]] == [
        ("Owner", "ADMIN", "PROGRAM")]
    client.delete(f"{API}/project-members/{direct['project_member_id']}", headers=w["admin"],
                  params={"row_version": direct["row_version"]})
    assert my_level(client, w["out"], w["p_sales"]) == "EDIT"                     # still in, through the program


def test_restricting_counts_program_members_as_keeping_access_and_a_late_one_is_409(client, pg):
    w = pg
    prev = preview_restrict(client, w, w["p_fin"]).json()
    assert [k["display_name"] for k in prev["keeps_via_program"]] == ["Owner"]
    assert "Owner" not in [x["display_name"] for x in prev["loses"]]
    padd(client, w["admin"], w["program_id"], w["users"]["outsider"], "VIEW")       # after the preview
    r = client.put(f"{API}/projects/{w['p_fin']}/restriction", headers=w["admin"],
                   json={"is_restricted": True, "confirm_hash": prev["confirm_hash"]})
    assert r.status_code == 409


def test_a_move_names_who_gains_and_loses_and_a_late_member_makes_it_stale(client, pg):
    w = pg
    restrict(client, w["admin"], w["p_solo"])
    padd(client, w["admin"], w["other"], w["users"]["outsider"], "EDIT")
    pv = move(client, w, w["program_id"], w["p_solo"])                            # OTHER → CSR27
    assert [g["display_name"] for g in pv["preview"]["gains"]] == ["Owner"]
    assert [x["display_name"] for x in pv["preview"]["loses"]] == ["Outsider"]
    padd(client, w["admin"], w["program_id"], w["users"]["editor"], "VIEW")
    r = client.post(f"{API}/programs/{w['program_id']}/projects", headers=w["admin"],
                    json={"project_id": w["p_solo"], "confirm_hash": pv["preview_hash"]})
    assert r.status_code == 409


# ---- the user-type preview counts program roles (sara 1g L9) -------------------------------------------------------------
def test_a_kind_change_lists_program_roles_that_come_back(client, pg, db):
    w = pg
    rid = w["users"]["reviewer"]
    db.execute(text("INSERT INTO program_member (program_id, app_user_id, access_level, created_by) "
                    "VALUES (:g, :u, 'ADMIN', :u)"), {"g": w["program_id"], "u": rid})       # stored before D-71 (7)
    db.commit()
    pv = client.post(f"{API}/users/{rid}/access-change-preview", headers=w["admin"],
                     json={"user_kind": "USER", "is_platform_admin": False}).json()
    assert {(r["project_code"], r["via"], r["level_after"]) for r in pv["comes_back"]} == {
        ("SALES", "PROGRAM", "ADMIN"), ("FIN", "PROGRAM", "ADMIN"), ("CSR27", "PROGRAM_ROLE", "ADMIN")}


def test_a_kind_change_lists_a_program_role_with_no_projects_behind_it(client, world, db):
    """sara B M1: an admin role over an EMPTY program still comes back only through the preview."""
    w = world
    g = client.post(f"{API}/programs", headers=w["admin"], json={
        "client_id": w["client_id"], "program_code": "EMPTY", "program_name": "Empty"}).json()
    rid = w["users"]["reviewer"]
    db.execute(text("INSERT INTO program_member (program_id, app_user_id, access_level, created_by) "
                    "VALUES (:g, :u, 'ADMIN', :u)"), {"g": g["program_id"], "u": rid})
    db.commit()
    pv = client.post(f"{API}/users/{rid}/access-change-preview", headers=w["admin"],
                     json={"user_kind": "USER", "is_platform_admin": False}).json()
    assert [(r["project_code"], r["via"], r["level_before"], r["level_after"]) for r in pv["comes_back"]] == [
        ("EMPTY", "PROGRAM_ROLE", "VIEW", "ADMIN")]
    rv = next(u for u in client.get(f"{API}/users", headers=w["admin"]).json() if u["app_user_id"] == rid)["row_version"]
    r = client.patch(f"{API}/users/{rid}/kind", headers=w["admin"], json={"user_kind": "USER", "row_version": rv})
    assert r.status_code == 409                                                 # no confirm: refused


# ---- sara B M2: another program's admin cannot touch this program's members -------------------------------------------
def test_another_programs_admin_cannot_change_or_remove_this_programs_members(client, pg):
    w = pg
    padd(client, w["admin"], w["other"], w["users"]["outsider"], "ADMIN")
    row = next(x for x in client.get(f"{API}/programs/{w['program_id']}/members", headers=w["admin"]).json()
               if x["user_id"] == w["users"]["owner"])
    url = f"{API}/program-members/{row['program_member_id']}"
    restrict(client, w["admin"], w["p_fin"])                                    # every CSR27 project restricted
    assert client.patch(url, headers=w["out"], json={"access_level": "VIEW", "row_version": row["row_version"]}
                        ).status_code == 404
    assert client.delete(url, headers=w["out"], params={"row_version": row["row_version"]}).status_code == 404
    pv = preview_restrict(client, w, w["p_fin"], False).json()                   # FIN open again: CSR27 visible
    client.put(f"{API}/projects/{w['p_fin']}/restriction", headers=w["admin"],
               json={"is_restricted": False, "confirm_hash": pv["confirm_hash"]})
    assert client.patch(url, headers=w["out"], json={"access_level": "VIEW", "row_version": row["row_version"]}
                        ).status_code == 403
    assert client.delete(url, headers=w["out"], params={"row_version": row["row_version"]}).status_code == 403
    assert client.get(f"{API}/programs/{w['program_id']}/members", headers=w["out"]).status_code == 403
    assert client.delete(url, headers=w["ed"], params={"row_version": row["row_version"]}).status_code == 403


# ---- D-73 and the audit --------------------------------------------------------------------------------------------------
def test_removing_a_program_admin_keeps_the_project_admins_they_appointed(client, pg, db):
    w = pg
    client.post(f"{API}/projects/{w['p_sales']}/members", headers=w["ga"],
                json={"user_id": w["users"]["editor"], "access_level": "ADMIN"})
    row = next(x for x in client.get(f"{API}/programs/{w['program_id']}/members", headers=w["admin"]).json()
               if x["user_id"] == w["users"]["owner"])
    client.delete(f"{API}/program-members/{row['program_member_id']}", headers=w["admin"],
                  params={"row_version": row["row_version"]})
    assert my_level(client, w["ed"], w["p_sales"]) == "ADMIN"
    types = db.execute(text("SELECT event_type FROM audit_event WHERE target_table = 'program_member' "
                            "ORDER BY audit_event_id")).scalars().all()
    assert types == ["PROGRAM_MEMBER_ADDED", "PROGRAM_MEMBER_REMOVED"]


def test_a_project_created_in_a_program_names_the_members_it_admits(client, pg, db):
    w = pg
    r = client.post(f"{API}/projects", headers=w["admin"], json={
        "client_id": w["client_id"], "project_code": "NEW", "project_name": "New", "program_id": w["program_id"],
        "component_codes": ["ISSUE"], "is_restricted": True})
    assert r.status_code == 201
    detail = db.execute(text("SELECT detail FROM audit_event WHERE event_type = 'PROJECT_CREATED' "
                             "AND project_id = :p"), {"p": r.json()["project_id"]}).scalar_one()
    assert detail["program_members_admitted"] == [{"user_id": w["users"]["owner"], "level": "ADMIN"}]
    assert my_level(client, w["ga"], r.json()["project_id"]) == "ADMIN"
