"""app_user.user_kind — USER (read and edit every visible project) or VIEWER (read only) (D-40,
slice7_schema §8.2, Q-11). The database default is the least privilege.

Data step: USER for platform admins and for users whose live grant's role is OWNER or EDITOR;
everyone else (REVIEWER holders, users with no grant) stays VIEWER, so nobody jumps from "nothing"
to "edit everything". Admins review the result in Users.

Revision ID: 0035
Revises: 0034
"""
from alembic import op
import sqlalchemy as sa

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("user_kind", sa.String(20), nullable=False, server_default="VIEWER"))
    op.create_check_constraint("ck_app_user_kind", "app_user", "user_kind IN ('USER', 'VIEWER')")
    op.execute("""
        UPDATE app_user u SET user_kind = 'USER'
        WHERE u.is_platform_admin
           OR EXISTS (SELECT 1 FROM user_access_grant g JOIN code_master c ON c.code_id = g.project_role_code_id
                      WHERE g.app_user_id = u.app_user_id AND g.is_active AND c.code IN ('OWNER', 'EDITOR'))""")
    counts = op.get_bind().execute(sa.text("SELECT user_kind, count(*) FROM app_user GROUP BY 1 ORDER BY 1")).all()
    print(f"0035 user_kind counts: {dict(counts)} — review them in Administration → Users")   # §8.2


def downgrade() -> None:
    op.drop_constraint("ck_app_user_kind", "app_user", type_="check")
    op.drop_column("app_user", "user_kind")
