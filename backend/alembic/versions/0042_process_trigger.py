"""process_trigger — a named time or event trigger in one project (D-49, slice7_schema §9.5).

"Month-end close" starts many processes, so it is a catalogue row, shared by both sets, linked by
bfc_node_trigger (0043). No number series. Live names are unique per project.

Revision ID: 0042
Revises: 0041
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, updated_at_trigger

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "process_trigger",
        sa.Column("process_trigger_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("trigger_name", sa.String(200), nullable=False),
        sa.Column("trigger_kind", sa.String(10), nullable=False),
        sa.Column("schedule_note", sa.String(200)),
        sa.Column("description", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("process_trigger_id", "project_id", name="uq_ptrg_project"),
        sa.CheckConstraint("trigger_kind IN ('TIME', 'EVENT')", name="ck_ptrg_kind"),
        sa.CheckConstraint("schedule_note IS NULL OR trigger_kind = 'TIME'", name="ck_ptrg_schedule_time_only"),
        sa.CheckConstraint("btrim(trigger_name) <> ''", name="ck_ptrg_name_not_blank"),
    )
    op.execute("CREATE UNIQUE INDEX uq_ptrg_name_live ON process_trigger (project_id, lower(btrim(trigger_name))) "
               "WHERE is_active")
    op.create_index("ix_ptrg_project", "process_trigger", ["project_id"])
    updated_at_trigger("process_trigger")


def downgrade() -> None:
    """Destructive once triggers exist: pauses for Ben."""
    drop_updated_at_trigger("process_trigger")
    op.drop_table("process_trigger")
