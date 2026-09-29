"""br_data_entity — BR × data entity × CRUD, licensed by step I/O (§5.3, §5.4.2, D-24).

Slice 1, docs/slice1_schema.md §1.9. direction is generated from crud_code; the licence FK
proves a live step I/O row exists for it. bfc_node_id is copied from the BR by the service,
never taken from the request. S1-5: surrogate PK; the design's key is a UNIQUE.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, live_guard, updated_at_trigger

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "br_data_entity",
        sa.Column("br_data_entity_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("br_id", sa.BigInteger, nullable=False),
        sa.Column("bfc_node_id", sa.BigInteger, nullable=False),
        sa.Column("data_entity_id", sa.BigInteger, nullable=False),
        sa.Column("crud_code", sa.CHAR(1), nullable=False),
        sa.Column("direction", sa.CHAR(1),
                  sa.Computed("CASE WHEN crud_code = 'R' THEN 'I' ELSE 'O' END", persisted=True),
                  nullable=False),
        live_guard("io_is_active", True),
        sa.Column("usage_note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("br_id", "data_entity_id", "crud_code", name="uq_brde_grain"),
        sa.ForeignKeyConstraint(["br_id", "project_id", "bfc_node_id"],
                                ["business_requirement.br_id", "business_requirement.project_id",
                                 "business_requirement.bfc_node_id"], name="fk_brde_br"),
        sa.ForeignKeyConstraint(["data_entity_id", "project_id"],
                                ["data_entity.data_entity_id", "data_entity.project_id"], name="fk_brde_de"),
        # D-24: a live CRUD row needs a live step I/O row in the matching direction.
        sa.ForeignKeyConstraint(["bfc_node_id", "data_entity_id", "direction", "io_is_active"],
                                ["bfc_node_data_entity.bfc_node_id", "bfc_node_data_entity.data_entity_id",
                                 "bfc_node_data_entity.direction", "bfc_node_data_entity.is_active"],
                                name="fk_brde_io_licence", onupdate="NO ACTION"),
        sa.CheckConstraint("crud_code IN ('C', 'R', 'U', 'D')", name="ck_brde_crud"),
    )
    op.create_index("ix_brde_de", "br_data_entity", ["data_entity_id"])
    op.create_index("ix_brde_io", "br_data_entity", ["bfc_node_id", "data_entity_id", "direction"])
    op.create_index("ix_brde_project", "br_data_entity", ["project_id"])
    updated_at_trigger("br_data_entity")


def downgrade() -> None:
    drop_updated_at_trigger("br_data_entity")
    op.drop_table("br_data_entity")
