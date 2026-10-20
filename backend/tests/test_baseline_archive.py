"""Slice 16 step 1: baseline_archive, the outbox of archive files a baseline owes (slice16 schema §3.1, §12.3;
spec §3, §10 criteria 1 and 4 — the owed half; Q-79). Grade 2 for the writer to come; the guard on the record is
proven at the database, for the app role and the owner, because a written file's record that can change or
vanish is no evidence at all."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from tests.conftest import OWNER_URL
from tests.test_baseline import approve, bid, freeze, scope
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture

APP_UPDATABLE = {"object_name", "file_sha256", "byte_size", "key_ref", "written_at", "attempt_count",
                 "last_attempt_at", "last_error", "check_failed_at", "last_check_error", "updated_by", "row_version"}
WRITE = ("UPDATE baseline_archive SET object_name = :n, file_sha256 = repeat('a', 64), byte_size = 10, "
         "key_ref = 'k@1', written_at = now() WHERE baseline_id = :b AND archive_part = :p")


@pytest.fixture
def owner():
    eng = create_engine(OWNER_URL)
    yield eng
    eng.dispose()


def owed(db, b):
    return db.execute(text("SELECT archive_part, file_seq, project_id, format_version, written_at, created_by "
                           "FROM baseline_archive WHERE baseline_id = :b ORDER BY archive_part"), {"b": b}).all()


def refused(eng, sql, **params):
    with pytest.raises(DBAPIError) as e, eng.begin() as c:
        c.execute(text(sql), params)
    return str(e.value.orig)


def test_a_freeze_owes_its_scope_file_and_an_approval_its_signoff_file(client, ed, db):
    """Criterion 1 (owed half), Q-79: one owed SCOPE row in the freeze transaction, one owed SIGNOFF row with the
    approval — by the people who did them."""
    scope(client, ed)
    b = bid(freeze(client, ed))
    me = db.scalar(text("SELECT frozen_by_user_id FROM baseline WHERE baseline_id = :b"), {"b": b})
    assert owed(db, b) == [("SCOPE", 1, ed["p"], 1, None, me)]
    approve(client, ed, b)
    db.expire_all()
    assert [r[0] for r in owed(db, b)] == ["SCOPE", "SIGNOFF"]
    assert all(r.written_at is None for r in owed(db, b))


def test_a_refused_freeze_or_approval_owes_nothing(client, ed, db):
    """The owed row lives and dies with its transaction: a refused freeze leaves none, a refused approval none."""
    scope(client, ed)
    freeze(client, ed, expect=422, confirm_text="wrong")
    assert db.scalar(text("SELECT count(*) FROM baseline_archive")) == 0
    b = bid(freeze(client, ed))
    approve(client, ed, b, expect=422, client_approver_name=" ")
    db.expire_all()
    assert [r[0] for r in owed(db, b)] == ["SCOPE"]


def test_the_guard_holds_a_written_file_record_for_every_role(client, ed, owner):
    """Schema §3.1 / §12.3: nobody deletes the record; the file columns are set together once; a written row then
    accepts only its check result, once; the key never changes."""
    scope(client, ed)
    b = bid(freeze(client, ed))
    assert "permission denied" in refused(create_engine_app(), "DELETE FROM baseline_archive WHERE baseline_id = :b",
                                          b=b)
    assert "not allowed" in refused(owner, "DELETE FROM baseline_archive WHERE baseline_id = :b", b=b)
    assert "ck_ba_written_set" in refused(owner, "UPDATE baseline_archive SET written_at = now() WHERE baseline_id = :b",
                                          b=b)
    with owner.begin() as c:
        c.execute(text(WRITE), {"n": f"t/1/{b}.json.enc", "b": b, "p": "SCOPE"})
    for sql in ("UPDATE baseline_archive SET object_name = 'other' WHERE baseline_id = :b",
                "UPDATE baseline_archive SET attempt_count = 5 WHERE baseline_id = :b",
                "UPDATE baseline_archive SET file_seq = 2 WHERE baseline_id = :b"):
        assert "cannot change" in refused(owner, sql, b=b)
    with owner.begin() as c:
        c.execute(text("UPDATE baseline_archive SET check_failed_at = now(), last_check_error = 'Mismatch: sha256' "
                       "WHERE baseline_id = :b"), {"b": b})
    assert "cannot change" in refused(owner, "UPDATE baseline_archive SET last_check_error = 'x' WHERE baseline_id = :b",
                                      b=b)


def test_a_signoff_or_replacement_is_owed_only_when_its_condition_holds(client, ed, owner):
    """Q-79: no SIGNOFF before the approval; §18 S5: no replacement unless the file before it was written and
    failed its check."""
    scope(client, ed)
    b = bid(freeze(client, ed))
    ins = ("INSERT INTO baseline_archive (baseline_id, archive_part, file_seq, project_id, format_version, created_by) "
           "SELECT baseline_id, :p, :s, project_id, 1, frozen_by_user_id FROM baseline WHERE baseline_id = :b")
    assert "client approval" in refused(owner, ins, b=b, p="SIGNOFF", s=1)
    born_written = ("INSERT INTO baseline_archive (baseline_id, archive_part, file_seq, project_id, format_version, "
                    "created_by, object_name, file_sha256, byte_size, key_ref, written_at) SELECT baseline_id, 'SCOPE', "
                    "2, project_id, 1, frozen_by_user_id, 'fake', repeat('a', 64), 1, 'k@1', now() FROM baseline "
                    "WHERE baseline_id = :b")
    assert "failed its check" in refused(owner, ins, b=b, p="SCOPE", s=2)
    with owner.begin() as c:
        c.execute(text(WRITE), {"n": f"t/1/{b}.json.enc", "b": b, "p": "SCOPE"})
    assert "failed its check" in refused(owner, ins, b=b, p="SCOPE", s=2)
    with owner.begin() as c:
        c.execute(text("UPDATE baseline_archive SET check_failed_at = now(), last_check_error = 'Missing' "
                       "WHERE baseline_id = :b"), {"b": b})
    # sara M1: seq 2 is now legal, so only the born-written rule can refuse a row inserted as already written
    assert "recorded as owed" in refused(owner, born_written, b=b)
    with owner.begin() as c:
        c.execute(text(ins), {"b": b, "p": "SCOPE", "s": 2})
        assert c.scalar(text("SELECT count(*) FROM baseline_archive WHERE baseline_id = :b AND written_at IS NULL"),
                        {"b": b}) == 1
    # a second replacement while the first is still owed: its predecessor is not written, so it is refused
    assert "failed its check" in refused(owner, ins.replace(":s", "3"), b=b, p="SCOPE")


def test_the_app_role_updates_only_the_writer_columns(db):
    """§6.6: vb_app's column grant on baseline_archive is exactly the writer's and the check's columns; no DELETE."""
    cols = {r[0] for r in db.execute(text(
        "SELECT column_name FROM information_schema.column_privileges WHERE grantee = 'vb_app' "
        "AND table_name = 'baseline_archive' AND privilege_type = 'UPDATE'"))}
    assert cols == APP_UPDATABLE
    assert not db.scalar(text("SELECT has_table_privilege('vb_app', 'baseline_archive', 'DELETE')"))


def create_engine_app():
    from database import engine
    return engine
