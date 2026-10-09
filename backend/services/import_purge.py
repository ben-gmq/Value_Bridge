"""The 90-day import_row purge (Q14; design §7.12b; slice 4a spec §4, criterion 16; schema S4-9).

One of VB's three hard deletes (VB law 1): staged rows hold raw client content — people's names
among it — so 90 days after their batch was uploaded they are deleted, the batch's file name is
overwritten with '(purged)' (Q6: a file name can identify a person) and `rows_purged_at` is set.
The header keeps who, when, what and the counts. A batch that never committed becomes REJECTED,
so "purged ⇒ REJECTED or COMMITTED" holds.

4a-R6: an UPDATE row's before-values (`payload.before`) are kept 90 days from `committed_at`, so a
COMMITTED batch that holds any such row is due 90 days after its commit, not its upload. The
deferral is per batch — its rows go together and `rows_purged_at` keeps one meaning.

Runs as vb_app, which has DELETE on import_row and an UPDATE grant on file_name / status /
rows_purged_at / row_version (0019, 0020). Batches are locked first, FOR UPDATE SKIP LOCKED
(S4-9): a batch mid-commit is skipped and purged on the next run, and the lock order (batch, then
rows) is the commit's, so the two never deadlock. Idempotent: a purged batch is never due again.
Every run writes one IMPORT_ROWS_PURGED audit event, an empty run included, so a run is provable."""
from datetime import datetime

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session
from sqlalchemy.types import BigInteger

from services import audit, code_master

RETENTION_DAYS = 90
PURGED_FILE_NAME = "(purged)"

# A batch is due when its rows are past the window: 90 days from upload, or, for a COMMITTED
# batch holding before-values, 90 days from its commit (4a-R6). committed_at is set iff COMMITTED
# (service-enforced; a consistency line for it, import_batch_status_drift, is still owed), and committed_at >= uploaded_at
# is a CHECK, so "committed_at < cutoff" implies the upload is past it too.
DUE = """
    b.rows_purged_at IS NULL
    AND b.uploaded_at < :cutoff
    AND (b.committed_at IS NULL OR b.committed_at < :cutoff
         OR NOT EXISTS (SELECT 1 FROM import_row r
                        WHERE r.import_batch_id = b.import_batch_id AND r.payload ? 'before'))
"""


def cutoff_of(db: Session, now: datetime | None = None) -> datetime:
    """now − 90 days; `now` defaults to the database's transaction time."""
    return db.execute(text(f"SELECT coalesce(CAST(:now AS timestamptz), now()) - interval '{RETENTION_DAYS} days'"),
                      {"now": now}).scalar_one()


def purge_import_rows(db: Session) -> dict:
    """Purge every due batch this session can lock; commit once. Returns the run's summary.
    The clock is the database's only: no caller can pass a time that would purge young rows."""
    now = db.execute(text("SELECT now()")).scalar_one()
    cutoff = cutoff_of(db, now)
    status = {r.code: r.code_id for r in code_master.resolve(db, None, "IMPORT_STATUS")}   # Q-12

    ids = list(db.execute(text(f"SELECT b.import_batch_id FROM import_batch b WHERE {DUE} "
                               "ORDER BY b.import_batch_id FOR UPDATE OF b SKIP LOCKED"),
                          {"cutoff": cutoff}).scalars())
    if ids:
        # sara H-1: a batch committed while the locking statement ran is re-checked by Postgres on
        # its newest row, but the NOT EXISTS (… 'before') subquery still sees the statement's old
        # snapshot, so a just-committed UPDATE batch can look due. Re-test DUE in a new statement
        # (fresh snapshot) now that we hold the locks; one that drops out stays locked, harmlessly.
        ids = list(db.execute(text(f"SELECT b.import_batch_id FROM import_batch b "
                                   f"WHERE b.import_batch_id = ANY(:ids) AND {DUE} ORDER BY 1")
                              .bindparams(bindparam("ids", ids, type_=ARRAY(BigInteger))),
                              {"cutoff": cutoff}).scalars())
    rows, rejected = 0, []
    if ids:
        arr = bindparam("ids", ids, type_=ARRAY(BigInteger))
        rejected = list(db.execute(text(
            "SELECT import_batch_id FROM import_batch WHERE import_batch_id = ANY(:ids) "
            "AND status_code_id IN (:validating, :validated) ORDER BY import_batch_id").bindparams(arr),
            {"validating": status["VALIDATING"], "validated": status["VALIDATED"]}).scalars())
        rows = db.execute(text("DELETE FROM import_row WHERE import_batch_id = ANY(:ids)")
                          .bindparams(arr)).rowcount
        db.execute(text(
            "UPDATE import_batch SET rows_purged_at = :now, file_name = :purged, "
            "status_code_id = CASE WHEN status_code_id IN (:validating, :validated) "
            "THEN :rejected ELSE status_code_id END, row_version = row_version + 1 "
            "WHERE import_batch_id = ANY(:ids)").bindparams(arr),
            {"now": now, "purged": PURGED_FILE_NAME, "validating": status["VALIDATING"],
             "validated": status["VALIDATED"], "rejected": status["REJECTED"]})
    summary = {"batches": ids, "rows": rows, "rejected": rejected, "cutoff": cutoff.isoformat()}
    audit.record(db, "IMPORT_ROWS_PURGED", target_table="import_batch", detail=summary)
    db.commit()
    return summary


def overdue(db: Session, project_id: int | None = None, now: datetime | None = None) -> list[dict]:
    """Batches past their window that still hold rows — the same rule the purge uses, so a batch
    shows here exactly until a run purges it (A-4a-5). Every project when project_id is None."""
    found = db.execute(text(
        "SELECT b.import_batch_id, b.project_id, b.uploaded_at, b.committed_at, "
        "(SELECT count(*) FROM import_row r WHERE r.import_batch_id = b.import_batch_id) AS rows "
        f"FROM import_batch b WHERE {DUE} "
        "AND (CAST(:p AS bigint) IS NULL OR b.project_id = :p) "
        "AND EXISTS (SELECT 1 FROM import_row r WHERE r.import_batch_id = b.import_batch_id) "
        "ORDER BY b.uploaded_at, b.import_batch_id"),
        {"cutoff": cutoff_of(db, now), "p": project_id}).mappings()
    return [dict(r) for r in found]
