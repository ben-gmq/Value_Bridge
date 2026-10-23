"""project_purge: one request to take one project out of VB, or to delete its archive (slice16 schema §3.2 as revised by
§12.5; spec §15a, §18 S7, §19 U1/U6, §20; Q-72, Q-73, Q-85, AR-1, AR-5, AR-9).

Kinds (a CHECK list — the script and the triggers branch on it): ARCHIVE writes the verified project file, then removes
the project and keeps its keys; DELETE removes it under a contract (Q15) and destroys its keys; DELETE_ARCHIVE destroys
an archived project's keys and files. No FK to project — the record outlives it. State is derived from the dates.
Added at build (spec §19): destroy_started_at (U6, the guarded step before a DELETE_ARCHIVE touches the vault) and
archive_checked_at / archive_check_error (U1, the weekly check of a held project file).

trg_project_purge_guard, for every role: INSERT needs two live platform admins and, for ARCHIVE / DELETE, the project;
a DELETE_ARCHIVE names an executed ARCHIVE of the same project and copies its client and code. Approval: once, by a
second live platform admin, approved_at := now(). Cancel: once, while not executed. The project-file columns,
repurge_of_purge_id and destroy_started_at: once, by vb_owner only. Execution re-checks four eyes, the 24 h, two live
admins and, by kind, that the project is gone / the keys are destroyed. A cancelled or executed row is then fixed.
DELETE refused outright. vb_app: SELECT, INSERT, and UPDATE only on the approve / cancel / weekly-check columns —
the running app can never mark a purge executed.

Downgrade: refuses if any row exists.

Revision ID: 0072
Revises: 0071
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import drop_updated_at_trigger, updated_at_trigger

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None

APP_UPDATABLE = ("approved_at", "approved_by_user_id", "cancelled_at", "cancelled_by_user_id", "archive_checked_at",
                 "archive_check_error", "updated_by", "row_version")
FIXED = ("project_purge_id", "purge_kind", "project_id", "client_id", "project_code", "reason", "archive_purge_id",
         "requested_at", "requested_by_user_id")
ARCHIVE_FILE = ("archive_object_name", "archive_sha256", "archive_byte_size", "archive_key_ref")
# Every column a request's life changes; a cancelled request changes none of them again.
STATE = ("repurge_of_purge_id", *ARCHIVE_FILE, "archive_checked_at", "archive_check_error", "approved_at",
         "approved_by_user_id", "cancelled_at", "cancelled_by_user_id", "destroy_started_at", "executed_at",
         "executed_by_user_id", "backups_age_out_on", "files_deleted_at", "files_deleted_count")
TWO_ADMINS = "(SELECT count(*) FROM app_user WHERE is_active AND is_platform_admin) >= 2"
# AR-13: the audit events that make someone a platform admin (services/user_admin, auth_service, seeds.create_admin)
GRANT_EVENTS = ("PLATFORM_ADMIN_GRANTED", "FIRST_ADMIN_CREATED", "ADMIN_CREATED_BY_CLI")


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _changed(cols) -> str:
    return "(" + " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in cols) + ")"


def _live_admin(col: str) -> str:
    return f"EXISTS (SELECT 1 FROM app_user u WHERE u.app_user_id = {col} AND u.is_active AND u.is_platform_admin)"


def _user(col: str) -> sa.Column:
    return sa.Column(col, sa.BigInteger, sa.ForeignKey("app_user.app_user_id"))


def upgrade() -> None:
    op.create_table(
        "project_purge",
        sa.Column("project_purge_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("purge_kind", sa.String(15), nullable=False),
        sa.Column("project_id", sa.BigInteger, nullable=False),
        sa.Column("client_id", sa.BigInteger, sa.ForeignKey("client.client_id"), nullable=False),
        sa.Column("project_code", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("archive_purge_id", sa.BigInteger),
        sa.Column("archive_purge_kind", sa.String(15),
                  sa.Computed("CASE WHEN archive_purge_id IS NOT NULL THEN 'ARCHIVE' END", persisted=True)),
        sa.Column("repurge_of_purge_id", sa.BigInteger),
        sa.Column("archive_object_name", sa.String(400)),
        sa.Column("archive_sha256", sa.CHAR(64)),
        sa.Column("archive_byte_size", sa.BigInteger),
        sa.Column("archive_key_ref", sa.String(400)),
        sa.Column("archive_checked_at", sa.DateTime(timezone=True)),
        sa.Column("archive_check_error", sa.String(2000)),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("requested_by_user_id", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)), _user("approved_by_user_id"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)), _user("cancelled_by_user_id"),
        sa.Column("destroy_started_at", sa.DateTime(timezone=True)),
        sa.Column("executed_at", sa.DateTime(timezone=True)), _user("executed_by_user_id"),
        sa.Column("backups_age_out_on", sa.Date),
        sa.Column("files_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("files_deleted_count", sa.Integer),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        _user("updated_by"),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint("purge_kind IN ('ARCHIVE', 'DELETE', 'DELETE_ARCHIVE')", name="ck_pp_kind"),
        sa.CheckConstraint("btrim(reason) <> ''", name="ck_pp_reason"),
        sa.CheckConstraint("num_nonnulls(approved_at, approved_by_user_id) IN (0, 2)", name="ck_pp_approved"),
        sa.CheckConstraint("approved_by_user_id <> requested_by_user_id", name="ck_pp_four_eyes"),
        sa.CheckConstraint("num_nonnulls(cancelled_at, cancelled_by_user_id) IN (0, 2)", name="ck_pp_cancelled"),
        sa.CheckConstraint("num_nonnulls(executed_at, executed_by_user_id) IN (0, 2)", name="ck_pp_executed"),
        sa.CheckConstraint("num_nonnulls(cancelled_at, executed_at) <= 1", name="ck_pp_one_end"),
        sa.CheckConstraint("executed_at IS NULL OR approved_at IS NOT NULL", name="ck_pp_exec_approved"),
        sa.CheckConstraint("(purge_kind = 'DELETE_ARCHIVE') = (archive_purge_id IS NOT NULL)", name="ck_pp_archive_ref"),
        sa.CheckConstraint("purge_kind <> 'DELETE_ARCHIVE' OR repurge_of_purge_id IS NULL", name="ck_pp_repurge_kind"),
        sa.CheckConstraint(f"num_nonnulls({', '.join(ARCHIVE_FILE)}) IN (0, 4)", name="ck_pp_archive_set"),
        sa.CheckConstraint("purge_kind = 'ARCHIVE' OR archive_object_name IS NULL", name="ck_pp_archive_kind"),
        sa.CheckConstraint("purge_kind <> 'ARCHIVE' OR executed_at IS NULL OR archive_object_name IS NOT NULL",
                           name="ck_pp_archive_exec"),
        sa.CheckConstraint("archive_sha256 ~ '^[0-9a-f]{64}$'", name="ck_pp_archive_sha256"),
        sa.CheckConstraint("archive_byte_size > 0", name="ck_pp_archive_size"),
        sa.CheckConstraint("archive_checked_at IS NULL OR (purge_kind = 'ARCHIVE' AND executed_at IS NOT NULL)",
                           name="ck_pp_check_kind"),
        sa.CheckConstraint("archive_check_error IS NULL OR archive_checked_at IS NOT NULL", name="ck_pp_check_pair"),
        sa.CheckConstraint("destroy_started_at IS NULL OR (purge_kind = 'DELETE_ARCHIVE' AND approved_at IS NOT NULL)",
                           name="ck_pp_destroy_kind"),
        sa.CheckConstraint("num_nonnulls(files_deleted_at, files_deleted_count) IN (0, 2) AND (files_deleted_at IS NULL "
                           "OR (purge_kind = 'DELETE_ARCHIVE' AND executed_at IS NOT NULL))", name="ck_pp_files_deleted"),
        sa.CheckConstraint("files_deleted_count >= 0", name="ck_pp_files_count"),
        sa.CheckConstraint("(executed_at IS NOT NULL AND purge_kind <> 'DELETE_ARCHIVE') = (backups_age_out_on IS NOT NULL)",
                           name="ck_pp_backups"),
        sa.UniqueConstraint("archive_object_name", name="uq_pp_archive_object"),
        sa.UniqueConstraint("project_purge_id", "project_id", "purge_kind", name="uq_pp_id_project_kind"),
    )
    op.create_foreign_key("fk_pp_archive", "project_purge", "project_purge",
                          ["archive_purge_id", "project_id", "archive_purge_kind"],
                          ["project_purge_id", "project_id", "purge_kind"])
    op.create_index("uq_pp_open", "project_purge", ["project_id"], unique=True,
                    postgresql_where=sa.text("executed_at IS NULL AND cancelled_at IS NULL"))
    op.create_index("uq_pp_removed", "project_purge", ["project_id"], unique=True,
                    postgresql_where=sa.text("executed_at IS NOT NULL AND purge_kind IN ('ARCHIVE', 'DELETE')"))
    op.create_index("uq_pp_archive_deleted", "project_purge", ["archive_purge_id"], unique=True,
                    postgresql_where=sa.text("executed_at IS NOT NULL"))
    updated_at_trigger("project_purge")
    owner_only = ("repurge_of_purge_id", "destroy_started_at", "executed_at", "executed_by_user_id",
                  "backups_age_out_on", "files_deleted_at", "files_deleted_count")
    op.execute(f"""
        CREATE FUNCTION fn_project_purge_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE src project_purge; grant_by bigint; grant_at timestamptz;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'DELETE on project_purge is not allowed: the record is kept forever'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF TG_OP = 'INSERT' THEN
            IF NOT {TWO_ADMINS} THEN
              RAISE EXCEPTION 'a purge needs at least two live platform admins (AR-5)' USING ERRCODE = 'restrict_violation';
            END IF;
            IF NOT {_live_admin('NEW.requested_by_user_id')} THEN                     -- sara L3
              RAISE EXCEPTION 'only a live platform admin requests a purge' USING ERRCODE = 'restrict_violation';
            END IF;
            IF num_nonnulls(NEW.approved_at, NEW.cancelled_at, NEW.executed_at, NEW.destroy_started_at,
                            NEW.archive_object_name, NEW.archive_checked_at, NEW.repurge_of_purge_id,
                            NEW.files_deleted_at, NEW.backups_age_out_on) > 0 THEN
              RAISE EXCEPTION 'a purge request is born open: nothing approved, cancelled, executed or recorded'
                USING ERRCODE = 'restrict_violation';
            END IF;
            IF NEW.purge_kind = 'DELETE_ARCHIVE' THEN
              SELECT * INTO src FROM project_purge WHERE project_purge_id = NEW.archive_purge_id;
              IF src.executed_at IS NULL OR src.purge_kind <> 'ARCHIVE' THEN
                RAISE EXCEPTION 'an archive can be deleted only after its ARCHIVE purge ran'
                  USING ERRCODE = 'restrict_violation';
              END IF;
              NEW.client_id := src.client_id;
              NEW.project_code := src.project_code;
            ELSIF NOT EXISTS (SELECT 1 FROM project p WHERE p.project_id = NEW.project_id) THEN
              RAISE EXCEPTION 'no such project to remove' USING ERRCODE = 'restrict_violation';
            END IF;
            NEW.requested_at := statement_timestamp();
            RETURN NEW;
          END IF;
          IF {_changed(FIXED)} THEN
            RAISE EXCEPTION 'a purge request''s kind, project, client, code, reason and requester never change'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF OLD.cancelled_at IS NOT NULL AND {_changed(STATE)} THEN
            RAISE EXCEPTION 'a cancelled purge request never changes' USING ERRCODE = 'restrict_violation';
          END IF;
          IF {_changed(owner_only + ARCHIVE_FILE)} AND session_user <> 'vb_owner' THEN
            RAISE EXCEPTION 'only the operator job records a project file, a re-purge, key destruction or execution'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF OLD.approved_at IS NULL AND NEW.approved_at IS NOT NULL THEN
            IF NEW.approved_by_user_id = OLD.requested_by_user_id THEN
              RAISE EXCEPTION 'four eyes: the requester cannot approve their own request'
                USING ERRCODE = 'restrict_violation';
            END IF;
            IF OLD.executed_at IS NOT NULL OR OLD.cancelled_at IS NOT NULL
               OR NOT {_live_admin('NEW.approved_by_user_id')} OR NOT {_live_admin('OLD.requested_by_user_id')}
               OR NOT {TWO_ADMINS} THEN
              RAISE EXCEPTION 'an open request is approved once, by a second live platform admin, while two exist'
                USING ERRCODE = 'restrict_violation';
            END IF;
            -- AR-13 (Q-93 a, U9): the approver's latest platform-admin grant must be at least 30 days old and not made
            -- by the requester; no grant on record counts as too recent. The setup and CLI admins' creation is their grant.
            SELECT e.app_user_id, e.occurred_at INTO grant_by, grant_at FROM audit_event e
             WHERE e.target_table = 'app_user' AND e.target_id = NEW.approved_by_user_id
               AND e.event_type IN ({_in(GRANT_EVENTS)})
             ORDER BY e.occurred_at DESC, e.audit_event_id DESC LIMIT 1;
            IF grant_at IS NULL OR grant_at > statement_timestamp() - interval '30 days'
               OR grant_by IS NOT DISTINCT FROM OLD.requested_by_user_id THEN
              RAISE EXCEPTION 'the approver''s admin rights must be at least 30 days old and not granted by the '
                'requester (AR-13)' USING ERRCODE = 'restrict_violation';
            END IF;
            NEW.approved_at := statement_timestamp();
          ELSIF {_changed(("approved_at", "approved_by_user_id"))} THEN
            RAISE EXCEPTION 'an approval never changes' USING ERRCODE = 'restrict_violation';
          END IF;
          IF OLD.cancelled_at IS NULL AND NEW.cancelled_at IS NOT NULL THEN
            IF OLD.executed_at IS NOT NULL OR OLD.destroy_started_at IS NOT NULL OR NEW.destroy_started_at IS NOT NULL THEN
              RAISE EXCEPTION 'an executed request, or one whose keys are being destroyed, cannot be cancelled'
                USING ERRCODE = 'restrict_violation';
            END IF;
            IF NOT {_live_admin('NEW.cancelled_by_user_id')} THEN                     -- sara L2
              RAISE EXCEPTION 'only a live platform admin cancels a purge' USING ERRCODE = 'restrict_violation';
            END IF;
            NEW.cancelled_at := statement_timestamp();
          ELSIF {_changed(("cancelled_at", "cancelled_by_user_id"))} THEN
            RAISE EXCEPTION 'a cancellation never changes' USING ERRCODE = 'restrict_violation';
          END IF;
          IF {_changed(ARCHIVE_FILE)} AND (OLD.archive_object_name IS NOT NULL OR OLD.purge_kind <> 'ARCHIVE'
               OR OLD.approved_at IS NULL OR OLD.executed_at IS NOT NULL OR OLD.cancelled_at IS NOT NULL) THEN
            RAISE EXCEPTION 'the project file is recorded once, on an open approved ARCHIVE'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF {_changed(("repurge_of_purge_id",))} AND (OLD.repurge_of_purge_id IS NOT NULL
               OR OLD.executed_at IS NOT NULL OR OLD.cancelled_at IS NOT NULL OR OLD.approved_at IS NOT NULL
               OR NEW.repurge_of_purge_id = OLD.project_purge_id
               OR EXISTS (SELECT 1 FROM project_purge o WHERE o.project_purge_id = NEW.repurge_of_purge_id
                           AND o.project_id <> OLD.project_id)) THEN
            RAISE EXCEPTION 'a re-purge is recorded once, before approval, naming a removal of this project (sara M1)'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF {_changed(("destroy_started_at",))} THEN
            IF OLD.destroy_started_at IS NOT NULL OR OLD.purge_kind <> 'DELETE_ARCHIVE' OR OLD.executed_at IS NOT NULL
               OR OLD.cancelled_at IS NOT NULL OR OLD.approved_at IS NULL
               OR OLD.approved_at > statement_timestamp() - interval '24 hours'
               OR NOT {_live_admin('OLD.approved_by_user_id')} OR NOT {_live_admin('OLD.requested_by_user_id')}
               OR NOT {TWO_ADMINS} THEN                                              -- sara H1: before the vault
              RAISE EXCEPTION 'key destruction starts once, on an approved DELETE_ARCHIVE at least 24 hours old whose '
                'requester and approver are still live platform admins, while two exist (U6, S7)'
                USING ERRCODE = 'restrict_violation';
            END IF;
            NEW.destroy_started_at := statement_timestamp();
          END IF;
          IF OLD.executed_at IS NULL AND NEW.executed_at IS NOT NULL THEN
            IF OLD.cancelled_at IS NOT NULL OR OLD.approved_at IS NULL
               OR (OLD.approved_at > statement_timestamp() - interval '24 hours' AND OLD.repurge_of_purge_id IS NULL)
               OR NOT {_live_admin('OLD.approved_by_user_id')} OR NOT {_live_admin('OLD.requested_by_user_id')}
               OR NOT {TWO_ADMINS} THEN
              RAISE EXCEPTION 'execution needs an approval at least 24 hours old by a second admin, both still live '
                'platform admins, and two live platform admins (Q-72, S7)' USING ERRCODE = 'restrict_violation';
            END IF;
            IF OLD.purge_kind IN ('ARCHIVE', 'DELETE') THEN
              IF EXISTS (SELECT 1 FROM project p WHERE p.project_id = OLD.project_id) THEN
                RAISE EXCEPTION 'the project still exists: a removal is executed only once it is gone'
                  USING ERRCODE = 'restrict_violation';
              END IF;
              IF NOT EXISTS (SELECT 1 FROM project_purge_key k WHERE k.project_purge_id = OLD.project_purge_id) THEN
                RAISE EXCEPTION 'a removal records the project''s key names before it is executed (sara M2)'
                  USING ERRCODE = 'restrict_violation';
              END IF;
              NEW.backups_age_out_on := ((statement_timestamp() AT TIME ZONE 'Asia/Bangkok')::date + interval '13 months')::date;
            ELSE
              IF OLD.destroy_started_at IS NULL OR EXISTS (SELECT 1 FROM project_purge_key k
                  WHERE k.project_purge_id = OLD.archive_purge_id AND k.destroyed_at IS NULL) THEN
                RAISE EXCEPTION 'a DELETE_ARCHIVE is executed only once every key of its archive is destroyed'
                  USING ERRCODE = 'restrict_violation';
              END IF;
            END IF;
            NEW.executed_at := statement_timestamp();
          ELSIF OLD.executed_at IS NOT NULL AND {_changed(("executed_at", "executed_by_user_id", "backups_age_out_on"))} THEN
            RAISE EXCEPTION 'an execution never changes' USING ERRCODE = 'restrict_violation';
          ELSIF OLD.executed_at IS NULL AND {_changed(("executed_by_user_id", "backups_age_out_on"))} THEN
            RAISE EXCEPTION 'execution columns are set with executed_at' USING ERRCODE = 'restrict_violation';
          END IF;
          IF {_changed(("files_deleted_at", "files_deleted_count"))} THEN
            IF OLD.files_deleted_at IS NOT NULL OR OLD.executed_at IS NULL THEN
              RAISE EXCEPTION 'deleted files are recorded once, after the keys are destroyed'
                USING ERRCODE = 'restrict_violation';
            END IF;
            NEW.files_deleted_at := statement_timestamp();
          END IF;
          IF NEW.archive_checked_at IS DISTINCT FROM OLD.archive_checked_at THEN       -- sara L4: the check's own clock
            NEW.archive_checked_at := statement_timestamp();
          END IF;
          RETURN NEW;
        END $$;
    """)
    op.execute("CREATE TRIGGER trg_project_purge_guard BEFORE INSERT OR UPDATE OR DELETE ON project_purge "
               "FOR EACH ROW EXECUTE FUNCTION fn_project_purge_guard()")
    op.execute("REVOKE ALL ON project_purge FROM vb_app")
    op.execute("GRANT SELECT, INSERT ON project_purge TO vb_app")
    op.execute(f"GRANT UPDATE ({', '.join(APP_UPDATABLE)}) ON project_purge TO vb_app")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM project_purge) THEN "
               "RAISE EXCEPTION 'purge requests exist: downgrade refused'; END IF; END $$")
    op.execute("DROP TRIGGER IF EXISTS trg_project_purge_guard ON project_purge")
    op.execute("DROP FUNCTION IF EXISTS fn_project_purge_guard()")
    drop_updated_at_trigger("project_purge")
    op.drop_table("project_purge")
