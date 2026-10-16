"""One-off for the slice 11 deploy (slice11_schema §1.2): each live BR's legacy business_logic and output_expectation
are copied once into a Rule and an Output requirement line. Per project, skipped once it has a BR_LINES_BACKFILLED
event, so a rerun is a no-op. Run from backend/, after alembic upgrade head and seed_code_master:
    python -m seeds.backfill_br_lines --actor-email <active platform admin>"""
import argparse

from database import SessionLocal
from services import br_lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--actor-email", required=True)
    args = ap.parse_args()
    with SessionLocal() as db:
        for row in br_lines.backfill(db, args.actor_email):
            done = "already backfilled" if row["count"] is None else f"{row['count']} lines copied"
            print(f"project {row['project_id']}: {done}")


if __name__ == "__main__":
    main()
