"""Shared migration helpers. The conventions live here once, not in every revision."""
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
