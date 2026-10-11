"""application — one application or technology in one project's landscape (§5.3 APPLICATION, D-8).

Slice 6b-1, docs/slice6b_schema.md §1 with S6b-2/S6b-6: code typed, upper-case, A–Z 0–9 . _ -,
full UK (never reused); live names unique; lifecycle a system code (AS_IS/TO_BE/BOTH); kind optional.

Revision ID: 0025
Revises: 0024
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application",
        sa.Column("application_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("application_code", sa.String(30), nullable=False),
        sa.Column("application_name", sa.String(200), nullable=False),
        sa.Column("vendor", sa.String(200)),
        sa.Column("version_label", sa.String(50)),
        sa.Column("app_kind_code_id", sa.BigInteger),
        category_column("app_kind_category", "APP_KIND"),
        sa.Column("lifecycle_code_id", sa.BigInteger, nullable=False),
        category_column("lifecycle_category", "APP_LIFECYCLE"),
        sa.Column("description", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("project_id", "application_code", name="uq_application_code"),
        sa.UniqueConstraint("application_id", "project_id", name="uq_application_project"),
        sa.ForeignKeyConstraint(["app_kind_code_id", "app_kind_category"], ["code_master.code_id", "code_master.category"],
                                name="fk_app_kind_code", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["lifecycle_code_id", "lifecycle_category"], ["code_master.code_id", "code_master.category"],
                                name="fk_app_lifecycle_code", onupdate="NO ACTION"),
        sa.CheckConstraint("application_code ~ '^[A-Z0-9._-]+$'", name="ck_app_code_chars"),
        sa.CheckConstraint("btrim(application_name) <> ''", name="ck_app_name_not_blank"),
    )
    op.execute("CREATE UNIQUE INDEX uq_application_name_live ON application "
               "(project_id, lower(btrim(application_name))) WHERE is_active")
    op.create_index("ix_app_kind", "application", ["app_kind_code_id"])
    op.create_index("ix_app_lifecycle", "application", ["lifecycle_code_id"])
    updated_at_trigger("application")


def downgrade() -> None:
    drop_updated_at_trigger("application")
    op.drop_table("application")
