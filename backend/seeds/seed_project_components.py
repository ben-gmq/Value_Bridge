"""One-off for the 7a deploy: projects created before Slice 7a keep every component on (slice7_schema
§5.3, Q-9). Touches only projects with no project_component row at all, live or retired, so a later
run never undoes a switch-off (DR7-P1). Idempotent, one audit event per project changed. Run from backend/, after seed_code_master:
    python -m seeds.seed_project_components --actor-email <active platform admin>"""
import argparse

from database import SessionLocal
from services import components


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--actor-email", required=True)
    args = ap.parse_args()
    with SessionLocal() as db:
        for row in components.backfill(db, args.actor_email):
            print(f"project {row['project_id']}: {len(row['added'])} components switched on")


if __name__ == "__main__":
    main()
