"""app_user gets the full §5.1 audit trail: updated_by, deleted_at, deleted_by (sara M12).

§13: audit columns are never retrofitted — added now, before any real user exists.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("updated_by", sa.BigInteger,
                                        sa.ForeignKey("app_user.app_user_id", name="fk_app_user_updated_by")))
    op.add_column("app_user", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("app_user", sa.Column("deleted_by", sa.BigInteger,
                                        sa.ForeignKey("app_user.app_user_id", name="fk_app_user_deleted_by")))


def downgrade() -> None:
    op.drop_column("app_user", "deleted_by")
    op.drop_column("app_user", "deleted_at")
    op.drop_column("app_user", "updated_by")
