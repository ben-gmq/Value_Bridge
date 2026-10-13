"""Before deploying migration 0052 (D-64, one RACI per process): list what would stop it. Read-only.
Run from backend/ against the database you are about to migrate:
    ./venv/bin/python -m scripts.precheck_0052
It connects as the application role (DATABASE_URL), runs one SELECT in a read-only transaction and prints every
to-be process step that has live step roles but no live business requirement (Q-5). 0052 refuses to run while
any exists, because it never invents a requirement. Fix each one first (restore or create its requirement, or
remove the step roles), then run this again until it prints nothing to fix. Exit code 1 while anything is listed.
The query is the same as 0052's step 1, and works before and after 0052."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from database import SessionLocal  # noqa: E402

QUERY = """
    SELECT n.project_id, p.project_code, n.hier_code, n.node_name, n.bfc_node_id,
           array_agg(r.bfc_node_org_role_id ORDER BY r.bfc_node_org_role_id) AS step_role_ids
    FROM   bfc_node_org_role r
    JOIN   bfc_node n ON n.bfc_node_id = r.bfc_node_id
    JOIN   project p  ON p.project_id = n.project_id
    WHERE  r.is_active AND n.bfc_set_code = 'TO_BE'
      AND  NOT EXISTS (SELECT 1 FROM business_requirement b WHERE b.bfc_node_id = r.bfc_node_id AND b.is_active)
    GROUP  BY n.project_id, p.project_code, n.hier_code, n.node_name, n.bfc_node_id
    ORDER  BY n.project_id, n.hier_code"""


def find(db) -> list:
    db.connection(execution_options={"postgresql_readonly": True})
    try:
        return db.execute(text(QUERY)).all()
    finally:
        db.rollback()


def main() -> int:
    with SessionLocal() as db:
        rows = find(db)
    if not rows:
        print("0052 pre-check: nothing to fix.")
        return 0
    print(f"0052 pre-check: {len(rows)} to-be process step(s) have live roles and no live requirement:")
    for project_id, code, hier, name, node_id, ids in rows:
        print(f"  project {project_id} ({code}): {hier} {name} (bfc_node_id {node_id}, step roles {list(ids)})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
