"""solution — one transformation answer in one project (§5.3 SOLUTION, D-7).

Slice 5, docs/slice5_schema.md §1. solution_number is minted by next_number(…, 'SOL') and never
reused (full UK). Q-1: solution_name is unique among live solutions, normalised.

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "solution",
        sa.Column("solution_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("solution_number", sa.String(20), nullable=False),
        sa.Column("solution_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("category_code_id", sa.BigInteger, nullable=False),
        category_column("category_category", "SOLUTION_CATEGORY"),
        sa.Column("status_code_id", sa.BigInteger, nullable=False),
        category_column("status_category", "SOLUTION_STATUS"),
        sa.Column("benefit_note", sa.Text),
        sa.Column("effort_note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("project_id", "solution_number", name="uq_solution_number"),
        sa.UniqueConstraint("solution_id", "project_id", name="uq_solution_project"),
        sa.ForeignKeyConstraint(["category_code_id", "category_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_sol_category_code", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["status_code_id", "status_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_sol_status_code", onupdate="NO ACTION"),
        sa.CheckConstraint("btrim(solution_name) <> ''", name="ck_sol_name_not_blank"),
    )
    op.execute("CREATE UNIQUE INDEX uq_solution_name_live ON solution "
               "(project_id, lower(btrim(solution_name))) WHERE is_active")
    op.create_index("ix_sol_category", "solution", ["category_code_id"])
    op.create_index("ix_sol_status", "solution", ["status_code_id"])
    updated_at_trigger("solution")


def downgrade() -> None:
    drop_updated_at_trigger("solution")
    op.drop_table("solution")
