"""fr_interface_data_entity — a data entity an interface carries, with its note (§5.3, D-27, S6b2-4).

Slice 6b-2, docs/slice6b_schema.md §5. S1-5 surrogate PK, (fr_id, data_entity_id) a full UNIQUE.
The live guard onto uq_fri_live_target refuses retiring detail that still lists live carried rows.

Revision ID: 0029
Revises: 0028
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, live_guard, updated_at_trigger

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fr_interface_data_entity",
        sa.Column("fr_interface_data_entity_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("fr_id", sa.BigInteger, nullable=False),
        sa.Column("data_entity_id", sa.BigInteger, nullable=False),
        live_guard("interface_is_active", True),
        sa.Column("note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("fr_id", "data_entity_id", name="uq_fide_grain"),
        sa.ForeignKeyConstraint(["fr_id", "project_id"], ["fr_interface.fr_id", "fr_interface.project_id"],
                                name="fk_fide_interface"),
        sa.ForeignKeyConstraint(["fr_id", "project_id", "interface_is_active"],
                                ["fr_interface.fr_id", "fr_interface.project_id", "fr_interface.is_active"],
                                name="fk_fide_interface_live", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["data_entity_id", "project_id"], ["data_entity.data_entity_id", "data_entity.project_id"],
                                name="fk_fide_de"),
    )
    op.create_index("ix_fide_de", "fr_interface_data_entity", ["data_entity_id", "project_id"])
    op.create_index("ix_fide_project", "fr_interface_data_entity", ["project_id"])
    updated_at_trigger("fr_interface_data_entity")


def downgrade() -> None:
    drop_updated_at_trigger("fr_interface_data_entity")
    op.drop_table("fr_interface_data_entity")
