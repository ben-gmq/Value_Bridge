"""Backfill the rate card for projects created before Slice 6c (spec §4). Fills missing cells only,
idempotent, one audited transaction per project. Run from backend/:
    python -m seeds.seed_effort_rate --actor-email <active platform admin>"""
import argparse

from database import SessionLocal
from services import effort


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--actor-email", required=True)
    args = ap.parse_args()
    with SessionLocal() as db:
        for row in effort.backfill(db, args.actor_email):
            print(f"project {row['project_id']}: {row['rate_cells_seeded']} cells seeded"
                  + (f", unresolved {row['rate_cells_unresolved']}" if row["rate_cells_unresolved"] else ""))


if __name__ == "__main__":
    main()
