"""Access, numbering and audit: user_access_grant (D-32), project_sequence (R2-D14),
audit_event (append-only, §6.6).

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB

from vb_ops import audit_columns, drop_updated_at_trigger, updated_at_trigger

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_access_grant",
        sa.Column("user_access_grant_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("app_user_id", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id")),
        sa.Column("program_id", sa.BigInteger, sa.ForeignKey("program.program_id")),
        sa.Column("project_role_code_id", sa.BigInteger, sa.ForeignKey("code_master.code_id"),
                  nullable=False),
        sa.Column("scope_is_active", sa.Boolean,
                  sa.Computed("CASE WHEN is_active THEN TRUE END", persisted=True)),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("granted_by_user_id", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"),
                  nullable=False),
        *audit_columns(),
        sa.CheckConstraint("num_nonnulls(project_id, program_id) = 1", name="ck_grant_one_scope"),
        sa.ForeignKeyConstraint(["project_id", "scope_is_active"],
                                ["project.project_id", "project.is_active"],
                                name="fk_grant_live_project", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["program_id", "scope_is_active"],
                                ["program.program_id", "program.is_active"],
                                name="fk_grant_live_program", onupdate="NO ACTION"),
    )
    # D-32: at most one live grant per user. The backstop behind grant_access's 409.
    op.execute("CREATE UNIQUE INDEX uq_grant_one_live_per_user ON user_access_grant "
               "(app_user_id) WHERE is_active")
    op.execute("CREATE INDEX ix_grant_program_live ON user_access_grant (program_id) WHERE is_active")
    op.execute("CREATE INDEX ix_grant_project_live ON user_access_grant (project_id) WHERE is_active")
    updated_at_trigger("user_access_grant")

    op.create_table(
        "project_sequence",
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), primary_key=True),
        sa.Column("sequence_code", sa.String(10), primary_key=True),
        sa.Column("prefix", sa.String(10), nullable=False),
        sa.Column("pad_width", sa.Integer, nullable=False, server_default="4"),
        sa.Column("last_value", sa.BigInteger, nullable=False, server_default="0"),
        sa.CheckConstraint("sequence_code IN ('DE','BR','FR','ISSUE','SOL','BEN','RSK','CR','DEC','EXT')",
                           name="ck_sequence_code"),
    )

    op.create_table(
        "audit_event",
        sa.Column("audit_event_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("app_user_id", sa.BigInteger, sa.ForeignKey("app_user.app_user_id")),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id")),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("target_table", sa.String(60)),
        sa.Column("target_id", sa.BigInteger),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("source_ip", INET),
        sa.Column("detail", JSONB),
    )
    op.execute("CREATE INDEX ix_audit_event_project ON audit_event (project_id, occurred_at)")
    # §6.6: append-only. The app role may INSERT and SELECT, never UPDATE (or DELETE).
    op.execute("REVOKE UPDATE ON audit_event FROM vb_app")
    op.execute("CREATE TRIGGER trg_audit_event_immutable BEFORE UPDATE OR DELETE ON audit_event "
               "FOR EACH ROW EXECUTE FUNCTION fn_reject_modification()")


def downgrade() -> None:
    op.drop_table("audit_event")
    op.drop_table("project_sequence")
    drop_updated_at_trigger("user_access_grant")
    op.drop_table("user_access_grant")
