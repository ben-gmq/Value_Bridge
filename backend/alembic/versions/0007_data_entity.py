"""data_entity — logical data entity in one project (§5.3 DATA_ENTITY, D-3).

Slice 1, docs/slice1_schema.md §1.3. de_number is minted by next_number(…, 'DE') and never
reused (full UK). S1-6: de_name is unique among live entities, normalised.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, updated_at_trigger

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_entity",
        sa.Column("data_entity_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("de_number", sa.String(20), nullable=False),
        sa.Column("de_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("business_owner_note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("project_id", "de_number", name="uq_de_number"),
        sa.UniqueConstraint("data_entity_id", "project_id", name="uq_data_entity_project"),
    )
    op.execute("CREATE UNIQUE INDEX uq_de_name_live ON data_entity "
               "(project_id, lower(btrim(de_name))) WHERE is_active")
    updated_at_trigger("data_entity")


def downgrade() -> None:
    drop_updated_at_trigger("data_entity")
    op.drop_table("data_entity")
