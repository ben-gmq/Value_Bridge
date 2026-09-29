"""bfc_node_org_role — step × org role × RACI code (§5.3, §5.4.5, Q7).

Slice 1, docs/slice1_schema.md §1.10. RACI rules key on the behaviour, FK-verified against
code_master (code_id, category, behaviour_code) — never on the letter (VB law 5). raci_behaviour
is copied by the service from the code. S1-5: surrogate PK; the design's key is a UNIQUE.

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, live_guard, updated_at_trigger

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bfc_node_org_role",
        sa.Column("bfc_node_org_role_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("bfc_node_id", sa.BigInteger, nullable=False),
        live_guard("node_is_process", True),
        sa.Column("org_role_id", sa.BigInteger, nullable=False),
        sa.Column("raci_code_id", sa.BigInteger, nullable=False),
        category_column("raci_category", "RACI_TYPE"),
        sa.Column("raci_behaviour", sa.String(20), nullable=False),
        *audit_columns(),
        sa.UniqueConstraint("bfc_node_id", "org_role_id", "raci_code_id", name="uq_bnor_grain"),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_bnor_node"),
        sa.ForeignKeyConstraint(["bfc_node_id", "project_id", "node_is_process"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id", "bfc_node.is_process"],
                                name="fk_bnor_node_process", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["org_role_id", "project_id"],
                                ["org_role.org_role_id", "org_role.project_id"], name="fk_bnor_role"),
        sa.ForeignKeyConstraint(["raci_code_id", "raci_category", "raci_behaviour"],
                                ["code_master.code_id", "code_master.category", "code_master.behaviour_code"],
                                name="fk_bnor_raci", onupdate="NO ACTION"),
    )
    op.execute("CREATE UNIQUE INDEX uq_bnor_one_accountable ON bfc_node_org_role (bfc_node_id) "
               "WHERE is_active AND raci_behaviour = 'ACCOUNTABLE'")
    # Also the swimlane lookup (A-46): at most one RESPONSIBLE-behaviour role per step.
    op.execute("CREATE UNIQUE INDEX uq_bnor_one_responsible ON bfc_node_org_role (bfc_node_id) "
               "WHERE is_active AND raci_behaviour = 'RESPONSIBLE'")
    op.create_index("ix_bnor_node", "bfc_node_org_role", ["bfc_node_id", "project_id"])
    op.create_index("ix_bnor_role", "bfc_node_org_role", ["org_role_id", "project_id"])
    op.create_index("ix_bnor_raci", "bfc_node_org_role", ["raci_code_id"])
    op.create_index("ix_bnor_project", "bfc_node_org_role", ["project_id"])
    updated_at_trigger("bfc_node_org_role")


def downgrade() -> None:
    drop_updated_at_trigger("bfc_node_org_role")
    op.drop_table("bfc_node_org_role")
