"""business_requirement — exactly one per live process node (§5.3, D-2, D-23, §5.4.1a).

Slice 1, docs/slice1_schema.md §1.7. The node guard FK proves the node is a process while the
BR is live. S1-7: br_statement is nullable (created empty with its node). S1-4: status is
category-verified.

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, live_guard, updated_at_trigger

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_requirement",
        sa.Column("br_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("bfc_node_id", sa.BigInteger, nullable=False),
        live_guard("node_is_process", True),
        sa.Column("br_number", sa.String(20), nullable=False),
        sa.Column("br_statement", sa.Text),
        sa.Column("business_logic", sa.Text),
        sa.Column("output_expectation", sa.Text),
        sa.Column("status_code_id", sa.BigInteger, nullable=False),
        category_column("status_category", "BR_STATUS"),
        *audit_columns(),
        sa.UniqueConstraint("project_id", "br_number", name="uq_br_number"),
        sa.UniqueConstraint("br_id", "project_id", name="uq_br_project"),
        sa.UniqueConstraint("br_id", "project_id", "bfc_node_id", name="uq_br_node_carrier"),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_br_node"),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id", "node_is_process"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                                name="fk_br_node_process", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["status_code_id", "status_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_br_status_code", onupdate="NO ACTION"),
    )
    # D-2: one live BR per node. Dropping this index is the whole cost of reversing D-2.
    op.execute("CREATE UNIQUE INDEX uq_br_one_per_node ON business_requirement (bfc_node_id) WHERE is_active")
    op.create_index("ix_br_node", "business_requirement", ["bfc_node_id", "project_id"])
    op.create_index("ix_br_status", "business_requirement", ["status_code_id"])
    updated_at_trigger("business_requirement")


def downgrade() -> None:
    drop_updated_at_trigger("business_requirement")
    op.drop_table("business_requirement")
