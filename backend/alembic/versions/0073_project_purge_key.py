"""project_purge_key: one project key name recorded by a removal, and its destruction (slice16 schema §3.3 as revised by
§12.6; spec §17 R8, §18 S2, §19 U6; Q-71, AR-9).

Rows are inserted by the owner-run purge job inside the purge transaction of an ARCHIVE or DELETE: one per key name
seen in the project's files, plus the project's computed name. A DELETE destroys its own keys after its commit; an
ARCHIVE destroys none ("keys held for the archive") — a later DELETE_ARCHIVE of that ARCHIVE does. No key material:
names and versions only.

trg_project_purge_key_guard, for every role: INSERT only by vb_owner while the parent ARCHIVE / DELETE is open,
approved and named by this transaction's vb.purge_project_id (the conditions fn_purge_allows will own from 0074);
destroyed_at / was_present / destroyed_by_purge_id once, by vb_owner, where the destroyer is the parent DELETE once
executed, or an approved DELETE_ARCHIVE of the parent at least 24 hours old whose destruction has started (U6) — an
ARCHIVE can never mark its own keys destroyed; nothing else changes; DELETE refused. vb_app: SELECT only.

Downgrade: refuses if any row exists.

Revision ID: 0073
Revises: 0072
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import drop_updated_at_trigger, updated_at_trigger

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_purge_key",
        sa.Column("project_purge_id", sa.BigInteger, sa.ForeignKey("project_purge.project_purge_id"), primary_key=True),
        sa.Column("key_name", sa.String(200), primary_key=True),
        sa.Column("key_refs", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("destroyed_at", sa.DateTime(timezone=True)),
        sa.Column("was_present", sa.Boolean),
        sa.Column("destroyed_by_purge_id", sa.BigInteger, sa.ForeignKey("project_purge.project_purge_id")),
        sa.Column("proof_object_name", sa.String(400)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint("num_nonnulls(destroyed_at, was_present, destroyed_by_purge_id) IN (0, 3)",
                           name="ck_ppk_destroyed"),
        sa.CheckConstraint("proof_object_name IS NULL OR destroyed_at IS NOT NULL", name="ck_ppk_proof"),
        sa.CheckConstraint("key_name ~ '^vb-[a-z0-9][a-z0-9-]{2,39}-proj-[0-9]+$'", name="ck_ppk_key_name"),
    )
    updated_at_trigger("project_purge_key")
    op.execute("""
        CREATE FUNCTION fn_project_purge_key_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
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
            -- schema §12.4's fn_purge_allows, in full until 0074 owns it (sara M3): 0074 re-points this to the function
            IF current_user <> 'vb_owner' OR parent.purge_kind NOT IN ('ARCHIVE', 'DELETE')
               OR parent.executed_at IS NOT NULL OR parent.cancelled_at IS NOT NULL OR parent.approved_at IS NULL
               OR (parent.approved_at > statement_timestamp() - interval '24 hours'
                   AND parent.repurge_of_purge_id IS NULL)
               OR (parent.purge_kind = 'ARCHIVE' AND parent.archive_object_name IS NULL)
               OR parent.project_id::text IS DISTINCT FROM current_setting('vb.purge_project_id', true) THEN
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
    """)
    op.execute("CREATE TRIGGER trg_project_purge_key_guard BEFORE INSERT OR UPDATE OR DELETE ON project_purge_key "
               "FOR EACH ROW EXECUTE FUNCTION fn_project_purge_key_guard()")
    op.execute("REVOKE ALL ON project_purge_key FROM vb_app")
    op.execute("GRANT SELECT ON project_purge_key TO vb_app")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM project_purge_key) THEN "
               "RAISE EXCEPTION 'purge key records exist: downgrade refused'; END IF; END $$")
    op.execute("DROP TRIGGER IF EXISTS trg_project_purge_key_guard ON project_purge_key")
    op.execute("DROP FUNCTION IF EXISTS fn_project_purge_key_guard()")
    drop_updated_at_trigger("project_purge_key")
    op.drop_table("project_purge_key")
