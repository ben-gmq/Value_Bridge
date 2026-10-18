"""stakeholder — a named client-side person in one project, no login (D-4; slice14_issue_schema §3.1; I-2, I-16).

The org unit is optional (I-2); the composite FK proves it is the same project's. Two people may share a name in
different units (I-16): the live unique key is (project, unit, normalised name), a NULL unit counting as one unit.
Not shadowed — a person is not scope (§6.1 row 28). vb_app gets SELECT/INSERT/UPDATE from 0001's default privileges
and no DELETE. A live stakeholder blocks retiring its org unit through the FK (lifecycle.LINKS, law 1).

Downgrade: refuses while the table holds any row.

Revision ID: 0062
Revises: 0061
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, drop_updated_at_trigger, updated_at_trigger

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stakeholder",
        sa.Column("stakeholder_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("org_unit_id", sa.BigInteger),
        sa.Column("stakeholder_name", sa.String(200), nullable=False),
        sa.Column("job_title", sa.String(200)),
        sa.Column("is_bpo", sa.Boolean, nullable=False, server_default="false"),
        *audit_columns(),
        sa.UniqueConstraint("stakeholder_id", "project_id", name="uq_stk_project"),
        sa.ForeignKeyConstraint(["org_unit_id", "project_id"], ["org_unit.org_unit_id", "org_unit.project_id"],
                                name="fk_stk_org_unit"),
        sa.CheckConstraint("btrim(stakeholder_name) <> ''", name="ck_stk_name_not_blank"),
    )
    op.execute("CREATE UNIQUE INDEX uq_stk_name_live ON stakeholder "
               "(project_id, coalesce(org_unit_id, 0), lower(btrim(stakeholder_name))) WHERE is_active")
    op.create_index("ix_stk_org_unit", "stakeholder", ["org_unit_id", "project_id"])
    updated_at_trigger("stakeholder")


def downgrade() -> None:
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM stakeholder) THEN "
               "RAISE EXCEPTION 'stakeholders exist: downgrade refused'; END IF; END $$")
    drop_updated_at_trigger("stakeholder")
    op.drop_table("stakeholder")
