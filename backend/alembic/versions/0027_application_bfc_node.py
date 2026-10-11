"""application_bfc_node — as-is support: an application supports a process step today (D-8, D-23).

Slice 6b-1, docs/slice6b_schema.md §3. Process-only by the guard FK onto uq_bfc_node_process_target.
Owned by its step (S6b-1): step_retire.OWNED_BY_STEP gains it in this same commit.

Revision ID: 0027
Revises: 0026
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, live_guard, updated_at_trigger

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_bfc_node",
        sa.Column("application_bfc_node_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("application_id", sa.BigInteger, nullable=False),
        sa.Column("bfc_node_id", sa.BigInteger, nullable=False),
        live_guard("node_is_process", True),
        sa.Column("support_note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("application_id", "bfc_node_id", name="uq_appnode_grain"),
        sa.ForeignKeyConstraint(["application_id", "project_id"],
                                ["application.application_id", "application.project_id"], name="fk_appnode_application"),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id"], ["bfc_node.bfc_node_id", "bfc_node.project_id"],
                                name="fk_appnode_node"),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id", "node_is_process"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                                name="fk_appnode_node_process", onupdate="NO ACTION"),
    )
    op.create_index("ix_appnode_node", "application_bfc_node", ["bfc_node_id", "project_id"])
    op.create_index("ix_appnode_project", "application_bfc_node", ["project_id"])
    updated_at_trigger("application_bfc_node")


def downgrade() -> None:
    drop_updated_at_trigger("application_bfc_node")
    op.drop_table("application_bfc_node")
