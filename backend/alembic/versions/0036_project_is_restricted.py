"""project.is_restricted — a restricted project is visible only to admins and its live members
(D-40, OR-6, slice7_schema §8.3). Off by default; read per request.

Revision ID: 0036
Revises: 0035
"""
from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project", sa.Column("is_restricted", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("project", "is_restricted")
