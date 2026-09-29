"""br_org_role — BR × org role × RACI code (§5.3, §5.4.5).

Slice 1, docs/slice1_schema.md §1.11. One ACCOUNTABLE-behaviour role per BR; no process guard
(the BR carries it). S1-5: surrogate PK; the design's key is a UNIQUE.

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "br_org_role",
        sa.Column("br_org_role_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("br_id", sa.BigInteger, nullable=False),
        sa.Column("org_role_id", sa.BigInteger, nullable=False),
        sa.Column("raci_code_id", sa.BigInteger, nullable=False),
        category_column("raci_category", "RACI_TYPE"),
        sa.Column("raci_behaviour", sa.String(20), nullable=False),
        *audit_columns(),
        sa.UniqueConstraint("br_id", "org_role_id", "raci_code_id", name="uq_bror_grain"),
        sa.ForeignKeyConstraint(["br_id", "project_id"],
                                ["business_requirement.br_id", "business_requirement.project_id"],
                                name="fk_bror_br"),
        sa.ForeignKeyConstraint(["org_role_id", "project_id"],
                                ["org_role.org_role_id", "org_role.project_id"], name="fk_bror_role"),
        sa.ForeignKeyConstraint(["raci_code_id", "raci_category", "raci_behaviour"],
                                ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                                name="fk_bror_raci", onupdate="NO ACTION"),
    )
    op.execute("CREATE UNIQUE INDEX uq_bror_one_accountable ON br_org_role (br_id) "
               "WHERE is_active AND raci_behaviour = 'ACCOUNTABLE'")
    op.create_index("ix_bror_role", "br_org_role", ["org_role_id", "project_id"])
    op.create_index("ix_bror_raci", "br_org_role", ["raci_code_id"])
    op.create_index("ix_bror_project", "br_org_role", ["project_id"])
    updated_at_trigger("br_org_role")


def downgrade() -> None:
    drop_updated_at_trigger("br_org_role")
    op.drop_table("br_org_role")
