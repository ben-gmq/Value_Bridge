"""fr_interface — 1:0..1 interface detail of an INTERFACE-behaviour FR (§5.3 FR_INTERFACE, D-27, A-55).

Slice 6b-2, docs/slice6b_schema.md §4. PK fr_id; the generated fr_type_behaviour ('INTERFACE' while
live) carries the guard FK onto uq_fr_behaviour_target (0023). Same commit:
lifecycle.GUARD_TARGET_COLUMNS gains fr_type_behaviour, and vb_ops.live_tag is added.

Revision ID: 0028
Revises: 0027
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, live_tag, updated_at_trigger

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fr_interface",
        sa.Column("fr_id", sa.BigInteger, primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        live_tag("fr_type_behaviour", "INTERFACE"),
        sa.Column("source_application_id", sa.BigInteger, nullable=False),
        sa.Column("target_application_id", sa.BigInteger, nullable=False),
        sa.Column("pattern_code_id", sa.BigInteger),
        category_column("pattern_category", "INTERFACE_PATTERN"),
        sa.Column("method_code_id", sa.BigInteger),
        category_column("method_category", "INTERFACE_METHOD"),
        sa.Column("frequency_code_id", sa.BigInteger),
        category_column("frequency_category", "INTERFACE_FREQUENCY"),
        sa.Column("volume_note", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("fr_id", "project_id", name="uq_fri_project"),
        sa.UniqueConstraint("fr_id", "project_id", "is_active", name="uq_fri_live_target"),
        sa.ForeignKeyConstraint(["fr_id", "project_id"], ["function_requirement.fr_id", "function_requirement.project_id"],
                                name="fk_fri_fr"),
        sa.ForeignKeyConstraint(["fr_id", "project_id", "fr_type_behaviour"],
                                ["function_requirement.fr_id", "function_requirement.project_id",
                                 "function_requirement.fr_type_behaviour"], name="fk_fri_fr_behaviour", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["source_application_id", "project_id"],
                                ["application.application_id", "application.project_id"], name="fk_fri_source"),
        sa.ForeignKeyConstraint(["target_application_id", "project_id"],
                                ["application.application_id", "application.project_id"], name="fk_fri_target"),
        sa.ForeignKeyConstraint(["pattern_code_id", "pattern_category"], ["code_master.code_id", "code_master.category"],
                                name="fk_fri_pattern_code", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["method_code_id", "method_category"], ["code_master.code_id", "code_master.category"],
                                name="fk_fri_method_code", onupdate="NO ACTION"),
        sa.ForeignKeyConstraint(["frequency_code_id", "frequency_category"], ["code_master.code_id", "code_master.category"],
                                name="fk_fri_frequency_code", onupdate="NO ACTION"),
        sa.CheckConstraint("source_application_id <> target_application_id", name="ck_fri_endpoints_distinct"),
    )
    op.create_index("ix_fri_pair", "fr_interface", ["project_id", "source_application_id", "target_application_id"])
    op.create_index("ix_fri_target", "fr_interface", ["target_application_id", "project_id"])
    op.create_index("ix_fri_pattern", "fr_interface", ["pattern_code_id"])
    op.create_index("ix_fri_method", "fr_interface", ["method_code_id"])
    op.create_index("ix_fri_frequency", "fr_interface", ["frequency_code_id"])
    updated_at_trigger("fr_interface")


def downgrade() -> None:
    drop_updated_at_trigger("fr_interface")
    op.drop_table("fr_interface")
