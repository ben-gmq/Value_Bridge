"""Slice 17, migration 0078: the guard on becoming a platform admin (schema rev 3 §4; spec §10 criteria 7–10; AR-13,
AR-16, AR-24; D1, D3, N6). Grade 1 — this is the one door to every client's data, so each way through it is proven
at the database for both roles, and every way around it is proven shut."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from database import engine as app_engine
from tests.admin_team import legacy, owner_user, run, team
from tests.conftest import OWNER_URL

FLAG = "UPDATE app_user SET is_platform_admin = true WHERE app_user_id = :t"
REQUEST = ("INSERT INTO platform_admin_grant (grant_origin, target_user_id, reason, requested_by_user_id) "
           "VALUES ('REQUEST', :t, 'Cover', :by) RETURNING platform_admin_grant_id")


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


def test_the_setup_admin_got_its_bootstrap_record(world, owner):
    """Criterion 9: first_run_setup on an empty table — the trigger records it, no operator, nobody asked."""
    row = run(owner, "SELECT g.grant_origin, g.operator_name, g.requested_by_user_id, g.approved_at IS NOT NULL "
                     "FROM platform_admin_grant g JOIN app_user u ON u.app_user_id = g.target_user_id "
                     "WHERE u.email = 'admin@example.test'")
    assert tuple(row) == ("BOOTSTRAP", None, None, True)


def test_the_flag_comes_only_from_an_approval_in_the_same_transaction(t, owner):
    """Criterion 8 and D1: no grant, an earlier transaction's approval, or the owner without a LEGACY row — refused."""
    tgt = owner_user(owner, "tgt@example.test")
    assert "approved in this transaction" in refused(app_engine, FLAG, t=tgt)
    assert "approved in this transaction" in refused(owner, FLAG, t=tgt)
    g = run(app_engine, REQUEST, t=tgt, by=t["a1"])[0]
    with app_engine.begin() as c:                                                      # the approval and the flag
        c.execute(text("UPDATE platform_admin_grant SET approved_by_user_id = :u WHERE platform_admin_grant_id = :g"),
                  {"u": t["a3"], "g": g})
        c.execute(text(FLAG), {"t": tgt})
    run(app_engine, "UPDATE app_user SET is_platform_admin = false WHERE app_user_id = :t", t=tgt)   # AR-17: one admin
    assert "approved in this transaction" in refused(app_engine, FLAG, t=tgt)          # D1: no replay of that approval


def test_a_deactivated_admin_cannot_be_brought_back_with_the_flag_on(t, owner):
    """D3: reactivation with the flag needs a fresh approval; the way back is to clear the flag, then request."""
    run(owner, "UPDATE app_user SET is_active = false WHERE app_user_id = :u", u=t["a3"])
    assert "approved in this transaction" in refused(app_engine, "UPDATE app_user SET is_active = true "
                                                                 "WHERE app_user_id = :u", u=t["a3"])
    run(app_engine, "UPDATE app_user SET is_active = true, is_platform_admin = false WHERE app_user_id = :u", u=t["a3"])


def test_nobody_is_born_an_admin_except_on_an_empty_table_or_by_the_owners_first_two(t, owner):
    """Criteria 8 and 9 (AR-16, N6, D3)."""
    born = ("INSERT INTO app_user (email, password_hash, display_name, is_platform_admin, is_active, created_by) "
            "VALUES (:e, 'x', 'X', true, :act, :by)")
    assert "only on an empty database" in refused(app_engine, born, e="x@example.test", act=True, by=t["a1"])
    assert "born active" in refused(owner, born, e="y@example.test", act=False, by=None)
    assert "already been granted" in refused(owner, born, e="z@example.test", act=True, by=None)   # a1, a2, a3 exist


def test_the_owners_command_line_records_who_ran_it_and_who_asked(client, owner):
    """Criterion 9, AR-16 with P1: on an empty database, the first two admins; the second names its asker; a third
    is refused — and removing an admin never reopens it (the count is of everyone ever granted)."""
    def create(email, operator="IS op", actor=None):
        with owner.begin() as c:
            c.execute(text("SELECT set_config('vb.operator', :o, true), set_config('vb.grant_actor_id', :a, true)"),
                      {"o": operator, "a": str(actor) if actor else ""})
            return c.execute(text("INSERT INTO app_user (email, password_hash, display_name, is_platform_admin, "
                                  "user_kind) VALUES (:e, 'x', 'X', true, 'USER') RETURNING app_user_id"),
                             {"e": email}).scalar_one()
    with pytest.raises(DBAPIError, match="names its operator"):
        create("first@example.test", operator="")
    first = create("first@example.test")
    with pytest.raises(DBAPIError, match="names the admin who asked"):
        create("second@example.test")                                                  # a live admin exists
    second = create("second@example.test", actor=first)
    assert run(owner, "SELECT grant_origin, operator_name, requested_by_user_id FROM platform_admin_grant "
                      "WHERE target_user_id = :u", u=second) == ("BOOTSTRAP", "IS op", first)
    run(owner, "UPDATE app_user SET is_platform_admin = false WHERE app_user_id = :u", u=second)    # one left
    with pytest.raises(DBAPIError, match="already been granted"):
        create("third@example.test", actor=first)


def unrecorded_admin(owner, email: str) -> int:
    """Test-only: a flagged admin with no grant record — what 0076's backfill leaves when it skips someone."""
    run(owner, "ALTER TABLE app_user DISABLE TRIGGER trg_app_user_admin_guard")
    run(owner, "ALTER TABLE app_user DISABLE TRIGGER trg_app_user_bootstrap_grant")
    try:
        return run(owner, "INSERT INTO app_user (email, password_hash, display_name, is_platform_admin, user_kind) "
                          "VALUES (:e, 'x', 'Skipped', true, 'USER') RETURNING app_user_id", e=email)[0]
    finally:
        run(owner, "ALTER TABLE app_user ENABLE TRIGGER trg_app_user_bootstrap_grant")
        run(owner, "ALTER TABLE app_user ENABLE TRIGGER trg_app_user_admin_guard")


def test_live_admins_with_no_record_still_close_the_command_line(client, owner):
    """sara M-1, N6: the AR-16 count is the greater of everyone ever granted and the live admins — a database whose
    backfill skipped an admin is still closed at two."""
    with owner.begin() as c:
        c.execute(text("SELECT set_config('vb.operator', 'IS op', true)"))
        c.execute(text("INSERT INTO app_user (email, password_hash, display_name, is_platform_admin, user_kind) "
                       "VALUES ('first@example.test', 'x', 'F', true, 'USER')"))
    skipped = unrecorded_admin(owner, "skipped@example.test")
    assert run(owner, "SELECT count(*) FROM platform_admin_grant")[0] == 1                # only one ever granted
    with pytest.raises(DBAPIError, match="already been granted"):
        with owner.begin() as c:
            c.execute(text("SELECT set_config('vb.operator', 'IS op', true), set_config('vb.grant_actor_id', :a, "
                           "true)"), {"a": str(skipped)})
            c.execute(text("INSERT INTO app_user (email, password_hash, display_name, is_platform_admin, "
                           "user_kind) VALUES ('third@example.test', 'x', 'T', true, 'USER')"))


def test_an_accounts_creator_is_permanent_and_an_app_made_account_names_a_live_admin(t, owner):
    """Criterion 10 (AR-24): created_by never changes, for either role; the app may not make an account in nobody's
    name or a non-admin's."""
    editor = t["users"]["editor"]
    for eng in (app_engine, owner):
        assert "creator never changes" in refused(eng, "UPDATE app_user SET created_by = :a WHERE app_user_id = :u",
                                                  a=t["a3"], u=editor)
    made = ("INSERT INTO app_user (email, password_hash, display_name, created_by) VALUES (:e, 'x', 'X', :by)")
    assert "named as its creator" in refused(app_engine, made, e="n@example.test", by=None)
    assert "named as its creator" in refused(app_engine, made, e="s@example.test", by=t["users"]["owner"])
    run(app_engine, made, e="ok@example.test", by=t["a1"])


def test_the_owners_legacy_grant_is_the_only_owner_path_to_the_flag(t, owner):
    """Criterion 9 (AR-19, AR-25): the IS command's function sets the flag with its record; the flag alone is refused."""
    tgt = owner_user(owner, "third@example.test")
    assert "approved in this transaction" in refused(owner, FLAG, t=tgt)
    legacy(owner, tgt, t["a3"])
    assert run(owner, "SELECT is_platform_admin FROM app_user WHERE app_user_id = :u", u=tgt)[0] is True
    assert run(owner, "SELECT count(*) FROM audit_event WHERE event_type = 'PLATFORM_ADMIN_GRANTED' "
                      "AND target_id = :u", u=tgt)[0] == 1
