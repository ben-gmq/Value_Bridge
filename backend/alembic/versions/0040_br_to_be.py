"""business_requirement.node_bfc_set — a BR hangs off a to-be process only (D-47, S7-2, §9.2).

A generated constant 'TO_BE' plus a composite FK to bfc_node (uq_bfc_node_set) makes a BR on an as-is
node impossible in the database.

Revision ID: 0040
Revises: 0039
"""
from alembic import op
import sqlalchemy as sa

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("business_requirement", sa.Column("node_bfc_set", sa.String(10),
                                                    sa.Computed("'TO_BE'", persisted=True), nullable=False))
    op.create_foreign_key("fk_br_node_to_be", "business_requirement", "bfc_node",
                          ["bfc_node_id", "project_id", "node_bfc_set"],
                          ["bfc_node_id", "project_id", "bfc_set_code"], onupdate="NO ACTION")


def downgrade() -> None:
    op.drop_constraint("fk_br_node_to_be", "business_requirement", type_="foreignkey")
    op.drop_column("business_requirement", "node_bfc_set")
