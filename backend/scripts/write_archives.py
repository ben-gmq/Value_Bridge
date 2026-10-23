"""Write every owed baseline archive file (slice16 spec §7, Q-77). Run from backend/:
    ./venv/bin/python -m scripts.write_archives [--limit N]
Covers the backlog: baselines frozen before slice 16, a write that failed after a freeze, a host where archiving was
not configured at the time. Connects as the application role; needs VB_ARCHIVE_DIR and VB_ARCHIVE_KEY_DIR and a
stamped database. Safe to run again: a written file is never written twice, and a file stored but not recorded is
verified and adopted (R9). A row that failed in the last 6 hours waits for a later run (R10)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from config import get_settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import BaselineArchive  # noqa: E402
from services import archive  # noqa: E402
from services.archive_store import from_settings  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=500)
    a = p.parse_args()
    target = from_settings(get_settings())
    if target is None:
        raise SystemExit("VB_ARCHIVE_DIR and VB_ARCHIVE_KEY_DIR must be set.")
    done = archive.write_pending(*target, limit=a.limit)
    with SessionLocal() as db:
        owed = db.scalar(select(func.count()).select_from(BaselineArchive).where(BaselineArchive.written_at.is_(None)))
    print(f"Written {done['written']}, adopted {done['adopted']}, failed {done['failed']}; still owed {owed}.")


if __name__ == "__main__":
    main()
