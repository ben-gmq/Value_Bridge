"""function_requirement — one FTC-specified system function in one project (§5.3, D-7/D-27/D-28).

Slice 6a, docs/slice6a_schema.md §1 as amended by S6a-1: no suggested_br_id yet (it arrives with
the FR import). Solution optional (MATCH SIMPLE skips a NULL). The type's behaviour is a verified
copy (3-column FK). complexity and effort ship NULL, tied by the D-13 CHECK (S6a-3).

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "function_requirement",
        sa.Column("fr_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("fr_number", sa.String(20), nullable=False),
        sa.Column("fr_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("solution_id", sa.BigInteger),
        sa.Column("fr_type_code_id", sa.BigInteger, nullable=False),
        category_column("fr_type_category", "FR_TYPE"),
        sa.Column("fr_type_behaviour", sa.String(20), nullable=False),
        sa.Column("complexity_code_id", sa.BigInteger),
        category_column("complexity_category", "FR_COMPLEXITY"),
        sa.Column("effort_days", sa.Numeric(7, 2)),
        sa.Column("fulfilment_status_code_id", sa.BigInteger, nullable=False),
        category_column("fulfilment_status_category", "FR_FULFILMENT_STATUS"),
        sa.Column("acceptance_note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("project_id", "fr_number", name="uq_fr_number"),
        sa.UniqueConstraint("fr_id", "project_id", name="uq_fr_project"),
        sa.UniqueConstraint("fr_id", "project_id", "fr_type_behaviour", name="uq_fr_behaviour_target"),
        sa.ForeignKeyConstraint(["solution_id", "project_id"], ["solution.solution_id", "solution.project_id"],
                                name="fk_fr_solution"),
        sa.ForeignKeyConstraint(["fr_type_code_id", "fr_type_category", "fr_type_behaviour"],
                                ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                                name="fk_fr_type_code", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["complexity_code_id", "complexity_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_fr_complexity_code", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["fulfilment_status_code_id", "fulfilment_status_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_fr_fulfilment_code", onupdate="NO ACTION"),
        sa.CheckConstraint("btrim(fr_name) <> ''", name="ck_fr_name_not_blank"),
        sa.CheckConstraint("(complexity_code_id IS NULL) = (effort_days IS NULL)",
                           name="ck_fr_effort_with_complexity"),
        sa.CheckConstraint("effort_days IS NULL OR effort_days >= 0", name="ck_fr_effort_nonneg"),
    )
    op.create_index("ix_fr_solution", "function_requirement", ["solution_id", "project_id"])
    op.execute("CREATE INDEX ix_fr_unlinked ON function_requirement (project_id) "
               "WHERE solution_id IS NULL AND is_active")
    op.execute("CREATE INDEX ix_fr_behaviour ON function_requirement (project_id, fr_type_behaviour) "
               "WHERE is_active")
    op.create_index("ix_fr_type", "function_requirement", ["fr_type_code_id"])
    op.create_index("ix_fr_complexity", "function_requirement", ["complexity_code_id"])
    op.create_index("ix_fr_fulfilment", "function_requirement", ["fulfilment_status_code_id"])
    updated_at_trigger("function_requirement")


def downgrade() -> None:
    drop_updated_at_trigger("function_requirement")
    op.drop_table("function_requirement")
