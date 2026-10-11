"""project.data_model_depth — how much of each data entity the project defines (D-39, slice7_schema §4).

KEYS_ONLY expects primary and foreign keys only; FULL also expects other attributes. A CHECK-listed
column, not a code_master FK (S2-1 precedent: two values the code branches on). Existing projects get
FULL, today's behaviour.

Revision ID: 0032
Revises: 0031
"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project", sa.Column("data_model_depth", sa.String(10), nullable=False,
                                       server_default="FULL"))
    op.create_check_constraint("ck_project_depth", "project",
                               "data_model_depth IN ('KEYS_ONLY', 'FULL')")


def downgrade() -> None:
    op.drop_constraint("ck_project_depth", "project", type_="check")
    op.drop_column("project", "data_model_depth")
