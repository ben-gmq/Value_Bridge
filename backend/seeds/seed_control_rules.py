"""The FTC house control rules, and copying them into existing projects (docs/slice_control_a_spec.md §2; CT-4).
Inserts the house rules that are missing (never overwrites one); with --actor-email, also copies every house rule a live
project lacks into it — one audited transaction per project. Idempotent. Run from backend/, after seed_code_master:
    python -m seeds.seed_control_rules                                   # first time on a machine: the house tier
    python -m seeds.seed_control_rules --actor-email <active platform admin>   # deploy: existing projects too"""
import argparse

from database import SessionLocal
from services import control


def seed(db) -> list[str]:
    """The house tier only (the test harness and a fresh machine). Commits."""
    added = control.seed_house(db)
    db.commit()
    return added


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--actor-email")
    args = ap.parse_args()
    with SessionLocal() as db:
        out = control.backfill(db, args.actor_email)
    print(f"house rules added: {', '.join(out['house_added']) or 'none'}")
    for row in out["projects"]:
        print(f"project {row['project_id']}: {', '.join(row['added']) or 'nothing to add'}")


if __name__ == "__main__":
    main()
