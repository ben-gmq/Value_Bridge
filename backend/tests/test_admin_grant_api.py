"""Slice 17 through the API (spec §9, §10 criteria 1–4, 6, 7, 10, 12). The database refuses every one of these on its
own (test_admin_grant_record, test_app_user_admin_guard); here the routes answer with the right code and words, and a
proper approval makes the admin in one step."""
import pytest
from sqlalchemy import create_engine, select

from models import AuditEvent
from services import admin_grant
from tests.admin_team import owner_user, run, team
from tests.conftest import OWNER_URL, login

API = "/api/v1"


@pytest.fixture
def owner():
    eng = create_engine(OWNER_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def t(client, world, owner):
    """a1 the setup admin; a2 granted at a1's request; a3 at a2's — (a1, a3) the only independent pair."""
    tm = team(owner, world)
    return {**tm, "h1": world["admin"], "h2": login(client, "a2@example.test"), "h3": login(client, "a3@example.test")}


def ask(client, h, uid, reason="Cover for the Q1 engagement"):
    return client.post(f"{API}/users/{uid}/grant-requests", headers=h, json={"reason": reason})


def decide(client, h, g, what="approve", **extra):
    return client.post(f"{API}/grant-requests/{g['grant_id']}/{what}", headers=h,
                       json={"row_version": g["row_version"], **extra})


def is_admin(owner, uid) -> bool:
    return run(owner, "SELECT is_platform_admin FROM app_user WHERE app_user_id = :u", u=uid)[0]


def test_a_request_needs_an_admin_a_reason_and_a_user_who_is_not_one(client, t, owner):
    """Criterion 1."""
    tgt = owner_user(owner, "tgt@example.test")
    assert ask(client, login(client, "editor@example.test"), tgt).status_code == 403
    assert ask(client, t["h1"], tgt, reason="  ").status_code == 422
    r = ask(client, t["h1"], tgt)
    assert r.status_code == 201 and r.json()["state"] == "OPEN" and not is_admin(owner, tgt)
    assert r.json()["target_email"] == "tgt@example.test" and r.json()["target_has_signed_in"] is False
    again = ask(client, t["h3"], tgt)
    assert again.status_code == 409 and "already been requested" in again.json()["detail"]
    assert ask(client, t["h1"], t["a2"]).status_code == 409                            # already an admin
    assert ask(client, t["h1"], 99999).status_code == 404


def test_four_eyes_independence_then_one_step_makes_the_admin(client, t, owner, db):
    """Criteria 2, 3, 4."""
    tgt = owner_user(owner, "tgt@example.test")
    g = ask(client, t["h1"], tgt).json()
    assert decide(client, t["h1"], g).json()["detail"].startswith("four eyes")
    no = decide(client, t["h2"], g)                                                    # a1 asked for a2's rights
    assert no.status_code == 409 and "not independent" in no.json()["detail"]
    ok = decide(client, t["h3"], g)
    assert ok.status_code == 200 and ok.json()["state"] == "APPROVED" and ok.json()["approved_by"] == "A3"
    assert is_admin(owner, tgt)
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PLATFORM_ADMIN_GRANTED",
                                             AuditEvent.target_id == tgt)).one()
    assert ev.app_user_id == t["a3"] and ev.detail["requested_by"] == t["a1"]
    assert decide(client, t["h3"], {**g, "row_version": ok.json()["row_version"]}).status_code == 409   # decided


def test_the_creator_of_an_account_neither_requests_nor_approves_its_rights(client, t, owner):
    """Criterion 10 (AR-24): editor was created by a1; an account a3 creates through the API is a3's."""
    r = ask(client, t["h1"], t["users"]["editor"])
    assert r.status_code == 409 and "AR-24" in r.json()["detail"]
    made = client.post(f"{API}/users", headers=t["h3"], json={
        "email": "made3@example.test", "display_name": "Made3", "initial_password": "correct-horse-battery",
        "user_kind": "USER"}).json()["app_user_id"]
    g = ask(client, t["h1"], made).json()
    no = decide(client, t["h3"], g)
    assert no.status_code == 409 and "created this account" in no.json()["detail"]


def test_reject_and_cancel_close_it_and_the_user_can_be_asked_for_again(client, t, owner):
    """Criterion 6."""
    tgt = owner_user(owner, "tgt@example.test")
    g = ask(client, t["h1"], tgt).json()
    assert decide(client, t["h1"], g, "reject", reason="no").status_code == 409        # the requester cancels instead
    assert decide(client, t["h2"], g, "reject", reason=" ").status_code == 422
    r = decide(client, t["h2"], g, "reject", reason="Not on this engagement")
    assert r.status_code == 200 and r.json()["state"] == "REJECTED"
    g2 = ask(client, t["h1"], tgt).json()
    assert decide(client, t["h1"], g2, "cancel").json()["state"] == "CANCELLED"
    rows = client.get(f"{API}/admin/grant-requests", headers=t["h2"]).json()
    assert [x["state"] for x in rows] == ["CANCELLED", "REJECTED"]
    assert client.get(f"{API}/admin/grant-requests", headers=login(client, "editor@example.test")).status_code == 403


def test_open_requests_come_first_with_their_age_and_who_made_the_account(client, t, owner):
    """Criterion 13's data: the card shows the target's email, who created the account and when, and the age."""
    old = ask(client, t["h1"], owner_user(owner, "old@example.test")).json()
    run(owner, "ALTER TABLE platform_admin_grant DISABLE TRIGGER trg_platform_admin_grant_guard")
    try:                                                                               # test-only: an old request
        run(owner, "UPDATE platform_admin_grant SET requested_at = now() - interval '9 days' "
                   "WHERE platform_admin_grant_id = :g", g=old["grant_id"])
    finally:
        run(owner, "ALTER TABLE platform_admin_grant ENABLE TRIGGER trg_platform_admin_grant_guard")
    made = client.post(f"{API}/users", headers=t["h3"], json={
        "email": "new@example.test", "display_name": "New", "initial_password": "correct-horse-battery",
        "user_kind": "USER"}).json()["app_user_id"]
    ask(client, t["h1"], made)
    rows = client.get(f"{API}/admin/grant-requests", headers=t["h1"]).json()
    assert [(x["target_email"], x["age_days"], x["target_created_by"]) for x in rows] == [
        ("old@example.test", 9, None), ("new@example.test", 0, "A3")]


def test_the_weekly_check_reads_its_lines_from_the_record(client, t, owner, db):
    """Criterion 12 (§7, N3, N4, N5)."""
    g = ask(client, t["h1"], owner_user(owner, "old@example.test")).json()
    run(owner, "ALTER TABLE platform_admin_grant DISABLE TRIGGER trg_platform_admin_grant_guard")
    try:
        run(owner, "UPDATE platform_admin_grant SET requested_at = now() - interval '9 days' "
                   "WHERE platform_admin_grant_id = :g", g=g["grant_id"])
    finally:
        run(owner, "ALTER TABLE platform_admin_grant ENABLE TRIGGER trg_platform_admin_grant_guard")
    lines = admin_grant.weekly_admin_lines(db)
    assert lines["open_over_7_days"] == [g["grant_id"]]
    assert lines["live_admins_below_two"] is False and lines["admins_without_a_grant"] == []
    got = sorted((x["origin"], x["backdated"]) for x in lines["owner_grants_last_7_days"])
    assert got == [("BOOTSTRAP", False), ("LEGACY", True), ("LEGACY", True)]          # a1's setup; a2, a3 by IS,
                                                                                        # backdated on a test DB (N4)
    assert lines["legacy_without_asker"] == []


def test_every_weekly_line_reports_what_it_names(client, t, owner, db):
    """sara M-2, criterion 12: each line made non-empty by the event it names — an approval, an admin with no record
    (0076 skipped them), a LEGACY row with no asker (backfilled), a removal, a deactivation, and fewer than two."""
    from tests.test_app_user_admin_guard import unrecorded_admin
    tgt = owner_user(owner, "tgt@example.test")
    g = ask(client, t["h1"], tgt).json()
    decide(client, t["h3"], g)
    skipped = unrecorded_admin(owner, "skipped@example.test")
    asker_less = unrecorded_admin(owner, "backfilled@example.test")
    run(owner, "ALTER TABLE platform_admin_grant DISABLE TRIGGER trg_platform_admin_grant_guard")
    try:                                                         # test-only: what 0076's backfill writes
        lg = run(owner, "INSERT INTO platform_admin_grant (grant_origin, target_user_id, reason, operator_name, "
                        "source_audit_event_id, requested_at, approved_at, approved_xact) VALUES ('LEGACY', :u, 'x', "
                        "'migration 0076', 1, now(), now(), pg_current_xact_id()) RETURNING platform_admin_grant_id",
                 u=asker_less)[0]
    finally:
        run(owner, "ALTER TABLE platform_admin_grant ENABLE TRIGGER trg_platform_admin_grant_guard")
    rv = next(u for u in client.get(f"{API}/users", headers=t["h1"]).json() if u["app_user_id"] == tgt)["row_version"]
    assert client.patch(f"{API}/users/{tgt}/platform-admin", headers=t["h1"], json={
        "is_platform_admin": False, "rationale": "Moved on", "row_version": rv, "user_kind": "USER"}).status_code == 200
    assert client.patch(f"{API}/users/{t['a2']}/deactivate", headers=t["h1"]).status_code == 200
    db.expire_all()
    lines = admin_grant.weekly_admin_lines(db)
    assert lines["approved_last_7_days"] == [g["grant_id"]]
    assert lines["admins_without_a_grant"] == [skipped]
    assert lines["legacy_without_asker"] == [lg]
    assert lines["admins_removed_last_7_days"] == [tgt]
    assert lines["admins_deactivated_last_7_days"] == [t["a2"]]
    assert lines["live_admins_below_two"] is False
    for uid in (t["a3"], skipped, asker_less):
        run(owner, "UPDATE app_user SET is_active = false, deleted_at = now() WHERE app_user_id = :u", u=uid)
    assert admin_grant.weekly_admin_lines(db)["live_admins_below_two"] is True        # a1 alone