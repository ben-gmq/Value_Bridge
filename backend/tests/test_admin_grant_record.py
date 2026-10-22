"""Slice 17, migration 0076: the platform-admin grant record (schema rev 3 §3, §6; spec §10 criteria 1–4, 6, 9–11).
Grade 1 — a wrong answer makes someone an admin over every client's data, so each control is proven at the database,
for the app role and the owner, with the creator rule (AR-24) on every path."""
import re

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from database import engine as app_engine
from tests.admin_team import legacy, owner_user, run, team
from tests.conftest import OWNER_URL

REQUEST = ("INSERT INTO platform_admin_grant (grant_origin, target_user_id, reason, requested_by_user_id) "
           "VALUES ('REQUEST', :t, :r, :by) RETURNING platform_admin_grant_id")
APPROVE = "UPDATE platform_admin_grant SET approved_by_user_id = :u WHERE platform_admin_grant_id = :g"
FLAG = "UPDATE app_user SET is_platform_admin = true WHERE app_user_id = :t"


@pytest.fixture
def owner():
    eng = create_engine(OWNER_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def t(client, world, owner):
    return team(owner, world)


def refused(eng, sql, **kw) -> str:
    with pytest.raises(DBAPIError) as e:
        run(eng, sql, **kw)
    return str(e.value.orig)


def request(t, target, by=None, reason="Cover for the Q1 engagement"):
    return run(app_engine, REQUEST, t=target, r=reason, by=by or t["a1"])[0]


def approve(t, g, target, by=None):
    """As the service does: the approval and the flag in one transaction."""
    with app_engine.begin() as c:
        c.execute(text(APPROVE), {"u": by or t["a3"], "g": g})
        c.execute(text(FLAG), {"t": target})


def test_a_request_is_born_open_for_a_live_non_admin_by_a_live_admin(t, owner):
    """Criterion 1."""
    tgt = owner_user(owner, "tgt@example.test")
    g = request(t, tgt)
    row = run(owner, "SELECT approved_at, requested_at > now() - interval '1 minute', recorded_at IS NOT NULL "
                     "FROM platform_admin_grant WHERE platform_admin_grant_id = :g", g=g)
    assert tuple(row) == (None, True, True)
    assert run(owner, "SELECT is_platform_admin FROM app_user WHERE app_user_id = :t", t=tgt)[0] is False
    assert "uq_pag_open" in refused(app_engine, REQUEST, t=tgt, r="again", by=t["a1"])
    assert "ck_pag_reason" in refused(app_engine, REQUEST, t=owner_user(owner, "b@example.test"), r=" ", by=t["a1"])
    assert "live platform admin requests" in refused(app_engine, REQUEST, t=owner_user(owner, "c@example.test"),
                                                     r="x", by=t["users"]["editor"])
    assert "not an admin" in refused(app_engine, REQUEST, t=t["a2"], r="x", by=t["a1"])
    assert "born open" in refused(app_engine, REQUEST.replace("requested_by_user_id)", "requested_by_user_id, "
                                                              "approved_by_user_id)").replace(":by)", ":by, :by)"),
                                  t=owner_user(owner, "d@example.test"), r="x", by=t["a1"])


def test_the_creator_of_an_account_never_requests_or_approves_its_rights(t, owner):
    """Criterion 10, AR-24: editor was created by a1 through the API."""
    editor = t["users"]["editor"]
    assert "account they created" in refused(app_engine, REQUEST, t=editor, r="x", by=t["a1"])
    made_by_a3 = run(owner, "INSERT INTO app_user (email, password_hash, display_name, created_by) "
                            "VALUES ('m3@example.test', 'x', 'M3', :a) RETURNING app_user_id", a=t["a3"])[0]
    g = request(t, made_by_a3)                                                         # a1 asks; a3 made the account
    with pytest.raises(DBAPIError, match="account they created"):
        approve(t, g, made_by_a3, by=t["a3"])
    with pytest.raises(DBAPIError, match="account they created"):
        legacy(owner, editor, t["a1"])                                                 # nor through IS


def test_four_eyes_and_independence_decide_an_approval(t, owner):
    """Criteria 2, 3, 4: the requester, the target, and an admin the requester made (a2) are refused; a3 approves at
    the database's time; the record and the flag land together."""
    tgt = owner_user(owner, "tgt@example.test")
    g = request(t, tgt)
    with pytest.raises(DBAPIError, match="four eyes"):
        approve(t, g, tgt, by=t["a1"])
    with pytest.raises(DBAPIError, match="independent"):
        approve(t, g, tgt, by=t["a2"])                                                 # a1 asked for a2's rights
    with pytest.raises(DBAPIError, match="land together"):                             # approval without the flag
        run(app_engine, APPROVE, u=t["a3"], g=g)
    approve(t, g, tgt)
    row = run(owner, "SELECT approved_by_user_id, approved_at > now() - interval '1 minute', approved_xact IS NOT NULL "
                     "FROM platform_admin_grant WHERE platform_admin_grant_id = :g", g=g)
    assert tuple(row) == (t["a3"], True, True)
    assert "decided grant never changes" in refused(owner, "UPDATE platform_admin_grant SET approved_at = "
                                                           "'2020-01-01' WHERE platform_admin_grant_id = :g", g=g)


def test_independence_is_symmetric_counts_the_creator_and_purges_need_30_days(t, owner):
    """Criteria 4, 5 (the functions), 10: makers are the latest grant's requester and approver, and the creator."""
    ind = "SELECT fn_admin_grant_independent(:a, :b)"
    pur = "SELECT fn_admin_purge_independent(:a, :b)"
    a1, a2, a3 = t["a1"], t["a2"], t["a3"]
    assert run(owner, ind, a=a2, b=a1)[0] is False and run(owner, ind, a=a1, b=a2)[0] is False
    assert run(owner, ind, a=a3, b=a1)[0] is True and run(owner, ind, a=a1, b=a3)[0] is True
    assert run(owner, ind, a=a2, b=a3)[0] is False
    b = run(owner, "INSERT INTO app_user (email, password_hash, display_name, created_by) "
                   "VALUES ('b@example.test', 'x', 'B', :a) RETURNING app_user_id", a=a1)[0]
    legacy(owner, b, a3, days=31)                                                      # asked by a3, created by a1
    assert run(owner, ind, a=b, b=a1)[0] is False                                      # the creator is a maker
    assert run(owner, ind, a=a2, b=b)[0] is True
    assert run(owner, pur, a=a3, b=a1)[0] is True                                      # granted 31 days ago
    fresh = owner_user(owner, "fresh@example.test")
    legacy(owner, fresh, a3, days=0)
    assert run(owner, ind, a=fresh, b=a1)[0] is True and run(owner, pur, a=fresh, b=a1)[0] is False
    assert run(owner, ind, a=None, b=a1)[0] is False and run(owner, pur, a=owner_user(owner, "n@example.test"),
                                                                  b=a1)[0] is False   # never NULL


def test_reject_and_cancel_close_a_request_once_and_it_can_be_asked_again(t, owner):
    """Criterion 6."""
    tgt = owner_user(owner, "tgt@example.test")
    g = request(t, tgt)
    reject = ("UPDATE platform_admin_grant SET rejected_by_user_id = :u, rejection_reason = :r "
              "WHERE platform_admin_grant_id = :g")
    assert "other than its requester" in refused(app_engine, reject, u=t["a1"], r="no", g=g)
    assert "ck_pag_rejected" in refused(app_engine, reject, u=t["a2"], r=" ", g=g)
    run(app_engine, reject, u=t["a2"], r="Not on this engagement", g=g)
    assert "never changes" in refused(app_engine, "UPDATE platform_admin_grant SET cancelled_by_user_id = :u "
                                                  "WHERE platform_admin_grant_id = :g", u=t["a1"], g=g)
    g2 = request(t, tgt)                                                               # asked again
    run(app_engine, "UPDATE platform_admin_grant SET cancelled_by_user_id = :u WHERE platform_admin_grant_id = :g",
        u=t["a1"], g=g2)
    assert run(owner, "SELECT cancelled_at IS NOT NULL FROM platform_admin_grant WHERE platform_admin_grant_id = :g",
               g=g2)[0]


def test_legacy_is_the_owners_with_an_operator_and_an_asker_and_dated_by_the_database_elsewhere(t, owner):
    """Criterion 9 (AR-19, N4, N5)."""
    tgt = owner_user(owner, "tgt@example.test")
    ins = ("INSERT INTO platform_admin_grant (grant_origin, target_user_id, reason, operator_name, "
           "requested_by_user_id) VALUES ('LEGACY', :t, 'x', :o, :a)")
    assert "only Fortience IS" in refused(app_engine, ins, t=tgt, o="IS", a=t["a1"])
    assert "operator and the live admin" in refused(owner, ins, t=tgt, o=" ", a=t["a1"])
    assert "live admin who asked" in refused(owner, ins, t=tgt, o="IS", a=None)          # N5 (ck_pag_requester too)
    assert "bootstrap grant is recorded only" in refused(owner, ins.replace("'LEGACY'", "'BOOTSTRAP'"), t=tgt,
                                                         o="IS", a=t["a1"])
    assert run(owner, "SELECT fn_backdating_allowed()")[0] is True                     # this is a test database
    g = legacy(owner, tgt, t["a1"], days=40)
    assert run(owner, "SELECT approved_at < now() - interval '39 days' FROM platform_admin_grant "
                      "WHERE platform_admin_grant_id = :g", g=g)[0]


@pytest.mark.parametrize("name, ok", [
    ("vb_test_db", True), ("vb_test_db_gw3", True), ("vb_s17try_test_db", True), ("vb_s17try_test_db_gw0", True),
    ("vb_demo_db", True), ("vb_uat_db", True), ("vb_s16_demo_db", True), ("vb_db", False), ("vb_latest_db", False),
    ("vb_evaluation_db", False), ("vb_demo_prod", False), ("vb_prod_db", False), ("vb_s17_test_db_x", False),
    ("VB_TEST_DB", False), ("vb_a_b_test_db", False)])
def test_backdating_matches_whole_names_only(owner, name, ok):
    """N4: the function's own patterns, applied to names (it reads current_database(), which no URL can change)."""
    src = run(owner, "SELECT prosrc FROM pg_proc WHERE proname = 'fn_backdating_allowed'")[0]
    patterns = re.findall(r"~ '([^']+)'", src)
    assert len(patterns) == 2
    assert any(re.fullmatch(p.strip("^$"), name) for p in patterns) is ok


def test_nobody_deletes_or_backdates_a_grant(t, owner):
    """Criterion 11."""
    assert "not allowed" in refused(owner, "DELETE FROM platform_admin_grant")
    assert "permission denied" in refused(app_engine, "DELETE FROM platform_admin_grant")
    tgt = owner_user(owner, "tgt@example.test")
    g = request(t, tgt)
    assert "permission denied" in refused(app_engine, "UPDATE platform_admin_grant SET approved_at = now() "
                                                      "WHERE platform_admin_grant_id = :g", g=g)
    assert "names who made it" in refused(owner, "UPDATE platform_admin_grant SET approved_at = now() "
                                                 "WHERE platform_admin_grant_id = :g", g=g)
    assert "never change" in refused(owner, "UPDATE platform_admin_grant SET requested_at = '2020-01-01' "
                                            "WHERE platform_admin_grant_id = :g", g=g)
    assert "only the 0076 backfill" in refused(owner, "INSERT INTO platform_admin_grant (grant_origin, target_user_id, "
                                                      "reason, operator_name, requested_by_user_id, "
                                                      "source_audit_event_id) VALUES ('LEGACY', :t, 'x', 'IS', :a, 1)",
                                               t=owner_user(owner, "s@example.test"), a=t["a1"])
