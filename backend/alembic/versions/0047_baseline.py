"""baseline: the header of one frozen version of one project's scope (slice8_schema §2; §4.6, A-36, Q8).

No soft delete and no created_* pair (A-36, [Q-6]). A straight line of versions held by the database
[Q-8]: one first baseline per project, each succeeded at most once, "no prior" exactly when v1.0. Frozen
columns are locked twice [Q-10]: vb_app may UPDATE only the status, the approval set, updated_by and
row_version (§6.6 column grant), and trg_baseline_header_guard rejects DELETE and any change to a frozen
column or to an approval once recorded — for every role, the owner included. content_digest (DR8-S1) is
frozen with the header; an approval may be recorded on a FROZEN or a SUPERSEDED baseline (DR8-P1).

Revision ID: 0047
Revises: 0046
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

FROZEN_COLUMNS = ("baseline_id", "project_id", "major_no", "minor_no", "hash_spec_version", "data_model_depth",
                  "note", "prior_baseline_id", "frozen_at", "frozen_by_user_id", "content_digest")
APPROVAL_COLUMNS = ("client_approver_name", "client_approved_on", "approval_note", "approval_reference",
                    "approved_at", "approved_by_user_id")
APP_UPDATABLE = ("status_code_id", *APPROVAL_COLUMNS, "updated_by", "row_version")
REFUSE_IF_BASELINES = ("DO $$ BEGIN IF EXISTS (SELECT 1 FROM baseline) THEN "
                       "RAISE EXCEPTION 'baselines exist: downgrade refused'; END IF; END $$")


def upgrade() -> None:
    op.create_table(
        "baseline",
        sa.Column("baseline_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("major_no", sa.Integer, nullable=False),
        sa.Column("minor_no", sa.Integer, nullable=False),
        sa.Column("version_label", sa.String(24), sa.Computed("'v' || major_no || '.' || minor_no", persisted=True)),
        sa.Column("status_code_id", sa.BigInteger, nullable=False),
        category_column("status_category", "BASELINE_STATUS"),
        sa.Column("hash_spec_version", sa.SmallInteger, nullable=False),
        sa.Column("data_model_depth", sa.String(10), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("prior_baseline_id", sa.BigInteger),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("frozen_by_user_id", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"), nullable=False),
        # DR8-S1: sha256 over every frozen (entity, source_id, content_hash), written with the header; reads
        # recompute it, so a row added to an old baseline cannot pass unnoticed.
        sa.Column("content_digest", sa.CHAR(64), nullable=False),
        sa.Column("client_approver_name", sa.String(200)),
        sa.Column("client_approved_on", sa.Date),
        sa.Column("approval_note", sa.Text),
        sa.Column("approval_reference", sa.String(200)),   # DR8-Q3: the signed document's id or file hash
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by_user_id", sa.BigInteger, sa.ForeignKey("app_user.app_user_id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id")),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("baseline_id", "project_id", name="uq_baseline_project"),
        sa.UniqueConstraint("project_id", "major_no", "minor_no", name="uq_baseline_version"),
        sa.UniqueConstraint("project_id", "version_label", name="uq_baseline_label"),
        sa.UniqueConstraint("prior_baseline_id", name="uq_baseline_prior"),
        sa.CheckConstraint("major_no >= 1", name="ck_baseline_major"),
        sa.CheckConstraint("minor_no >= 0", name="ck_baseline_minor"),
        sa.CheckConstraint("hash_spec_version >= 1", name="ck_baseline_hash_spec"),
        sa.CheckConstraint("data_model_depth IN ('KEYS_ONLY', 'FULL')", name="ck_baseline_depth"),
        sa.CheckConstraint("note IS NULL OR btrim(note) <> ''", name="ck_baseline_note_not_blank"),
        sa.CheckConstraint("approval_note IS NULL OR btrim(approval_note) <> ''",
                           name="ck_baseline_approval_note_not_blank"),
        sa.CheckConstraint("approval_reference IS NULL OR client_approver_name IS NOT NULL",
                           name="ck_baseline_approval_reference"),
        sa.CheckConstraint("(prior_baseline_id IS NULL) = (major_no = 1 AND minor_no = 0)",
                           name="ck_baseline_prior"),
        sa.CheckConstraint("num_nonnulls(client_approver_name, client_approved_on, approved_at, "
                           "approved_by_user_id) IN (0, 4)", name="ck_baseline_approval_set"),
        sa.ForeignKeyConstraint(["prior_baseline_id", "project_id"],
                                ["baseline.baseline_id", "baseline.project_id"], name="fk_baseline_prior"),
        sa.ForeignKeyConstraint(["status_code_id", "status_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_baseline_status", onupdate="NO ACTION"),
    )
    op.execute("CREATE UNIQUE INDEX uq_baseline_first ON baseline (project_id) WHERE prior_baseline_id IS NULL")
    op.execute("CREATE INDEX ix_baseline_status ON baseline (status_code_id)")
    updated_at_trigger("baseline")

    frozen = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in FROZEN_COLUMNS)
    # sara M1: once an approval is recorded, the whole set is closed — an empty optional field stays empty.
    approval = ("OLD.client_approver_name IS NOT NULL AND ("
                + " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in APPROVAL_COLUMNS) + ")")
    op.execute(f"""
        CREATE FUNCTION fn_baseline_header_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
    """)
    op.execute("CREATE TRIGGER trg_baseline_header_guard BEFORE UPDATE OR DELETE ON baseline "
               "FOR EACH ROW EXECUTE FUNCTION fn_baseline_header_guard()")
    # §6.6: the header's only app-writable columns.
    op.execute("REVOKE UPDATE ON baseline FROM vb_app")
    op.execute(f"GRANT UPDATE ({', '.join(APP_UPDATABLE)}) ON baseline TO vb_app")


def downgrade() -> None:
    op.execute(REFUSE_IF_BASELINES)
    op.execute("DROP TRIGGER IF EXISTS trg_baseline_header_guard ON baseline")
    op.execute("DROP FUNCTION IF EXISTS fn_baseline_header_guard()")
    drop_updated_at_trigger("baseline")
    op.drop_table("baseline")
