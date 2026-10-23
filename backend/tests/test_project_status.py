"""A project's status and its two-year archive clock; reopening and retiring (slice 16: AR-8, AR-10, U2, Q-90).
Grade 2 — a wrong date starts or stops the archive clock early or late, which the weekly report and the Removals tab
show; so each rule is proven through the API, the platform-admin-only reopen included."""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text

from services.baseline import local_today
from tests.conftest import OWNER_URL, login

API = "/api/v1"


@pytest.fixture
def owner():
    eng = create_engine(OWNER_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def w(client, world):
    return {**world, "ed": login(client, "editor@example.test"), "rv": login(client, "reviewer@example.test"),
            "p": world["p_solo"]}


def project(client, w, h=None):
    r = client.get(f"{API}/projects/{w['p']}", headers=h or w["admin"])
    assert r.status_code == 200, r.text
    return r.json()


def set_status(client, w, code, h=None, expect=200):
    r = client.patch(f"{API}/projects/{w['p']}/status", headers=h or w["ed"],
                     json={"status_code": code, "row_version": project(client, w)["row_version"]})
    assert r.status_code == expect, r.text
    return r.json()


def events(owner, kind):
    with owner.connect() as c:
        return c.execute(text("SELECT detail FROM audit_event WHERE event_type = :k ORDER BY audit_event_id"),
                         {"k": kind}).scalars().all()


def test_closing_starts_the_clock_today_and_open_statuses_have_none(client, w, owner):
    """AR-8: an editor closes the project; closed_on is today (ICT). Moving between open statuses keeps it empty."""
    assert project(client, w)["closed_on"] is None and project(client, w)["status_behaviour"] == "OPEN"
    assert set_status(client, w, "ACTIVE")["closed_on"] is None
    p = set_status(client, w, "CLOSED")
    assert p["status_behaviour"] == "CLOSED" and p["closed_on"] == local_today().isoformat()
    assert events(owner, "PROJECT_STATUS_CHANGED")[-1] == {"from": "ACTIVE", "to": "CLOSED",
                                                           "closed_on": local_today().isoformat()}


def test_only_a_platform_admin_reopens_and_reopening_clears_the_clock(client, w, owner):
    """U2: leaving a closed status is the reminder's off-switch — refused to an editor, a platform admin's to do."""
    set_status(client, w, "CLOSED")
    r = client.patch(f"{API}/projects/{w['p']}/status", headers=w["ed"],
                     json={"status_code": "ACTIVE", "row_version": project(client, w)["row_version"]})
    assert r.status_code == 403 and "platform admin" in r.json()["detail"]
    reopen = f"{API}/projects/{w['p']}/reopen"
    body = {"status_code": "ACTIVE", "row_version": project(client, w)["row_version"]}
    assert client.post(reopen, headers=w["ed"], json=body).status_code == 403
    assert client.post(reopen, headers=w["admin"], json={**body, "status_code": "CLOSED"}).status_code == 422
    r = client.post(reopen, headers=w["admin"], json=body)
    assert r.status_code == 200 and r.json()["closed_on"] is None and r.json()["status_behaviour"] == "OPEN"
    assert events(owner, "PROJECT_REOPENED")[-1]["was_closed_on"] == local_today().isoformat()
    again = client.post(reopen, headers=w["admin"], json={**body, "row_version": r.json()["row_version"]})
    assert again.status_code == 409                                                    # not closed any more


def test_closing_again_restarts_the_clock(client, w, owner):
    """AR-8: after a reopen, closing again records the new day, not the old one."""
    set_status(client, w, "CLOSED")
    with owner.begin() as c:                                                           # test-only: closed long ago
        c.execute(text("UPDATE project SET closed_on = :d WHERE project_id = :p"),
                  {"d": local_today() - timedelta(days=800), "p": w["p"]})
    client.post(f"{API}/projects/{w['p']}/reopen", headers=w["admin"],
                json={"status_code": "ACTIVE", "row_version": project(client, w)["row_version"]})
    assert set_status(client, w, "CLOSED")["closed_on"] == local_today().isoformat()


def test_status_writes_need_edit_rights_a_known_code_and_a_fresh_row(client, w):
    assert set_status(client, w, "CLOSED", h=w["rv"], expect=403)
    r = client.patch(f"{API}/projects/{w['p']}/status", headers=w["ed"], json={"status_code": "NOPE",
                                                                               "row_version": project(client, w)["row_version"]})
    assert r.status_code == 400
    r = client.patch(f"{API}/projects/{w['p']}/status", headers=w["ed"], json={"status_code": "ACTIVE",
                                                                               "row_version": 999})
    assert r.status_code == 409
    set_status(client, w, "ACTIVE")
    assert "already" in set_status(client, w, "ACTIVE", expect=409)["detail"]


def test_retiring_an_open_project_closes_it_first_so_its_clock_starts(client, w, owner):
    """AR-10 / Q-90: retire = closed (closed_on today) + soft-deleted, in one transaction; platform admin only."""
    url = f"{API}/projects/{w['p']}/retire"
    rv = project(client, w)["row_version"]
    assert client.post(url, headers=w["ed"], json={"confirm_text": "SOLO", "row_version": rv}).status_code == 403
    assert client.post(url, headers=w["admin"], json={"confirm_text": "SOL", "row_version": rv}).status_code == 422
    r = client.post(url, headers=w["admin"], json={"confirm_text": "SOLO", "row_version": rv})
    assert r.status_code == 200 and r.json()["closed_on"] == local_today().isoformat()
    with owner.connect() as c:
        row = c.execute(text("SELECT is_active, status_behaviour, closed_on, deleted_by IS NOT NULL FROM project "
                             "WHERE project_id = :p"), {"p": w["p"]}).one()
    assert tuple(row) == (False, "CLOSED", local_today(), True)
    assert events(owner, "PROJECT_RETIRED")[-1]["to"] == "CLOSED"


def test_retiring_is_refused_by_name_while_the_project_has_members(client, w, owner):
    """sara HIGH-1: a live member holds the project live (fk_pm_live_project); the refusal names them, before anything
    changes — the status stays as it was."""
    from tests.conftest import restrict
    restrict(client, w["admin"], w["p"], {w["users"]["editor"]: "EDIT"})
    r = client.post(f"{API}/projects/{w['p']}/retire", headers=w["admin"],
                    json={"confirm_text": "SOLO", "row_version": project(client, w)["row_version"]})
    assert r.status_code == 409 and "Remove the project's members first (Editor)" in r.json()["detail"]
    assert project(client, w)["closed_on"] is None


def test_a_retired_project_takes_no_further_status_change(client, w, owner):
    """sara MEDIUM-1: reopening a retired project would stop its clock for good, so it never came due (AR-10)."""
    rv = project(client, w)["row_version"]
    retired = client.post(f"{API}/projects/{w['p']}/retire", headers=w["admin"],
                          json={"confirm_text": "SOLO", "row_version": rv}).json()
    for path, body in (("reopen", {"status_code": "ACTIVE"}), ("retire", {"confirm_text": "SOLO"})):
        r = client.post(f"{API}/projects/{w['p']}/{path}", headers=w["admin"],
                        json={**body, "row_version": retired["row_version"]})
        assert r.status_code == 409 and "retired" in r.json()["detail"], (path, r.text)
    with owner.connect() as c:
        assert c.execute(text("SELECT closed_on FROM project WHERE project_id = :p"), {"p": w["p"]}).scalar() \
            == local_today()


def test_a_stale_editor_reopening_is_told_who_may_before_being_told_to_refresh(client, w):
    """sara LOW-1: 404 → 403 → 409."""
    set_status(client, w, "CLOSED")
    r = client.patch(f"{API}/projects/{w['p']}/status", headers=w["ed"], json={"status_code": "ACTIVE", "row_version": 1})
    assert r.status_code == 403


def test_retiring_a_closed_project_keeps_its_date(client, w, owner):
    set_status(client, w, "CLOSED")
    with owner.begin() as c:
        c.execute(text("UPDATE project SET closed_on = :d WHERE project_id = :p"), {"d": date(2024, 3, 1), "p": w["p"]})
    r = client.post(f"{API}/projects/{w['p']}/retire", headers=w["admin"],
                    json={"confirm_text": "SOLO", "row_version": project(client, w)["row_version"]})
    assert r.status_code == 200 and r.json()["closed_on"] == "2024-03-01"


def test_retiring_is_refused_when_no_closed_status_is_live(client, w, owner):
    """AR-10: the retire needs a closed status to move the project to."""
    with owner.begin() as c:                                                           # test-only: the library's
        c.execute(text("UPDATE code_master SET is_active = false, deleted_at = now() "     # CLOSED code retired
                       "WHERE category = 'PROJECT_STATUS' AND behaviour_code = 'CLOSED'"))
    r = client.post(f"{API}/projects/{w['p']}/retire", headers=w["admin"],
                    json={"confirm_text": "SOLO", "row_version": project(client, w)["row_version"]})
    assert r.status_code == 409 and "No live closed" in r.json()["detail"]
    assert project(client, w)["closed_on"] is None


def test_a_project_with_an_open_removal_request_refuses_all_three(client, w, owner):
    """Q-73: while a removal request is open, the status, the reopen and the retire are writes like any other."""
    from tests.admin_team import owner_user
    from tests.test_project_purge_record import promote
    promote(owner, owner_user(owner, "a2.purge@example.test"))
    r = client.post(f"{API}/projects/{w['p']}/purge-requests", headers=w["admin"],
                    json={"kind": "DELETE", "reason": "Contract clause 9.2", "confirm_text": "ACME/SOLO"})
    assert r.status_code == 201, r.text
    rv = project(client, w)["row_version"]
    for method, path, body in (("PATCH", "status", {"status_code": "CLOSED", "row_version": rv}),
                               ("POST", "reopen", {"status_code": "ACTIVE", "row_version": rv}),
                               ("POST", "retire", {"confirm_text": "SOLO", "row_version": rv})):
        got = client.request(method, f"{API}/projects/{w['p']}/{path}", headers=w["admin"], json=body)
        assert got.status_code == 409 and got.headers.get("X-VB-Error") == "PURGE_PENDING", (path, got.text)
