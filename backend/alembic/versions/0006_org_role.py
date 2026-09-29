"""org_role — a role within one client org unit (§5.3 ORG_ROLE). Never bare `role` (VB law 7).

Slice 1, docs/slice1_schema.md §1.2. S1-7: org_unit FK is composite (same project).
S1-6: org_role_code is unique among live roles.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, updated_at_trigger

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_role",
        sa.Column("org_role_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("org_unit_id", sa.BigInteger, nullable=False),
        sa.Column("org_role_code", sa.String(30), nullable=False),
        sa.Column("org_role_name", sa.String(200), nullable=False),
        sa.Column("responsibility_desc", sa.Text),
        sa.Column("headcount", sa.Integer),
        *audit_columns(),
        sa.UniqueConstraint("org_role_id", "project_id", name="uq_org_role_project"),
        sa.ForeignKeyConstraint(["org_unit_id", "project_id"],
                                ["org_unit.org_unit_id", "org_unit.project_id"],
                                name="fk_org_role_unit"),
        sa.CheckConstraint("headcount IS NULL OR headcount >= 0", name="ck_org_role_headcount"),
    )
    op.execute("CREATE UNIQUE INDEX uq_org_role_code_live ON org_role "
               "(project_id, lower(btrim(org_role_code))) WHERE is_active")
    op.create_index("ix_org_role_project", "org_role", ["project_id"])
    op.create_index("ix_org_role_unit", "org_role", ["org_unit_id", "project_id"])
    updated_at_trigger("org_role")


def downgrade() -> None:
    drop_updated_at_trigger("org_role")
    op.drop_table("org_role")
