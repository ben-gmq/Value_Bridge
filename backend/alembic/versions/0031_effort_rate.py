"""effort_rate — the project's rate card: (FR type × complexity) → standard man-days (§5.3, D-13, R2-D7).

Slice 6c, docs/slice6c_schema.md §1 and spec rev 2: surrogate PK + the natural key as a full UNIQUE;
days > 0 and not NaN (DR6c-D4); a reason once changed (§6.2); and a BEFORE UPDATE trigger that refuses
any change to standard_days which does not bump row_version and carry a non-blank reason (DR6c-D1) —
so no write path, ORM or not, can move a rate silently. A key-only re-point is unaffected.

Revision ID: 0031
Revises: 0030
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "effort_rate",
        sa.Column("effort_rate_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("fr_type_code_id", sa.BigInteger, nullable=False),
        category_column("fr_type_category", "FR_TYPE"),
        sa.Column("complexity_code_id", sa.BigInteger, nullable=False),
        category_column("complexity_category", "FR_COMPLEXITY"),
        sa.Column("standard_days", sa.Numeric(7, 2), nullable=False),
        sa.Column("change_rationale", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("project_id", "fr_type_code_id", "complexity_code_id", name="uq_effort_rate_cell"),
        sa.ForeignKeyConstraint(["fr_type_code_id", "fr_type_category"], ["code_master.code_id", "code_master.category"],
                                name="fk_effort_rate_type", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["complexity_code_id", "complexity_category"], ["code_master.code_id", "code_master.category"],
                                name="fk_effort_rate_complexity", onupdate="NO ACTION"),
        sa.CheckConstraint("standard_days > 0 AND standard_days <> 'NaN'", name="ck_effort_rate_days_positive"),
        sa.CheckConstraint("row_version = 1 OR change_rationale IS NOT NULL", name="ck_effort_rate_rationale"),
        sa.CheckConstraint("change_rationale IS NULL OR btrim(change_rationale) <> ''",
                           name="ck_effort_rate_rationale_not_blank"),
    )
    op.create_index("ix_effort_rate_type", "effort_rate", ["fr_type_code_id"])
    op.create_index("ix_effort_rate_complexity", "effort_rate", ["complexity_code_id"])
    updated_at_trigger("effort_rate")
    op.execute("""
        CREATE FUNCTION fn_effort_rate_change_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.standard_days IS DISTINCT FROM OLD.standard_days
               AND (NEW.row_version <= OLD.row_version
                    OR NEW.change_rationale IS NULL OR btrim(NEW.change_rationale) = '') THEN
                RAISE EXCEPTION 'a rate change needs a new row_version and a reason'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("CREATE TRIGGER trg_effort_rate_change_guard BEFORE UPDATE ON effort_rate "
               "FOR EACH ROW EXECUTE FUNCTION fn_effort_rate_change_guard()")


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_effort_rate_change_guard ON effort_rate")
    op.execute("DROP FUNCTION fn_effort_rate_change_guard()")
    drop_updated_at_trigger("effort_rate")
    op.drop_table("effort_rate")
