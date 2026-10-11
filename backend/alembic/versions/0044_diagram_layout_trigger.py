"""diagram_layout gains trigger positions for the DFD (D-49, slice7_schema §9.10).

S7-5: PROCESS_FLOW rows are kept, not deleted, and ck_dl_type is unchanged; the service refuses new
PROCESS_FLOW writes. uq_dl_object (named in ON CONFLICT, S2-6) and ck_dl_one_object are re-created with
the new object column.

Revision ID: 0044
Revises: 0043
"""
from alembic import op
import sqlalchemy as sa

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

_OLD = ("bfc_node_id", "data_entity_id", "external_entity_id", "bfc_node_flow_id")


def upgrade() -> None:
    op.add_column("diagram_layout", sa.Column("process_trigger_id", sa.BigInteger))
    op.create_foreign_key("fk_dl_trigger", "diagram_layout", "process_trigger", ["process_trigger_id", "project_id"],
                          ["process_trigger_id", "project_id"])
    op.execute("CREATE INDEX ix_dl_trigger ON diagram_layout (process_trigger_id, project_id) "
               "WHERE process_trigger_id IS NOT NULL")
    op.drop_constraint("uq_dl_object", "diagram_layout", type_="unique")
    op.create_unique_constraint("uq_dl_object", "diagram_layout",
                                ["project_id", "diagram_type", "scope_bfc_node_id", *_OLD, "process_trigger_id"],
                                postgresql_nulls_not_distinct=True)
    op.drop_constraint("ck_dl_one_object", "diagram_layout", type_="check")
    op.create_check_constraint("ck_dl_one_object", "diagram_layout",
                               f"num_nonnulls({', '.join(_OLD)}, process_trigger_id) = 1")


def downgrade() -> None:
    """DR7-D4: trigger positions are presentation rows (D-30) and are deleted first, or the 4-column
    CHECK would refuse them."""
    op.execute("DELETE FROM diagram_layout WHERE process_trigger_id IS NOT NULL")
    op.drop_constraint("ck_dl_one_object", "diagram_layout", type_="check")
    op.create_check_constraint("ck_dl_one_object", "diagram_layout", f"num_nonnulls({', '.join(_OLD)}) = 1")
    op.drop_constraint("uq_dl_object", "diagram_layout", type_="unique")
    op.create_unique_constraint("uq_dl_object", "diagram_layout", ["project_id", "diagram_type", "scope_bfc_node_id", *_OLD],
                                postgresql_nulls_not_distinct=True)
    op.execute("DROP INDEX ix_dl_trigger")
    op.drop_constraint("fk_dl_trigger", "diagram_layout", type_="foreignkey")
    op.drop_column("diagram_layout", "process_trigger_id")
