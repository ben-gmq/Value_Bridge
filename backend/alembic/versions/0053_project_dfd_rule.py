"""project_dfd_rule: each chart of a project chooses the DFD elements a process needs before a freeze (D-70;
docs/slice13_schema.md §2, S13-1). Runs as vb_owner, one transaction.

1. `project_dfd_rule` (project × chart × element). A live row = required, a retired row = not required; re-adding
   restores the row (S1-7). The element is CHECK-listed, not a code_master FK [Q-17]: the codes are predicates in
   services/process_flow, and a code_master row could not be referenced here (seeds run after the migration, F1).
   STARTED can never be retired (ck_pdr_started_locked). ORDER needing both data elements is a cross-row rule held
   by services/dfd_rule.validate (422) and re-proved by the must-be-empty consistency line `dfd_rule_invalid`.
2. Backfill — data in a migration only because the table is born empty and must equal today's behaviour (spec §6):
   EVERY project, live or retired, both charts, exactly the D-38 rule (STARTED + DATA_OUT) [Q-4, Q-18, DR13-D3],
   authored by the project's creator (F11). One PROJECT_DFD_RULE_BACKFILLED audit event per project, no actor
   (the 0038 precedent); a re-run after a clean downgrade writes the same rows and no second event. So no
   project's freeze changes on deploy (B1).
3. `baseline.dfd_rule_to_be` / `dfd_rule_as_is` (varchar(12)[], nullable, no default — not a row write, F6): the
   rule each chart passed at the freeze. Both NULL = frozen before 13b, the D-38 rule [Q-19].
4. fn_baseline_header_guard() is replaced with both columns in its frozen list (F5): the owner role cannot change
   them either. vb_app never had UPDATE on them (0047's column grant).

Downgrade, refused (pauses for Ben, law 10) while a baseline records a rule — dropping it erases which rule a frozen
baseline passed (law 2) — or while any chart's live rule differs from the backfilled pair, which would silently
change that project's freeze. Otherwise: the 0047 guard body back, the header columns and the table dropped. The
backfill audit rows stay (append-only, landmine 2).

Revision ID: 0053
Revises: 0052
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, updated_at_trigger

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

ELEMENTS = ("STARTED", "DATA_IN", "DATA_OUT", "EXTERNAL", "ORDER")
_ARR = "ARRAY[" + ",".join(f"'{e}'" for e in ELEMENTS) + "]::varchar(12)[]"

# 0047's lists, unchanged except for the two new frozen columns.
FROZEN_0047 = ("baseline_id", "project_id", "major_no", "minor_no", "hash_spec_version", "data_model_depth",
               "note", "prior_baseline_id", "frozen_at", "frozen_by_user_id", "content_digest")
FROZEN_0053 = (*FROZEN_0047, "dfd_rule_to_be", "dfd_rule_as_is")
APPROVAL_COLUMNS = ("client_approver_name", "client_approved_on", "approval_note", "approval_reference",
                    "approved_at", "approved_by_user_id")


def _guard_sql(frozen_columns: tuple[str, ...]) -> str:
    frozen = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in frozen_columns)
    approval = ("OLD.client_approver_name IS NOT NULL AND ("
                + " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in APPROVAL_COLUMNS) + ")")
    return f"""
        CREATE OR REPLACE FUNCTION fn_baseline_header_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'DELETE on baseline is not allowed: a baseline is never removed'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF {frozen} THEN
            RAISE EXCEPTION 'a frozen baseline column cannot change' USING ERRCODE = 'restrict_violation';
          END IF;
          IF {approval} THEN
            RAISE EXCEPTION 'a recorded client approval cannot change' USING ERRCODE = 'restrict_violation';
          END IF;
          RETURN NEW;
        END $$;
    """


def upgrade() -> None:
    # 1. the table
    op.create_table(
        "project_dfd_rule",
        sa.Column("project_dfd_rule_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("bfc_set_code", sa.String(10), nullable=False),
        sa.Column("element_code", sa.String(12), nullable=False),
        *audit_columns(),
        sa.UniqueConstraint("project_id", "bfc_set_code", "element_code", name="uq_project_dfd_rule"),
        sa.CheckConstraint("bfc_set_code IN ('TO_BE', 'AS_IS')", name="ck_pdr_set"),
        sa.CheckConstraint("element_code IN (" + ", ".join(f"'{e}'" for e in ELEMENTS) + ")", name="ck_pdr_element"),
        sa.CheckConstraint("element_code <> 'STARTED' OR is_active", name="ck_pdr_started_locked"),
    )
    updated_at_trigger("project_dfd_rule")

    # 2. backfill: every project, whatever its is_active, both charts, today's rule
    op.execute("""
        INSERT INTO project_dfd_rule (project_id, bfc_set_code, element_code, created_by)
        SELECT p.project_id, s.c, e.c, p.created_by
        FROM   project p
        CROSS  JOIN (VALUES ('TO_BE'), ('AS_IS')) s(c)
        CROSS  JOIN (VALUES ('STARTED'), ('DATA_OUT')) e(c)
        ORDER  BY p.project_id, s.c DESC, e.c""")
    op.execute("""
        DO $$ BEGIN
          IF (SELECT count(*) FROM project_dfd_rule) <> 4 * (SELECT count(*) FROM project) THEN
            RAISE EXCEPTION '0053: the DFD rule backfill did not cover every project on both charts';
          END IF;
        END $$""")
    op.execute("""
        INSERT INTO audit_event (event_type, project_id, target_table, detail)
        SELECT 'PROJECT_DFD_RULE_BACKFILLED', p.project_id, 'project_dfd_rule',
               jsonb_build_object('decision', 'D-70', 'migration', '0053',
                                  'rule', jsonb_build_array('DATA_OUT', 'STARTED'),
                                  'charts', jsonb_build_array('AS_IS', 'TO_BE'),
                                  'project_is_active', p.is_active)
        FROM   project p
        WHERE  NOT EXISTS (SELECT 1 FROM audit_event e WHERE e.event_type = 'PROJECT_DFD_RULE_BACKFILLED'
                           AND e.project_id = p.project_id)       -- a re-run after a clean downgrade: already told
        ORDER  BY p.project_id""")

    # 3. the header: the rule each chart passed
    op.add_column("baseline", sa.Column("dfd_rule_to_be", sa.ARRAY(sa.String(12))))
    op.add_column("baseline", sa.Column("dfd_rule_as_is", sa.ARRAY(sa.String(12))))
    op.create_check_constraint("ck_baseline_dfd_rule_pair", "baseline",
                               "num_nonnulls(dfd_rule_to_be, dfd_rule_as_is) IN (0, 2)")
    op.create_check_constraint(
        "ck_baseline_dfd_rule_vals", "baseline",
        f"dfd_rule_to_be IS NULL OR (cardinality(dfd_rule_to_be) >= 1 AND cardinality(dfd_rule_as_is) >= 1 "
        f"AND dfd_rule_to_be <@ {_ARR} AND dfd_rule_as_is <@ {_ARR})")

    # 4. the header guard freezes them for every role
    op.execute(_guard_sql(FROZEN_0053))


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM baseline WHERE dfd_rule_to_be IS NOT NULL OR dfd_rule_as_is IS NOT NULL) THEN
            RAISE EXCEPTION '0053 downgrade refused: a baseline records the DFD rule it was frozen under '
                            '(dropping it erases frozen evidence; pauses for Ben)';
          END IF;
          IF EXISTS (
              SELECT 1
              FROM   (SELECT DISTINCT project_id, bfc_set_code FROM project_dfd_rule) k
              WHERE  ARRAY(SELECT r.element_code::text FROM project_dfd_rule r
                           WHERE  r.project_id = k.project_id AND r.bfc_set_code = k.bfc_set_code AND r.is_active
                           ORDER  BY r.element_code) <> ARRAY['DATA_OUT', 'STARTED']) THEN
            RAISE EXCEPTION '0053 downgrade refused: a project chose a DFD rule other than D-38 '
                            '(dropping it would change that project''s freeze; pauses for Ben)';
          END IF;
        END $$""")
    op.execute(_guard_sql(FROZEN_0047))
    op.drop_constraint("ck_baseline_dfd_rule_vals", "baseline", type_="check")
    op.drop_constraint("ck_baseline_dfd_rule_pair", "baseline", type_="check")
    op.drop_column("baseline", "dfd_rule_as_is")
    op.drop_column("baseline", "dfd_rule_to_be")
    drop_updated_at_trigger("project_dfd_rule")
    op.drop_table("project_dfd_rule")
