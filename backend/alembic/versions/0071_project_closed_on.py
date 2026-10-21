"""project.closed_on and the status's open / closed meaning on the project row (slice16 schema §12.3, §12.8; AR-8,
AR-10, AR-12 — Q-87, Q-89 b, Q-90, Q-92).

closed_on is the day the project's status became a closed one (ICT), the start of the two-year archive clock; it is
set and cleared by the project service only (law 6). The row carries its status's behaviour through the composite
fk_project_status (code_id, category, behaviour) — the fk_issue_status precedent (0063) — so ck_project_closed_on can
hold "closed exactly when closed_on is set" without naming a code (law 5).

Backfill (AR-12, Q-92): every project already closed gets closed_on = the migration day (ICT), so nothing comes due
on the day the rule arrives; every retired project that was never closed is moved to the company CLOSED status with
the same date (AR-10: retiring closes first).

Downgrade: refuses while project_purge exists (0072 first) or while any project holds a clock (closed_on set) — a
clock would be lost. Stricter than schema §12.8 ("set after the migration day"), which needs the backfill day kept
somewhere the models would also have to describe; otherwise drops the columns and restores the single-column
fk_project_status. Retired
projects moved to CLOSED stay CLOSED (their old status was not recorded and is no longer meaningful).

Revision ID: 0071
Revises: 0070
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import category_column

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None

TODAY = "(now() AT TIME ZONE 'Asia/Bangkok')::date"


def upgrade() -> None:
    op.add_column("project", sa.Column("closed_on", sa.Date))
    op.add_column("project", category_column("status_category", "PROJECT_STATUS"))
    op.add_column("project", sa.Column("status_behaviour", sa.String(20)))
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM project WHERE NOT is_active) AND NOT EXISTS (
          SELECT 1 FROM code_master WHERE category = 'PROJECT_STATUS' AND code = 'CLOSED' AND project_id IS NULL
             AND is_active AND behaviour_code = 'CLOSED') THEN
        RAISE EXCEPTION 'retired projects must move to a closed status (AR-10) but no live company CLOSED status exists';
      END IF;
    END $$""")
    op.execute("UPDATE project p SET status_code_id = c.code_id FROM code_master c "
               "WHERE NOT p.is_active AND c.category = 'PROJECT_STATUS' AND c.code = 'CLOSED' AND c.project_id IS NULL "
               "AND p.status_code_id IS DISTINCT FROM c.code_id "
               "AND (SELECT behaviour_code FROM code_master s WHERE s.code_id = p.status_code_id) <> 'CLOSED'")
    op.execute("UPDATE project p SET status_behaviour = c.behaviour_code FROM code_master c "
               "WHERE c.code_id = p.status_code_id")
    op.execute(f"UPDATE project SET closed_on = {TODAY} WHERE status_behaviour = 'CLOSED'")
    op.alter_column("project", "status_behaviour", nullable=False)
    op.drop_constraint("fk_project_status", "project", type_="foreignkey")
    op.create_foreign_key("fk_project_status", "project", "code_master",
                          ["status_code_id", "status_category", "status_behaviour"],
                          ["code_id", "category", "behaviour_code"], onupdate="NO ACTION")
    op.create_check_constraint("ck_project_closed_on", "project",
                               "(status_behaviour = 'CLOSED') = (closed_on IS NOT NULL)")
    op.create_index("ix_project_closed_on", "project", ["closed_on"], postgresql_where=sa.text("closed_on IS NOT NULL"))


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF to_regclass('public.project_purge') IS NOT NULL THEN
        RAISE EXCEPTION 'project_purge exists: downgrade 0072 first';
      END IF;
      IF EXISTS (SELECT 1 FROM project WHERE closed_on IS NOT NULL) THEN
        RAISE EXCEPTION 'a closed project holds an archive clock that would be lost, downgrade refused';
      END IF;
    END $$""")
    op.drop_index("ix_project_closed_on", table_name="project")
    op.drop_constraint("ck_project_closed_on", "project", type_="check")
    op.drop_constraint("fk_project_status", "project", type_="foreignkey")
    op.create_foreign_key("fk_project_status", "project", "code_master", ["status_code_id"], ["code_id"])
    op.drop_column("project", "status_behaviour")
    op.drop_column("project", "status_category")
    op.drop_column("project", "closed_on")
