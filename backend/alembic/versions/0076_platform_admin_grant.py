"""platform_admin_grant: one row per way one user was made, or asked to be made, a platform admin (slice17 schema rev 3
§1, §3, §6, §8; spec §10; AR-13, AR-16…AR-20, AR-24, AR-25). Paused for Ben: new access functions and a backfill whose
NOTICEs he reads (D2) — built and tested on throwaway databases only until he clicks.

1. The table, its checks and indexes. A REQUEST is born open and decided once (approved / rejected / cancelled);
   BOOTSTRAP (the first two admins, written by 0078's trigger) and LEGACY (owner-run, AR-19) are born approved.
2. fn_backdating_allowed(): the only databases where a LEGACY grant may carry an earlier date (N4, whole names).
3. fn_admin_grant_independent / fn_admin_purge_independent (AR-18, AR-20, AR-24): neither of two admins made the other —
   made = requested or approved their latest grant, or created their account. Never NULL.
4. Backfill, as the owner and before any trigger: one row per flagged admin from their latest grant event, with a
   NOTICE for every admin recorded and every admin skipped. It trusts the audit history as of the migration day (D2).
5. fn_platform_admin_grant_guard (every role) and the deferred trg_pag_grant_effective (the record and the flag land
   together). vb_app: SELECT, INSERT, and UPDATE of the deciding-admin columns only; no DELETE for anyone.

Downgrade: refuses once a row exists that the backfill did not write (a record made since would be lost).

Revision ID: 0076
Revises: 0075
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import drop_updated_at_trigger, updated_at_trigger

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

PATH = "pg_catalog, public, pg_temp"
# The audit events that made an admin before this table existed (0072's AR-13 list).
BOOTSTRAP_EVENTS = ("FIRST_ADMIN_CREATED", "ADMIN_CREATED_BY_CLI")
LEGACY_EVENTS = ("PLATFORM_ADMIN_GRANTED",)
FIXED = ("platform_admin_grant_id", "grant_origin", "target_user_id", "reason", "operator_name",
         "source_audit_event_id", "recorded_at", "requested_at", "requested_by_user_id")
DECISION = ("approved_at", "approved_by_user_id", "approved_xact", "rejected_at", "rejected_by_user_id",
            "rejection_reason", "cancelled_at", "cancelled_by_user_id")
APP_UPDATABLE = ("approved_by_user_id", "rejected_by_user_id", "rejection_reason", "cancelled_by_user_id",
                 "updated_by", "row_version")


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _changed(cols) -> str:
    return "(" + " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in cols) + ")"


def _live_admin(col: str) -> str:
    return (f"EXISTS (SELECT 1 FROM public.app_user u WHERE u.app_user_id = {col} "
            f"AND u.is_active AND u.is_platform_admin)")


def _user(col: str) -> sa.Column:
    return sa.Column(col, sa.BigInteger, sa.ForeignKey("app_user.app_user_id"))


BACKDATING = f"""
    CREATE FUNCTION public.fn_backdating_allowed() RETURNS boolean
    LANGUAGE sql STABLE SET search_path = {PATH} AS $$
      -- N4: whole names, case-sensitive, never a substring; one optional token before the suffix
      SELECT current_database() ~ '^vb_([a-z0-9]+_)?test_db(_gw[0-9]+)?$'
          OR current_database() ~ '^vb_([a-z0-9]+_)?(uat|demo)_db$' $$
"""

GRANT_INDEPENDENT = f"""
    CREATE FUNCTION public.fn_admin_grant_independent(p_approver bigint, p_requester bigint) RETURNS boolean
    LANGUAGE sql STABLE SET search_path = {PATH} AS $$
      WITH latest AS (
        SELECT DISTINCT ON (g.target_user_id) g.target_user_id, g.requested_by_user_id, g.approved_by_user_id
          FROM public.platform_admin_grant g
         WHERE g.target_user_id IN (p_approver, p_requester) AND g.approved_at IS NOT NULL
         ORDER BY g.target_user_id, g.approved_at DESC, g.platform_admin_grant_id DESC),
      makers AS (                     -- AR-18 + AR-24: the latest grant's requester and approver, and the creator
        SELECT l.target_user_id, m.maker_id
          FROM latest l
          JOIN public.app_user u ON u.app_user_id = l.target_user_id
         CROSS JOIN LATERAL (VALUES (l.requested_by_user_id), (l.approved_by_user_id), (u.created_by)) AS m(maker_id))
      SELECT p_approver IS NOT NULL AND p_requester IS NOT NULL
         AND p_approver <> p_requester
         AND (SELECT count(*) FROM latest) = 2
         AND NOT EXISTS (SELECT 1 FROM makers
                          WHERE (target_user_id = p_approver AND maker_id = p_requester)
                             OR (target_user_id = p_requester AND maker_id = p_approver)) $$
"""

PURGE_INDEPENDENT = f"""
    CREATE FUNCTION public.fn_admin_purge_independent(p_approver bigint, p_requester bigint) RETURNS boolean
    LANGUAGE sql STABLE SET search_path = {PATH} AS $$
      -- AR-20: a grant approval's independence, plus the approver's latest grant at least 30 days old; never NULL
      SELECT public.fn_admin_grant_independent(p_approver, p_requester)
         AND COALESCE((SELECT g.approved_at <= statement_timestamp() - interval '30 days'
                         FROM public.platform_admin_grant g
                        WHERE g.target_user_id = p_approver AND g.approved_at IS NOT NULL
                        ORDER BY g.approved_at DESC, g.platform_admin_grant_id DESC
                        LIMIT 1), false) $$
"""

BACKFILL = f"""
    DO $$
    DECLARE r record; e record; origin text;
    BEGIN
      FOR r IN SELECT app_user_id, email FROM public.app_user WHERE is_platform_admin ORDER BY app_user_id LOOP
        SELECT a.* INTO e FROM public.audit_event a
         WHERE a.target_table = 'app_user' AND a.target_id = r.app_user_id
           AND a.event_type IN ({_in(BOOTSTRAP_EVENTS + LEGACY_EVENTS)})
         ORDER BY a.occurred_at DESC, a.audit_event_id DESC LIMIT 1;
        IF e.audit_event_id IS NULL THEN
          RAISE NOTICE '0076: SKIPPED admin % (user %): no grant event on record; until IS records a LEGACY grant they '
            'can neither approve nor be approved', r.email, r.app_user_id;
          CONTINUE;
        END IF;
        origin := CASE WHEN e.event_type IN ({_in(BOOTSTRAP_EVENTS)}) THEN 'BOOTSTRAP' ELSE 'LEGACY' END;
        INSERT INTO public.platform_admin_grant (grant_origin, target_user_id, reason, operator_name,
               source_audit_event_id, recorded_at, requested_at, requested_by_user_id, approved_at, approved_xact)
        VALUES (origin, r.app_user_id,
                COALESCE(NULLIF(btrim(e.detail->>'rationale'), ''), 'recorded by migration 0076 from audit event '
                         || e.audit_event_id),
                'migration 0076', e.audit_event_id, statement_timestamp(), e.occurred_at,
                CASE WHEN origin = 'LEGACY' AND e.app_user_id IS DISTINCT FROM r.app_user_id THEN e.app_user_id END,
                e.occurred_at, pg_current_xact_id());
        RAISE NOTICE '0076: admin % (user %) recorded as % from audit event % (%)', r.email, r.app_user_id, origin,
          e.audit_event_id, e.event_type;
      END LOOP;
    END $$
"""

GUARD = f"""
    CREATE FUNCTION public.fn_platform_admin_grant_guard() RETURNS trigger
    LANGUAGE plpgsql SET search_path = {PATH} AS $$
    DECLARE t public.app_user;
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'DELETE on platform_admin_grant is not allowed: the record is kept forever'
          USING ERRCODE = 'restrict_violation';
      END IF;
      SELECT * INTO t FROM public.app_user WHERE app_user_id = NEW.target_user_id;
      IF TG_OP = 'INSERT' THEN
        NEW.recorded_at := statement_timestamp();
        IF NEW.source_audit_event_id IS NOT NULL THEN
          RAISE EXCEPTION 'only the 0076 backfill records a source event' USING ERRCODE = 'restrict_violation';
        END IF;
        IF num_nonnulls(NEW.rejected_at, NEW.rejected_by_user_id, NEW.rejection_reason, NEW.cancelled_at,
                        NEW.cancelled_by_user_id) > 0 THEN
          RAISE EXCEPTION 'a grant is born neither rejected nor cancelled' USING ERRCODE = 'restrict_violation';
        END IF;
        IF NEW.grant_origin = 'REQUEST' THEN
          IF num_nonnulls(NEW.approved_at, NEW.approved_by_user_id, NEW.approved_xact) > 0 THEN
            RAISE EXCEPTION 'a request is born open' USING ERRCODE = 'restrict_violation';
          END IF;
          IF t.app_user_id IS NULL OR NOT t.is_active OR t.is_platform_admin THEN
            RAISE EXCEPTION 'admin rights are requested for an active user who is not an admin'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF NOT {_live_admin('NEW.requested_by_user_id')} THEN
            RAISE EXCEPTION 'only a live platform admin requests admin rights' USING ERRCODE = 'restrict_violation';
          END IF;
          IF t.created_by = NEW.requested_by_user_id THEN
            RAISE EXCEPTION 'an admin cannot ask for admin rights for an account they created (AR-24)'
              USING ERRCODE = 'restrict_violation';
          END IF;
          NEW.requested_at := statement_timestamp();
        ELSIF NEW.grant_origin = 'BOOTSTRAP' THEN
          IF pg_trigger_depth() < 2 THEN                     -- only from 0078's trigger, with the account it makes
            RAISE EXCEPTION 'a bootstrap grant is recorded only with the account it makes (AR-16)'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF t.app_user_id IS NULL OR NOT t.is_active OR NOT t.is_platform_admin
             OR EXISTS (SELECT 1 FROM public.platform_admin_grant g WHERE g.target_user_id = NEW.target_user_id) THEN
            RAISE EXCEPTION 'a bootstrap grant records a new admin account once' USING ERRCODE = 'restrict_violation';
          END IF;
          NEW.requested_at := statement_timestamp();
          NEW.approved_at := NEW.requested_at;
          NEW.approved_by_user_id := NULL;
          NEW.approved_xact := pg_current_xact_id();
        ELSE                                                 -- LEGACY (AR-19, N5)
          IF session_user <> 'vb_owner' THEN
            RAISE EXCEPTION 'only Fortience IS, as the owner, records a legacy grant (AR-19, AR-22)'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF btrim(COALESCE(NEW.operator_name, '')) = '' OR NOT {_live_admin('NEW.requested_by_user_id')} THEN
            RAISE EXCEPTION 'a legacy grant names its operator and the live admin who asked for it (N5)'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF t.app_user_id IS NULL OR NOT t.is_active OR t.is_platform_admin THEN
            RAISE EXCEPTION 'admin rights are granted to an active user who is not an admin'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF t.created_by = NEW.requested_by_user_id THEN
            RAISE EXCEPTION 'an admin cannot ask for admin rights for an account they created (AR-24)'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF NOT (public.fn_backdating_allowed() AND NEW.requested_at IS NOT NULL
                  AND NEW.requested_at <= statement_timestamp()) THEN
            NEW.requested_at := statement_timestamp();         -- AR-19: the database's time outside test / demo
          END IF;
          NEW.approved_at := NEW.requested_at;
          NEW.approved_by_user_id := NULL;
          NEW.approved_xact := pg_current_xact_id();
        END IF;
        RETURN NEW;
      END IF;
      IF {_changed(FIXED)} THEN
        RAISE EXCEPTION 'a grant''s origin, target, reason, operator, asker and times never change'
          USING ERRCODE = 'restrict_violation';
      END IF;
      IF OLD.approved_at IS NOT NULL OR OLD.rejected_at IS NOT NULL OR OLD.cancelled_at IS NOT NULL THEN
        IF {_changed(DECISION)} THEN
          RAISE EXCEPTION 'a decided grant never changes' USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN NEW;
      END IF;
      IF num_nonnulls(NEW.approved_by_user_id, NEW.rejected_by_user_id, NEW.cancelled_by_user_id) > 1 THEN
        RAISE EXCEPTION 'a request is decided once, one way' USING ERRCODE = 'restrict_violation';
      END IF;
      IF NEW.approved_by_user_id IS NOT NULL THEN                                        -- approve
        IF NEW.approved_by_user_id IN (OLD.requested_by_user_id, OLD.target_user_id) THEN
          RAISE EXCEPTION 'four eyes: neither the requester nor the user themselves approves'
            USING ERRCODE = 'restrict_violation';
        END IF;
        IF NOT {_live_admin('NEW.approved_by_user_id')} OR NOT {_live_admin('OLD.requested_by_user_id')} THEN
          RAISE EXCEPTION 'a request is approved by a live platform admin while its requester is one'
            USING ERRCODE = 'restrict_violation';
        END IF;
        IF t.app_user_id IS NULL OR NOT t.is_active OR t.is_platform_admin THEN
          RAISE EXCEPTION 'the user is no longer active, or is already an admin' USING ERRCODE = 'restrict_violation';
        END IF;
        IF t.created_by = NEW.approved_by_user_id THEN
          RAISE EXCEPTION 'an admin cannot approve admin rights for an account they created (AR-24)'
            USING ERRCODE = 'restrict_violation';
        END IF;
        IF NOT public.fn_admin_grant_independent(NEW.approved_by_user_id, OLD.requested_by_user_id) THEN
          RAISE EXCEPTION 'the approver must be independent of the requester: neither made the other an admin or '
            'created their account (AR-18, AR-24)' USING ERRCODE = 'restrict_violation';
        END IF;
        NEW.approved_at := statement_timestamp();
        NEW.approved_xact := pg_current_xact_id();
      ELSIF NEW.rejected_by_user_id IS NOT NULL THEN                                      -- reject
        IF NEW.rejected_by_user_id = OLD.requested_by_user_id OR NOT {_live_admin('NEW.rejected_by_user_id')} THEN
          RAISE EXCEPTION 'a request is rejected by a live platform admin other than its requester'
            USING ERRCODE = 'restrict_violation';
        END IF;
        NEW.rejected_at := statement_timestamp();
      ELSIF NEW.cancelled_by_user_id IS NOT NULL THEN                                     -- cancel
        IF NOT {_live_admin('NEW.cancelled_by_user_id')} THEN
          RAISE EXCEPTION 'a request is cancelled by a live platform admin' USING ERRCODE = 'restrict_violation';
        END IF;
        NEW.cancelled_at := statement_timestamp();
      ELSIF num_nonnulls(NEW.approved_at, NEW.approved_xact, NEW.rejected_at, NEW.rejection_reason,
                         NEW.cancelled_at) > 0 THEN
        RAISE EXCEPTION 'a decision names who made it' USING ERRCODE = 'restrict_violation';
      END IF;
      RETURN NEW;
    END $$
"""

EFFECTIVE = f"""
    CREATE FUNCTION public.fn_pag_grant_effective() RETURNS trigger
    LANGUAGE plpgsql SET search_path = {PATH} AS $$
    BEGIN
      IF (TG_OP = 'INSERT' AND NEW.grant_origin = 'LEGACY')
         OR (TG_OP = 'UPDATE' AND OLD.approved_at IS NULL AND NEW.approved_at IS NOT NULL) THEN
        IF NOT EXISTS (SELECT 1 FROM public.app_user u WHERE u.app_user_id = NEW.target_user_id
                        AND u.is_active AND u.is_platform_admin) THEN
          RAISE EXCEPTION 'an approved grant and the admin flag land together, or neither does'
            USING ERRCODE = 'restrict_violation';
        END IF;
      END IF;
      RETURN NULL;
    END $$
"""


def upgrade() -> None:
    op.create_table(
        "platform_admin_grant",
        sa.Column("platform_admin_grant_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("grant_origin", sa.String(10), nullable=False),
        sa.Column("target_user_id", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("operator_name", sa.String(200)),
        sa.Column("source_audit_event_id", sa.BigInteger),                    # no FK: audit_event is a purge table
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        _user("requested_by_user_id"),
        sa.Column("approved_at", sa.DateTime(timezone=True)), _user("approved_by_user_id"),
        sa.Column("rejected_at", sa.DateTime(timezone=True)), _user("rejected_by_user_id"),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)), _user("cancelled_by_user_id"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        _user("updated_by"),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint("grant_origin IN ('REQUEST', 'BOOTSTRAP', 'LEGACY')", name="ck_pag_origin"),
        sa.CheckConstraint("btrim(reason) <> ''", name="ck_pag_reason"),
        sa.CheckConstraint("(grant_origin <> 'REQUEST' OR operator_name IS NULL) "
                           "AND (grant_origin <> 'LEGACY' OR operator_name IS NOT NULL)", name="ck_pag_operator"),
        sa.CheckConstraint("grant_origin = 'BOOTSTRAP' OR requested_by_user_id IS NOT NULL "
                           "OR source_audit_event_id IS NOT NULL", name="ck_pag_requester"),
        sa.CheckConstraint("approved_by_user_id <> requested_by_user_id AND approved_by_user_id <> target_user_id "
                           "AND requested_by_user_id <> target_user_id", name="ck_pag_four_eyes"),
        sa.CheckConstraint("rejected_by_user_id <> requested_by_user_id", name="ck_pag_reject_not_requester"),
        sa.CheckConstraint("num_nonnulls(approved_at, rejected_at, cancelled_at) <= 1", name="ck_pag_one_end"),
        sa.CheckConstraint("grant_origin = 'REQUEST' OR num_nonnulls(rejected_at, cancelled_at) = 0",
                           name="ck_pag_request_only"),
        sa.CheckConstraint("source_audit_event_id IS NULL OR grant_origin <> 'REQUEST'", name="ck_pag_source"),
        sa.CheckConstraint("num_nonnulls(rejected_at, rejected_by_user_id, rejection_reason) IN (0, 3) "
                           "AND (rejection_reason IS NULL OR btrim(rejection_reason) <> '')", name="ck_pag_rejected"),
        sa.CheckConstraint("num_nonnulls(cancelled_at, cancelled_by_user_id) IN (0, 2)", name="ck_pag_cancelled"),
    )
    op.execute("ALTER TABLE platform_admin_grant ADD COLUMN approved_xact xid8")
    op.execute("ALTER TABLE platform_admin_grant ADD CONSTRAINT ck_pag_approved CHECK ("
               "(grant_origin = 'REQUEST' AND num_nonnulls(approved_at, approved_by_user_id, approved_xact) IN (0, 3)) "
               "OR (grant_origin <> 'REQUEST' AND approved_at IS NOT NULL AND approved_xact IS NOT NULL "
               "AND approved_by_user_id IS NULL))")
    op.create_index("uq_pag_open", "platform_admin_grant", ["target_user_id"], unique=True,
                    postgresql_where=sa.text("approved_at IS NULL AND rejected_at IS NULL AND cancelled_at IS NULL"))
    op.execute("CREATE INDEX ix_pag_target_granted ON platform_admin_grant (target_user_id, approved_at DESC) "
               "WHERE approved_at IS NOT NULL")
    op.execute(BACKDATING)
    op.execute(GRANT_INDEPENDENT)
    op.execute(PURGE_INDEPENDENT)
    op.execute(BACKFILL)                                       # D2: before the guard exists, as the owner
    updated_at_trigger("platform_admin_grant")
    op.execute(GUARD)
    op.execute("CREATE TRIGGER trg_platform_admin_grant_guard BEFORE INSERT OR UPDATE OR DELETE "
               "ON platform_admin_grant FOR EACH ROW EXECUTE FUNCTION fn_platform_admin_grant_guard()")
    op.execute(EFFECTIVE)
    op.execute("CREATE CONSTRAINT TRIGGER trg_pag_grant_effective AFTER INSERT OR UPDATE ON platform_admin_grant "
               "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fn_pag_grant_effective()")
    op.execute("REVOKE ALL ON platform_admin_grant FROM vb_app")
    op.execute("GRANT SELECT, INSERT ON platform_admin_grant TO vb_app")
    op.execute(f"GRANT UPDATE ({', '.join(APP_UPDATABLE)}) ON platform_admin_grant TO vb_app")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM platform_admin_grant WHERE source_audit_event_id IS NULL) THEN "
               "RAISE EXCEPTION 'grant records exist that the backfill did not write: downgrade refused'; "
               "END IF; END $$")
    op.execute("DROP TRIGGER IF EXISTS trg_pag_grant_effective ON platform_admin_grant")
    op.execute("DROP TRIGGER IF EXISTS trg_platform_admin_grant_guard ON platform_admin_grant")
    drop_updated_at_trigger("platform_admin_grant")
    op.execute("DROP FUNCTION IF EXISTS fn_pag_grant_effective()")
    op.execute("DROP FUNCTION IF EXISTS fn_platform_admin_grant_guard()")
    op.execute("DROP FUNCTION IF EXISTS fn_admin_purge_independent(bigint, bigint)")
    op.execute("DROP FUNCTION IF EXISTS fn_admin_grant_independent(bigint, bigint)")
    op.execute("DROP FUNCTION IF EXISTS fn_backdating_allowed()")
    op.drop_table("platform_admin_grant")
