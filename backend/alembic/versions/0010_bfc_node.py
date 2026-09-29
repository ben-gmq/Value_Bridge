"""bfc_node — node of the business function chart, L1–L5 (§5.3 BFC_NODE, D-23, §5.4.7).

Slice 1, docs/slice1_schema.md §1.6. is_process is the only process test (VB law 4); the
parent guard FK makes "a process has no children" declarative. S1-1: sibling order covers
L1. S1-2: hier_code is varchar(40) for the two-phase reorder's temporary code. S1-3: range.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, live_guard, updated_at_trigger

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bfc_node",
        sa.Column("bfc_node_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("parent_bfc_node_id", sa.BigInteger),
        live_guard("parent_is_process", False),
        sa.Column("level_no", sa.SmallInteger, nullable=False),
        sa.Column("is_process", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("seq_no", sa.Integer, nullable=False),
        sa.Column("hier_code", sa.String(40), nullable=False),
        sa.Column("node_name", sa.String(200), nullable=False),
        sa.Column("purpose_desc", sa.Text),
        sa.Column("data_processing_desc", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("bfc_node_id", "project_id", name="uq_bfc_node_project"),
        sa.UniqueConstraint("bfc_node_id", "project_id", "is_process", name="uq_bfc_node_process_target"),
        sa.ForeignKeyConstraint(["parent_bfc_node_id", "project_id"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id"],
                                name="fk_bfc_node_parent"),
        # D-23: while a node is live, its parent must not be a process. Never CASCADE (§5.4.7(2)).
        sa.ForeignKeyConstraint(["parent_bfc_node_id", "project_id", "parent_is_process"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                                name="fk_bfc_node_parent_not_process", onupdate="NO ACTION"),
        sa.CheckConstraint("level_no BETWEEN 1 AND 5", name="ck_bfc_level"),
        sa.CheckConstraint("(level_no = 1) = (parent_bfc_node_id IS NULL)", name="ck_bfc_root"),
        sa.CheckConstraint("NOT is_process OR level_no >= 3", name="ck_bfc_process_level"),
        sa.CheckConstraint("level_no < 5 OR is_process", name="ck_bfc_l5_is_process"),
        sa.CheckConstraint("is_process OR data_processing_desc IS NULL", name="ck_bfc_desc_process_only"),
        sa.CheckConstraint("seq_no <> 0 AND seq_no BETWEEN -99 AND 99", name="ck_bfc_seq"),
    )
    op.execute("CREATE UNIQUE INDEX uq_bfc_hier_code_live ON bfc_node (project_id, hier_code) WHERE is_active")
    op.execute("CREATE UNIQUE INDEX uq_bfc_sibling_seq ON bfc_node "
               "(project_id, parent_bfc_node_id, seq_no) NULLS NOT DISTINCT WHERE is_active")
    op.execute("CREATE UNIQUE INDEX uq_bfc_process_name ON bfc_node "
               "(parent_bfc_node_id, lower(btrim(node_name))) WHERE is_active AND is_process")
    op.create_index("ix_bfc_parent_guard", "bfc_node",
                    ["parent_bfc_node_id", "project_id", "parent_is_process"])
    op.execute("CREATE INDEX ix_bfc_hier_pattern ON bfc_node "
               "(project_id, hier_code varchar_pattern_ops) WHERE is_active")
    op.execute("CREATE INDEX ix_bfc_process_live ON bfc_node (project_id) WHERE is_process AND is_active")
    op.create_index("ix_bfc_project", "bfc_node", ["project_id"])
    updated_at_trigger("bfc_node")


def downgrade() -> None:
    drop_updated_at_trigger("bfc_node")
    op.drop_table("bfc_node")
