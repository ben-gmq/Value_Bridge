"""The 90-day import_row purge, run by hand until a schedule exists (Q14, A-4a-5). Run from backend/:
    ./venv/bin/python -m scripts.purge_import_rows
It connects as the application role (DATABASE_URL, vb_app), purges every batch past its window
that no other session holds (SKIP LOCKED, S4-9), writes one IMPORT_ROWS_PURGED audit event, and
prints a short summary plus anything still overdue (a batch locked mid-commit is purged on the
next run). Safe to run again: a purged batch is never due twice."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import SessionLocal  # noqa: E402
from services import import_purge  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        run = import_purge.purge_import_rows(db)
        left = import_purge.overdue(db)
    print(f"Purged {run['rows']} rows from {len(run['batches'])} batches, {len(run['purged'])} now fully "
          f"purged ({len(run['rejected'])} uncommitted, now REJECTED); cutoff {run['cutoff']}.")
    if left:
        print(f"Still overdue (locked during this run): batches {', '.join(str(b['import_batch_id']) for b in left)}.")


if __name__ == "__main__":
    main()
