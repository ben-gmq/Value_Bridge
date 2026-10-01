"""import_batch — one uploaded file awaiting validation, review and commit (D-5, D-25, D-28, D-33, Q14).

Slice 4, docs/slice4_schema.md §1 (S4-1…S4-10). The import trail: kept through the 90-day row
purge, never deleted by the app and never retired — its life is its status. Deviation 7c: no
soft delete, no updated_by; uploaded_at / uploaded_by_user_id are its created pair, and
row_version is kept. The app role may UPDATE only the lifecycle columns (Q-17b), so who, when,
what target and which anchor are write-once. file_name is the one exception: the 90-day purge
overwrites it with '(purged)', because a file name can identify a person (S4-11/Q6).

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from vb_ops import category_column, drop_updated_at_trigger, updated_at_trigger

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_COUNTS = ("row_count", "error_count", "warning_count", "insert_count", "update_count", "retire_count")
# Q-17(b): everything else is write-once for vb_app; updated_at is the trigger's alone.
# file_name is amended in by S4-11/Q6: the purge sets it to '(purged)'.
_APP_UPDATABLE = ("status_code_id", *_COUNTS, "file_warning_detail", "committed_at",
                  "committed_by_user_id", "rows_purged_at", "file_name", "row_version")


def upgrade() -> None:
    op.create_table(
        "import_batch",
        sa.Column("import_batch_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("project.project_id"), nullable=False),
        sa.Column("target_entity", sa.String(30), nullable=False),
        sa.Column("source_format", sa.String(40), nullable=False, server_default="xlsx"),
        sa.Column("import_mode", sa.String(10)),
        sa.Column("anchor_bfc_node_id", sa.BigInteger),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("uploaded_by_user_id", sa.BigInteger, nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("status_code_id", sa.BigInteger, nullable=False),
        category_column("status_category", "IMPORT_STATUS"),
        *(sa.Column(c, sa.Integer, nullable=False, server_default="0") for c in _COUNTS),
        sa.Column("file_warning_detail", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.Column("committed_by_user_id", sa.BigInteger),
        sa.Column("rows_purged_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("import_batch_id", "project_id", name="uq_import_batch_project"),
        sa.UniqueConstraint("import_batch_id", "target_entity", name="uq_import_batch_target"),
        sa.ForeignKeyConstraint(["anchor_bfc_node_id", "project_id"],
                                ["bfc_node.bfc_node_id", "bfc_node.project_id"], name="fk_ib_anchor"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["app_user.app_user_id"], name="fk_ib_uploaded_by"),
        sa.ForeignKeyConstraint(["committed_by_user_id"], ["app_user.app_user_id"], name="fk_ib_committed_by"),
        sa.ForeignKeyConstraint(["status_code_id", "status_category"],
                                ["code_master.code_id", "code_master.category"],
                                name="fk_ib_status_code", onupdate="NO ACTION"),
        sa.CheckConstraint("target_entity IN ('ISSUE', 'DATA_ENTITY', 'DATA_FIELD', 'BUSINESS_REQUIREMENT', "
                           "'FUNCTION_REQUIREMENT', 'PROCESS_FLOW', 'WBS_ITEM')", name="ck_ib_target_entity"),
        sa.CheckConstraint("(target_entity = 'PROCESS_FLOW') = (source_format LIKE 'vb-process-flow/%')",
                           name="ck_ib_flow_format"),
        sa.CheckConstraint("import_mode IN ('MERGE', 'REPLACE')", name="ck_ib_import_mode"),
        sa.CheckConstraint("(target_entity IN ('PROCESS_FLOW', 'WBS_ITEM')) = (import_mode IS NOT NULL)",
                           name="ck_ib_mode_targets"),
        sa.CheckConstraint("(target_entity = 'PROCESS_FLOW') = (anchor_bfc_node_id IS NOT NULL)",
                           name="ck_ib_flow_anchor"),
        sa.CheckConstraint(f"least({', '.join(_COUNTS)}) >= 0", name="ck_ib_counts_nonneg"),
        sa.CheckConstraint("error_count <= row_count AND warning_count <= row_count "
                           "AND insert_count + update_count + retire_count <= row_count",
                           name="ck_ib_counts_bounded"),
        sa.CheckConstraint("retire_count = 0 OR import_mode IS NOT DISTINCT FROM 'REPLACE'", name="ck_ib_retire_needs_replace"),
        sa.CheckConstraint("(committed_at IS NULL) = (committed_by_user_id IS NULL)",
                           name="ck_ib_committed_pair"),
        sa.CheckConstraint("committed_at IS NULL OR committed_at >= uploaded_at",
                           name="ck_ib_commit_after_upload"),
        sa.CheckConstraint("rows_purged_at IS NULL OR rows_purged_at >= uploaded_at",
                           name="ck_ib_purge_after_upload"),
        sa.CheckConstraint("btrim(file_name) <> ''", name="ck_ib_file_name"),
        sa.CheckConstraint("btrim(source_format) <> ''", name="ck_ib_source_format"),
        sa.CheckConstraint("jsonb_typeof(file_warning_detail) = 'array'", name="ck_ib_file_warning_array"),
    )
    # §6.3: the 90-day purge scan; a project's import history (and purge_project).
    op.execute("CREATE INDEX ix_ib_purge_due ON import_batch (uploaded_at) WHERE rows_purged_at IS NULL")
    op.execute("CREATE INDEX ix_ib_project ON import_batch (project_id, uploaded_at DESC)")
    # The anchor FK index — partial, because six of seven targets leave it NULL.
    op.execute("CREATE INDEX ix_ib_anchor ON import_batch (anchor_bfc_node_id, project_id) "
               "WHERE anchor_bfc_node_id IS NOT NULL")
    op.create_index("ix_ib_status", "import_batch", ["status_code_id"])
    updated_at_trigger("import_batch")
    op.execute("REVOKE UPDATE ON import_batch FROM vb_app")
    op.execute(f"GRANT UPDATE ({', '.join(_APP_UPDATABLE)}) ON import_batch TO vb_app")


def downgrade() -> None:
    # The column grants go with the table.
    drop_updated_at_trigger("import_batch")
    op.drop_table("import_batch")
