"""control_rule — a threshold on one analysis, with the client role that owns the response (D-19; design §5.3;
docs/slice_control_a_spec.md §2; CT-1…CT-4, Ben 2026-10-30).

Two tiers: project_id NULL is the FTC house default (one per analysis), copied — never referenced — into each project
by create_project and seeds.seed_control_rules. A house row has no author (seeded by the CLI, deviation 7j) and no
owner (no client org chart exists yet). A project row's owner is optional (CT-1) and, when set, a role of the same
project through the composite FK. analysis_code is the §7.13 registry and comparison the operator the code branches
on, both CHECK-listed (deviation 7j). Not shadowed — governance config, not scope (§5.10 row 40). vb_app gets
SELECT/INSERT/UPDATE from 0001's default privileges and no DELETE. A live rule blocks retiring its owning org role
through the FK (lifecycle, law 1).

Downgrade: refuses while any project rule has been edited (row_version > 1) — that row is what a client agreed and
nothing could recreate it. Unedited rows are copies of the house tier, which seeds.seed_control_rules recreates, so
they go with the table.

Revision ID: 0081
Revises: 0080
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, updated_at_trigger

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None

REGISTRY = ("priced_diff", "requirement_volatility", "coverage", "solution_matrix", "application_gap",
            "interface_load", "org_impact_heatmap", "stakeholder_engagement", "value_ranking", "benefit_gap",
            "risk_register", "issue_dashboard", "data_migration_map", "master_data_candidates",
            "process_change_intensity", "phase_plan", "consistency_check")


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    cols = [c for c in audit_columns() if c.name != "created_by"]
    op.create_table(
        "control_rule",
        sa.Column("control_rule_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id")),
        sa.Column("analysis_code", sa.String(40), nullable=False),
        sa.Column("comparison", sa.String(10), nullable=False),
        sa.Column("threshold_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("escalate_value", sa.Numeric(12, 2)),
        sa.Column("owner_org_role_id", sa.BigInteger),
        sa.Column("prescribed_action", sa.Text),
        sa.Column("escalation_path", sa.Text),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_house_default", sa.Boolean, nullable=False),
        sa.Column("change_rationale", sa.Text),
        sa.Column("agreed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id")),
        *cols,
        sa.ForeignKeyConstraint(["owner_org_role_id", "project_id"], ["org_role.org_role_id", "org_role.project_id"],
                                name="fk_ctl_owner_role"),
        sa.CheckConstraint(f"analysis_code IN ({_in(REGISTRY)})", name="ck_ctl_analysis"),
        sa.CheckConstraint("comparison IN ('GT', 'LT', 'PCT_GT')", name="ck_ctl_comparison"),
        sa.CheckConstraint("is_house_default = (project_id IS NULL)", name="ck_ctl_house_tier"),
        sa.CheckConstraint("project_id IS NOT NULL OR owner_org_role_id IS NULL", name="ck_ctl_house_no_owner"),
        sa.CheckConstraint("project_id IS NULL OR created_by IS NOT NULL", name="ck_ctl_project_author"),
        sa.CheckConstraint("row_version = 1 OR change_rationale IS NOT NULL", name="ck_ctl_rationale"),
    )
    op.execute("CREATE UNIQUE INDEX uq_ctl_house ON control_rule (analysis_code) WHERE project_id IS NULL")
    op.execute("CREATE UNIQUE INDEX uq_ctl_project ON control_rule (project_id, analysis_code) "
               "WHERE project_id IS NOT NULL")
    op.create_index("ix_ctl_owner", "control_rule", ["owner_org_role_id", "project_id"])
    updated_at_trigger("control_rule")


def downgrade() -> None:
    op.execute("DO $$ DECLARE n bigint; BEGIN "
               "SELECT count(*) INTO n FROM control_rule WHERE project_id IS NOT NULL AND row_version > 1; "
               "IF n > 0 THEN RAISE EXCEPTION '% edited project control rule(s) exist: downgrade refused; "
               "nothing dropped', n; END IF; END $$")
    drop_updated_at_trigger("control_rule")
    op.drop_table("control_rule")
