"""import_row takes the 1e-b flow kinds (docs/slice1e_b_flow_import_spec.md §5–6; FI-5, Ben 2026-10-28).

The process-flow file (vb-process-flow/2.0) stages three new kinds of object — a step's performer, a catalogue trigger
and a step's link to a trigger — and needs one staged row per kind at each position in the file (a new data entity and
the input that names it share one JSON pointer). This only widens:
  1. ck_ir_row_kind and ck_ir_kind_fits_target gain PERFORMER, TRIGGER and STEP_TRIGGER (STEP_ROLE, FLOW_EDGE and LANE
     stay: S7 Q-32);
  2. ck_ir_retire_kinds gains STEP_TRIGGER (replace mode retires an omitted trigger link);
  3. ck_ir_lane_match becomes ck_ir_match_only: a LANE or a PERFORMER row is always MATCH;
  4. ck_ir_target_kind: neither a LANE nor a PERFORMER row carries committed_target_id (a performer may be one of three
     tables; its id lives in the payload);
  5. uq_ir_source_path becomes (import_batch_id, row_kind, source_path).

Downgrade: refuses, by count, while any row of the three new kinds or any batch with two kinds on one pointer exists —
it deletes nothing (Q-21 pattern); otherwise restores the 0020 constraints exactly.

Revision ID: 0080
Revises: 0079
"""
from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None

_NEW = ("PERFORMER", "TRIGGER", "STEP_TRIGGER")
_NEW_NAMES = " / ".join(_NEW)
_ROW_KINDS = ("ISSUE", "DATA_ENTITY", "DATA_FIELD", "BUSINESS_REQUIREMENT", "FUNCTION_REQUIREMENT",
              "WBS_ITEM", "STEP", "STEP_IO", "STEP_ROLE", "FLOW_EDGE", "EXTERNAL_ENTITY",
              "EXTERNAL_FLOW", "LANE")
_FLOW_KINDS = ("STEP", "STEP_IO", "STEP_ROLE", "FLOW_EDGE", "EXTERNAL_ENTITY", "EXTERNAL_FLOW",
               "DATA_ENTITY", "LANE")
_RETIRE = ("FLOW_EDGE", "STEP_IO", "WBS_ITEM")


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _swap(row_kinds, flow_kinds, retire_kinds, match_only) -> None:
    for name in ("ck_ir_row_kind", "ck_ir_kind_fits_target", "ck_ir_retire_kinds", "ck_ir_target_kind"):
        op.drop_constraint(name, "import_row", type_="check")
    op.create_check_constraint("ck_ir_row_kind", "import_row", f"row_kind IN ({_in(row_kinds)})")
    op.create_check_constraint(
        "ck_ir_kind_fits_target", "import_row",
        f"CASE WHEN target_entity = 'PROCESS_FLOW' THEN row_kind IN ({_in(flow_kinds)}) "
        "ELSE row_kind = target_entity END")
    op.create_check_constraint("ck_ir_retire_kinds", "import_row",
                               f"verdict <> 'RETIRE' OR row_kind IN ({_in(retire_kinds)})")
    if len(match_only) == 1:
        op.create_check_constraint("ck_ir_target_kind", "import_row",
                                   "committed_target_id IS NULL OR row_kind <> 'LANE'")
    else:
        op.create_check_constraint("ck_ir_target_kind", "import_row",
                                   f"committed_target_id IS NULL OR row_kind NOT IN ({_in(match_only)})")


def upgrade() -> None:
    _swap(_ROW_KINDS + _NEW, _FLOW_KINDS + _NEW, _RETIRE + ("STEP_TRIGGER",), ("LANE", "PERFORMER"))
    op.drop_constraint("ck_ir_lane_match", "import_row", type_="check")
    op.create_check_constraint("ck_ir_match_only", "import_row",
                               "row_kind NOT IN ('LANE', 'PERFORMER') OR verdict = 'MATCH'")
    op.drop_constraint("uq_ir_source_path", "import_row", type_="unique")
    op.create_unique_constraint("uq_ir_source_path", "import_row", ["import_batch_id", "row_kind", "source_path"])


def downgrade() -> None:
    op.execute(f"""DO $$ DECLARE n_kind bigint; n_path bigint; BEGIN
      SELECT count(*) INTO n_kind FROM import_row WHERE row_kind IN ({_in(_NEW)});
      SELECT count(*) INTO n_path FROM (SELECT 1 FROM import_row WHERE source_path IS NOT NULL
        GROUP BY import_batch_id, source_path HAVING count(*) > 1) d;
      IF n_kind > 0 OR n_path > 0 THEN
        RAISE EXCEPTION 'import_row holds % row(s) of the 1e-b kinds (%) and % pointer(s) staged under two kinds: '
          'the 0079 constraints cannot hold them; nothing deleted. Let the 90-day purge clear them, or remove them '
          'by hand with Ben''s approval, then downgrade again', n_kind, '{_NEW_NAMES}', n_path;
      END IF;
    END $$""")
    op.drop_constraint("uq_ir_source_path", "import_row", type_="unique")
    op.create_unique_constraint("uq_ir_source_path", "import_row", ["import_batch_id", "source_path"])
    op.drop_constraint("ck_ir_match_only", "import_row", type_="check")
    op.create_check_constraint("ck_ir_lane_match", "import_row", "row_kind <> 'LANE' OR verdict = 'MATCH'")
    _swap(_ROW_KINDS, _FLOW_KINDS, _RETIRE, ("LANE",))
