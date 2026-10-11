"""application_solution — to-be allocation: an application delivers a Solution (§5.3, D-8).

Slice 6b-1, docs/slice6b_schema.md §2. S1-5 surrogate PK; (application, solution) a full UNIQUE so a
relink restores the row. Never for an AS_IS application (R2-D11) — service-enforced.

Revision ID: 0026
Revises: 0025
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, updated_at_trigger

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_solution",
        sa.Column("application_solution_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("application_id", sa.BigInteger, nullable=False),
        sa.Column("solution_id", sa.BigInteger, nullable=False),
        sa.Column("allocation_note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("application_id", "solution_id", name="uq_appsol_grain"),
        sa.ForeignKeyConstraint(["application_id", "project_id"],
                                ["application.application_id", "application.project_id"], name="fk_appsol_application"),
        sa.ForeignKeyConstraint(["solution_id", "project_id"], ["solution.solution_id", "solution.project_id"],
                                name="fk_appsol_solution"),
    )
    op.create_index("ix_appsol_solution", "application_solution", ["solution_id", "project_id"])
    op.create_index("ix_appsol_project", "application_solution", ["project_id"])
    updated_at_trigger("application_solution")


def downgrade() -> None:
    drop_updated_at_trigger("application_solution")
    op.drop_table("application_solution")
