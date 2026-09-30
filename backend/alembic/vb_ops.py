"""Shared migration helpers. The conventions live here once, not in every revision.

Append-only: revisions replay these on every upgrade, so changing a helper rewrites every
migration that already used it. Add a new helper instead of editing an old one."""
from alembic import op
import sqlalchemy as sa


def audit_columns() -> list[sa.Column]:
    """§5.1 — every business table is born with these (never retrofitted, §13)."""
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.Column("updated_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id")),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="1"),
    ]


def updated_at_trigger(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at()"
    )


def drop_updated_at_trigger(table: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")


def live_guard(name: str, value: bool) -> sa.Column:
    """§5.4.7(1): a generated guard that carries `value` while the row is live and NULL once
    retired, so a composite FK through it applies only to live rows (MATCH SIMPLE)."""
    return sa.Column(name, sa.Boolean,
                     sa.Computed(f"CASE WHEN is_active THEN {str(value).upper()} END", persisted=True))


def category_column(name: str, category: str) -> sa.Column:
    """S1-4: a generated constant naming the code_master category a code FK must belong to.
    Paired with an FK to code_master (code_id, category) — uq_code_category_target."""
    return sa.Column(name, sa.String(40), sa.Computed(f"'{category}'", persisted=True),
                     nullable=False)


def presence_columns() -> list[sa.Column]:
    """S2-6: the four audit columns without soft delete or row_version — for the documented
    hard-deleted presentation tables (diagram_layout, D-30, A-52). Not for business rows."""
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.Column("updated_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id")),
    ]
