"""import_row — one staged sheet row or staged JSON object (D-5, D-25, R2-D1, Q14).

Slice 4, docs/slice4_schema.md §2 (S4-1…S4-10). Staging is forensic and short-lived: rows are
hard-deleted 90 days after their batch's uploaded_at (Q14, deviation 7b), so vb_app gets DELETE
on this table — the second and last documented hard-delete table (§6.6). No audit columns, no
soft delete, no row_version: provenance is the batch header (deviation 7c). target_entity is
the batch's, carried through fk_ir_batch, so the kind and locator rules are declarative (S4-2).

Revision ID: 0020
Revises: 0019
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_ROW_KINDS = ("ISSUE", "DATA_ENTITY", "DATA_FIELD", "BUSINESS_REQUIREMENT", "FUNCTION_REQUIREMENT",
              "WBS_ITEM", "STEP", "STEP_IO", "STEP_ROLE", "FLOW_EDGE", "EXTERNAL_ENTITY",
              "EXTERNAL_FLOW", "LANE")
_FLOW_KINDS = ("STEP", "STEP_IO", "STEP_ROLE", "FLOW_EDGE", "EXTERNAL_ENTITY", "EXTERNAL_FLOW",
               "DATA_ENTITY", "LANE")


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.create_table(
        "import_row",
        sa.Column("import_row_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("import_batch_id", sa.BigInteger, nullable=False),
        sa.Column("target_entity", sa.String(30), nullable=False),
        sa.Column("row_kind", sa.String(30), nullable=False),
        sa.Column("sheet_row_no", sa.Integer),
        sa.Column("source_path", sa.String(200)),
        sa.Column("local_key", sa.String(50)),
        sa.Column("source_ref", sa.String(200)),
        sa.Column("business_key", sa.String(250)),
        sa.Column("cross_check_key", sa.String(100)),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("verdict", sa.String(10), nullable=False),
        sa.Column("is_valid", sa.Boolean, nullable=False),
        sa.Column("error_detail", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("warning_detail", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("committed_target_id", sa.BigInteger),
        sa.ForeignKeyConstraint(["import_batch_id", "target_entity"],
                                ["import_batch.import_batch_id", "import_batch.target_entity"],
                                name="fk_ir_batch"),
        sa.UniqueConstraint("import_batch_id", "sheet_row_no", name="uq_ir_sheet_row"),
        sa.UniqueConstraint("import_batch_id", "source_path", name="uq_ir_source_path"),
        sa.CheckConstraint(f"row_kind IN ({_in(_ROW_KINDS)})", name="ck_ir_row_kind"),
        sa.CheckConstraint(f"CASE WHEN target_entity = 'PROCESS_FLOW' THEN row_kind IN ({_in(_FLOW_KINDS)}) "
                           "ELSE row_kind = target_entity END", name="ck_ir_kind_fits_target"),
        sa.CheckConstraint("CASE WHEN verdict IN ('RETIRE', 'KEPT') THEN num_nonnulls(sheet_row_no, source_path) = 0 "
                           "WHEN target_entity = 'PROCESS_FLOW' THEN source_path IS NOT NULL AND sheet_row_no IS NULL "
                           "ELSE sheet_row_no IS NOT NULL AND source_path IS NULL END", name="ck_ir_locator"),
        sa.CheckConstraint("verdict IN ('INSERT', 'UPDATE', 'MATCH', 'RETIRE', 'KEPT')", name="ck_ir_verdict"),
        sa.CheckConstraint("CASE WHEN jsonb_typeof(error_detail) = 'array' "
                           "THEN is_valid = (jsonb_array_length(error_detail) = 0) ELSE false END",
                           name="ck_ir_valid_matches_errors"),
        sa.CheckConstraint("jsonb_typeof(warning_detail) = 'array'", name="ck_ir_warning_array"),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_ir_payload_object"),
        sa.CheckConstraint("verdict NOT IN ('RETIRE', 'KEPT') OR payload ? 'target'",
                           name="ck_ir_db_staged_target"),
        sa.CheckConstraint("verdict <> 'RETIRE' OR row_kind IN ('FLOW_EDGE', 'STEP_IO', 'WBS_ITEM')",
                           name="ck_ir_retire_kinds"),
        sa.CheckConstraint("verdict <> 'KEPT' OR row_kind = 'STEP_IO'", name="ck_ir_kept_kind"),
        sa.CheckConstraint("row_kind <> 'LANE' OR verdict = 'MATCH'", name="ck_ir_lane_match"),
        sa.CheckConstraint("target_entity = 'PROCESS_FLOW' OR (local_key IS NULL AND source_ref IS NULL)",
                           name="ck_ir_flow_only_fields"),
        sa.CheckConstraint("sheet_row_no IS NULL OR sheet_row_no BETWEEN 2 AND 1048576", name="ck_ir_sheet_row"),
        sa.CheckConstraint("source_path IS NULL OR left(source_path, 1) = '/'", name="ck_ir_source_path"),
        sa.CheckConstraint("(local_key IS NULL OR btrim(local_key) <> '') "
                           "AND (business_key IS NULL OR btrim(business_key) <> '') "
                           "AND (cross_check_key IS NULL OR btrim(cross_check_key) <> '')",
                           name="ck_ir_keys_not_blank"),
        sa.CheckConstraint("committed_target_id IS NULL OR row_kind <> 'LANE'", name="ck_ir_target_kind"),
    )
    # Backstops: the service catches duplicates in memory first (S4-4, Q-5).
    op.execute("CREATE UNIQUE INDEX uq_ir_local_key ON import_row (import_batch_id, row_kind, local_key) "
               "WHERE local_key IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_ir_business_key ON import_row (import_batch_id, row_kind, business_key) "
               "WHERE business_key IS NOT NULL")
    # §6.6 / Q14: the 90-day purge hard-deletes staged rows (deviation 7b).
    op.execute("GRANT DELETE ON import_row TO vb_app")


def downgrade() -> None:
    op.execute("REVOKE DELETE ON import_row FROM vb_app")
    op.drop_table("import_row")
