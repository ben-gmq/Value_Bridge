"""Retire user_access_grant (D-40, slice7_schema §8.5 step 2, S7-6).

Every live grant is soft-revoked (it was copied into project_member by 0037), with one
ACCESS_REVOKED audit row each, and the app role loses INSERT and UPDATE on the table. Rows, model
and table stay readable as history. Nothing is deleted.

Revision ID: 0038
Revises: 0037
"""
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO audit_event (event_type, project_id, target_table, target_id, detail)
        SELECT 'ACCESS_REVOKED', g.project_id, 'user_access_grant', g.user_access_grant_id,
               jsonb_build_object('reason', 'D-40', 'migration', '0038', 'user_id', g.app_user_id,
                                  'project_id', g.project_id, 'program_id', g.program_id, 'role', c.code)
        FROM user_access_grant g JOIN code_master c ON c.code_id = g.project_role_code_id
        WHERE g.is_active""")
    op.execute("UPDATE user_access_grant SET is_active = false, deleted_at = now() WHERE is_active")
    op.execute("REVOKE INSERT, UPDATE ON user_access_grant FROM vb_app")


def downgrade() -> None:
    # The revocations are evidence and stay; only the privilege returns.
    op.execute("GRANT INSERT, UPDATE ON user_access_grant TO vb_app")
