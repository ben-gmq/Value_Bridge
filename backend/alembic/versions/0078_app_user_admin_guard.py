"""The guard on becoming a platform admin (slice17 schema rev 3 §4, §8; spec §10 criteria 7–10; AR-13, AR-16, AR-19,
AR-24; D1, D3, N6). Paused for Ben: it is the access guard every admin passes through — built and tested on throwaway
databases only until he clicks.

fn_app_user_admin_guard, for every role:
- `is_platform_admin` false → true (or an admin reactivated) only when a grant for that user was approved IN THIS
  TRANSACTION (approved_xact = pg_current_xact_id(), D1): a REQUEST a second admin approved, or the owner's LEGACY.
- an account is born an admin only on an empty table (first_run_setup) or by the owner while fewer than two people
  have ever been granted or are live admins (AR-16, N6); never born inactive (D3).
- `created_by` never changes, and an account the app creates names a live platform admin as its creator (AR-24).
trg_app_user_bootstrap_grant writes the BOOTSTRAP record of a born admin, with the operator and the asking admin the
owner's command line sets (vb.operator, vb.grant_actor_id) — the asking admin required once a live admin exists (P1).
Removing admin rights is not guarded (AR-17).

Downgrade: drops both triggers and functions — no data.

Revision ID: 0078
Revises: 0077
"""
from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

PATH = "pg_catalog, public, pg_temp"
LIVE = "EXISTS (SELECT 1 FROM public.app_user c WHERE c.app_user_id = {col} AND c.is_active AND c.is_platform_admin)"

GUARD = f"""
    CREATE FUNCTION public.fn_app_user_admin_guard() RETURNS trigger
    LANGUAGE plpgsql SET search_path = {PATH} AS $$
    BEGIN
      IF TG_OP = 'INSERT' THEN
        -- AR-24: an account made in the app names the live admin who made it; the empty table is first_run_setup,
        -- the owner is the command line (recorded on the BOOTSTRAP row instead)
        IF session_user <> 'vb_owner' AND EXISTS (SELECT 1 FROM public.app_user)
           AND NOT {LIVE.format(col='NEW.created_by')} THEN
          RAISE EXCEPTION 'an account is created by a live platform admin, named as its creator (AR-24)'
            USING ERRCODE = 'restrict_violation';
        END IF;
        IF NEW.is_platform_admin THEN
          IF NOT NEW.is_active THEN
            RAISE EXCEPTION 'an admin is born active (D3)' USING ERRCODE = 'restrict_violation';
          END IF;
          PERFORM pg_advisory_xact_lock(hashtext('vb.platform_admin_bootstrap'));
          IF session_user = 'vb_owner' THEN
            IF GREATEST((SELECT count(DISTINCT g.target_user_id) FROM public.platform_admin_grant g
                          WHERE g.approved_at IS NOT NULL),
                        (SELECT count(*) FROM public.app_user u WHERE u.is_active AND u.is_platform_admin)) >= 2 THEN
              RAISE EXCEPTION 'two admins have already been granted: every further admin comes through a request '
                'or a recorded IS grant (AR-16)' USING ERRCODE = 'restrict_violation';
            END IF;
          ELSIF EXISTS (SELECT 1 FROM public.app_user) THEN
            RAISE EXCEPTION 'a new user is born an admin only on an empty database, or by the owner (AR-16)'
              USING ERRCODE = 'restrict_violation';
          END IF;
        END IF;
        RETURN NEW;
      END IF;
      IF NEW.created_by IS DISTINCT FROM OLD.created_by THEN
        RAISE EXCEPTION 'an account''s creator never changes (AR-24)' USING ERRCODE = 'restrict_violation';
      END IF;
      IF NEW.is_platform_admin AND (NOT OLD.is_platform_admin OR (NEW.is_active AND NOT OLD.is_active)) THEN
        IF NOT EXISTS (SELECT 1 FROM public.platform_admin_grant g
                        WHERE g.target_user_id = NEW.app_user_id
                          AND g.approved_xact = pg_current_xact_id()
                          AND (g.grant_origin = 'REQUEST'
                               OR (g.grant_origin = 'LEGACY' AND session_user = 'vb_owner'))) THEN
          RAISE EXCEPTION 'admin rights come only from a grant approved in this transaction (AR-13)'
            USING ERRCODE = 'restrict_violation';
        END IF;
      END IF;
      RETURN NEW;
    END $$
"""

BOOTSTRAP = f"""
    CREATE FUNCTION public.fn_app_user_bootstrap_grant() RETURNS trigger
    LANGUAGE plpgsql SET search_path = {PATH} AS $$
    DECLARE operator text; asker bigint;
    BEGIN
      IF session_user = 'vb_owner' THEN                 -- seeds.create_admin: who ran it, and who asked (P1)
        operator := NULLIF(btrim(current_setting('vb.operator', true)), '');
        asker := NULLIF(current_setting('vb.grant_actor_id', true), '')::bigint;
        IF operator IS NULL THEN
          RAISE EXCEPTION 'the owner''s command line names its operator (AR-16)' USING ERRCODE = 'restrict_violation';
        END IF;
        IF EXISTS (SELECT 1 FROM public.app_user u WHERE u.is_active AND u.is_platform_admin
                    AND u.app_user_id <> NEW.app_user_id)
           AND (asker IS NULL OR NOT {LIVE.format(col='asker')} OR asker = NEW.app_user_id) THEN
          RAISE EXCEPTION 'while a live admin exists, the command line names the admin who asked (AR-16, P1)'
            USING ERRCODE = 'restrict_violation';
        END IF;
      END IF;
      INSERT INTO public.platform_admin_grant (grant_origin, target_user_id, reason, operator_name, requested_by_user_id)
      VALUES ('BOOTSTRAP', NEW.app_user_id,
              CASE WHEN operator IS NULL THEN 'first admin, created at first-run setup'
                   ELSE 'created by the owner''s command line (AR-16)' END,
              operator, asker);
      RETURN NULL;
    END $$
"""


def upgrade() -> None:
    op.execute(GUARD)
    op.execute("CREATE TRIGGER trg_app_user_admin_guard BEFORE INSERT OR UPDATE OF is_platform_admin, is_active, "
               "created_by ON app_user FOR EACH ROW EXECUTE FUNCTION fn_app_user_admin_guard()")
    op.execute(BOOTSTRAP)
    op.execute("CREATE TRIGGER trg_app_user_bootstrap_grant AFTER INSERT ON app_user FOR EACH ROW "
               "WHEN (NEW.is_platform_admin) EXECUTE FUNCTION fn_app_user_bootstrap_grant()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_app_user_bootstrap_grant ON app_user")
    op.execute("DROP TRIGGER IF EXISTS trg_app_user_admin_guard ON app_user")
    op.execute("DROP FUNCTION IF EXISTS fn_app_user_bootstrap_grant()")
    op.execute("DROP FUNCTION IF EXISTS fn_app_user_admin_guard()")
