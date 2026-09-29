"""external_entity — a party outside the client that exchanges data (§5.3, D-24a).

Slice 1, docs/slice1_schema.md §1.5. ext_number minted ('EXT' series), never reused.
S1-4: kind is category-verified (and optional — an unknown kind is a warning, §5.3).

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_entity",
        sa.Column("external_entity_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("ext_number", sa.String(20), nullable=False),
        sa.Column("ext_name", sa.String(200), nullable=False),
        sa.Column("kind_code_id", sa.BigInteger),
        category_column("kind_category", "EXTERNAL_ENTITY_KIND"),
        sa.Column("description", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("project_id", "ext_number", name="uq_ext_number"),
        sa.UniqueConstraint("external_entity_id", "project_id", name="uq_external_entity_project"),
        sa.ForeignKeyConstraint(["kind_code_id", "kind_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_ext_kind_code", onupdate="NO ACTION"),
    )
    op.execute("CREATE UNIQUE INDEX uq_ext_name_live ON external_entity "
               "(project_id, lower(btrim(ext_name))) WHERE is_active")
    op.create_index("ix_ext_kind", "external_entity", ["kind_code_id"])
    updated_at_trigger("external_entity")


def downgrade() -> None:
    drop_updated_at_trigger("external_entity")
    op.drop_table("external_entity")
