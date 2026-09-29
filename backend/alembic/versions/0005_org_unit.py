"""org_unit — client organisational unit, L1–L3, within one project (§5.3 ORG_UNIT).

Slice 1, docs/slice1_schema.md §1.1. S1-1: sibling order covers L1 (NULLS NOT DISTINCT).
S1-3: seq_no range tolerates the two-phase reorder. S1-4: level code is category-verified.
S1-6: org_unit_code is unique among live units.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_unit",
        sa.Column("org_unit_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("parent_org_unit_id", sa.BigInteger),
        sa.Column("level_no", sa.SmallInteger, nullable=False),
        sa.Column("level_code_id", sa.BigInteger, nullable=False),
        category_column("level_category", "ORG_UNIT_LEVEL"),
        sa.Column("org_unit_code", sa.String(30), nullable=False),
        sa.Column("org_unit_name", sa.String(200), nullable=False),
        sa.Column("seq_no", sa.Integer, nullable=False),
        sa.Column("description", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("org_unit_id", "project_id", name="uq_org_unit_project"),
        sa.ForeignKeyConstraint(["parent_org_unit_id", "project_id"],
                                ["org_unit.org_unit_id", "org_unit.project_id"],
                                name="fk_org_unit_parent"),
        sa.ForeignKeyConstraint(["level_code_id", "level_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_org_unit_level_code", onupdate="NO ACTION"),
        sa.CheckConstraint("level_no BETWEEN 1 AND 3", name="ck_org_unit_level"),
        sa.CheckConstraint("(level_no = 1) = (parent_org_unit_id IS NULL)", name="ck_org_unit_root"),
        sa.CheckConstraint("seq_no <> 0 AND seq_no BETWEEN -99 AND 99", name="ck_org_unit_seq"),
    )
    op.execute("CREATE UNIQUE INDEX uq_org_unit_sibling_seq ON org_unit "
               "(project_id, parent_org_unit_id, seq_no) NULLS NOT DISTINCT WHERE is_active")
    op.execute("CREATE UNIQUE INDEX uq_org_unit_code_live ON org_unit "
               "(project_id, lower(btrim(org_unit_code))) WHERE is_active")
    op.create_index("ix_org_unit_project", "org_unit", ["project_id"])
    op.create_index("ix_org_unit_parent", "org_unit", ["parent_org_unit_id", "project_id"])
    op.create_index("ix_org_unit_level_code", "org_unit", ["level_code_id"])
    updated_at_trigger("org_unit")


def downgrade() -> None:
    drop_updated_at_trigger("org_unit")
    op.drop_table("org_unit")
