"""project_member.access_level takes ADMIN — the project admin (D-71; docs/slice_access_a_plan.md step 1).

The column widens from varchar(4) to varchar(5) ('ADMIN' is five characters) — a length increase, so a catalog-only
change with no table rewrite; project_member is not shadowed, so law 2's no-ALTER-on-shadow-type rule does not apply.
The CHECK is dropped and re-added under the same name. No existing row changes meaning.

Nothing opens by this migration alone: the request schemas accept ADMIN only from the access commit that also moves
the FTC-only project settings behind the PLATFORM level.

Downgrade: refuses while any membership, live or retired, holds ADMIN — narrowing would rewrite membership history.

Revision ID: 0058
Revises: 0057
"""
from alembic import op
import sqlalchemy as sa

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("project_member", "access_level", type_=sa.String(5), existing_type=sa.String(4),
                    existing_nullable=False)
    op.drop_constraint("ck_pm_level", "project_member", type_="check")
    op.create_check_constraint("ck_pm_level", "project_member", "access_level IN ('ADMIN', 'EDIT', 'VIEW')")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM project_member WHERE access_level = 'ADMIN') THEN "
               "RAISE EXCEPTION 'project admin memberships exist: downgrade refused'; END IF; END $$")
    op.drop_constraint("ck_pm_level", "project_member", type_="check")
    op.create_check_constraint("ck_pm_level", "project_member", "access_level IN ('EDIT', 'VIEW')")
    op.alter_column("project_member", "access_level", type_=sa.String(4), existing_type=sa.String(5),
                    existing_nullable=False)
