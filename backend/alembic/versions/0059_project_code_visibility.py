"""project_code_visibility — a company code a project has hidden from its pickers (wave 1g; slice1g_spec §5–§6, G-1).

One row per (project, company code) for life: hiding inserts it or restores it, unhiding retires it (S1-7). That the
code is a company row (project_id NULL) is service-enforced — a CHECK cannot see code_master, and a composite FK cannot
match a NULL project_id. Not shadowed or frozen: visibility only changes what pickers offer, never what a row holds.
vb_app gets SELECT/INSERT/UPDATE from 0001's default privileges and no DELETE (law 1).

Downgrade: refuses while the table holds any row — dropping it would un-hide codes projects chose to hide.

Revision ID: 0059
Revises: 0058
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, updated_at_trigger

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_code_visibility",
        sa.Column("project_code_visibility_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("code_id", sa.BigInteger, sa.ForeignKey("code_master.code_id"), nullable=False),
        *audit_columns(),
        sa.UniqueConstraint("project_id", "code_id", name="uq_pcv_project_code"),
    )
    updated_at_trigger("project_code_visibility")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM project_code_visibility) THEN "
               "RAISE EXCEPTION 'projects have hidden codes: downgrade refused'; END IF; END $$")
    drop_updated_at_trigger("project_code_visibility")
    op.drop_table("project_code_visibility")
