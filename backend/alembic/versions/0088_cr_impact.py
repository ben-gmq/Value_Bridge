"""cr_impact — one row per (change request × impacted object), ever (design §4.11, §5 CR_IMPACT, D-16;
docs/slice_change_requests_spec.md §3; CR-1, CR-2, Ben 2026-11-03).

A row is a seed (a BR or FR the team marked ADD / MODIFY / REMOVE, impact_type_code_id set) or an object the trace
reached (reached_via names the first route), never both as two rows: exactly one of the seven typed references is
set, and the (change request, seven) tuple is unique with NULLs not distinct, so tracing again restores the same row.
Every reference is a same-project composite FK. Only an FR seed carries an effort delta; an FR row carries its
agreed (frozen) days; a benefit row carries its unit, value at stake and value change (per unit, never one total —
Q9, CR-2). vb_app gets SELECT / INSERT / UPDATE from 0001's default privileges and no DELETE (law 1). Live-only.

Downgrade: refuses while cr_impact holds any row; then drops it.

Revision ID: 0088
Revises: 0087
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None

# (column, table, key) — literal, so a later model edit never changes this revision
TARGETS = (("impacted_br_id", "business_requirement", "br_id"),
           ("impacted_fr_id", "function_requirement", "fr_id"),
           ("impacted_solution_id", "solution", "solution_id"),
           ("impacted_application_id", "application", "application_id"),
           ("impacted_data_entity_id", "data_entity", "data_entity_id"),
           ("impacted_phase_id", "phase", "phase_id"),
           ("impacted_benefit_id", "benefit", "benefit_id"))
SEVEN = ", ".join(c for c, _, _ in TARGETS)
ROUTES = ("'SEED', 'BR_FR', 'BR_SOLUTION', 'FR_SOLUTION', 'SOLUTION_APP', 'BR_ENTITY', 'SOLUTION_WAVE', "
          "'SOLUTION_BENEFIT'")


def upgrade() -> None:
    op.create_table(
        "cr_impact",
        sa.Column("cr_impact_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("change_request_id", sa.BigInteger, nullable=False),
        *[sa.Column(c, sa.BigInteger) for c, _, _ in TARGETS],
        sa.Column("is_seed", sa.Boolean, nullable=False),
        sa.Column("impact_type_code_id", sa.BigInteger),
        category_column("impact_type_category", "CR_IMPACT_TYPE"),
        sa.Column("reached_via", sa.String(20), nullable=False),
        sa.Column("effort_delta_days", sa.Numeric(9, 2)),
        sa.Column("agreed_effort_days", sa.Numeric(9, 2)),
        sa.Column("value_unit", sa.String(40)),
        sa.Column("value_at_stake", sa.Numeric(16, 2)),
        sa.Column("value_change", sa.Numeric(16, 2)),
        *audit_columns(),
        sa.ForeignKeyConstraint(["change_request_id", "project_id"],
                                ["change_request.change_request_id", "change_request.project_id"],
                                name="fk_cri_change_request"),
        *[sa.ForeignKeyConstraint([c, "project_id"], [f"{t}.{k}", f"{t}.project_id"], name=f"fk_cri_{c[9:-3]}")
          for c, t, k in TARGETS],
        sa.ForeignKeyConstraint(["impact_type_code_id", "impact_type_category"],
                                ["code_master.code_id", "code_master.category"], name="fk_cri_impact_type",
                                onupdate="NO ACTION"),
        sa.CheckConstraint(f"num_nonnulls({SEVEN}) = 1", name="ck_cri_one_object"),
        sa.CheckConstraint("is_seed = (impact_type_code_id IS NOT NULL)", name="ck_cri_seed_has_type"),
        sa.CheckConstraint("NOT is_seed OR num_nonnulls(impacted_br_id, impacted_fr_id) = 1",
                           name="ck_cri_seed_is_br_or_fr"),
        sa.CheckConstraint("is_seed = (reached_via = 'SEED')", name="ck_cri_seed_route"),
        sa.CheckConstraint(f"reached_via IN ({ROUTES})", name="ck_cri_route"),
        sa.CheckConstraint("effort_delta_days IS NULL OR (is_seed AND impacted_fr_id IS NOT NULL)",
                           name="ck_cri_delta_on_fr_seed"),
        sa.CheckConstraint("agreed_effort_days IS NULL OR impacted_fr_id IS NOT NULL", name="ck_cri_agreed_on_fr"),
        sa.CheckConstraint("(value_unit IS NULL AND value_at_stake IS NULL AND value_change IS NULL) "
                           "OR impacted_benefit_id IS NOT NULL", name="ck_cri_value_on_benefit"),
    )
    op.execute(f"ALTER TABLE cr_impact ADD CONSTRAINT uq_cri_grain UNIQUE NULLS NOT DISTINCT "
               f"(change_request_id, {SEVEN})")
    for c, _, _ in TARGETS:
        op.create_index(f"ix_cri_{c[9:-3]}", "cr_impact", [c])
    op.create_index("ix_cri_impact_type", "cr_impact", ["impact_type_code_id"])
    updated_at_trigger("cr_impact")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM cr_impact) THEN "
               "RAISE EXCEPTION 'change request impacts exist: downgrade refused'; END IF; END $$")
    drop_updated_at_trigger("cr_impact")
    op.drop_table("cr_impact")
