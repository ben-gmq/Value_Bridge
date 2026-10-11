"""bfc_node_trigger — this trigger starts this process (D-49, slice7_schema §9.5).

Step-owned like step I/O: retires and restores with its step (step_retire.OWNED_BY_STEP, same commit).
Full grain UK, so re-linking restores (S1-7). Process steps only, live guard.

Revision ID: 0043
Revises: 0042
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, live_guard, updated_at_trigger

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bfc_node_trigger",
        sa.Column("bfc_node_trigger_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("bfc_node_id", sa.BigInteger, nullable=False),
        live_guard("node_is_process", True),
        sa.Column("process_trigger_id", sa.BigInteger, nullable=False),
        sa.Column("note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("bfc_node_id", "process_trigger_id", name="uq_bntr_grain"),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id"], ["bfc_node.bfc_node_id", "bfc_node.project_id"],
                                name="fk_bntr_node"),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id", "node_is_process"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                                name="fk_bntr_node_process", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["process_trigger_id", "project_id"],
                                ["process_trigger.process_trigger_id", "process_trigger.project_id"],
                                name="fk_bntr_trigger"),
    )
    op.create_index("ix_bntr_node", "bfc_node_trigger", ["bfc_node_id", "project_id"])
    op.create_index("ix_bntr_trigger", "bfc_node_trigger", ["process_trigger_id", "project_id"])
    op.create_index("ix_bntr_project", "bfc_node_trigger", ["project_id"])
    updated_at_trigger("bfc_node_trigger")


def downgrade() -> None:
    """Destructive once links exist: pauses for Ben."""
    drop_updated_at_trigger("bfc_node_trigger")
    op.drop_table("bfc_node_trigger")
