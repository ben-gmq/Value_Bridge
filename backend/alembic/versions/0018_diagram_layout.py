"""diagram_layout — one saved position per project × diagram × scope × object (D-29, D-30, S2-6).

Slice 2, docs/slice2_schema.md §2. Serves PROCESS_FLOW now and DFD / ERD later with no schema
change. The documented exception to the VB law (A-52): hard-deleted, no soft delete, no
row_version, never baselined — so vb_app gets DELETE on this table and no other (§6.6).

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import drop_updated_at_trigger, presence_columns, updated_at_trigger

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_OBJECTS = (("node", "bfc_node_id", "bfc_node"), ("de", "data_entity_id", "data_entity"),
            ("ext", "external_entity_id", "external_entity"),
            ("flow", "bfc_node_flow_id", "bfc_node_flow"))


def upgrade() -> None:
    op.create_table(
        "diagram_layout",
        sa.Column("diagram_layout_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("diagram_type", sa.String(20), nullable=False),
        sa.Column("scope_bfc_node_id", sa.BigInteger),
        *(sa.Column(col, sa.BigInteger) for _, col, _t in _OBJECTS),
        sa.Column("x", sa.Numeric(10, 2), nullable=False),
        sa.Column("y", sa.Numeric(10, 2), nullable=False),
        sa.Column("width", sa.Numeric(10, 2)),
        sa.Column("height", sa.Numeric(10, 2)),
        sa.Column("is_collapsed", sa.Boolean, nullable=False, server_default=sa.false()),
        *presence_columns(),
        sa.ForeignKeyConstraint(["scope_bfc_node_id", "project_id"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_dl_scope"),
        *(sa.ForeignKeyConstraint([col, "project_id"], [f"{tbl}.{col}", f"{tbl}.project_id"],
                                  name=f"fk_dl_{short}") for short, col, tbl in _OBJECTS),
        sa.UniqueConstraint("project_id", "diagram_type", "scope_bfc_node_id",
                            *(col for _, col, _t in _OBJECTS),
                            name="uq_dl_object", postgresql_nulls_not_distinct=True),
        sa.CheckConstraint("diagram_type IN ('ERD', 'PROCESS_FLOW', 'DFD')", name="ck_dl_type"),
        sa.CheckConstraint("num_nonnulls(bfc_node_id, data_entity_id, external_entity_id, "
                           "bfc_node_flow_id) = 1", name="ck_dl_one_object"),
        sa.CheckConstraint("diagram_type <> 'ERD' OR data_entity_id IS NOT NULL", name="ck_dl_erd_entity"),
        sa.CheckConstraint("diagram_type = 'PROCESS_FLOW' OR bfc_node_flow_id IS NULL",
                           name="ck_dl_event_flow_only"),
        sa.CheckConstraint("diagram_type = 'ERD' OR scope_bfc_node_id IS NOT NULL", name="ck_dl_scope"),
        sa.CheckConstraint("width IS NULL OR width > 0", name="ck_dl_width"),
        sa.CheckConstraint("height IS NULL OR height > 0", name="ck_dl_height"),
        sa.CheckConstraint("diagram_type = 'ERD' OR NOT is_collapsed", name="ck_dl_collapse_erd"),
    )
    for short, col in (("scope", "scope_bfc_node_id"), *((s, c) for s, c, _t in _OBJECTS)):
        op.execute(f"CREATE INDEX ix_dl_{short} ON diagram_layout ({col}, project_id) "
                   f"WHERE {col} IS NOT NULL")
    updated_at_trigger("diagram_layout")
    op.execute("GRANT DELETE ON diagram_layout TO vb_app")


def downgrade() -> None:
    op.execute("REVOKE DELETE ON diagram_layout FROM vb_app")
    drop_updated_at_trigger("diagram_layout")
    op.drop_table("diagram_layout")
