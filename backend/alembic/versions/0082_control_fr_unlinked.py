"""control_rule may name fr_unlinked — FRs nobody traced to a requirement (design §7.9, §7.13;
docs/slice_control_c_spec.md §2.3, §7; CC-3, Ben 2026-10-30).

Re-creates ck_ctl_analysis with the code added. No table, no shadow (control_rule is not frozen), no hash-spec bump.
The lists are literal here so a later edit to models/control.REGISTRY never changes what this revision did.

Downgrade (as 0081; Ben 2026-11-02): refuses while any project fr_unlinked rule has been edited (row_version > 1) —
that row is what a client agreed and nothing could recreate it. Otherwise the house row and the unedited project
copies are removed (the old constraint would refuse them; seeds.seed_control_rules recreates them after an upgrade).

Revision ID: 0082
Revises: 0081
"""
from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None

BEFORE = ("priced_diff", "requirement_volatility", "coverage", "solution_matrix", "application_gap",
          "interface_load", "org_impact_heatmap", "stakeholder_engagement", "value_ranking", "benefit_gap",
          "risk_register", "issue_dashboard", "data_migration_map", "master_data_candidates",
          "process_change_intensity", "phase_plan", "consistency_check")
AFTER = BEFORE + ("fr_unlinked",)


def _check(values) -> None:
    op.drop_constraint("ck_ctl_analysis", "control_rule", type_="check")
    op.create_check_constraint("ck_ctl_analysis", "control_rule",
                               "analysis_code IN (" + ", ".join(f"'{v}'" for v in values) + ")")


def upgrade() -> None:
    _check(AFTER)


def downgrade() -> None:
    op.execute("DO $$ DECLARE n bigint; BEGIN "
               "SELECT count(*) INTO n FROM control_rule WHERE analysis_code = 'fr_unlinked' "
               "AND project_id IS NOT NULL AND row_version > 1; "
               "IF n > 0 THEN RAISE EXCEPTION '% edited fr_unlinked control rule(s) exist: downgrade refused; "
               "nothing changed', n; END IF; END $$")
    op.execute("DELETE FROM control_rule WHERE analysis_code = 'fr_unlinked'")
    _check(BEFORE)
