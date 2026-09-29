"""bfc_node_data_entity — step I/O, the one record of it (§5.3, D-24, §5.4.2).

Slice 1, docs/slice1_schema.md §1.8. S1-5: surrogate PK so the baseline shadow keeps the
link; the design's composite key is a UNIQUE. Only bfc.ensure_step_io writes it (R2-D13), and
re-linking restores the retired row (S1-7).

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, live_guard, updated_at_trigger

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bfc_node_data_entity",
        sa.Column("bfc_node_data_entity_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("bfc_node_id", sa.BigInteger, nullable=False),
        live_guard("node_is_process", True),
        sa.Column("data_entity_id", sa.BigInteger, nullable=False),
        sa.Column("direction", sa.CHAR(1), nullable=False),
        sa.Column("note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("bfc_node_id", "data_entity_id", "direction", name="uq_bnde_grain"),
        # D-24 licence target: is_active is in the key so a retire is a key change.
        sa.UniqueConstraint("bfc_node_id", "data_entity_id", "direction", "is_active",
                            name="uq_bnde_live_target"),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_bnde_node"),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id", "node_is_process"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                                name="fk_bnde_node_process", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["data_entity_id", "project_id"],
                                ["data_entity.data_entity_id", "data_entity.project_id"], name="fk_bnde_de"),
        sa.CheckConstraint("direction IN ('I', 'O')", name="ck_bnde_direction"),
    )
    op.create_index("ix_bnde_node", "bfc_node_data_entity", ["bfc_node_id", "project_id"])
    op.create_index("ix_bnde_de", "bfc_node_data_entity", ["data_entity_id", "project_id"])
    op.create_index("ix_bnde_project", "bfc_node_data_entity", ["project_id"])
    updated_at_trigger("bfc_node_data_entity")


def downgrade() -> None:
    drop_updated_at_trigger("bfc_node_data_entity")
    op.drop_table("bfc_node_data_entity")
