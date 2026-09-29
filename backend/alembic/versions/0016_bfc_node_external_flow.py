"""bfc_node_external_flow — step × party × direction × data entity (nullable) (§5.3, D-24a, §5.4.9).

Slice 1, docs/slice1_schema.md §1.12. Surrogate PK because the DE is optional; when it is
named, the licence FK proves a live step I/O row (MATCH SIMPLE skips it when NULL). Re-adding
restores the row (full grain UK, NULLS NOT DISTINCT).

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, live_guard, updated_at_trigger

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bfc_node_external_flow",
        sa.Column("bfc_node_external_flow_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("bfc_node_id", sa.BigInteger, nullable=False),
        live_guard("node_is_process", True),
        sa.Column("external_entity_id", sa.BigInteger, nullable=False),
        sa.Column("direction", sa.CHAR(1), nullable=False),
        sa.Column("data_entity_id", sa.BigInteger),
        live_guard("io_is_active", True),
        sa.Column("flow_label", sa.String(200)),
        sa.Column("note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("bfc_node_id", "external_entity_id", "direction", "data_entity_id",
                            name="uq_bnef_grain", postgresql_nulls_not_distinct=True),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_bnef_node"),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id", "node_is_process"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                                name="fk_bnef_node_process", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["external_entity_id", "project_id"],
                                ["external_entity.external_entity_id", "external_entity.project_id"],
                                name="fk_bnef_ext"),
        sa.ForeignKeyConstraint(["data_entity_id", "project_id"],
                                ["data_entity.data_entity_id", "data_entity.project_id"], name="fk_bnef_de"),
        sa.ForeignKeyConstraint(["bfc_node_id", "data_entity_id", "direction", "io_is_active"],
                                ["bfc_node_data_entity.bfc_node_id", "bfc_node_data_entity.data_entity_id",
                                 "bfc_node_data_entity.direction", "bfc_node_data_entity.is_active"],
                                name="fk_bnef_io_licence", onupdate="NO ACTION"),
        sa.CheckConstraint("direction IN ('I', 'O')", name="ck_bnef_direction"),
    )
    op.create_index("ix_bnef_io", "bfc_node_external_flow", ["bfc_node_id", "data_entity_id", "direction"])
    op.create_index("ix_bnef_ext", "bfc_node_external_flow", ["external_entity_id", "project_id"])
    op.create_index("ix_bnef_node", "bfc_node_external_flow", ["bfc_node_id", "project_id"])
    op.create_index("ix_bnef_de", "bfc_node_external_flow", ["data_entity_id", "project_id"])
    op.create_index("ix_bnef_project", "bfc_node_external_flow", ["project_id"])
    updated_at_trigger("bfc_node_external_flow")


def downgrade() -> None:
    drop_updated_at_trigger("bfc_node_external_flow")
    op.drop_table("bfc_node_external_flow")
