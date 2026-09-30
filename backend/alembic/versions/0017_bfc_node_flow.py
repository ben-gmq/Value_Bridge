"""bfc_node_flow — one flow edge between process steps (§5.3, D-20, D-23, Q2, S2).

Slice 2, docs/slice2_schema.md §1. Both ends are process-guarded and project-scoped; a NULL
end is a start or end event. flow_type is CHECK-listed (S2-1), so a CONDITIONAL edge's label
is a table CHECK. The partial natural key makes the service restore a retired twin (Q2);
the full from/to indexes serve the guard-FK checks (S2-5).

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, live_guard, updated_at_trigger

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bfc_node_flow",
        sa.Column("bfc_node_flow_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("from_bfc_node_id", sa.BigInteger),
        live_guard("from_is_process", True),
        sa.Column("to_bfc_node_id", sa.BigInteger),
        live_guard("to_is_process", True),
        sa.Column("flow_type", sa.String(20), nullable=False),
        sa.Column("condition_label", sa.String(200)),
        sa.Column("seq_no", sa.SmallInteger),
        sa.Column("note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("bfc_node_flow_id", "project_id", name="uq_bfc_node_flow_project"),
        sa.ForeignKeyConstraint(["from_bfc_node_id", "project_id"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_bnf_from"),
        sa.ForeignKeyConstraint(["from_bfc_node_id", "project_id", "from_is_process"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                                name="fk_bnf_from_process", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["to_bfc_node_id", "project_id"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_bnf_to"),
        sa.ForeignKeyConstraint(["to_bfc_node_id", "project_id", "to_is_process"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                                name="fk_bnf_to_process", onupdate="NO ACTION"),
        sa.CheckConstraint("num_nonnulls(from_bfc_node_id, to_bfc_node_id) >= 1", name="ck_bnf_has_end"),
        sa.CheckConstraint("flow_type IN ('SEQUENCE', 'CONDITIONAL', 'PARALLEL', 'HANDOFF')",
                           name="ck_bnf_flow_type"),
        sa.CheckConstraint("condition_label IS NULL OR btrim(condition_label) <> ''",
                           name="ck_bnf_label_not_blank"),
        sa.CheckConstraint("flow_type <> 'CONDITIONAL' OR condition_label IS NOT NULL",
                           name="ck_bnf_conditional_label"),
        sa.CheckConstraint("seq_no IS NULL OR seq_no BETWEEN 1 AND 99", name="ck_bnf_seq"),
    )
    op.execute("CREATE UNIQUE INDEX uq_bfc_node_flow_edge ON bfc_node_flow "
               "(from_bfc_node_id, to_bfc_node_id, lower(btrim(condition_label))) "
               "NULLS NOT DISTINCT WHERE is_active")
    op.create_index("ix_bnf_from", "bfc_node_flow", ["from_bfc_node_id", "project_id"])
    op.create_index("ix_bnf_to", "bfc_node_flow", ["to_bfc_node_id", "project_id"])
    op.create_index("ix_bnf_project", "bfc_node_flow", ["project_id"])
    updated_at_trigger("bfc_node_flow")


def downgrade() -> None:
    drop_updated_at_trigger("bfc_node_flow")
    op.drop_table("bfc_node_flow")
