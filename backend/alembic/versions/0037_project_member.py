"""project_member — a named member of a project, with a level (OR-6, slice7_schema §8.4).

Membership only matters while the project is restricted. Each membership period is its own row
(partial unique while live); re-adding inserts, never restores (R2-S5). A live membership blocks
retiring its project through the generated live guard, as a live grant did.

Data step (§8.5 step 1): every live grant is copied before 0038 revokes it — a project grant to one
row, a program grant to one row per active project of the program; OWNER/EDITOR → EDIT,
REVIEWER → VIEW; the note names the grant.

Revision ID: 0037
Revises: 0036
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, live_guard, updated_at_trigger

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_member",
        sa.Column("project_member_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        live_guard("project_is_active", True),
        sa.Column("app_user_id", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.Column("access_level", sa.String(4), nullable=False),
        sa.Column("member_note", sa.Text),
        *audit_columns(),
        sa.ForeignKeyConstraint(["project_id", "project_is_active"], ["project.project_id", "project.is_active"],
                                name="fk_pm_live_project", onupdate="NO ACTION"),
        sa.CheckConstraint("access_level IN ('EDIT', 'VIEW')", name="ck_pm_level"),
        sa.CheckConstraint("member_note IS NULL OR btrim(member_note) <> ''", name="ck_pm_note_not_blank"),
    )
    op.execute("CREATE UNIQUE INDEX uq_pm_live ON project_member (project_id, app_user_id) WHERE is_active")
    op.execute("CREATE INDEX ix_pm_user_live ON project_member (app_user_id) WHERE is_active")
    updated_at_trigger("project_member")
    op.execute("""
        INSERT INTO project_member (project_id, app_user_id, access_level, member_note, created_by)
        SELECT p.project_id, g.app_user_id,
               CASE WHEN c.code = 'REVIEWER' THEN 'VIEW' ELSE 'EDIT' END,
               'from grant #' || g.user_access_grant_id || ' (D-40)', g.granted_by_user_id
        FROM user_access_grant g
        JOIN code_master c ON c.code_id = g.project_role_code_id
        JOIN project p ON p.is_active AND (p.project_id = g.project_id OR p.program_id = g.program_id)
        WHERE g.is_active""")


def downgrade() -> None:
    drop_updated_at_trigger("project_member")
    op.drop_table("project_member")
