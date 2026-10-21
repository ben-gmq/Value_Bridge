"""Slice 16, migration 0072: project_purge, the record of a request to remove a project or delete its archive (schema
§3.2, §12.5; spec §18 S7, §19 U6; Q-72, AR-5). Grade 1 — this record is the control on an irreversible deletion, so
four eyes, the 24 hours, the order of steps and "the running app can never execute" are proven at the database, for
the app role and the owner."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from database import engine as app_engine
from tests.conftest import OWNER_URL

INSERT = ("INSERT INTO project_purge (purge_kind, project_id, client_id, project_code, reason, requested_by_user_id, "
          "archive_purge_id) VALUES (:k, :p, :c, 'X', 'contract clause 9.2', :r, :a) RETURNING project_purge_id")
APP_UPDATABLE = {"approved_at", "approved_by_user_id", "cancelled_at", "cancelled_by_user_id", "archive_checked_at",
                 "archive_check_error", "updated_by", "row_version"}


@pytest.fixture
def owner():
    eng = create_engine(OWNER_URL)
    yield eng
    eng.dispose()


def run(eng, sql, **kw):
    with eng.begin() as c:
        r = c.execute(text(sql), kw)
        return r.first() if r.returns_rows else None


def refused(eng, sql, **kw) -> str:
    with pytest.raises(DBAPIError) as e:
        run(eng, sql, **kw)
    return str(e.value.orig)


@pytest.fixture
def two(client, world, owner):
    """Two live platform admins, a bare project (no child rows, so the owner can remove it here without 0074)."""
    a1, staff = run(owner, "SELECT array_agg(app_user_id ORDER BY app_user_id) FILTER (WHERE is_platform_admin), "
                           "array_agg(app_user_id ORDER BY app_user_id) FILTER (WHERE NOT is_platform_admin) "
                           "FROM app_user")
    p = run(owner, "INSERT INTO project (client_id, project_code, project_name, status_code_id, status_behaviour, "
                   "created_by) SELECT :c, 'BARE', 'Bare', code_id, behaviour_code, :u FROM code_master "
                   "WHERE category = 'PROJECT_STATUS' AND code = 'PLANNING' AND project_id IS NULL "
                   "RETURNING project_id", c=world["client_id"], u=a1[0])[0]
    return {"a1": a1[0], "staff": staff[0], "a2": staff[1], "p": p, "c": world["client_id"]}


def promote(owner, uid, by=None, days=31):
    """A platform admin whose grant (AR-13) was made `days` ago by `by` (None: a system grant, never the requester)."""
    run(owner, "UPDATE app_user SET is_platform_admin = true WHERE app_user_id = :u", u=uid)
    run(owner, "INSERT INTO audit_event (event_type, app_user_id, target_table, target_id, occurred_at) VALUES "
               "('PLATFORM_ADMIN_GRANTED', :by, 'app_user', :u, now() - make_interval(days => :d))", by=by, u=uid, d=days)


def request(eng, t, kind="DELETE", archive=None, p=None):
    return run(eng, INSERT, k=kind, p=p or t["p"], c=t["c"], r=t["a1"], a=archive)[0]


def backdate(owner, pp, hours=25):
    """Test-only: an approval made `hours` ago (the guard forces now() on every approval)."""
    run(owner, f"ALTER TABLE project_purge DISABLE TRIGGER trg_project_purge_guard; "
               f"UPDATE project_purge SET approved_at = now() - interval '{hours} hours' WHERE project_purge_id = {pp}; "
               f"ALTER TABLE project_purge ENABLE TRIGGER trg_project_purge_guard")


def test_a_request_needs_two_live_platform_admins_and_is_born_open(two, owner):
    assert "two live platform admins" in refused(app_engine, INSERT, k="DELETE", p=two["p"], c=two["c"],
                                                 r=two["a1"], a=None)
    promote(owner, two["a2"])
    assert "born open" in refused(owner, INSERT.replace("archive_purge_id)", "archive_purge_id, approved_at)")
                                  .replace(":a)", ":a, now())"), k="DELETE", p=two["p"], c=two["c"], r=two["a1"], a=None)
    assert "no such project" in refused(app_engine, INSERT, k="ARCHIVE", p=two["p"] + 999, c=two["c"], r=two["a1"],
                                        a=None)
    request(app_engine, two)
    assert "uq_pp_open" in refused(app_engine, INSERT, k="ARCHIVE", p=two["p"], c=two["c"], r=two["a1"], a=None)


def test_four_eyes_at_the_database(two, owner):
    promote(owner, two["a2"])
    pp = request(app_engine, two)
    approve = "UPDATE project_purge SET approved_at = :t, approved_by_user_id = :u WHERE project_purge_id = :pp"
    assert "four eyes" in refused(app_engine, approve, t="2020-01-01", u=two["a1"], pp=pp)
    assert "second live platform admin" in refused(app_engine, approve, t="2020-01-01", u=two["staff"], pp=pp)
    run(app_engine, approve, t="2020-01-01", u=two["a2"], pp=pp)
    assert run(owner, "SELECT approved_at > now() - interval '1 minute' FROM project_purge")[0]   # never backdated
    assert "never changes" in refused(app_engine, approve, t="2020-01-01", u=two["a2"], pp=pp)


def test_only_the_owner_executes_and_only_after_24_hours_with_the_project_gone(two, owner):
    promote(owner, two["a2"])
    pp = request(app_engine, two)
    run(app_engine, "UPDATE project_purge SET approved_at = now(), approved_by_user_id = :u WHERE project_purge_id = :pp",
        u=two["a2"], pp=pp)
    execute = "UPDATE project_purge SET executed_at = now(), executed_by_user_id = :u WHERE project_purge_id = :pp"
    assert "permission denied" in refused(app_engine, execute, u=two["a1"], pp=pp)
    assert "24 hours" in refused(owner, execute, u=two["a1"], pp=pp)
    backdate(owner, pp)
    assert "still exists" in refused(owner, execute, u=two["a1"], pp=pp)
    run(owner, "UPDATE app_user SET is_platform_admin = false WHERE app_user_id = :u", u=two["a2"])   # S7: demoted
    run(owner, "DELETE FROM project WHERE project_id = :p", p=two["p"])                       # bare: no child rows
    assert "24 hours" in refused(owner, execute, u=two["a1"], pp=pp)
    promote(owner, two["a2"])
    assert "key names" in refused(owner, execute, u=two["a1"], pp=pp)                         # sara M2
    record_key(owner, pp, two["p"], f"vb-test-a-proj-{two['p']}")
    run(owner, execute, u=two["a1"], pp=pp)
    got = run(owner, "SELECT backups_age_out_on = ((now() AT TIME ZONE 'Asia/Bangkok')::date + interval '13 months')::date "
                     "FROM project_purge WHERE project_purge_id = :pp", pp=pp)
    assert got[0]
    assert "cannot be cancelled" in refused(app_engine, "UPDATE project_purge SET cancelled_at = now(), "
                                                        "cancelled_by_user_id = :u WHERE project_purge_id = :pp",
                                            u=two["a1"], pp=pp)
    assert "not allowed" in refused(owner, "DELETE FROM project_purge")


@pytest.mark.parametrize("by, days, ok", [("requester", 31, False), (None, 10, False), (None, 31, True),
                                          ("staff", 31, True)])
def test_the_approver_s_rights_must_be_old_and_not_granted_by_the_requester(two, owner, by, days, ok):
    """Criterion 28 (AR-13, Q-93 a): an approval is refused when the approver's latest platform-admin grant was made
    by the requester or is under 30 days old."""
    promote(owner, two["staff"])                                                 # a third admin, granted long ago
    promote(owner, two["a2"], by={"requester": two["a1"], "staff": two["staff"]}.get(by), days=days)
    pp = request(app_engine, two)
    approve = "UPDATE project_purge SET approved_at = now(), approved_by_user_id = :u WHERE project_purge_id = :pp"
    if ok:
        run(app_engine, approve, u=two["a2"], pp=pp)
    else:
        assert "AR-13" in refused(app_engine, approve, u=two["a2"], pp=pp)


def test_only_the_latest_grant_counts_and_no_grant_is_too_recent(two, owner):
    promote(owner, two["a2"], days=90)
    promote(owner, two["a2"], by=two["a1"], days=40)                             # re-granted by the requester later
    pp = request(app_engine, two)
    approve = "UPDATE project_purge SET approved_at = now(), approved_by_user_id = :u WHERE project_purge_id = :pp"
    assert "AR-13" in refused(app_engine, approve, u=two["a2"], pp=pp)
    run(owner, "UPDATE app_user SET is_platform_admin = true WHERE app_user_id = :u", u=two["staff"])   # no audit row
    assert "AR-13" in refused(app_engine, approve, u=two["staff"], pp=pp)


def test_a_cancelled_request_is_fixed_and_frees_the_project(two, owner):
    promote(owner, two["a2"])
    pp = request(app_engine, two)
    run(app_engine, "UPDATE project_purge SET cancelled_at = '2020-01-01', cancelled_by_user_id = :u "
                    "WHERE project_purge_id = :pp", u=two["a2"], pp=pp)
    assert "never changes" in refused(app_engine, "UPDATE project_purge SET approved_at = now(), approved_by_user_id = "
                                                  ":u WHERE project_purge_id = :pp", u=two["a2"], pp=pp)
    assert "never changes" in refused(app_engine, "UPDATE project_purge SET archive_check_error = 'x', "
                                                  "archive_checked_at = now() WHERE project_purge_id = :pp", pp=pp)
    request(app_engine, two)                                                    # a new request may open


def test_the_project_file_and_key_destruction_are_the_owners_in_order(two, owner):
    promote(owner, two["a2"])
    pp = request(app_engine, two, kind="ARCHIVE")
    file = ("UPDATE project_purge SET archive_object_name = 'i/1/project-1.json.enc', archive_sha256 = repeat('a', 64), "
            "archive_byte_size = 10, archive_key_ref = 'k@1' WHERE project_purge_id = :pp")
    assert "permission denied" in refused(app_engine, file, pp=pp)
    assert "open approved ARCHIVE" in refused(owner, file, pp=pp)
    run(app_engine, "UPDATE project_purge SET approved_at = now(), approved_by_user_id = :u WHERE project_purge_id = :pp",
        u=two["a2"], pp=pp)
    run(owner, file, pp=pp)
    assert "open approved ARCHIVE" in refused(owner, file.replace("project-1", "project-2"), pp=pp)
    assert "after its ARCHIVE purge ran" in refused(app_engine, INSERT, k="DELETE_ARCHIVE", p=two["p"], c=two["c"],
                                                    r=two["a1"], a=pp)
    assert "U6" in refused(owner, "UPDATE project_purge SET destroy_started_at = now() WHERE project_purge_id = :pp",
                           pp=pp)


def test_the_app_role_writes_only_the_request_approve_cancel_and_check_columns(db):
    cols = {r[0] for r in db.execute(text(
        "SELECT column_name FROM information_schema.column_privileges WHERE grantee = 'vb_app' "
        "AND table_name = 'project_purge' AND privilege_type = 'UPDATE'"))}
    assert cols == APP_UPDATABLE
    assert not db.scalar(text("SELECT has_table_privilege('vb_app', 'project_purge', 'DELETE')"))
    assert db.scalar(text("SELECT has_table_privilege('vb_app', 'project_purge_key', 'SELECT')"))
    assert not any(db.scalar(text(f"SELECT has_table_privilege('vb_app', 'project_purge_key', '{p}')"))
                   for p in ("INSERT", "UPDATE", "DELETE"))


# ---- 0073: project_purge_key -------------------------------------------------------------------------------

KEY = "INSERT INTO project_purge_key (project_purge_id, key_name, key_refs) VALUES (:pp, CAST(:n AS text), ARRAY[CAST(:n AS text) || '@1'])"
DESTROY = ("UPDATE project_purge_key SET destroyed_at = now(), was_present = true, destroyed_by_purge_id = :by "
           "WHERE project_purge_id = :pp")


def record_key(owner, pp, p, name):
    """As the purge job does: inside its transaction, with the scoped setting naming the project."""
    with owner.begin() as c:
        c.execute(text("SELECT set_config('vb.purge_project_id', :p, true)"), {"p": str(p)})
        c.execute(text(KEY), {"pp": pp, "n": name})


def approved(owner, t, kind, **kw):
    pp = request(app_engine, t, kind=kind, **kw)
    run(app_engine, "UPDATE project_purge SET approved_at = now(), approved_by_user_id = :u WHERE project_purge_id = :pp",
        u=t["a2"], pp=pp)
    backdate(owner, pp)
    return pp


def execute(owner, t, pp):
    run(owner, "UPDATE project_purge SET executed_at = now(), executed_by_user_id = :u WHERE project_purge_id = :pp",
        u=t["a1"], pp=pp)


def test_keys_are_recorded_only_inside_the_purge_and_a_delete_destroys_its_own(two, owner):
    promote(owner, two["a2"])
    pp = approved(owner, two, "DELETE")
    name = f"vb-test-a-proj-{two['p']}"
    assert "permission denied" in refused(app_engine, KEY, pp=pp, n=name)
    assert "inside the purge transaction" in refused(owner, KEY, pp=pp, n=name)
    record_key(owner, pp, two["p"], name)
    assert "its executed DELETE" in refused(owner, DESTROY, by=pp, pp=pp)            # not before the commit
    run(owner, "DELETE FROM project WHERE project_id = :p", p=two["p"])
    execute(owner, two, pp)
    run(owner, DESTROY, by=pp, pp=pp)
    assert "never changes" in refused(owner, "UPDATE project_purge_key SET was_present = false")
    assert "never changes" in refused(owner, "UPDATE project_purge_key SET key_refs = '{}'")
    assert "not allowed" in refused(owner, "DELETE FROM project_purge_key")


def test_an_archive_keeps_its_keys_until_a_started_delete_archive_destroys_them(two, owner):
    promote(owner, two["a2"])
    arch = approved(owner, two, "ARCHIVE")
    run(owner, "UPDATE project_purge SET archive_object_name = 'test-a/1/project-1.json.enc', archive_sha256 = "
               "repeat('a', 64), archive_byte_size = 10, archive_key_ref = 'k@1' WHERE project_purge_id = :pp", pp=arch)
    record_key(owner, arch, two["p"], f"vb-test-a-proj-{two['p']}")
    run(owner, "DELETE FROM project WHERE project_id = :p", p=two["p"])
    execute(owner, two, arch)
    assert "its executed DELETE" in refused(owner, DESTROY, by=arch, pp=arch)        # an ARCHIVE never destroys
    dela = approved(owner, two, "DELETE_ARCHIVE", archive=arch)
    assert tuple(run(owner, "SELECT project_code, client_id FROM project_purge WHERE project_purge_id = :pp",
                     pp=dela)) == ("X", two["c"])                                   # copied from the ARCHIVE
    assert "its executed DELETE" in refused(owner, DESTROY, by=dela, pp=arch)        # U6: not before it starts
    start = "UPDATE project_purge SET destroy_started_at = now() WHERE project_purge_id = :pp"
    run(owner, "UPDATE app_user SET is_platform_admin = false WHERE app_user_id = :u", u=two["a2"])
    assert "still live platform admins" in refused(owner, start, pp=dela)           # sara H1: before the vault
    promote(owner, two["a2"])
    assert "every key of its archive" in refused(owner, "UPDATE project_purge SET executed_at = now(), "
                                                        "executed_by_user_id = :u WHERE project_purge_id = :pp",
                                                 u=two["a1"], pp=dela)
    run(owner, "UPDATE project_purge SET destroy_started_at = now() WHERE project_purge_id = :pp", pp=dela)
    run(owner, DESTROY, by=dela, pp=arch)
    execute(owner, two, dela)
    assert tuple(run(owner, "SELECT backups_age_out_on FROM project_purge WHERE project_purge_id = :pp",
                     pp=dela)) == (None,)                                           # no rows left the database
    run(owner, "UPDATE project_purge SET files_deleted_at = now(), files_deleted_count = 3 WHERE project_purge_id = :pp",
        pp=dela)
    assert "recorded once" in refused(owner, "UPDATE project_purge SET files_deleted_count = 4 "
                                             "WHERE project_purge_id = :pp", pp=dela)
