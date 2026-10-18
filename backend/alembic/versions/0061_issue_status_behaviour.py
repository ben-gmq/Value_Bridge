"""ISSUE_STATUS becomes a behaviour category: every issue status is open or closed (slice 14 §15 N1–N2, I-1).

The issue row carries its status's behaviour through a composite FK (migration 0063), so the database can hold
"resolved_at is set exactly when the status is closed" without reading a code (law 5). This migration:
  1. refuses while any project-tier ISSUE_STATUS row or project hide of one exists (R6) — issue statuses are
     company-only from here on (I-1), so a project-only status would escape the open count;
  2. widens ck_code_behaviour_present to ISSUE_STATUS and adds ck_code_issue_status_behaviour (OPEN / CLOSED);
  3. sets the behaviour on the five company rows, matched by code only, idempotent (deviation 14a): OPEN,
     IN_PROGRESS and DEFERRED are open (I-11), RESOLVED and CLOSED are closed. Any other company ISSUE_STATUS row
     refuses the upgrade by name rather than being guessed. seed_code_master carries the same behaviours.

Downgrade: clears the five behaviours and restores the two-category CHECK; refuses while an `issue` table exists
(0063 must be downgraded first, as its FK needs the behaviour).

Revision ID: 0061
Revises: 0060
"""
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

_OPEN = ("OPEN", "IN_PROGRESS", "DEFERRED")
_CLOSED = ("RESOLVED", "CLOSED")


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM code_master WHERE category = 'ISSUE_STATUS' AND project_id IS NOT NULL) THEN
        RAISE EXCEPTION 'project-tier ISSUE_STATUS rows exist (%): issue statuses are company-only (I-1) '
          'and every row needs a behaviour; resolve them by hand first',
          (SELECT string_agg(project_id || ':' || code, ', ') FROM code_master
            WHERE category = 'ISSUE_STATUS' AND project_id IS NOT NULL);
      END IF;
      IF EXISTS (SELECT 1 FROM project_code_visibility v JOIN code_master c ON c.code_id = v.code_id
                  WHERE c.category = 'ISSUE_STATUS' AND v.is_active) THEN
        RAISE EXCEPTION 'a project hides an ISSUE_STATUS (%): issue statuses are company-only (I-1); unhide first',
          (SELECT string_agg(v.project_id || ':' || c.code, ', ') FROM project_code_visibility v
             JOIN code_master c ON c.code_id = v.code_id WHERE c.category = 'ISSUE_STATUS' AND v.is_active);
      END IF;
      IF EXISTS (SELECT 1 FROM code_master WHERE category = 'ISSUE_STATUS'
                  AND code NOT IN (""" + _in(_OPEN + _CLOSED) + """)) THEN
        RAISE EXCEPTION 'unknown ISSUE_STATUS codes (%): give each an open / closed behaviour by hand first',
          (SELECT string_agg(code, ', ') FROM code_master WHERE category = 'ISSUE_STATUS'
            AND code NOT IN (""" + _in(_OPEN + _CLOSED) + """));
      END IF;
    END $$""")
    op.drop_constraint("ck_code_behaviour_present", "code_master", type_="check")
    op.execute(f"UPDATE code_master SET behaviour_code = 'OPEN' WHERE category = 'ISSUE_STATUS' "
               f"AND code IN ({_in(_OPEN)}) AND behaviour_code IS DISTINCT FROM 'OPEN'")
    op.execute(f"UPDATE code_master SET behaviour_code = 'CLOSED' WHERE category = 'ISSUE_STATUS' "
               f"AND code IN ({_in(_CLOSED)}) AND behaviour_code IS DISTINCT FROM 'CLOSED'")
    op.create_check_constraint(
        "ck_code_behaviour_present", "code_master",
        "(category IN ('FR_TYPE','RACI_TYPE','ISSUE_STATUS')) = (behaviour_code IS NOT NULL)")
    op.create_check_constraint(
        "ck_code_issue_status_behaviour", "code_master",
        "category <> 'ISSUE_STATUS' OR behaviour_code IN ('OPEN','CLOSED')")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF to_regclass('public.issue') IS NOT NULL THEN "
               "RAISE EXCEPTION 'the issue table exists: downgrade 0063 first'; END IF; END $$")
    op.drop_constraint("ck_code_issue_status_behaviour", "code_master", type_="check")
    op.drop_constraint("ck_code_behaviour_present", "code_master", type_="check")
    op.execute("UPDATE code_master SET behaviour_code = NULL WHERE category = 'ISSUE_STATUS' "
               "AND behaviour_code IS NOT NULL")
    op.create_check_constraint(
        "ck_code_behaviour_present", "code_master",
        "(category IN ('FR_TYPE','RACI_TYPE')) = (behaviour_code IS NOT NULL)")
