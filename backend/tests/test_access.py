"""Visibility and the one-grant rule (§7.8, §7.10, D-32, Q10, Q16, R2-S2/S4). Gate 2."""
from tests.conftest import login


def grant(client, headers, project_id, user_id, role):
    return client.post(f"/api/v1/projects/{project_id}/access", headers=headers,
                       json={"user_id": user_id, "project_role_code": role})


def program_grant(client, w, user_id, role):
    return client.post(f"/api/v1/programs/{w['program_id']}/access", headers=w["admin"],
                       json={"user_id": user_id, "project_role_code": role})


def visible(client, headers):
    return sorted(p["project_code"] for p in client.get("/api/v1/projects", headers=headers).json())


def test_gate2_grant_and_see(client, world):
    """Gate 2 exit: grant a colleague access, they see exactly that project, an outsider sees
    none and gets 404 — not 403 — on the project URL."""
    w = world
    assert grant(client, w["admin"], w["p_solo"], w["users"]["editor"], "EDITOR").status_code == 201
    editor = login(client, "editor@example.test")
    assert visible(client, editor) == ["SOLO"]
    outsider = login(client, "outsider@example.test")
    assert visible(client, outsider) == []
    assert client.get(f"/api/v1/projects/{w['p_solo']}", headers=outsider).status_code == 404
    assert client.get(f"/api/v1/projects/{w['p_solo']}", headers=editor).status_code == 200


def test_program_grant_sees_every_project_in_program(client, world):
    w = world
    assert program_grant(client, w, w["users"]["reviewer"], "REVIEWER").status_code == 201
    rev = login(client, "reviewer@example.test")
    assert visible(client, rev) == ["FIN", "SALES"]
    assert client.get(f"/api/v1/projects/{w['p_solo']}", headers=rev).status_code == 404
    # a project added to the program later is visible on the next request (D-32)
    r = client.post("/api/v1/projects", headers=w["admin"], json={
        "client_id": w["client_id"], "project_code": "HR", "project_name": "HR",
        "program_id": w["program_id"]})
    assert r.status_code == 201
    assert visible(client, rev) == ["FIN", "HR", "SALES"]


def test_project_grant_sees_no_program_rollup(client, world):
    """R2-S2: a project grant inside a program must not reach the program's roll-ups."""
    w = world
    grant(client, w["admin"], w["p_sales"], w["users"]["editor"], "EDITOR")
    editor = login(client, "editor@example.test")
    assert client.get(f"/api/v1/programs/{w['program_id']}", headers=editor).status_code == 404
    assert client.get(f"/api/v1/programs/{w['program_id']}/projects",
                      headers=editor).status_code == 404
    assert client.get("/api/v1/programs", headers=editor).json() == []


def test_one_grant_per_user(client, world):
    """R2-S4: a second scope is a 409 naming the first; the same scope is a role change."""
    w = world
    assert grant(client, w["admin"], w["p_solo"], w["users"]["editor"], "EDITOR").status_code == 201
    r = grant(client, w["admin"], w["p_sales"], w["users"]["editor"], "EDITOR")
    assert r.status_code == 409 and "SOLO" in r.json()["detail"]
    # a role change on the same scope must carry row_version (D-6, sara M4)
    r = grant(client, w["admin"], w["p_solo"], w["users"]["editor"], "REVIEWER")
    assert r.status_code == 422
    access = client.get(f"/api/v1/projects/{w['p_solo']}/access", headers=w["admin"]).json()
    row = next(a for a in access if a["user_id"] == w["users"]["editor"])
    r = client.post(f"/api/v1/projects/{w['p_solo']}/access", headers=w["admin"], json={
        "user_id": w["users"]["editor"], "project_role_code": "REVIEWER", "row_version": row["row_version"]})
    assert r.status_code == 201
    stale = client.post(f"/api/v1/projects/{w['p_solo']}/access", headers=w["admin"], json={
        "user_id": w["users"]["editor"], "project_role_code": "OWNER", "row_version": row["row_version"]})
    assert stale.status_code == 409
    access = client.get(f"/api/v1/projects/{w['p_solo']}/access", headers=w["admin"]).json()
    editor_rows = [a for a in access if a["user_id"] == w["users"]["editor"]]
    assert [a["project_role_code"] for a in editor_rows] == ["REVIEWER"]


def test_program_owner_grants_inside_not_outside(client, world):
    """Q16: a program OWNER may grant one project inside their program — never outside it,
    and never the program itself."""
    w = world
    program_grant(client, w, w["users"]["owner"], "OWNER")
    owner = login(client, "owner@example.test")
    assert grant(client, owner, w["p_fin"], w["users"]["editor"], "EDITOR").status_code == 201
    assert grant(client, owner, w["p_solo"], w["users"]["reviewer"], "REVIEWER").status_code == 404
    r = client.post(f"/api/v1/programs/{w['program_id']}/access", headers=owner,
                    json={"user_id": w["users"]["reviewer"], "project_role_code": "REVIEWER"})
    assert r.status_code == 403


def test_editor_cannot_grant_and_admin_needs_no_grant(client, world):
    w = world
    grant(client, w["admin"], w["p_solo"], w["users"]["editor"], "EDITOR")
    editor = login(client, "editor@example.test")
    assert grant(client, editor, w["p_solo"], w["users"]["reviewer"], "REVIEWER").status_code == 403
    admin_id = client.get("/auth/me", headers=w["admin"]).json()["user"]["app_user_id"]
    assert grant(client, w["admin"], w["p_solo"], admin_id, "OWNER").status_code == 422


def test_effective_access_lists_program_derived(client, world):
    w = world
    program_grant(client, w, w["users"]["reviewer"], "REVIEWER")
    grant(client, w["admin"], w["p_sales"], w["users"]["editor"], "EDITOR")
    rows = client.get(f"/api/v1/projects/{w['p_sales']}/access", headers=w["admin"]).json()
    sources = {(r["display_name"], r["source"]) for r in rows}
    assert ("Editor", "PROJECT") in sources
    assert ("Reviewer", "PROGRAM") in sources
    assert ("Admin", "PLATFORM_ADMIN") in sources


def test_revoke_then_invisible_and_not_restorable(client, world):
    w = world
    g = grant(client, w["admin"], w["p_solo"], w["users"]["editor"], "EDITOR").json()
    editor = login(client, "editor@example.test")
    assert client.delete(f"/api/v1/access/{g['user_access_grant_id']}", headers=editor
                         ).status_code == 403     # EDITOR cannot revoke
    assert client.delete(f"/api/v1/access/{g['user_access_grant_id']}", headers=w["admin"]
                         ).status_code == 200
    assert visible(client, editor) == []
    # a new grant is a new row; the revoked one stays revoked
    assert grant(client, w["admin"], w["p_fin"], w["users"]["editor"], "EDITOR").status_code == 201


def test_revoke_route_is_404_for_other_projects(client, world):
    """object_guard: an OWNER elsewhere cannot even discover another project's grant ids."""
    w = world
    g = grant(client, w["admin"], w["p_beta"], w["users"]["editor"], "EDITOR").json()
    grant(client, w["admin"], w["p_solo"], w["users"]["owner"], "OWNER")
    owner = login(client, "owner@example.test")
    assert client.delete(f"/api/v1/access/{g['user_access_grant_id']}", headers=owner
                         ).status_code == 404


def test_deactivation_takes_effect_on_next_request(client, world):
    w = world
    grant(client, w["admin"], w["p_solo"], w["users"]["editor"], "EDITOR")
    editor = login(client, "editor@example.test")
    assert client.get("/api/v1/projects", headers=editor).status_code == 200
    r = client.patch(f"/api/v1/users/{w['users']['editor']}/deactivate", headers=w["admin"])
    assert r.status_code == 200
    assert client.get("/api/v1/projects", headers=editor).status_code == 401


def test_move_project_needs_preview_then_confirm(client, world):
    """R2-S3: step 1 previews who gains access and writes nothing; step 2 applies it."""
    w = world
    program_grant(client, w, w["users"]["reviewer"], "REVIEWER")
    rev = login(client, "reviewer@example.test")
    url = f"/api/v1/programs/{w['program_id']}/projects"
    pre = client.post(url, headers=w["admin"], json={"project_id": w["p_solo"]}).json()
    assert pre["applied"] is False
    assert [g["display_name"] for g in pre["preview"]["gains"]] == ["Reviewer"]
    assert "SOLO" not in visible(client, rev)
    r = client.post(url, headers=w["admin"],
                    json={"project_id": w["p_solo"], "confirm_hash": pre["preview_hash"]})
    assert r.json()["applied"] is True
    assert "SOLO" in visible(client, rev)
    # another client's project can never join
    r = client.post(url, headers=w["admin"], json={"project_id": w["p_beta"]})
    assert r.status_code == 422


def test_non_admin_cannot_create_projects_or_move(client, world):
    w = world
    grant(client, w["admin"], w["p_solo"], w["users"]["owner"], "OWNER")
    owner = login(client, "owner@example.test")
    r = client.post("/api/v1/projects", headers=owner, json={
        "client_id": w["client_id"], "project_code": "X", "project_name": "X"})
    assert r.status_code == 403
    r = client.post(f"/api/v1/programs/{w['program_id']}/projects", headers=owner,
                    json={"project_id": w["p_solo"]})
    assert r.status_code == 403


def test_admin_gets_404_for_missing_program_and_wrong_program_detach(client, world):
    """sara M2, M1."""
    w = world
    assert client.get("/api/v1/programs/9999", headers=w["admin"]).status_code == 404
    assert client.get("/api/v1/programs/9999/projects", headers=w["admin"]).status_code == 404
    other = client.post("/api/v1/programs", headers=w["admin"], json={
        "client_id": w["client_id"], "program_code": "OTHER", "program_name": "Other"}).json()
    r = client.delete(f"/api/v1/programs/{other['program_id']}/projects/{w['p_sales']}",
                      headers=w["admin"])
    assert r.status_code == 404      # SALES is not in OTHER — detaching must not happen


def test_revoke_records_who_and_when(client, world, db):
    """sara M3: deleted_at and deleted_by are both set."""
    from sqlalchemy import text
    w = world
    g = grant(client, w["admin"], w["p_solo"], w["users"]["editor"], "EDITOR").json()
    client.delete(f"/api/v1/access/{g['user_access_grant_id']}", headers=w["admin"])
    row = db.execute(text("SELECT deleted_at, deleted_by FROM user_access_grant "
                          "WHERE user_access_grant_id = :g"), {"g": g["user_access_grant_id"]}).one()
    assert row.deleted_at is not None and row.deleted_by is not None


def test_platform_admin_is_a_separate_audited_act(client, world):
    """sara M7: no admin flag on create; promotion needs a reason and a clean grant state."""
    w = world
    r = client.post("/api/v1/users", headers=w["admin"], json={
        "email": "sneaky@example.test", "display_name": "Sneaky", "initial_password": "correct-horse-battery",
        "is_platform_admin": True})
    assert r.status_code == 201 and r.json()["is_platform_admin"] is False
    uid, rv = r.json()["app_user_id"], r.json()["row_version"]
    url = f"/api/v1/users/{uid}/platform-admin"
    assert client.patch(url, headers=w["admin"], json={
        "is_platform_admin": True, "rationale": "", "row_version": rv}).status_code == 422
    ok = client.patch(url, headers=w["admin"], json={
        "is_platform_admin": True, "rationale": "Second admin for cover", "row_version": rv})
    assert ok.status_code == 200 and ok.json()["is_platform_admin"] is True
    grant(client, w["admin"], w["p_solo"], w["users"]["editor"], "EDITOR")
    ed = client.get("/api/v1/users", headers=w["admin"]).json()
    ed = next(u for u in ed if u["app_user_id"] == w["users"]["editor"])
    r = client.patch(f"/api/v1/users/{ed['app_user_id']}/platform-admin", headers=w["admin"], json={
        "is_platform_admin": True, "rationale": "x", "row_version": ed["row_version"]})
    assert r.status_code == 409      # holds a grant — revoke first
