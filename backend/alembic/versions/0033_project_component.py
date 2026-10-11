"""project_component — one row per component a project uses (D-37, slice7_schema §2).

A live row means "on", a retired row means "off"; switching back on restores the same row (S1-7),
so its baseline source_id stays stable. Codes come from the system category PROJECT_COMPONENT.
Existing projects are backfilled by `seeds.seed_project_components`, not here: the codes it
references are seeded after `alembic upgrade head`.

Revision ID: 0033
Revises: 0032
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_component",
        sa.Column("project_component_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("component_code_id", sa.BigInteger, nullable=False),
        category_column("component_category", "PROJECT_COMPONENT"),
        *audit_columns(),
        sa.UniqueConstraint("project_id", "component_code_id", name="uq_project_component"),
        sa.ForeignKeyConstraint(["component_code_id", "component_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_pc_component", onupdate="NO ACTION"),
    )
    op.create_index("ix_pc_component", "project_component", ["component_code_id"])
    updated_at_trigger("project_component")


def downgrade() -> None:
    """Destructive once any project has switched a component off: the scope decision is lost.
    Pauses for Ben in that case (slice7_schema §7)."""
    drop_updated_at_trigger("project_component")
    op.drop_table("project_component")
