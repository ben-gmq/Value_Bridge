"""Slice 16, migration 0074: the scoped purge bypass (schema §4, §12.4; AR-4, Q-75). Grade 1 — a fault here deletes a
client's frozen record or another project's, so every condition is proven at the database, for both roles:
the owner deletes one project's frozen rows only inside an approved request at least 24 hours old, in a transaction
that names that project, row by row; nobody ever updates a frozen row; the app role never deletes one."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database import engine as app_engine
from tests.test_baseline import bid, freeze, scope
from tests.test_project_purge_record import (INSERT, backdate, owner, promote, refused, run,  # noqa: F401 — fixture
                                              two)
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture

SHADOW = "baseline_business_requirement"


def purge_tx(eng, p, sql, commit=False, **kw) -> int:
    """One transaction as a purge runs it: the setting names project `p`, then `sql`. Rolled back unless `commit`."""
    with eng.connect() as c:
        tx = c.begin()
        try:
            if p is not None:
                c.execute(text("SELECT set_config('vb.purge_project_id', :p, true)"), {"p": str(p)})
            n = c.execute(text(sql), kw).rowcount
        finally:
            tx.commit() if commit else tx.rollback()
    return n


def purge_refused(eng, p, sql, **kw) -> str:
    with pytest.raises(DBAPIError) as e:
        purge_tx(eng, p, sql, **kw)
    return str(e.value.orig)


@pytest.fixture
def frozen(client, world, ed, owner):
    """Two projects with a frozen, written-file baseline each; two platform admins (a2's grant 31 days old)."""
    scope(client, ed)
    b = bid(freeze(client, ed))
    other = {"h": world["admin"], "p": world["p_sales"]}
    scope(client, other)
    b_other = bid(freeze(client, other))
    admins = run(owner, "SELECT app_user_id FROM app_user WHERE is_platform_admin ORDER BY 1")
    a2 = world["users"]["owner"]
    promote(owner, a2)
    return {"p": ed["p"], "b": b, "other": world["p_sales"], "b_other": b_other, "a1": admins[0], "a2": a2,
            "c": world["client_id"]}


def request(t, kind="DELETE"):
    return run(app_engine, INSERT, k=kind, p=t["p"], c=t["c"], r=t["a1"], a=None)[0]


def approve(t, pp):
    run(app_engine, "UPDATE project_purge SET approved_at = now(), approved_by_user_id = :u WHERE project_purge_id = :pp",
        u=t["a2"], pp=pp)


def rows_of(t) -> str:
    return f"DELETE FROM {SHADOW} WHERE baseline_id = {t['b']}"


def test_nothing_is_deleted_before_an_approval_24_hours_old(frozen, owner):
    pp = request(frozen)
    assert "immutable" in purge_refused(owner, frozen["p"], rows_of(frozen))            # open, not approved
    approve(frozen, pp)
    assert "immutable" in purge_refused(owner, frozen["p"], rows_of(frozen))            # approved just now
    backdate(owner, pp, hours=23.98)
    assert "immutable" in purge_refused(owner, frozen["p"], rows_of(frozen))            # 23 h 59 min
    backdate(owner, pp, hours=24.02)
    assert purge_tx(owner, frozen["p"], rows_of(frozen)) > 0                            # 24 h 1 min


def test_the_transaction_must_name_the_project_and_every_row_is_tested(frozen, owner):
    pp = request(frozen)
    approve(frozen, pp)
    backdate(owner, pp)
    assert "immutable" in purge_refused(owner, None, rows_of(frozen))                   # no setting
    assert "immutable" in purge_refused(owner, frozen["other"], rows_of(frozen))        # names another project
    # A predicate that reaches another project's rows hits a raise, never a deletion — the whole statement fails.
    assert "immutable" in purge_refused(owner, frozen["p"], f"DELETE FROM {SHADOW}")
    other = f"SELECT count(*) FROM {SHADOW} WHERE baseline_id = {frozen['b_other']}"
    assert run(owner, other)[0] > 0
    assert "never removed" in purge_refused(owner, frozen["p"], "DELETE FROM baseline "
                                                                f"WHERE baseline_id = {frozen['b_other']}")


def test_nobody_updates_a_frozen_row_even_in_the_strongest_position(frozen, owner):
    pp = request(frozen)
    approve(frozen, pp)
    backdate(owner, pp)
    assert "UPDATE on" in purge_refused(owner, frozen["p"], f"UPDATE {SHADOW} SET baseline_id = baseline_id "
                                                             f"WHERE baseline_id = {frozen['b']}")
    assert "cannot change" in purge_refused(owner, frozen["p"], f"UPDATE baseline SET note = 'x' "
                                                                 f"WHERE baseline_id = {frozen['b']}")


def test_the_app_role_never_deletes_a_frozen_row_and_never_holds_the_bypass(frozen, owner):
    pp = request(frozen)
    approve(frozen, pp)
    backdate(owner, pp)
    for table in (SHADOW, "baseline", "baseline_archive"):
        msg = purge_refused(app_engine, frozen["p"], f"DELETE FROM {table} WHERE baseline_id = {frozen['b']}")
        assert "permission denied" in msg
    with app_engine.connect() as c, c.begin():
        c.execute(text("SELECT set_config('vb.purge_project_id', :p, true)"), {"p": str(frozen["p"])})
        assert c.scalar(text("SELECT fn_purge_allows(:p)"), {"p": frozen["p"]}) is False


def test_a_cancelled_request_or_one_for_another_project_lends_nothing(frozen, owner):
    pp = request(frozen)
    approve(frozen, pp)
    backdate(owner, pp)
    run(app_engine, "UPDATE project_purge SET cancelled_at = now(), cancelled_by_user_id = :u "
                    "WHERE project_purge_id = :pp", u=frozen["a1"], pp=pp)
    assert "immutable" in purge_refused(owner, frozen["p"], rows_of(frozen))
    pp2 = run(app_engine, INSERT, k="DELETE", p=frozen["other"], c=frozen["c"], r=frozen["a1"], a=None)[0]
    approve(frozen, pp2)
    backdate(owner, pp2)
    assert "immutable" in purge_refused(owner, frozen["p"], rows_of(frozen))            # the other project's request


def test_an_archive_lends_the_bypass_only_once_its_project_file_is_recorded(frozen, owner):
    pp = request(frozen, kind="ARCHIVE")
    approve(frozen, pp)
    backdate(owner, pp)
    assert "immutable" in purge_refused(owner, frozen["p"], rows_of(frozen))
    run(owner, "UPDATE project_purge SET archive_object_name = 't/1/project-1.json.enc', archive_sha256 = "
               "repeat('a', 64), archive_byte_size = 10, archive_key_ref = 'k@1' WHERE project_purge_id = :pp", pp=pp)
    assert purge_tx(owner, frozen["p"], rows_of(frozen)) > 0


def test_header_and_archive_records_go_in_order_under_the_bypass_only(frozen, owner):
    pp = request(frozen)
    approve(frozen, pp)
    assert "never removed" in purge_refused(owner, frozen["p"], f"DELETE FROM baseline WHERE baseline_id = {frozen['b']}")
    assert "goes only with its baseline" in purge_refused(owner, frozen["p"], "DELETE FROM baseline_archive "
                                                                              f"WHERE project_id = {frozen['p']}")
    backdate(owner, pp)
    shadows = [r[0] for r in run_all(owner, "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                                            "JOIN pg_proc f ON f.oid = t.tgfoid "
                                            "WHERE f.proname = 'fn_reject_modification_purgeable'")]
    sql = "; ".join([f"DELETE FROM baseline_archive WHERE project_id = {frozen['p']}"]
                    + [f"DELETE FROM {s} WHERE baseline_id = {frozen['b']}" for s in shadows]
                    + [f"DELETE FROM baseline WHERE project_id = {frozen['p']}"])
    purge_tx(owner, frozen["p"], sql)                                                   # all of it, then rolled back


def run_all(eng, sql, **kw):
    with eng.begin() as c:
        return c.execute(text(sql), kw).all()


def test_every_frozen_shadow_asks_the_rule_and_nothing_else_does(owner):
    """A shadow made with the old helper would make a purge fail loudly (schema §4); this pins that none exists."""
    rows = run_all(owner, "SELECT c.relname, f.proname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                          "JOIN pg_proc f ON f.oid = t.tgfoid WHERE NOT t.tgisinternal AND (t.tgtype & 8) <> 0 "
                          "AND c.relnamespace = 'public'::regnamespace")
    by_table = dict(rows)
    shadows = {t for (t,) in run_all(owner, "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                                            "AND tablename LIKE 'baseline\\_%' AND tablename <> 'baseline_archive'")}
    assert len(shadows) >= 33
    assert {by_table.get(t) for t in shadows} == {"fn_reject_modification_purgeable"}
    assert {t for t, f in rows if f == "fn_reject_modification_purgeable"} == shadows


def test_the_rule_answers_false_never_unknown_when_no_project_is_named(frozen, owner):
    """Found by the full suite: an unset setting reads as NULL; a NULL answer, negated in the key guard, let a key row
    through. The rule must say exactly false, on a fresh connection that never set it."""
    pp = request(frozen)
    approve(frozen, pp)
    backdate(owner, pp)
    from sqlalchemy import create_engine
    from tests.conftest import OWNER_URL
    eng = create_engine(OWNER_URL)                      # a new session that never touched the setting
    try:
        with eng.connect() as c, c.begin():
            assert c.scalar(text("SELECT fn_purge_allows(:p)"), {"p": frozen["p"]}) is False
        key = f"INSERT INTO project_purge_key (project_purge_id, key_name) VALUES ({pp}, 'vb-test-a-proj-{frozen['p']}')"
        assert "inside the purge transaction" in purge_refused(eng, None, key)
    finally:
        eng.dispose()


def test_the_key_record_follows_the_same_rule(frozen, owner):
    pp = request(frozen)
    approve(frozen, pp)
    key = ("INSERT INTO project_purge_key (project_purge_id, key_name) VALUES "
           f"({pp}, 'vb-test-a-proj-{frozen['p']}')")
    backdate(owner, pp, hours=23.98)
    assert "inside the purge transaction" in purge_refused(owner, frozen["p"], key)
    backdate(owner, pp, hours=24.02)
    assert "inside the purge transaction" in purge_refused(owner, frozen["other"], key)
    assert purge_tx(owner, frozen["p"], key) == 1


def test_an_owner_function_cannot_lend_the_bypass_to_an_app_session(frozen, owner):
    """sara M1: session_user is checked, not only current_user — a SECURITY DEFINER function owned by vb_owner runs
    with current_user = vb_owner, and must still say no to a session the app opened."""
    pp = request(frozen)
    approve(frozen, pp)
    backdate(owner, pp)
    run(owner, "CREATE FUNCTION public.test_lend(p bigint) RETURNS boolean LANGUAGE sql SECURITY DEFINER "
               "SET search_path = pg_catalog, public AS $$ SELECT current_user = 'vb_owner' "
               "AND public.fn_purge_allows(p) $$; GRANT EXECUTE ON FUNCTION public.test_lend(bigint) TO vb_app")
    try:
        with app_engine.connect() as c, c.begin():
            c.execute(text("SELECT set_config('vb.purge_project_id', :p, true)"), {"p": str(frozen["p"])})
            assert c.scalar(text("SELECT test_lend(:p)"), {"p": frozen["p"]}) is False
        with owner.connect() as c, c.begin():                                           # the same call as the owner
            c.execute(text("SELECT set_config('vb.purge_project_id', :p, true)"), {"p": str(frozen["p"])})
            assert c.scalar(text("SELECT test_lend(:p)"), {"p": frozen["p"]}) is True
    finally:
        run(owner, "DROP FUNCTION public.test_lend(bigint)")


def test_a_recorded_re_purge_waives_the_24_hours_but_never_the_approval(frozen, owner):
    """sara M2, Q-85: a re-purge of a removal a restore undid needs a second admin's approval, not the wait."""
    old = request(frozen)
    run(app_engine, "UPDATE project_purge SET cancelled_at = now(), cancelled_by_user_id = :u "
                    "WHERE project_purge_id = :pp", u=frozen["a1"], pp=old)
    pp = request(frozen)
    run(owner, "UPDATE project_purge SET repurge_of_purge_id = :o WHERE project_purge_id = :pp", o=old, pp=pp)
    assert "immutable" in purge_refused(owner, frozen["p"], rows_of(frozen))            # no approval yet
    approve(frozen, pp)
    assert purge_tx(owner, frozen["p"], rows_of(frozen)) > 0                            # approved just now
    run(app_engine, "UPDATE project_purge SET cancelled_at = now(), cancelled_by_user_id = :u "
                    "WHERE project_purge_id = :pp", u=frozen["a1"], pp=pp)
    assert "immutable" in purge_refused(owner, frozen["p"], rows_of(frozen))


def _forced(owner, sql, **kw):
    """Test-only: a request state the guard would not let the test reach directly."""
    run(owner, "ALTER TABLE project_purge DISABLE TRIGGER trg_project_purge_guard")
    try:
        return run(owner, sql, **kw)
    finally:
        run(owner, "ALTER TABLE project_purge ENABLE TRIGGER trg_project_purge_guard")


def test_a_delete_archive_or_an_executed_request_never_lends_the_bypass(frozen, owner):
    """sara M3, schema §12.4: only an open ARCHIVE or DELETE counts."""
    pp = request(frozen)
    approve(frozen, pp)
    backdate(owner, pp)
    _forced(owner, "UPDATE project_purge SET executed_at = now(), executed_by_user_id = :u, "
                   "backups_age_out_on = current_date WHERE project_purge_id = :pp", u=frozen["a1"], pp=pp)
    assert "immutable" in purge_refused(owner, frozen["p"], rows_of(frozen))            # executed
    # Re-shape it into an executed ARCHIVE, then open an approved, aged DELETE_ARCHIVE of it for the live project.
    _forced(owner, "UPDATE project_purge SET purge_kind = 'ARCHIVE', archive_object_name = 't/1/project-1.json.enc', "
                   "archive_sha256 = repeat('a', 64), archive_byte_size = 10, archive_key_ref = 'k@1' "
                   "WHERE project_purge_id = :pp", pp=pp)
    dela = _forced(owner, "INSERT INTO project_purge (purge_kind, project_id, client_id, project_code, reason, "
                          "requested_by_user_id, archive_purge_id, approved_at, approved_by_user_id) VALUES "
                          "('DELETE_ARCHIVE', :p, :c, 'X', 'test', :r, :a, now() - interval '25 hours', :u) "
                          "RETURNING project_purge_id", p=frozen["p"], c=frozen["c"], r=frozen["a1"], a=pp,
                   u=frozen["a2"])[0]
    assert run(owner, "SELECT purge_kind, executed_at IS NULL FROM project_purge WHERE project_purge_id = :d",
               d=dela) == ("DELETE_ARCHIVE", True)
    assert "immutable" in purge_refused(owner, frozen["p"], rows_of(frozen))            # open, approved, aged


def test_the_archive_record_is_tested_row_by_row(frozen, owner):
    """sara L1: under this project's setting, another project's archive records are refused, and a whole-table
    delete fails rather than reaching them."""
    pp = request(frozen)
    approve(frozen, pp)
    backdate(owner, pp)
    assert "goes only with its baseline" in purge_refused(
        owner, frozen["p"], f"DELETE FROM baseline_archive WHERE project_id = {frozen['other']}")
    assert "goes only with its baseline" in purge_refused(owner, frozen["p"], "DELETE FROM baseline_archive")
    with owner.connect() as c:
        tx = c.begin()
        c.execute(text("SELECT set_config('vb.purge_project_id', :p, true)"), {"p": str(frozen["p"])})
        c.execute(text(f"DELETE FROM baseline_archive WHERE project_id = {frozen['p']}"))
        mine, theirs = c.execute(text("SELECT count(*) FILTER (WHERE project_id = :p), "
                                      "count(*) FILTER (WHERE project_id = :o) FROM baseline_archive"),
                                 {"p": frozen["p"], "o": frozen["other"]}).one()
        tx.rollback()
    assert mine == 0 and theirs > 0


def test_a_key_is_recorded_only_under_the_open_request_itself(frozen, owner):
    """sara L2: a cancelled request of the project cannot take key rows, even while a later one is open and aged."""
    old = request(frozen)
    run(app_engine, "UPDATE project_purge SET cancelled_at = now(), cancelled_by_user_id = :u "
                    "WHERE project_purge_id = :pp", u=frozen["a1"], pp=old)
    pp = request(frozen)
    approve(frozen, pp)
    backdate(owner, pp)
    key = "INSERT INTO project_purge_key (project_purge_id, key_name) VALUES ({}, 'vb-test-a-proj-{}')"
    assert "inside the purge transaction" in purge_refused(owner, frozen["p"], key.format(old, frozen["p"]))
    assert purge_tx(owner, frozen["p"], key.format(pp, frozen["p"])) == 1
