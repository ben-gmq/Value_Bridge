"""PROJECT_STATUS becomes a behaviour category: every project status is open or closed (slice16 schema §12.3, §12.8;
Q-89 b, AR-10 — the I-1 precedent of migration 0061).

The project row will carry its status's behaviour through a composite FK (migration 0071), so the database can hold
"closed_on is set exactly when the status is closed" without reading a code (law 5), and a status an admin adds later
must say whether it closes the project — the two-year archive clock can never miss one because of its name. This:
  1. refuses while any project-tier PROJECT_STATUS row or project hide of one exists — project statuses are
     company-only (G-2), so neither should exist; a stray one would escape the clock;
  2. widens ck_code_behaviour_present to PROJECT_STATUS and adds ck_code_project_status_behaviour (OPEN / CLOSED);
  3. sets the behaviour on the four company rows, matched by code only, idempotent: PLANNING, ACTIVE and ON_HOLD are
     open, CLOSED is closed. Any other company PROJECT_STATUS row refuses the upgrade by name rather than being
     guessed. seed_code_master carries the same behaviours.

Downgrade: clears the four behaviours and restores the three-category CHECK; refuses while project.status_behaviour
exists (0071 must be downgraded first, as its FK needs the behaviour).

Revision ID: 0070
Revises: 0069
"""
from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None

_OPEN = ("PLANNING", "ACTIVE", "ON_HOLD")
_CLOSED = ("CLOSED",)


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM code_master WHERE category = 'PROJECT_STATUS' AND project_id IS NOT NULL) THEN
        RAISE EXCEPTION 'project-tier PROJECT_STATUS rows exist (%): project statuses are company-only (G-2) '
          'and every row needs a behaviour; resolve them by hand first',
          (SELECT string_agg(project_id || ':' || code, ', ') FROM code_master
            WHERE category = 'PROJECT_STATUS' AND project_id IS NOT NULL);
      END IF;
      IF EXISTS (SELECT 1 FROM project_code_visibility v JOIN code_master c ON c.code_id = v.code_id
                  WHERE c.category = 'PROJECT_STATUS' AND v.is_active) THEN
        RAISE EXCEPTION 'a project hides a PROJECT_STATUS (%): project statuses are company-only; unhide first',
          (SELECT string_agg(v.project_id || ':' || c.code, ', ') FROM project_code_visibility v
             JOIN code_master c ON c.code_id = v.code_id WHERE c.category = 'PROJECT_STATUS' AND v.is_active);
      END IF;
      IF EXISTS (SELECT 1 FROM code_master WHERE category = 'PROJECT_STATUS'
                  AND code NOT IN (""" + _in(_OPEN + _CLOSED) + """)) THEN
        RAISE EXCEPTION 'unknown PROJECT_STATUS codes (%): give each an open / closed behaviour by hand first',
          (SELECT string_agg(code, ', ') FROM code_master WHERE category = 'PROJECT_STATUS'
            AND code NOT IN (""" + _in(_OPEN + _CLOSED) + """));
      END IF;
    END $$""")
    op.drop_constraint("ck_code_behaviour_present", "code_master", type_="check")
    op.execute(f"UPDATE code_master SET behaviour_code = 'OPEN' WHERE category = 'PROJECT_STATUS' "
               f"AND code IN ({_in(_OPEN)}) AND behaviour_code IS DISTINCT FROM 'OPEN'")
    op.execute(f"UPDATE code_master SET behaviour_code = 'CLOSED' WHERE category = 'PROJECT_STATUS' "
               f"AND code IN ({_in(_CLOSED)}) AND behaviour_code IS DISTINCT FROM 'CLOSED'")
    op.create_check_constraint(
        "ck_code_behaviour_present", "code_master",
        "(category IN ('FR_TYPE','RACI_TYPE','ISSUE_STATUS','PROJECT_STATUS')) = (behaviour_code IS NOT NULL)")
    op.create_check_constraint(
        "ck_code_project_status_behaviour", "code_master",
        "category <> 'PROJECT_STATUS' OR behaviour_code IN ('OPEN','CLOSED')")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
               "AND table_name = 'project' AND column_name = 'status_behaviour') THEN "
               "RAISE EXCEPTION 'project.status_behaviour exists: downgrade 0071 first'; END IF; END $$")
    op.drop_constraint("ck_code_project_status_behaviour", "code_master", type_="check")
    op.drop_constraint("ck_code_behaviour_present", "code_master", type_="check")
    op.execute("UPDATE code_master SET behaviour_code = NULL WHERE category = 'PROJECT_STATUS' "
               "AND behaviour_code IS NOT NULL")
    op.create_check_constraint(
        "ck_code_behaviour_present", "code_master",
        "(category IN ('FR_TYPE','RACI_TYPE','ISSUE_STATUS')) = (behaviour_code IS NOT NULL)")
