"""Stamp this database's archive identity (slice16 schema §3.4, §12.7; spec §18 S6). Run from backend/, as the owner:
    ./venv/bin/python -m scripts.stamp_instance <instance-id>             # first stamp
    ./venv/bin/python -m scripts.stamp_instance <instance-id> --restamp   # a restored copy taking its own name
It connects with MIGRATION_DATABASE_URL (vb_owner); the app role can only read vb_instance. A first stamp refuses a
stamped database; a re-stamp keeps the old id in prior_instance_ids so its tombstones still stop the writer. Set
VB_INSTANCE_ID to the same id, or the server refuses to start."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from config import get_settings  # noqa: E402


def stamp(owner_url: str, instance_id: str, restamp: bool) -> str:
    eng = create_engine(owner_url)
    try:
        with eng.begin() as c:
            old = c.scalar(text("SELECT instance_id FROM vb_instance FOR UPDATE"))
            if old is None:
                c.execute(text("INSERT INTO vb_instance (instance_id) VALUES (:i)"), {"i": instance_id})
                return f"Stamped {instance_id!r}."
            if not restamp:
                raise SystemExit(f"Already stamped {old!r}; pass --restamp to give a restored copy its own id.")
            c.execute(text("UPDATE vb_instance SET instance_id = :i, "
                           "prior_instance_ids = prior_instance_ids || instance_id::text"), {"i": instance_id})
            return f"Re-stamped {old!r} -> {instance_id!r}; {old!r} kept as a prior id."
    finally:
        eng.dispose()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("instance_id")
    p.add_argument("--restamp", action="store_true")
    a = p.parse_args()
    print(stamp(get_settings().migration_database_url, a.instance_id, a.restamp))


if __name__ == "__main__":
    main()
