"""change_request and the CR_STATUS behaviours (design §4.11, §5 CHANGE_REQUEST, D-16; docs/slice_change_requests_spec.md
§3; CR-1…CR-3, Ben 2026-11-03).

  1. Refuses while any project-tier CR_STATUS row or project hide of one exists (CR statuses become company-only, as
     every status list, I-1 / W-4), or while any CR_STATUS code is one this revision cannot map, naming it as
     project:code. The operator resolves it by hand and re-runs (0083 / 0085's way); nothing is guessed.
  2. code_master: ck_code_behaviour_present widened to CR_STATUS; ck_code_cr_status_behaviour (OPEN / PRICED /
     DEFERRED / APPROVED / REJECTED). Library rows backfilled by code, idempotent; seed_code_master carries the same.
  3. change_request: one row per proposed change to one agreed baseline of one project. The target, the origin, the
     status (with its behaviour), the latest decision and the cut it uses are all same-project composite FKs. The four
     price columns are all set or all empty and only the service writes them (law 6); PRICED needs every seed rated;
     a decided CR names its decision; a cut is used once (uq_cr_displaces_once) and only by an approved increase; the
     budget record is all-or-none and only on an approved CR. vb_app gets SELECT / INSERT / UPDATE from 0001's default
     privileges, no DELETE (law 1). Live-only: no shadow, no freeze-set entry, hash spec unchanged (spec §5).

Downgrade: refuses while change_request holds any row; drops it, restores the CHECK and clears the behaviours.

Revision ID: 0087
Revises: 0086
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None

# Literal here so a later edit to the models or seeds never changes what this revision did.
BEHAVIOURS = {"DRAFT": "OPEN", "ANALYSED": "OPEN", "PRICED": "PRICED", "DEFERRED": "DEFERRED",
              "APPROVED": "APPROVED", "REJECTED": "REJECTED"}
BEHAVIOUR_BEFORE = ("('FR_TYPE','RACI_TYPE','ISSUE_STATUS','PROJECT_STATUS','RISK_PROBABILITY','RISK_IMPACT',"
                    "'RISK_STATUS','BENEFIT_STATUS')")
BEHAVIOUR_AFTER = ("('FR_TYPE','RACI_TYPE','ISSUE_STATUS','PROJECT_STATUS','RISK_PROBABILITY','RISK_IMPACT',"
                   "'RISK_STATUS','BENEFIT_STATUS','CR_STATUS')")
KNOWN = ", ".join(f"'{c}'" for c in BEHAVIOURS)
STATES = "('OPEN', 'PRICED', 'DEFERRED', 'APPROVED', 'REJECTED')"
PRICE = ("effort_delta_days", "effort_exposed_days", "unrated_fr_count", "priced_at")
BUDGET = ("budget_increase_days", "budget_reference", "budget_approved_by")


def upgrade() -> None:
    op.execute(f"""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM code_master WHERE category = 'CR_STATUS' AND project_id IS NOT NULL) THEN
        RAISE EXCEPTION 'project-tier CR_STATUS rows exist (%): change request statuses are company-only; resolve '
          'them by hand first', (SELECT string_agg(project_id || ':' || code, ', ') FROM code_master
                                 WHERE category = 'CR_STATUS' AND project_id IS NOT NULL);
      END IF;
      IF EXISTS (SELECT 1 FROM project_code_visibility v JOIN code_master c ON c.code_id = v.code_id
                  WHERE c.category = 'CR_STATUS' AND v.is_active) THEN
        RAISE EXCEPTION 'a project hides a CR_STATUS (%): change request statuses are company-only; unhide first',
          (SELECT string_agg(v.project_id || ':' || c.code, ', ') FROM project_code_visibility v
             JOIN code_master c ON c.code_id = v.code_id WHERE c.category = 'CR_STATUS' AND v.is_active);
      END IF;
      IF EXISTS (SELECT 1 FROM code_master WHERE category = 'CR_STATUS' AND code NOT IN ({KNOWN})) THEN
        RAISE EXCEPTION 'CR_STATUS codes with no known behaviour (%): set behaviour_code by hand first',
          (SELECT string_agg(coalesce(project_id::text, 'company') || ':' || code, ', ') FROM code_master
            WHERE category = 'CR_STATUS' AND code NOT IN ({KNOWN}));
      END IF;
    END $$""")
    op.drop_constraint("ck_code_behaviour_present", "code_master", type_="check")
    for code, behaviour in BEHAVIOURS.items():
        op.execute(f"UPDATE code_master SET behaviour_code = '{behaviour}' WHERE category = 'CR_STATUS' "
                   f"AND code = '{code}' AND behaviour_code IS DISTINCT FROM '{behaviour}'")
    op.create_check_constraint("ck_code_behaviour_present", "code_master",
                               f"(category IN {BEHAVIOUR_AFTER}) = (behaviour_code IS NOT NULL)")
    op.create_check_constraint("ck_code_cr_status_behaviour", "code_master",
                               f"category <> 'CR_STATUS' OR behaviour_code IN {STATES}")

    op.create_table(
        "change_request",
        sa.Column("change_request_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("cr_number", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("against_baseline_id", sa.BigInteger, nullable=False),
        sa.Column("origin_code_id", sa.BigInteger, nullable=False),
        category_column("origin_category", "CR_ORIGIN"),
        sa.Column("status_code_id", sa.BigInteger, nullable=False),
        category_column("status_category", "CR_STATUS"),
        sa.Column("status_behaviour", sa.String(20), nullable=False),
        sa.Column("raised_by_user_id", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.Column("effort_delta_days", sa.Numeric(9, 2)),
        sa.Column("effort_exposed_days", sa.Numeric(9, 2)),
        sa.Column("unrated_fr_count", sa.Integer),
        sa.Column("priced_at", sa.DateTime(timezone=True)),
        sa.Column("decision_id", sa.BigInteger),
        sa.Column("displaces_cr_id", sa.BigInteger),
        sa.Column("budget_increase_days", sa.Numeric(9, 2)),
        sa.Column("budget_reference", sa.String(200)),
        sa.Column("budget_approved_by", sa.String(200)),
        *audit_columns(),
        sa.UniqueConstraint("project_id", "cr_number", name="uq_cr_number"),
        sa.UniqueConstraint("change_request_id", "project_id", name="uq_cr_project"),
        sa.ForeignKeyConstraint(["against_baseline_id", "project_id"], ["baseline.baseline_id", "baseline.project_id"],
                                name="fk_cr_baseline"),
        sa.ForeignKeyConstraint(["origin_code_id", "origin_category"], ["code_master.code_id", "code_master.category"],
                                name="fk_cr_origin", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["status_code_id", "status_category", "status_behaviour"],
                                ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                                name="fk_cr_status", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["decision_id", "project_id"], ["decision.decision_id", "decision.project_id"],
                                name="fk_cr_decision"),
        sa.ForeignKeyConstraint(["displaces_cr_id", "project_id"],
                                ["change_request.change_request_id", "change_request.project_id"],
                                name="fk_cr_displaces"),
        sa.CheckConstraint("btrim(title) <> ''", name="ck_cr_title_not_blank"),
        sa.CheckConstraint("btrim(rationale) <> ''", name="ck_cr_rationale_not_blank"),
        sa.CheckConstraint(f"status_behaviour IN {STATES}", name="ck_cr_status_behaviour"),
        sa.CheckConstraint("raised_by_user_id = created_by", name="ck_cr_raised_by_creator"),
        sa.CheckConstraint(f"num_nulls({', '.join(PRICE)}) IN (0, 4)", name="ck_cr_price_all_or_none"),
        sa.CheckConstraint("unrated_fr_count IS NULL OR unrated_fr_count >= 0", name="ck_cr_unrated"),
        sa.CheckConstraint("status_behaviour NOT IN ('PRICED', 'APPROVED') OR (priced_at IS NOT NULL "
                           "AND unrated_fr_count = 0)", name="ck_cr_priced_is_rated"),
        sa.CheckConstraint("status_behaviour NOT IN ('APPROVED', 'REJECTED', 'DEFERRED') OR decision_id IS NOT NULL",
                           name="ck_cr_decided_has_decision"),
        sa.CheckConstraint("displaces_cr_id IS NULL OR displaces_cr_id <> change_request_id",
                           name="ck_cr_displaces_not_self"),
        sa.CheckConstraint("displaces_cr_id IS NULL OR (status_behaviour = 'APPROVED' AND effort_delta_days > 0)",
                           name="ck_cr_displaces_on_increase"),
        sa.CheckConstraint("num_nulls(budget_increase_days, budget_reference, budget_approved_by) IN (0, 3)",
                           name="ck_cr_budget_all_or_none"),
        sa.CheckConstraint("budget_increase_days IS NULL OR (budget_increase_days > 0 AND btrim(budget_reference) <> '' "
                           "AND btrim(budget_approved_by) <> '' AND status_behaviour = 'APPROVED' "
                           "AND effort_delta_days > 0)", name="ck_cr_budget_on_increase"),
    )
    op.create_index("ix_cr_status", "change_request", ["project_id", "status_code_id"])
    op.create_index("ix_cr_baseline", "change_request", ["against_baseline_id"])
    op.create_index("ix_cr_decision", "change_request", ["decision_id"])
    op.create_index("ix_cr_origin", "change_request", ["origin_code_id"])
    op.create_index("ix_cr_raised_by", "change_request", ["raised_by_user_id"])
    op.create_index("uq_cr_displaces_once", "change_request", ["displaces_cr_id"], unique=True,
                    postgresql_where=sa.text("displaces_cr_id IS NOT NULL"))
    updated_at_trigger("change_request")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM change_request) THEN "
               "RAISE EXCEPTION 'change requests exist: downgrade refused'; END IF; END $$")
    drop_updated_at_trigger("change_request")
    op.drop_table("change_request")
    op.drop_constraint("ck_code_cr_status_behaviour", "code_master", type_="check")
    op.drop_constraint("ck_code_behaviour_present", "code_master", type_="check")
    op.execute("UPDATE code_master SET behaviour_code = NULL WHERE category = 'CR_STATUS' "
               "AND behaviour_code IS NOT NULL")
    op.create_check_constraint("ck_code_behaviour_present", "code_master",
                               f"(category IN {BEHAVIOUR_BEFORE}) = (behaviour_code IS NOT NULL)")
