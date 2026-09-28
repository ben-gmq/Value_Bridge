"""Conventions: trigger functions and the application role's default privileges (§5.1, §6.6).

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The roles are cluster objects created by a DB admin (scripts/bootstrap_local_db.sh
    # locally; the Azure admin in prod, §15.2). Fail loudly rather than grant to nothing.
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vb_app') THEN
            RAISE EXCEPTION 'Role vb_app does not exist. Run scripts/bootstrap_local_db.sh first.';
          END IF;
        END $$;
    """)
    op.execute("""
        CREATE FUNCTION fn_set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          NEW.updated_at := now();
          RETURN NEW;
        END $$;
    """)
    # Attached to every baseline_* table and to decision (A-41) as they are created:
    # immutability enforced by the database, not by convention (§13).
    op.execute("""
        CREATE FUNCTION fn_reject_modification() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION '% on % is not allowed: the row is immutable', TG_OP, TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
        END $$;
    """)
    # §6.6: the app role gets SELECT/INSERT/UPDATE by default and NO DELETE, NO TRUNCATE,
    # NO DDL. The two DELETE exceptions (diagram_layout, import_row) are granted by the
    # migrations that create those tables.
    op.execute("GRANT USAGE ON SCHEMA public TO vb_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO vb_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO vb_app")


def downgrade() -> None:
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM vb_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE ON TABLES FROM vb_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM vb_app")
    op.execute("DROP FUNCTION IF EXISTS fn_reject_modification()")
    op.execute("DROP FUNCTION IF EXISTS fn_set_updated_at()")
