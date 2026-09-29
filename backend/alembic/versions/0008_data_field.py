"""data_field — logical field in one data entity (§5.3 DATA_FIELD, D-26, §5.4.17).

Slice 1, docs/slice1_schema.md §1.4. The ref FKs together prove the referenced field is in the
referenced entity and that entity is in this project. S1-4: data type is category-verified.
S1-6: field name and pk_ordinal are unique among live fields. S1-3: seq_no range.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

from vb_ops import audit_columns, category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_field",
        sa.Column("data_field_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("data_entity_id", sa.BigInteger, nullable=False),
        sa.Column("seq_no", sa.Integer, nullable=False),
        sa.Column("field_name", sa.String(200), nullable=False),
        sa.Column("data_type_code_id", sa.BigInteger),
        category_column("data_type_category", "FIELD_DATA_TYPE"),
        sa.Column("length_val", sa.Integer),
        sa.Column("precision_val", sa.Integer),
        sa.Column("scale_val", sa.Integer),
        sa.Column("is_mandatory", sa.Boolean),
        sa.Column("is_primary_key", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("pk_ordinal", sa.SmallInteger),
        sa.Column("is_foreign_key", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("ref_data_entity_id", sa.BigInteger),
        sa.Column("ref_data_field_id", sa.BigInteger),
        sa.Column("fk_group_no", sa.SmallInteger),
        sa.Column("description", sa.Text),
        *audit_columns(),
        sa.UniqueConstraint("data_field_id", "data_entity_id", name="uq_data_field_entity"),
        sa.ForeignKeyConstraint(["data_entity_id", "project_id"],
                                ["data_entity.data_entity_id", "data_entity.project_id"],
                                name="fk_df_entity"),
        sa.ForeignKeyConstraint(["ref_data_entity_id", "project_id"],
                                ["data_entity.data_entity_id", "data_entity.project_id"],
                                name="fk_df_ref_entity"),
        sa.ForeignKeyConstraint(["ref_data_field_id", "ref_data_entity_id"],
                                ["data_field.data_field_id", "data_field.data_entity_id"],
                                name="fk_df_ref_field"),
        sa.ForeignKeyConstraint(["data_type_code_id", "data_type_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_df_data_type_code", onupdate="NO ACTION"),
        sa.CheckConstraint("seq_no <> 0 AND seq_no BETWEEN -999 AND 999", name="ck_df_seq"),
        sa.CheckConstraint("is_primary_key = (pk_ordinal IS NOT NULL)", name="ck_df_pk_ordinal"),
        sa.CheckConstraint("pk_ordinal IS NULL OR pk_ordinal >= 1", name="ck_df_pk_ordinal_pos"),
        sa.CheckConstraint("is_foreign_key = (ref_data_entity_id IS NOT NULL)", name="ck_df_fk_target"),
        sa.CheckConstraint("ref_data_field_id IS NULL OR is_foreign_key", name="ck_df_ref_field"),
        sa.CheckConstraint("(fk_group_no IS NOT NULL) = is_foreign_key", name="ck_df_fk_group"),
        sa.CheckConstraint("fk_group_no IS NULL OR fk_group_no >= 1", name="ck_df_fk_group_pos"),
        sa.CheckConstraint("NOT is_primary_key OR is_mandatory IS DISTINCT FROM FALSE",
                           name="ck_df_pk_not_optional"),
        sa.CheckConstraint("data_type_code_id IS NOT NULL OR "
                           "num_nulls(length_val, precision_val, scale_val) = 3",
                           name="ck_df_size_needs_type"),
        sa.CheckConstraint("coalesce(length_val, 1) > 0 AND coalesce(precision_val, 1) > 0 "
                           "AND coalesce(scale_val, 0) >= 0 "
                           "AND (scale_val IS NULL OR precision_val IS NULL OR scale_val <= precision_val)",
                           name="ck_df_sizes"),
    )
    op.execute("CREATE UNIQUE INDEX uq_df_name_live ON data_field "
               "(data_entity_id, lower(btrim(field_name))) WHERE is_active")
    op.execute("CREATE UNIQUE INDEX uq_df_pk_ordinal ON data_field "
               "(data_entity_id, pk_ordinal) WHERE is_primary_key AND is_active")
    op.execute("CREATE UNIQUE INDEX uq_df_fk_group_field ON data_field "
               "(data_entity_id, ref_data_entity_id, fk_group_no, ref_data_field_id) "
               "WHERE is_active AND ref_data_field_id IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_df_seq_live ON data_field (data_entity_id, seq_no) WHERE is_active")
    op.create_index("ix_df_project", "data_field", ["project_id"])
    op.create_index("ix_df_entity", "data_field", ["data_entity_id", "project_id"])
    op.create_index("ix_df_ref_entity", "data_field", ["ref_data_entity_id", "project_id"])
    op.create_index("ix_df_ref_field", "data_field", ["ref_data_field_id"])
    op.create_index("ix_df_type", "data_field", ["data_type_code_id"])
    op.execute("CREATE INDEX ix_df_fk_group ON data_field "
               "(data_entity_id, ref_data_entity_id, fk_group_no) WHERE is_foreign_key")
    updated_at_trigger("data_field")


def downgrade() -> None:
    drop_updated_at_trigger("data_field")
    op.drop_table("data_field")
