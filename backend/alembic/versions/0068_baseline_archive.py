"""baseline_archive: one row per archive file owed or written for one part of one frozen baseline
(slice16_archive_purge_schema §3.1 as revised by §12.3; spec §3, Q-67, Q-68, Q-79, §18 S5).

The outbox that makes "every freeze writes a file" provable: the freeze owes the SCOPE file, the client approval
owes the SIGNOFF file, and the weekly check owes a replacement (file_seq n + 1) when file n fails. State is derived,
never coded (Q-67): owed = written_at IS NULL; failing = owed with last_error; check failed = check_failed_at set;
superseded = a higher file_seq of the same part exists. No soft delete (Q-68): the row goes only with its baseline.

trg_baseline_archive_guard, for every role, the owner included: the key, project_id, format_version and created_*
never change; the five file columns are set together once (ck_ba_written_set) and a written row then accepts only
check_failed_at / last_check_error, NULL to a value, once; a SIGNOFF row needs the header's approval; a replacement
needs its predecessor written and failed. DELETE is refused outright — migration 0074 gives it the purge branch.
vb_app: SELECT, INSERT and a column UPDATE grant (§6.6); no DELETE.

Backfill: one owed SCOPE row per existing baseline (created_by = the freezer) and one owed SIGNOFF row per baseline
with an approval (created_by = the approver), so scripts.write_archives covers the baselines frozen before this
slice (Q-77).

Downgrade: refuses once any file is written (the record of a written file would be lost).

Revision ID: 0068
Revises: 0067
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import drop_updated_at_trigger, updated_at_trigger

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None

WRITTEN = ("object_name", "file_sha256", "byte_size", "key_ref", "written_at")
APP_UPDATABLE = (*WRITTEN, "attempt_count", "last_attempt_at", "last_error", "check_failed_at", "last_check_error",
                 "updated_by", "row_version")
FIXED = ("baseline_id", "archive_part", "file_seq", "project_id", "format_version", "created_at", "created_by")
# What a written row may still change: the check result once, and the bookkeeping that comes with any update.
ON_WRITTEN = ("check_failed_at", "last_check_error", "updated_at", "updated_by", "row_version")


def _changed(cols) -> str:
    return "(" + " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in cols) + ")"


def upgrade() -> None:
    op.create_table(
        "baseline_archive",
        sa.Column("baseline_id", sa.BigInteger, primary_key=True),
        sa.Column("archive_part", sa.String(10), primary_key=True),
        sa.Column("file_seq", sa.SmallInteger, primary_key=True, server_default="1"),
        sa.Column("project_id", sa.BigInteger, nullable=False),
        sa.Column("format_version", sa.SmallInteger, nullable=False),
        sa.Column("object_name", sa.String(400)),
        sa.Column("file_sha256", sa.CHAR(64)),
        sa.Column("byte_size", sa.BigInteger),
        sa.Column("key_ref", sa.String(400)),
        sa.Column("written_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(2000)),
        sa.Column("check_failed_at", sa.DateTime(timezone=True)),
        sa.Column("last_check_error", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id")),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["baseline_id", "project_id"], ["baseline.baseline_id", "baseline.project_id"],
                                name="fk_ba_baseline"),
        sa.UniqueConstraint("object_name", name="uq_ba_object_name"),
        sa.CheckConstraint("archive_part IN ('SCOPE', 'SIGNOFF')", name="ck_ba_part"),
        sa.CheckConstraint("file_seq >= 1", name="ck_ba_file_seq"),
        sa.CheckConstraint("format_version >= 1", name="ck_ba_format_version"),
        sa.CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name="ck_ba_sha256"),
        sa.CheckConstraint("byte_size > 0", name="ck_ba_byte_size"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_ba_attempts"),
        sa.CheckConstraint(f"num_nonnulls({', '.join(WRITTEN)}) IN (0, 5)", name="ck_ba_written_set"),
        sa.CheckConstraint("num_nonnulls(check_failed_at, last_check_error) IN (0, 2)", name="ck_ba_check_pair"),
        sa.CheckConstraint("check_failed_at IS NULL OR written_at IS NOT NULL", name="ck_ba_check_on_written"),
    )
    op.create_index("uq_ba_owed", "baseline_archive", ["baseline_id", "archive_part"], unique=True,
                    postgresql_where=sa.text("written_at IS NULL"))
    op.create_index("ix_ba_owed", "baseline_archive", ["created_at"], postgresql_where=sa.text("written_at IS NULL"))
    op.create_index("ix_ba_project", "baseline_archive", ["project_id"])
    updated_at_trigger("baseline_archive")
    op.execute(f"""
        CREATE FUNCTION fn_baseline_archive_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
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
          IF {_changed(FIXED)} THEN
            RAISE EXCEPTION 'a baseline_archive key, project, format or creation column cannot change'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF OLD.written_at IS NOT NULL THEN
            IF {_changed(c for c in APP_UPDATABLE + ("updated_at",) if c not in ON_WRITTEN)} THEN
              RAISE EXCEPTION 'a written archive file record cannot change' USING ERRCODE = 'restrict_violation';
            END IF;
            IF OLD.check_failed_at IS NOT NULL AND {_changed(("check_failed_at", "last_check_error"))} THEN
              RAISE EXCEPTION 'a recorded check failure cannot change' USING ERRCODE = 'restrict_violation';
            END IF;
          END IF;
          RETURN NEW;
        END $$;
    """)
    op.execute("CREATE TRIGGER trg_baseline_archive_guard BEFORE INSERT OR UPDATE OR DELETE ON baseline_archive "
               "FOR EACH ROW EXECUTE FUNCTION fn_baseline_archive_guard()")
    # §6.6: the app reads, inserts owed rows and fills them in; it never deletes.
    op.execute("REVOKE ALL ON baseline_archive FROM vb_app")
    op.execute("GRANT SELECT, INSERT ON baseline_archive TO vb_app")
    op.execute(f"GRANT UPDATE ({', '.join(APP_UPDATABLE)}) ON baseline_archive TO vb_app")
    # Q-77: the baselines frozen before this slice owe their files too.
    op.execute("INSERT INTO baseline_archive (baseline_id, archive_part, file_seq, project_id, format_version, "
               "created_by) SELECT baseline_id, 'SCOPE', 1, project_id, 1, frozen_by_user_id FROM baseline")
    op.execute("INSERT INTO baseline_archive (baseline_id, archive_part, file_seq, project_id, format_version, "
               "created_by) SELECT baseline_id, 'SIGNOFF', 1, project_id, 1, approved_by_user_id FROM baseline "
               "WHERE client_approver_name IS NOT NULL")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM baseline_archive WHERE written_at IS NOT NULL) THEN "
               "RAISE EXCEPTION 'archive files are written: downgrade refused'; END IF; END $$")
    op.execute("DROP TRIGGER IF EXISTS trg_baseline_archive_guard ON baseline_archive")
    op.execute("DROP FUNCTION IF EXISTS fn_baseline_archive_guard()")
    drop_updated_at_trigger("baseline_archive")
    op.drop_table("baseline_archive")
