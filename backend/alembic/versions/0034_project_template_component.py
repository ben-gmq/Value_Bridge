"""project_template_component — which components each project template switches on (OR-3,
slice7_schema §3). Global, no project_id: copied once into project_component at create_project and
never linked afterwards. Seeded by `seeds.seed_project_templates`, so created_by is nullable like
code_master's (PLAYBOOK_DEVIATIONS 7d).

Revision ID: 0034
Revises: 0033
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = audit_columns()
    for i, c in enumerate(cols):
        if c.name == "created_by":
            cols[i] = sa.Column("created_by", sa.BigInteger, sa.ForeignKey("app_user.app_user_id"))
    op.create_table(
        "project_template_component",
        sa.Column("project_template_component_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("template_code_id", sa.BigInteger, nullable=False),
        category_column("template_category", "PROJECT_TEMPLATE"),
        sa.Column("component_code_id", sa.BigInteger, nullable=False),
        category_column("component_category", "PROJECT_COMPONENT"),
        *cols,
        sa.UniqueConstraint("template_code_id", "component_code_id", name="uq_ptc_grain"),
        sa.ForeignKeyConstraint(["template_code_id", "template_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_ptc_template", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["component_code_id", "component_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_ptc_component", onupdate="NO ACTION"),
    )
    op.create_index("ix_ptc_component", "project_template_component", ["component_code_id"])
    updated_at_trigger("project_template_component")


def downgrade() -> None:
    drop_updated_at_trigger("project_template_component")
    op.drop_table("project_template_component")
