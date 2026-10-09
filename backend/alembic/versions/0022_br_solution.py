"""br_solution — BR × solution pairing with its coverage note (§5.3 BR_SOLUTION, D-7).

Slice 5, docs/slice5_schema.md §2. S1-5: surrogate PK; the design's key (br_id, solution_id) is a
full UNIQUE, so a re-link restores the old row. Both composites keep a pairing in one project.

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, updated_at_trigger

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "br_solution",
        sa.Column("br_solution_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("br_id", sa.BigInteger, nullable=False),
        sa.Column("solution_id", sa.BigInteger, nullable=False),
        sa.Column("coverage_note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("br_id", "solution_id", name="uq_brsol_grain"),
        sa.ForeignKeyConstraint(["br_id", "project_id"],
                                ["business_requirement.br_id", "business_requirement.project_id"],
                                name="fk_brsol_br"),
        sa.ForeignKeyConstraint(["solution_id", "project_id"],
                                ["solution.solution_id", "solution.project_id"], name="fk_brsol_solution"),
    )
    op.create_index("ix_brsol_solution", "br_solution", ["solution_id", "project_id"])
    op.create_index("ix_brsol_project", "br_solution", ["project_id"])
    updated_at_trigger("br_solution")


def downgrade() -> None:
    drop_updated_at_trigger("br_solution")
    op.drop_table("br_solution")
