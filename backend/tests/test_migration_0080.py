"""Migration 0080 (slice 1e-b, FI-5): import_row takes PERFORMER, TRIGGER and STEP_TRIGGER, and one row per kind at a
pointer. A clean downgrade and re-upgrade round-trips; a staged row of a new kind, or two kinds on one pointer, refuses
the downgrade and nothing is deleted."""
import pytest
from alembic import command
from sqlalchemy import text

from tests.test_migration_0053 import _cfg, owner, q, x  # noqa: F401 — owner is a fixture
from tests.test_scope_api import ed  # noqa: F401 — ed is a fixture

KEY = ("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'uq_ir_source_path'")


def _ins(eng, sql, **kw) -> int:
    with eng.begin() as c:
        return c.execute(text(sql), kw).scalar_one()


def _flow_batch(owner, project_id) -> int:
    user = q(owner, "SELECT app_user_id FROM app_user ORDER BY app_user_id LIMIT 1")[0][0]
    status = q(owner, "SELECT code_id FROM code_master WHERE project_id IS NULL AND category = 'IMPORT_STATUS' "
                      "AND code = 'VALIDATING'")[0][0]
    node = _ins(owner, "INSERT INTO bfc_node (project_id, level_no, seq_no, hier_code, node_name, created_by, "
                    "bfc_set_code) VALUES (:p, 1, 99, '99', 'Anchor', :u, 'TO_BE') RETURNING bfc_node_id",
             p=project_id, u=user)
    return _ins(owner, "INSERT INTO import_batch (project_id, target_entity, source_format, import_mode, "
                    "anchor_bfc_node_id, file_name, uploaded_by_user_id, status_code_id) VALUES (:p, 'PROCESS_FLOW', "
                    "'vb-process-flow/2.0', 'MERGE', :n, 'f.json', :u, :s) RETURNING import_batch_id",
             p=project_id, n=node, u=user, s=status)


def _row(owner, batch, kind, path, verdict="INSERT"):
    x(owner, "INSERT INTO import_row (import_batch_id, target_entity, row_kind, source_path, verdict, is_valid) "
             "VALUES (:b, 'PROCESS_FLOW', :k, :sp, :v, true)", b=batch, k=kind, sp=path, v=verdict)


def _defs(owner) -> dict:
    return dict(q(owner, "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                         "WHERE conrelid = 'import_row'::regclass"))


def test_a_clean_downgrade_and_upgrade_round_trip(client, ed, owner):
    head = _defs(owner)
    command.downgrade(_cfg(), "0079")
    old = _defs(owner)
    assert "row_kind" not in old["uq_ir_source_path"]
    assert "ck_ir_match_only" not in old and "PERFORMER" not in old["ck_ir_target_kind"]
    assert old["ck_ir_lane_match"]
    assert not any(k in old["ck_ir_row_kind"] + old["ck_ir_kind_fits_target"] + old["ck_ir_retire_kinds"]
                   for k in ("PERFORMER", "TRIGGER"))
    command.upgrade(_cfg(), "head")
    assert _defs(owner) == head


@pytest.mark.parametrize("rows", [
    [("PERFORMER", "/steps/0/performer", "MATCH")],
    [("STEP_TRIGGER", "/steps/0/triggers/0", "INSERT")],
    [("STEP_IO", "/steps/0/inputs/0", "INSERT"), ("DATA_ENTITY", "/steps/0/inputs/0", "INSERT")],
])
def test_a_new_kind_or_a_shared_pointer_refuses_the_downgrade(client, ed, owner, rows):
    batch = _flow_batch(owner, ed["p"])
    for kind, path, verdict in rows:
        _row(owner, batch, kind, path, verdict)
    with pytest.raises(Exception, match="nothing deleted"):
        command.downgrade(_cfg(), "0079")
    assert "row_kind" in q(owner, KEY)[0][0]
    assert q(owner, "SELECT count(*) FROM import_row WHERE import_batch_id = :b", b=batch)[0][0] == len(rows)
