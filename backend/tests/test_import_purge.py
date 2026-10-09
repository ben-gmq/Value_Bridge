"""Slice 4a-3 — the 90-day import_row purge (docs/slice4a_spec.md §4, criterion 16, A-4a-5,
4a-R6; schema S4-9, Q6). Grade 1: the purge hard-deletes, so each rule is proven against the
database directly.

Batches are built through the real validate (and commit) path, then aged by moving
uploaded_at / committed_at back as the owner role — vb_app's column grant leaves uploaded_at
write-once, by design (Q-17b). The purge itself always runs as vb_app."""
import pytest
from sqlalchemy import create_engine, select, text

from database import SessionLocal
from models import AuditEvent
from scripts import purge_import_rows as cli
from services import bulk, import_purge
from services.consistency import consistency_check
from tests.conftest import OWNER_URL
from tests.test_bulk_import import batch, book, cell, commit, edit, export, staged, three  # noqa: F401
from tests.test_scope_api import ed  # noqa: F401 — fixture


@pytest.fixture
def owner():
    eng = create_engine(OWNER_URL)
    yield eng
    eng.dispose()


def age(owner, pv, uploaded_days: int, committed_days: int | None = None) -> int:
    """Move a batch's upload (and commit) that many days into the past; returns its id."""
    b = (pv["batch"] if "batch" in pv else pv)["import_batch_id"]
    with owner.begin() as c:
        c.execute(text("UPDATE import_batch SET uploaded_at = now() - make_interval(days => :u), "
                       "committed_at = CASE WHEN committed_at IS NULL THEN NULL "
                       "ELSE now() - make_interval(days => :c) END WHERE import_batch_id = :b"),
                  {"u": uploaded_days, "c": committed_days if committed_days is not None else uploaded_days,
                   "b": b})
    return b


def header(db, b) -> dict:
    return dict(db.execute(text(
        "SELECT b.file_name, b.uploaded_by_user_id, b.uploaded_at, b.row_count, b.error_count, "
        "b.insert_count, b.update_count, b.committed_at, b.rows_purged_at, b.row_version, c.code AS status "
        "FROM import_batch b JOIN code_master c ON c.code_id = b.status_code_id "
        "WHERE b.import_batch_id = :b"), {"b": b}).mappings().one())


def row_count(db, b) -> int:
    return db.execute(text("SELECT count(*) FROM import_row WHERE import_batch_id = :b"), {"b": b}).scalar_one()


def purge_events(db) -> list[AuditEvent]:
    db.expire_all()
    return list(db.scalars(select(AuditEvent).where(AuditEvent.event_type == "IMPORT_ROWS_PURGED")
                           .order_by(AuditEvent.audit_event_id)))


def overdue_ids(db, p=None) -> list[int]:
    return [b["import_batch_id"] for b in consistency_check(db, p)["purge_overdue"]]


# ---- criterion 16 (147, Q6) ---------------------------------------------------------------------

def test_a_91_day_batch_is_purged_and_an_89_day_batch_is_untouched(client, ed, db, owner):
    old = age(owner, staged(client, ed, book([{"de_name": "Customer"}, {"de_name": "Order"}]),
                            name="J Smith - salary review.xlsx"), 91)
    young = age(owner, staged(client, ed, book([{"de_name": "Product"}]), name="young.xlsx"), 89)
    done = staged(client, ed, book([{"de_name": "Invoice"}]), name="done.xlsx")
    assert commit(client, ed, done, ack=1).status_code == 200
    done = age(owner, done, 91)                         # INSERT rows only: no before-values
    before_old, before_young = header(db, old), header(db, young)
    assert before_old["status"] == "VALIDATED" and row_count(db, old) == 2

    # purge_overdue lists the overdue batches (and only those) until they are purged.
    assert overdue_ids(db) == sorted([old, done])
    assert overdue_ids(db, ed["p"]) == sorted([old, done])
    assert overdue_ids(db, ed["p"] + 999) == []

    run = bulk.purge_import_rows(db)
    assert (run["batches"], run["rows"], run["rejected"]) == (sorted([old, done]), 3, [old])

    after = header(db, old)
    assert row_count(db, old) == 0
    assert after["file_name"] == "(purged)"
    assert after["status"] == "REJECTED"                # it never committed
    assert after["rows_purged_at"] is not None
    for k in ("uploaded_by_user_id", "uploaded_at", "row_count", "error_count", "insert_count",
              "update_count", "committed_at"):
        assert after[k] == before_old[k], k             # the header keeps who, when and the counts
    assert after["row_version"] == before_old["row_version"] + 1

    d = header(db, done)
    assert (row_count(db, done), d["file_name"], d["status"]) == (0, "(purged)", "COMMITTED")

    assert header(db, young) == before_young            # untouched, to the row_version
    assert row_count(db, young) == 1

    [ev] = purge_events(db)                             # one audit row for the run
    assert ev.target_table == "import_batch" and ev.app_user_id is None
    assert ev.detail["batches"] == sorted([old, done]) and ev.detail["rows"] == 3
    assert ev.detail["rejected"] == [old] and ev.detail["cutoff"] == run["cutoff"]

    assert overdue_ids(db) == []                        # purged, so no longer listed
    shown = batch(client, ed, {"import_batch_id": old})
    assert shown["purged"] is True and shown["rows"] == []
    assert shown["batch"]["file_name"] == "(purged)" and shown["batch"]["row_count"] == 2


def test_a_purged_uncommitted_batch_can_no_longer_be_committed(client, ed, db, owner):
    pv = staged(client, ed, book([{"de_name": "Customer"}]))
    age(owner, pv, 91)
    bulk.purge_import_rows(db)
    r = commit(client, ed, pv, ack=1, row_version=pv["batch"]["row_version"] + 1)
    assert r.status_code == 409 and "rejected" in r.json()["detail"]


# ---- 4a-R6: before-values are kept 90 days from committed_at ------------------------------------

def test_before_values_defer_a_committed_batch_to_90_days_from_its_commit(client, ed, db, owner, three):
    body = edit(export(client, ed), lambda ws, col: cell(ws, col, 3, "description", "Who pays"))
    pv = staged(client, ed, body)
    assert commit(client, ed, pv, ack=None).status_code == 200
    b = age(owner, pv, 91, 30)                          # uploaded 91 days ago, committed 30 days ago
    assert db.execute(text("SELECT count(*) FROM import_row WHERE import_batch_id = :b "
                           "AND payload ? 'before'"), {"b": b}).scalar_one() == 1

    assert overdue_ids(db) == []
    run = bulk.purge_import_rows(db)
    assert run["batches"] == [] and row_count(db, b) == 3
    assert header(db, b)["file_name"] == "model.xlsx" and header(db, b)["rows_purged_at"] is None

    age(owner, pv, 121, 91)                             # now 91 days since the commit
    assert overdue_ids(db) == [b]
    assert bulk.purge_import_rows(db)["batches"] == [b]
    h = header(db, b)
    assert (row_count(db, b), h["file_name"], h["status"]) == (0, "(purged)", "COMMITTED")


# ---- S4-9: batches are locked first, SKIP LOCKED -------------------------------------------------

def test_a_batch_locked_by_another_session_is_skipped_not_waited_on(client, ed, db, owner):
    held = age(owner, staged(client, ed, book([{"de_name": "Customer"}])), 91)
    free = age(owner, staged(client, ed, book([{"de_name": "Order"}])), 91)
    other = SessionLocal()
    try:
        other.execute(text("SELECT 1 FROM import_batch WHERE import_batch_id = :b FOR UPDATE"), {"b": held})
        db.execute(text("SET LOCAL lock_timeout = '1s'"))  # waiting would raise, not hang
        run = bulk.purge_import_rows(db)
        assert run["batches"] == [free]
        assert row_count(db, held) == 1 and header(db, held)["status"] == "VALIDATED"
        assert overdue_ids(db) == [held]                # still visible while it waits
    finally:
        other.rollback()
        other.close()
    assert bulk.purge_import_rows(db)["batches"] == [held]
    assert row_count(db, held) == 0 and overdue_ids(db) == []


# ---- idempotence --------------------------------------------------------------------------------

def test_a_second_run_purges_nothing_and_audits_an_empty_run(client, ed, db, owner):
    b = age(owner, staged(client, ed, book([{"de_name": "Customer"}])), 91)
    bulk.purge_import_rows(db)
    first = header(db, b)
    again = bulk.purge_import_rows(db)
    assert (again["batches"], again["rows"], again["rejected"]) == ([], 0, [])
    assert header(db, b) == first                       # rows_purged_at and row_version unchanged
    events = purge_events(db)
    assert len(events) == 2 and events[1].detail["batches"] == [] and events[1].detail["rows"] == 0


# ---- the CLI (A-4a-5) -----------------------------------------------------------------------------

def test_the_cli_purges_as_the_app_role_and_prints_a_summary(client, ed, db, owner, capsys):
    b = age(owner, staged(client, ed, book([{"de_name": "Customer"}, {"de_name": "Order"}])), 91)
    with SessionLocal() as s:
        assert s.execute(text("SELECT current_user")).scalar_one() == "vb_app"
    cli.main()
    out = capsys.readouterr().out
    assert "Purged 2 rows from 1 batches (1 uncommitted, now REJECTED)" in out
    assert "Still overdue" not in out
    assert row_count(db, b) == 0 and len(purge_events(db)) == 1
    assert import_purge.overdue(db) == []
