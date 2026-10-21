"""The scoped purge bypass (slice16 schema §4, §12.4, §12.8; spec §15a, §18; AR-4, Q-75). Paused for Ben: this is the
one exception to law 2 — approved by Ben 2026-10-22 ("yeah, purge migration").

One function owns the rule. fn_purge_allows(project) is true only when all of these hold: the session and the current
role are vb_owner (so a SECURITY DEFINER function can never lend it to an app session); this transaction's
vb.purge_project_id names that one project; an open ARCHIVE or DELETE request for it was approved by a second platform
admin at least 24 hours ago (or is a recorded re-purge, Q-85); and an ARCHIVE has its project file recorded first.

1. fn_purge_allows (§12.4).
2. fn_reject_modification_purgeable: UPDATE always raises; DELETE of a frozen shadow row passes only when
   fn_purge_allows says so for the row's baseline's project (read from the header's NOT NULL project_id).
3. Every trigger on a baseline_* shadow that calls fn_reject_modification is re-pointed to it — read from the catalog,
   not counted by hand. fn_reject_modification itself is untouched: audit_event (until 0075) and anything else keep it.
4. fn_baseline_header_guard: FROZEN_0054 verbatim; only the DELETE branch asks fn_purge_allows.
5. fn_baseline_archive_guard: 0068's body; only the DELETE branch asks fn_purge_allows.
6. fn_project_purge_key_guard: 0073's inline copy of the rule is replaced by the function (0073's note, sara M3).
New shadows use vb_ops.immutable_guards_v2 from here on.

Downgrade: refuses once any purge has been executed (it must not re-arm guards under a half-run purge); else restores
the old triggers and functions.

Revision ID: 0074
Revises: 0073
"""
from alembic import op
from sqlalchemy import text

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None

# The header's frozen list as 0054 left it (no later migration changed it), restated so this revision replays.
FROZEN_0054 = ("baseline_id", "project_id", "major_no", "minor_no", "hash_spec_version", "data_model_depth",
               "note", "prior_baseline_id", "frozen_at", "frozen_by_user_id", "content_digest",
               "dfd_rule_to_be", "dfd_rule_as_is", "fte_working_days", "fte_hours_per_day")
# sara L4: pg_temp last, so a session's temporary table can never shadow a table these functions read.
PATH_0074 = "pg_catalog, public, pg_temp"
PATH_OLD = "pg_catalog, public"                     # 0068's and 0073's, restored by the downgrade
APPROVAL_COLUMNS = ("client_approver_name", "client_approved_on", "approval_note", "approval_reference",
                    "approved_at", "approved_by_user_id")

PURGE_ALLOWS = """
    CREATE FUNCTION public.fn_purge_allows(p_project_id bigint) RETURNS boolean
    LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
      SELECT session_user = 'vb_owner' AND current_user = 'vb_owner'
         AND p_project_id IS NOT NULL
         -- never NULL: an unset setting reads as NULL, and a NULL answer negated in a guard would let a row through
         AND p_project_id::text IS NOT DISTINCT FROM current_setting('vb.purge_project_id', true)
         AND EXISTS (SELECT 1 FROM public.project_purge pp WHERE pp.project_id = p_project_id
                      AND pp.purge_kind IN ('ARCHIVE', 'DELETE')
                      AND pp.executed_at IS NULL AND pp.cancelled_at IS NULL
                      AND pp.approved_at IS NOT NULL
                      AND (pp.approved_at <= now() - interval '24 hours' OR pp.repurge_of_purge_id IS NOT NULL)
                      AND (pp.purge_kind = 'DELETE' OR pp.archive_object_name IS NOT NULL)) $$
"""

REJECT_PURGEABLE = """
    CREATE FUNCTION public.fn_reject_modification_purgeable() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
    DECLARE pid bigint;
    BEGIN
      IF TG_OP = 'DELETE' THEN
        SELECT b.project_id INTO pid FROM public.baseline b WHERE b.baseline_id = OLD.baseline_id;
        IF public.fn_purge_allows(pid) THEN
          RETURN OLD;
        END IF;
      END IF;
      RAISE EXCEPTION '% on % is not allowed: the row is immutable', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
    END $$
"""

SHADOW_TRIGGERS = """
    SELECT c.relname, t.tgname FROM pg_trigger t
      JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_proc p ON p.oid = t.tgfoid
     WHERE NOT t.tgisinternal AND c.relnamespace = 'public'::regnamespace
       AND c.relname LIKE 'baseline\\_%' AND p.proname = :fn
     ORDER BY 1
"""


def _header_guard_sql(delete_branch: str, pinned: bool) -> str:
    frozen = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in FROZEN_0054)
    approval = ("OLD.client_approver_name IS NOT NULL AND ("
                + " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in APPROVAL_COLUMNS) + ")")
    path = f" SET search_path = {PATH_0074}" if pinned else ""
    return f"""
        CREATE OR REPLACE FUNCTION fn_baseline_header_guard() RETURNS trigger LANGUAGE plpgsql{path} AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            {delete_branch}
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


# 0068's guard on baseline_archive, restated; only the DELETE branch is a parameter.
ARCHIVE_KEYS = ("baseline_id", "archive_part", "file_seq", "project_id", "format_version", "created_at", "created_by")
ARCHIVE_WRITTEN = ("object_name", "file_sha256", "byte_size", "key_ref", "written_at", "attempt_count",
                   "last_attempt_at", "last_error")


def _changed(cols) -> str:
    return "(" + " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in cols) + ")"


def _archive_guard_sql(delete_branch: str, path: str = PATH_0074) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION fn_baseline_archive_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = {path} AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            {delete_branch}
            RAISE EXCEPTION 'DELETE on baseline_archive is not allowed: the record goes only with its baseline'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF TG_OP = 'INSERT' THEN
            IF NEW.archive_part = 'SIGNOFF' AND NOT EXISTS (
                SELECT 1 FROM baseline b WHERE b.baseline_id = NEW.baseline_id
                   AND b.client_approver_name IS NOT NULL) THEN
              RAISE EXCEPTION 'a sign-off file is owed only once the client approval is recorded'
                USING ERRCODE = 'restrict_violation';
            END IF;
            IF NEW.file_seq > 1 AND NOT EXISTS (
                SELECT 1 FROM baseline_archive a WHERE a.baseline_id = NEW.baseline_id
                   AND a.archive_part = NEW.archive_part AND a.file_seq = NEW.file_seq - 1
                   AND a.written_at IS NOT NULL AND a.check_failed_at IS NOT NULL) THEN
              RAISE EXCEPTION 'a replacement file is owed only when the file before it was written and failed its check'
                USING ERRCODE = 'restrict_violation';
            END IF;
            -- sara M1: a row is born owed; only the writer fills it in, and the queue order is the database's
            IF NEW.written_at IS NOT NULL OR NEW.check_failed_at IS NOT NULL OR NEW.attempt_count <> 0
               OR NEW.last_error IS NOT NULL THEN
              RAISE EXCEPTION 'an archive file is recorded as owed; the writer fills it in'
                USING ERRCODE = 'restrict_violation';
            END IF;
            NEW.created_at := now();
            RETURN NEW;
          END IF;
          IF {_changed(ARCHIVE_KEYS)} THEN
            RAISE EXCEPTION 'a baseline_archive key, project, format or creation column cannot change'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF OLD.written_at IS NOT NULL THEN
            IF {_changed(ARCHIVE_WRITTEN)} THEN
              RAISE EXCEPTION 'a written archive file record cannot change' USING ERRCODE = 'restrict_violation';
            END IF;
            IF OLD.check_failed_at IS NOT NULL AND {_changed(("check_failed_at", "last_check_error"))} THEN
              RAISE EXCEPTION 'a recorded check failure cannot change' USING ERRCODE = 'restrict_violation';
            END IF;
          END IF;
          RETURN NEW;
        END $$;
    """


# 0073's guard on project_purge_key, restated; only the INSERT condition is a parameter.
KEY_INSERT_0073 = """current_user <> 'vb_owner' OR parent.purge_kind NOT IN ('ARCHIVE', 'DELETE')
               OR parent.executed_at IS NOT NULL OR parent.cancelled_at IS NOT NULL OR parent.approved_at IS NULL
               OR (parent.approved_at > statement_timestamp() - interval '24 hours'
                   AND parent.repurge_of_purge_id IS NULL)
               OR (parent.purge_kind = 'ARCHIVE' AND parent.archive_object_name IS NULL)
               OR parent.project_id::text IS DISTINCT FROM current_setting('vb.purge_project_id', true)"""
# The parent must itself be the open request (uq_pp_open makes it the one fn_purge_allows found).
KEY_INSERT_0074 = """parent.purge_kind NOT IN ('ARCHIVE', 'DELETE')
               OR parent.executed_at IS NOT NULL OR parent.cancelled_at IS NOT NULL
               OR NOT public.fn_purge_allows(parent.project_id)"""


def _key_guard_sql(insert_refused: str, path: str = PATH_0074) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION fn_project_purge_key_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = {path} AS $$
        DECLARE parent project_purge; d project_purge;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'DELETE on project_purge_key is not allowed: the record is kept forever'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF session_user <> 'vb_owner' THEN
            RAISE EXCEPTION 'only the operator job records or destroys project keys' USING ERRCODE = 'restrict_violation';
          END IF;
          SELECT * INTO parent FROM project_purge WHERE project_purge_id = NEW.project_purge_id;
          IF TG_OP = 'INSERT' THEN
            IF {insert_refused} THEN
              RAISE EXCEPTION 'keys are recorded only inside the purge transaction of an open, approved ARCHIVE or DELETE'
                USING ERRCODE = 'restrict_violation';
            END IF;
            IF num_nonnulls(NEW.destroyed_at, NEW.was_present, NEW.destroyed_by_purge_id, NEW.proof_object_name) > 0 THEN
              RAISE EXCEPTION 'a key is recorded before it is destroyed' USING ERRCODE = 'restrict_violation';
            END IF;
            NEW.created_at := statement_timestamp();
            RETURN NEW;
          END IF;
          IF NEW.project_purge_id IS DISTINCT FROM OLD.project_purge_id OR NEW.key_name IS DISTINCT FROM OLD.key_name
             OR NEW.key_refs IS DISTINCT FROM OLD.key_refs OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'a recorded key never changes' USING ERRCODE = 'restrict_violation';
          END IF;
          IF OLD.destroyed_at IS NOT NULL THEN
            IF NEW.destroyed_at IS DISTINCT FROM OLD.destroyed_at OR NEW.was_present IS DISTINCT FROM OLD.was_present
               OR NEW.destroyed_by_purge_id IS DISTINCT FROM OLD.destroyed_by_purge_id
               OR NEW.proof_object_name IS DISTINCT FROM OLD.proof_object_name THEN
              RAISE EXCEPTION 'a key destruction never changes' USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.destroyed_at IS NOT NULL THEN
            SELECT * INTO d FROM project_purge WHERE project_purge_id = NEW.destroyed_by_purge_id;
            IF NOT ((d.project_purge_id = parent.project_purge_id AND parent.purge_kind = 'DELETE'
                     AND parent.executed_at IS NOT NULL)
                 OR (d.purge_kind = 'DELETE_ARCHIVE' AND d.archive_purge_id = parent.project_purge_id
                     AND d.executed_at IS NULL AND d.cancelled_at IS NULL AND d.destroy_started_at IS NOT NULL
                     AND d.approved_at <= statement_timestamp() - interval '24 hours')) THEN
              RAISE EXCEPTION 'a key is destroyed only by its executed DELETE, or by a started DELETE_ARCHIVE of its '
                'archive approved at least 24 hours ago' USING ERRCODE = 'restrict_violation';
            END IF;
            NEW.destroyed_at := statement_timestamp();
          END IF;
          RETURN NEW;
        END $$;
    """


ALLOWS = "IF public.fn_purge_allows(OLD.project_id) THEN RETURN OLD; END IF;"


def _repoint(old_fn: str, new_fn: str) -> list[str]:
    rows = op.get_bind().execute(text(SHADOW_TRIGGERS), {"fn": old_fn}).all()
    for table, trigger in rows:
        op.execute(f"DROP TRIGGER {trigger} ON {table}")
        op.execute(f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION {new_fn}()")
    return [t for t, _ in rows]


def upgrade() -> None:
    op.execute(PURGE_ALLOWS)
    op.execute(REJECT_PURGEABLE)
    tables = _repoint("fn_reject_modification", "fn_reject_modification_purgeable")
    # Every re-pointed shadow must carry baseline_id, or the purgeable function could not find its project.
    missing = op.get_bind().execute(text(
        "SELECT t FROM unnest(CAST(:t AS text[])) t WHERE NOT EXISTS (SELECT 1 FROM information_schema.columns c "
        "WHERE c.table_schema = 'public' AND c.table_name = t AND c.column_name = 'baseline_id')"),
        {"t": tables}).scalars().all()
    if missing or not tables:
        raise RuntimeError(f"0074: shadows without baseline_id, or none found: {missing}")
    op.execute(_header_guard_sql(ALLOWS, pinned=True))
    op.execute(_archive_guard_sql(ALLOWS))
    op.execute(_key_guard_sql(KEY_INSERT_0074))


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM project_purge WHERE executed_at IS NOT NULL) THEN "
               "RAISE EXCEPTION 'a purge has been executed: downgrade refused'; END IF; END $$")
    op.execute(_key_guard_sql(KEY_INSERT_0073, PATH_OLD))
    op.execute(_archive_guard_sql("", PATH_OLD))
    op.execute(_header_guard_sql("", pinned=False))
    _repoint("fn_reject_modification_purgeable", "fn_reject_modification")
    op.execute("DROP FUNCTION fn_reject_modification_purgeable()")
    op.execute("DROP FUNCTION fn_purge_allows(bigint)")
