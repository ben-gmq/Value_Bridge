"""vb_instance: this database's identity, the prefix of every archive file and key name (slice16 schema §3.4 as
revised by §12.7; spec §17 R8, §18 S6, S9).

One row, stamped by the owner-run scripts.stamp_instance — never by the app, which may only read it. A restored
database keeps the id it was stamped with, so it knows which instance wrote its archive names; re-stamping (a prod
backup restored into UAT) moves the old id into prior_instance_ids, where the writer and the restore runbook still
look for its tombstones.

trg_vb_instance_guard, for every role: no DELETE; an UPDATE must change instance_id and append exactly the old id to
prior_instance_ids, and stamped_at is the database's. Not a business table — no AuditMixin (recorded with Q-68).
vb_app: SELECT only.

Downgrade: refuses once stamped (the restore identity would be lost).

Revision ID: 0069
Revises: 0068
"""
from alembic import op
import sqlalchemy as sa

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vb_instance",
        sa.Column("one_row", sa.Boolean, primary_key=True, server_default=sa.true()),
        sa.Column("instance_id", sa.String(40), nullable=False),
        sa.Column("prior_instance_ids", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("stamped_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("one_row", name="ck_vi_one_row"),
        sa.CheckConstraint("instance_id ~ '^[a-z0-9][a-z0-9-]{2,39}$'", name="ck_vi_instance_id"),
    )
    op.execute("""
        CREATE FUNCTION fn_vb_instance_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'DELETE on vb_instance is not allowed: it is this database''s archive identity'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF TG_OP = 'UPDATE' AND (NEW.instance_id = OLD.instance_id
               OR NEW.prior_instance_ids IS DISTINCT FROM OLD.prior_instance_ids || OLD.instance_id::text) THEN
            RAISE EXCEPTION 'a re-stamp changes the instance id and appends the old one to prior_instance_ids'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF TG_OP = 'UPDATE' AND NEW.instance_id = ANY (OLD.prior_instance_ids) THEN
            RAISE EXCEPTION 'a re-stamp never takes back an earlier instance id (its files and keys are that copy''s)'
              USING ERRCODE = 'restrict_violation';
          END IF;
          IF TG_OP = 'INSERT' AND cardinality(NEW.prior_instance_ids) <> 0 THEN
            RAISE EXCEPTION 'a first stamp has no prior instance ids' USING ERRCODE = 'restrict_violation';
          END IF;
          NEW.stamped_at := now();
          RETURN NEW;
        END $$;
    """)
    op.execute("CREATE TRIGGER trg_vb_instance_guard BEFORE INSERT OR UPDATE OR DELETE ON vb_instance "
               "FOR EACH ROW EXECUTE FUNCTION fn_vb_instance_guard()")
    op.execute("REVOKE ALL ON vb_instance FROM vb_app")
    op.execute("GRANT SELECT ON vb_instance TO vb_app")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM vb_instance) THEN "
               "RAISE EXCEPTION 'this database is stamped: downgrade refused'; END IF; END $$")
    op.execute("DROP TRIGGER IF EXISTS trg_vb_instance_guard ON vb_instance")
    op.execute("DROP FUNCTION IF EXISTS fn_vb_instance_guard()")
    op.drop_table("vb_instance")
