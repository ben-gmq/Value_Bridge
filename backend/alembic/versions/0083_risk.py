"""risk — one row per risk in one project, and the code behaviours it scores by (design §4.10, §5 RISK, D-15;
docs/slice_risks_spec.md §5; RK-1…RK-6, Ben 2026-11-02).

  1. Refuses while any project-tier RISK_STATUS row or project hide of one exists (risk statuses are company-only,
     like every status list, I-1 / W-4), or while any RISK_PROBABILITY / RISK_IMPACT / RISK_STATUS code — company or
     project — is one this revision cannot map, naming it as project:code. The operator gives it a behaviour by hand
     and re-runs (0061's way); nothing is guessed.
  2. code_master: ck_code_behaviour_present widened to the three risk lists; ck_code_risk_weight_behaviour (W1…W5,
     RK-1) and ck_code_risk_status_behaviour (OPEN / CLOSED / MATERIALISED). Library and project rows backfilled by
     code, idempotent. seed_code_master carries the same behaviours.
  3. control_rule: ck_ctl_comparison gains GE (RK-2: "12 or more").
  4. risk: probability / impact carry their weight and the status its behaviour through composite FKs (as issue,
     0063), so exposure_score is a generated column (law 6, criterion 61) and "materialised exactly when linked" is a
     CHECK (law 5). Owner, node, solution, wave and issue are same-project composite FKs; risk_live keeps a live
     risk on a live issue (issue_br's guard). Live, never frozen: no shadow, no hash-spec bump (design §5 table 32).
     vb_app gets SELECT / INSERT / UPDATE from 0001's default privileges, no DELETE (law 1).

Downgrade: refuses while any risk row exists, or while any project rule comparing with GE has been edited
(row_version > 1 — what a client agreed; nothing could recreate it). Otherwise, as 0082 under CC-8 (Ben 2026-11-02),
the house GE rule and its unedited project copies are removed (the old CHECK would refuse them;
seeds.seed_control_rules recreates them after an upgrade); then the table goes, the CHECKs are restored and the
risk-list behaviours cleared.

Revision ID: 0083
Revises: 0082
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None

# Literal here so a later edit to the models or seeds never changes what this revision did.
WEIGHTS = {"RISK_PROBABILITY": {"RARE": "W1", "UNLIKELY": "W2", "POSSIBLE": "W3", "LIKELY": "W4",
                                "ALMOST_CERTAIN": "W5"},
           "RISK_IMPACT": {"NEGLIGIBLE": "W1", "MINOR": "W2", "MODERATE": "W3", "MAJOR": "W4", "SEVERE": "W5"},
           "RISK_STATUS": {"OPEN": "OPEN", "MITIGATING": "OPEN", "CLOSED": "CLOSED", "MATERIALISED": "MATERIALISED"}}
BEHAVIOUR_BEFORE = "('FR_TYPE','RACI_TYPE','ISSUE_STATUS','PROJECT_STATUS')"
BEHAVIOUR_AFTER = ("('FR_TYPE','RACI_TYPE','ISSUE_STATUS','PROJECT_STATUS','RISK_PROBABILITY','RISK_IMPACT',"
                   "'RISK_STATUS')")
EXPOSURE_SQL = "CAST(substr(probability_weight, 2) AS smallint) * CAST(substr(impact_weight, 2) AS smallint)"


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _known() -> str:
    """SQL: true when (category, code) is one this revision maps."""
    return " OR ".join(f"(category = '{cat}' AND code IN ({_in(codes)}))" for cat, codes in WEIGHTS.items())


def upgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM code_master WHERE category = 'RISK_STATUS' AND project_id IS NOT NULL) THEN
        RAISE EXCEPTION 'project-tier RISK_STATUS rows exist (%): risk statuses are company-only; resolve them by '
          'hand first', (SELECT string_agg(project_id || ':' || code, ', ') FROM code_master
                          WHERE category = 'RISK_STATUS' AND project_id IS NOT NULL);
      END IF;
      IF EXISTS (SELECT 1 FROM project_code_visibility v JOIN code_master c ON c.code_id = v.code_id
                  WHERE c.category = 'RISK_STATUS' AND v.is_active) THEN
        RAISE EXCEPTION 'a project hides a RISK_STATUS (%): risk statuses are company-only; unhide first',
          (SELECT string_agg(v.project_id || ':' || c.code, ', ') FROM project_code_visibility v
             JOIN code_master c ON c.code_id = v.code_id WHERE c.category = 'RISK_STATUS' AND v.is_active);
      END IF;
      IF EXISTS (SELECT 1 FROM code_master WHERE category IN ('RISK_PROBABILITY', 'RISK_IMPACT', 'RISK_STATUS')
                  AND NOT (""" + _known() + """)) THEN
        RAISE EXCEPTION 'risk-list codes with no known weight or behaviour (%): set behaviour_code by hand first',
          (SELECT string_agg(coalesce(project_id::text, 'company') || ':' || category || '.' || code, ', ')
             FROM code_master WHERE category IN ('RISK_PROBABILITY', 'RISK_IMPACT', 'RISK_STATUS')
              AND NOT (""" + _known() + """));
      END IF;
    END $$""")
    op.drop_constraint("ck_code_behaviour_present", "code_master", type_="check")
    for category, codes in WEIGHTS.items():
        for code, behaviour in codes.items():
            op.execute(f"UPDATE code_master SET behaviour_code = '{behaviour}' WHERE category = '{category}' "
                       f"AND code = '{code}' AND behaviour_code IS DISTINCT FROM '{behaviour}'")
    op.create_check_constraint("ck_code_behaviour_present", "code_master",
                               f"(category IN {BEHAVIOUR_AFTER}) = (behaviour_code IS NOT NULL)")
    op.create_check_constraint(
        "ck_code_risk_weight_behaviour", "code_master",
        "category NOT IN ('RISK_PROBABILITY', 'RISK_IMPACT') OR behaviour_code IN ('W1', 'W2', 'W3', 'W4', 'W5')")
    op.create_check_constraint(
        "ck_code_risk_status_behaviour", "code_master",
        "category <> 'RISK_STATUS' OR behaviour_code IN ('OPEN', 'CLOSED', 'MATERIALISED')")

    op.drop_constraint("ck_ctl_comparison", "control_rule", type_="check")
    op.create_check_constraint("ck_ctl_comparison", "control_rule", "comparison IN ('GT', 'LT', 'PCT_GT', 'GE')")

    op.create_table(
        "risk",
        sa.Column("risk_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("risk_number", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("probability_code_id", sa.BigInteger, nullable=False),
        category_column("probability_category", "RISK_PROBABILITY"),
        sa.Column("probability_weight", sa.String(20), nullable=False),
        sa.Column("impact_code_id", sa.BigInteger, nullable=False),
        category_column("impact_category", "RISK_IMPACT"),
        sa.Column("impact_weight", sa.String(20), nullable=False),
        sa.Column("exposure_score", sa.SmallInteger, sa.Computed(EXPOSURE_SQL, persisted=True)),
        sa.Column("mitigation", sa.Text),
        sa.Column("owner_org_role_id", sa.BigInteger, nullable=False),
        sa.Column("status_code_id", sa.BigInteger, nullable=False),
        category_column("status_category", "RISK_STATUS"),
        sa.Column("status_behaviour", sa.String(20), nullable=False),
        sa.Column("raised_date", sa.Date, nullable=False),
        sa.Column("target_date", sa.Date),
        sa.Column("bfc_node_id", sa.BigInteger),
        sa.Column("solution_id", sa.BigInteger),
        sa.Column("phase_id", sa.BigInteger),
        sa.Column("materialised_issue_id", sa.BigInteger),
        *audit_columns(),
        sa.Column("risk_live", sa.Boolean, sa.Computed("CASE WHEN is_active THEN TRUE END", persisted=True)),
        sa.UniqueConstraint("project_id", "risk_number", name="uq_risk_number"),
        sa.UniqueConstraint("risk_id", "project_id", name="uq_risk_project"),
        sa.ForeignKeyConstraint(["probability_code_id", "probability_category", "probability_weight"],
                                ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                                name="fk_risk_probability", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["impact_code_id", "impact_category", "impact_weight"],
                                ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                                name="fk_risk_impact", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["status_code_id", "status_category", "status_behaviour"],
                                ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                                name="fk_risk_status", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["owner_org_role_id", "project_id"], ["org_role.org_role_id", "org_role.project_id"],
                                name="fk_risk_owner"),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id"], ["bfc_node.bfc_node_id", "bfc_node.project_id"],
                                name="fk_risk_node"),
        sa.ForeignKeyConstraint(["solution_id", "project_id"], ["solution.solution_id", "solution.project_id"],
                                name="fk_risk_solution"),
        sa.ForeignKeyConstraint(["phase_id", "project_id"], ["phase.phase_id", "phase.project_id"],
                                name="fk_risk_phase"),
        sa.ForeignKeyConstraint(["materialised_issue_id", "project_id"], ["issue.issue_id", "issue.project_id"],
                                name="fk_risk_issue"),
        sa.ForeignKeyConstraint(["materialised_issue_id", "project_id", "risk_live"],
                                ["issue.issue_id", "issue.project_id", "issue.is_active"], name="fk_risk_issue_live"),
        sa.CheckConstraint("btrim(title) <> ''", name="ck_risk_title_not_blank"),
        sa.CheckConstraint("(status_behaviour = 'MATERIALISED') = (materialised_issue_id IS NOT NULL)",
                           name="ck_risk_materialised_iff_linked"),
        sa.CheckConstraint("probability_weight IN ('W1','W2','W3','W4','W5')", name="ck_risk_probability_weight"),
        sa.CheckConstraint("impact_weight IN ('W1','W2','W3','W4','W5')", name="ck_risk_impact_weight"),
        sa.CheckConstraint("target_date IS NULL OR target_date >= raised_date", name="ck_risk_target_after_raised"),
    )
    op.execute("CREATE UNIQUE INDEX uq_risk_issue ON risk (materialised_issue_id) "
               "WHERE materialised_issue_id IS NOT NULL")
    op.execute("CREATE INDEX ix_risk_open ON risk (project_id, exposure_score) "
               "WHERE is_active AND status_behaviour = 'OPEN'")
    for name, col in (("ix_risk_probability", "probability_code_id"), ("ix_risk_impact", "impact_code_id"),
                      ("ix_risk_status", "status_code_id"), ("ix_risk_owner", "owner_org_role_id"),
                      ("ix_risk_node", "bfc_node_id"), ("ix_risk_solution", "solution_id"),
                      ("ix_risk_phase", "phase_id")):
        op.create_index(name, "risk", [col])
    updated_at_trigger("risk")


def downgrade() -> None:
    op.execute("DO $$ DECLARE n bigint; BEGIN IF EXISTS (SELECT 1 FROM risk) THEN "
               "RAISE EXCEPTION 'risks exist: downgrade refused; nothing changed'; END IF; "
               "SELECT count(*) INTO n FROM control_rule WHERE comparison = 'GE' AND project_id IS NOT NULL "
               "AND row_version > 1; "
               "IF n > 0 THEN RAISE EXCEPTION '% edited GE control rule(s) exist: downgrade refused; nothing changed', "
               "n; END IF; END $$")
    op.execute("DELETE FROM control_rule WHERE comparison = 'GE'")
    drop_updated_at_trigger("risk")
    op.drop_table("risk")
    op.drop_constraint("ck_ctl_comparison", "control_rule", type_="check")
    op.create_check_constraint("ck_ctl_comparison", "control_rule", "comparison IN ('GT', 'LT', 'PCT_GT')")
    op.drop_constraint("ck_code_risk_status_behaviour", "code_master", type_="check")
    op.drop_constraint("ck_code_risk_weight_behaviour", "code_master", type_="check")
    op.drop_constraint("ck_code_behaviour_present", "code_master", type_="check")
    op.execute("UPDATE code_master SET behaviour_code = NULL WHERE category IN "
               "('RISK_PROBABILITY', 'RISK_IMPACT', 'RISK_STATUS') AND behaviour_code IS NOT NULL")
    op.create_check_constraint("ck_code_behaviour_present", "code_master",
                               f"(category IN {BEHAVIOUR_BEFORE}) = (behaviour_code IS NOT NULL)")
