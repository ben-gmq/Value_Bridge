"""The ERD load fixture for slice 3 criterion 17: 200 entities with 2,000 fields and FKs, added
to one project of a uat/demo database. Run from backend/:
    VB_ALLOW_DEMO_SEED=1 DATABASE_URL=<a throwaway db> ./venv/bin/python scripts/seed_erd_load.py \\
        --project-code DEMO
It refuses unless VB_ALLOW_DEMO_SEED=1 is set AND the database it is actually connected to
(`current_database()`, not the URL, sara H1) has 'uat' or 'demo' in its name, as
seeds/seed_demo.py does. It refuses a project that already holds the load entities, so it is
run once per database. Everything goes through services.data_entity, so numbering, FK groups
and the field rules are the app's own. The author is the first active platform admin.

Each entity gets a 1-field key, then up to 2 FKs to earlier entities (one of them part of a
two-field key every tenth entity, so identifying lines appear), then attributes up to 10 fields.
"""
import argparse
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import AppUser, DataEntity, Project  # noqa: E402
from services import data_entity  # noqa: E402

SAFE_MARKERS = ("uat", "demo")
PREFIX = "Load entity"
ENTITIES, FIELDS_EACH = 200, 10


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-code", default="DEMO")
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()
    if os.environ.get("VB_ALLOW_DEMO_SEED") != "1":
        raise SystemExit("Refusing: set VB_ALLOW_DEMO_SEED=1 to seed a demo database")
    rnd = random.Random(args.seed)
    with SessionLocal() as db:
        name = db.scalar(text("select current_database()"))
        if not any(m in name.lower() for m in SAFE_MARKERS):
            raise SystemExit(f"Refusing: connected database '{name}' is not a uat/demo database")
        proj = db.scalar(select(Project).where(Project.project_code == args.project_code))
        if proj is None:
            raise SystemExit(f"No project with code {args.project_code}")
        if db.scalar(select(DataEntity.data_entity_id).where(
                DataEntity.project_id == proj.project_id, DataEntity.de_name.startswith(PREFIX)).limit(1)):
            raise SystemExit("Refusing: this project already holds the load entities")
        actor = db.scalar(select(AppUser.app_user_id).where(AppUser.is_platform_admin, AppUser.is_active)
                          .order_by(AppUser.app_user_id).limit(1))
        if actor is None:
            raise SystemExit("No active platform admin to author the rows")

        made: list[tuple] = []                                   # (entity, its key field)
        total = 0
        for i in range(1, ENTITIES + 1):
            de = data_entity.create_entity(db, actor, proj.project_id, f"{PREFIX} {i:03d}", None, None)
            key = data_entity.create_field(db, actor, de, f"e{i:03d}_id", {
                "is_primary_key": True, "pk_ordinal": 1, "is_mandatory": True, "data_type_code": "INTEGER"})
            n = 1
            parents = rnd.sample(made, k=min(len(made), 2))
            for j, (parent, parent_key) in enumerate(parents):
                spec = {"ref_data_entity_id": parent.data_entity_id,
                        "ref_data_field_id": parent_key.data_field_id,
                        "is_mandatory": rnd.choice([True, False, None]), "data_type_code": "INTEGER"}
                if j == 0 and i % 10 == 0:                        # a two-field key: identifying
                    spec.update(is_primary_key=True, pk_ordinal=2, is_mandatory=True)
                data_entity.create_field(db, actor, de, f"{parent.de_name[-3:]}_ref_{j + 1}", spec)
                n += 1
            while n < FIELDS_EACH:
                data_entity.create_field(db, actor, de, f"attr_{n:02d}", {
                    "data_type_code": rnd.choice(["STRING", "INTEGER", "DATE", "DECIMAL", None]),
                    "is_mandatory": rnd.choice([True, False, None]),
                    "description": f"Load attribute {n} of entity {i}"})
                n += 1
            total += n
            made.append((de, key))
            if i % 20 == 0:
                print(f"{i} entities, {total} fields")
        print(f"Done: {ENTITIES} entities, {total} fields in project {args.project_code} of {name}")


if __name__ == "__main__":
    main()
