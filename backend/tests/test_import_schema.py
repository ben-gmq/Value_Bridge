"""Slice 4 — the rules the import-staging tables carry themselves (docs/slice4_schema.md, S4-1…S4-10).
Every write goes in as vb_app by direct SQL, so a missing grant or a weak CHECK fails here
before the bulk pipeline ever relies on it."""
import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from models import ImportBatch

INSUFFICIENT_PRIVILEGE = "42501"


def _code(db, category, code):
    return db.execute(text("SELECT code_id FROM code_master WHERE category = :c AND code = :k "
                           "AND project_id IS NULL"), {"c": category, "k": code}).scalar_one()


def _violates(db, constraint, fn):
    """fn() is refused by exactly the named constraint; earlier work in the test survives."""
    with pytest.raises(IntegrityError) as e:
        with db.begin_nested():
            fn()
    assert e.value.orig.diag.constraint_name == constraint


def _denied(db, fn):
    with pytest.raises(DBAPIError) as e:
        with db.begin_nested():
            fn()
    assert e.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE


class W:
    def __init__(self, db, world):
        self.db, self.p, self.u = db, world["p_solo"], world["users"]["owner"]
        self.validating = _code(db, "IMPORT_STATUS", "VALIDATING")
        self._anchor = None

    def anchor(self):
        """One live non-process node to anchor flow batches on."""
        if self._anchor is None:
            self._anchor = self.db.execute(text(
                "INSERT INTO bfc_node (project_id, level_no, seq_no, hier_code, node_name, created_by) "
                "VALUES (:p, 1, 1, '1', 'Sales', :u) RETURNING bfc_node_id"),
                {"p": self.p, "u": self.u}).scalar_one()
        return self._anchor

    def batch(self, target="DATA_ENTITY", **cols):
        if target == "PROCESS_FLOW":
            cols = {"source_format": "vb-process-flow/1.0", "import_mode": "MERGE",
                    "anchor_bfc_node_id": cols.pop("anchor", None) or self.anchor(), **cols}
        cols = {"project_id": self.p, "target_entity": target, "file_name": "upload.xlsx",
                "uploaded_by_user_id": self.u, "status_code_id": self.validating, **cols}
        return self.db.execute(text(
            f"INSERT INTO import_batch ({', '.join(cols)}) VALUES ({', '.join(':' + k for k in cols)}) "
            "RETURNING import_batch_id"), cols).scalar_one()

    def row(self, batch, target="DATA_ENTITY", kind=None, verdict="INSERT", errors=(), **cols):
        cols = {"import_batch_id": batch, "target_entity": target, "row_kind": kind or target,
                "verdict": verdict, "is_valid": not errors, "error_detail": json.dumps(list(errors)),
                **cols}
        for k in ("payload", "error_detail", "warning_detail"):
            if isinstance(cols.get(k), (dict, list)):
                cols[k] = json.dumps(cols[k])
        binds = ", ".join(f"CAST(:{k} AS jsonb)" if k in ("payload", "error_detail", "warning_detail")
                          else f":{k}" for k in cols)
        return self.db.execute(text(
            f"INSERT INTO import_row ({', '.join(cols)}) VALUES ({binds}) RETURNING import_row_id"), cols
        ).scalar_one()


@pytest.fixture
def w(db, world):
    return W(db, world)


TARGET = {"target": {"table": "bfc_node_flow", "id": 1, "label": "edge"}}
ERROR = {"code": "ROW_STALE", "column": None, "message": "stale", "params": {}}


# ---- ck_ir_locator (S4-1, Q-1) ------------------------------------------------------------

def test_sheet_rows_need_a_sheet_row_number_and_no_pointer(db, w):
    b = w.batch()
    w.row(b, sheet_row_no=2)
    _violates(db, "ck_ir_locator", lambda: w.row(b))
    _violates(db, "ck_ir_locator", lambda: w.row(b, sheet_row_no=3, source_path="/steps/0"))


def test_flow_rows_need_a_pointer_and_no_sheet_row(db, w):
    b = w.batch("PROCESS_FLOW")
    w.row(b, "PROCESS_FLOW", "STEP", source_path="/steps/0")
    _violates(db, "ck_ir_locator", lambda: w.row(b, "PROCESS_FLOW", "STEP"))
    _violates(db, "ck_ir_locator",
              lambda: w.row(b, "PROCESS_FLOW", "STEP", source_path="/steps/1", sheet_row_no=2))


def test_database_staged_rows_have_no_locator(db, w):
    """RETIRE / KEPT rows come from the database — the defect the old num_nonnulls = 1 had."""
    b = w.batch("PROCESS_FLOW", import_mode="REPLACE")
    w.row(b, "PROCESS_FLOW", "FLOW_EDGE", verdict="RETIRE", payload=TARGET)
    w.row(b, "PROCESS_FLOW", "STEP_IO", verdict="KEPT", payload=TARGET)
    _violates(db, "ck_ir_locator", lambda: w.row(b, "PROCESS_FLOW", "FLOW_EDGE", verdict="RETIRE",
                                                 payload=TARGET, source_path="/edges/0"))
    s = w.batch("WBS_ITEM", import_mode="REPLACE")
    w.row(s, "WBS_ITEM", verdict="RETIRE", payload=TARGET)
    _violates(db, "ck_ir_locator",
              lambda: w.row(s, "WBS_ITEM", verdict="RETIRE", payload=TARGET, sheet_row_no=2))
    # ...and they must name what they act on (Q-3).
    _violates(db, "ck_ir_db_staged_target", lambda: w.row(s, "WBS_ITEM", verdict="RETIRE"))


# ---- ck_ir_valid_matches_errors -----------------------------------------------------------

def test_is_valid_agrees_with_error_detail(db, w):
    b = w.batch()
    w.row(b, sheet_row_no=2)
    w.row(b, sheet_row_no=3, errors=[ERROR])
    _violates(db, "ck_ir_valid_matches_errors",
              lambda: w.row(b, sheet_row_no=4, is_valid=False))
    _violates(db, "ck_ir_valid_matches_errors",
              lambda: w.row(b, sheet_row_no=5, errors=[ERROR], is_valid=True))


@pytest.mark.parametrize("not_an_array", [{}, "oops", 0])
def test_a_non_array_error_detail_is_a_check_violation_not_a_crash(db, w, not_an_array):
    """The CASE form: jsonb_array_length would raise on a non-array; the CHECK refuses instead."""
    b = w.batch()
    for valid in (True, False):
        _violates(db, "ck_ir_valid_matches_errors",
                  lambda: w.row(b, sheet_row_no=2, is_valid=valid, error_detail=json.dumps(not_an_array)))


# ---- ck_ir_kind_fits_target via fk_ir_batch (S4-2, Q-2) -----------------------------------

def test_row_kind_fits_its_batch_target(db, w):
    sheet, flow = w.batch(), w.batch("PROCESS_FLOW")
    _violates(db, "ck_ir_kind_fits_target", lambda: w.row(sheet, kind="DATA_FIELD", sheet_row_no=2))
    w.row(flow, "PROCESS_FLOW", "DATA_ENTITY", source_path="/data/0")
    _violates(db, "ck_ir_kind_fits_target",
              lambda: w.row(flow, "PROCESS_FLOW", "DATA_FIELD", source_path="/data/1"))


def test_a_row_cannot_claim_a_target_its_batch_does_not_have(db, w):
    """The carrier FK: target_entity must be the batch's own, so the kind CHECK cannot be dodged."""
    sheet = w.batch()
    _violates(db, "fk_ir_batch",
              lambda: w.row(sheet, "PROCESS_FLOW", "STEP", source_path="/steps/0"))
    _violates(db, "fk_ir_batch", lambda: w.row(sheet, "DATA_FIELD", sheet_row_no=2))


# ---- the unique keys (Q-5, Q-21) ----------------------------------------------------------

def test_business_key_is_unique_per_batch_and_kind_when_present(db, w):
    b, other = w.batch(), w.batch()
    w.row(b, sheet_row_no=2, business_key="DE-0007", verdict="UPDATE")
    _violates(db, "uq_ir_business_key",
              lambda: w.row(b, sheet_row_no=3, business_key="DE-0007", verdict="UPDATE"))
    w.row(other, sheet_row_no=2, business_key="DE-0007", verdict="UPDATE")
    w.row(b, sheet_row_no=4)                         # blank key → INSERT, any number of them
    w.row(b, sheet_row_no=5)


def test_local_key_is_unique_per_batch_and_kind_when_present(db, w):
    b = w.batch("PROCESS_FLOW")
    w.row(b, "PROCESS_FLOW", "STEP", source_path="/steps/0", local_key="S1")
    _violates(db, "uq_ir_local_key",
              lambda: w.row(b, "PROCESS_FLOW", "STEP", source_path="/steps/1", local_key="S1"))
    w.row(b, "PROCESS_FLOW", "DATA_ENTITY", source_path="/data/0", local_key="S1")   # other kind
    _violates(db, "ck_ir_flow_only_fields", lambda: w.row(w.batch(), sheet_row_no=2, local_key="S1"))


def test_one_staged_row_per_sheet_row_or_pointer(db, w):
    sheet, flow = w.batch(), w.batch("PROCESS_FLOW")
    w.row(sheet, sheet_row_no=14)
    _violates(db, "uq_ir_sheet_row", lambda: w.row(sheet, sheet_row_no=14))
    w.row(flow, "PROCESS_FLOW", "STEP", source_path="/steps/0")
    _violates(db, "uq_ir_source_path", lambda: w.row(flow, "PROCESS_FLOW", "STEP", source_path="/steps/0"))
    w.row(flow, "PROCESS_FLOW", "STEP", source_path="/steps/1")   # NULL sheet_row_no never collides


# ---- import_batch CHECKs ------------------------------------------------------------------

def test_merge_never_retires(db, w):
    _violates(db, "ck_ib_retire_needs_replace",
              lambda: w.batch("WBS_ITEM", import_mode="MERGE", row_count=1, retire_count=1))
    _violates(db, "ck_ib_retire_needs_replace",
              lambda: w.batch("PROCESS_FLOW", row_count=1, retire_count=1))
    w.batch("WBS_ITEM", import_mode="REPLACE", row_count=1, retire_count=1)
    # a sheet target has no mode: a NULL mode must not let retires through (S4-7, build fix)
    _violates(db, "ck_ib_retire_needs_replace", lambda: w.batch(row_count=1, retire_count=1))


def test_mode_and_anchor_belong_to_their_targets(db, w):
    _violates(db, "ck_ib_mode_targets", lambda: w.batch(import_mode="MERGE"))
    _violates(db, "ck_ib_mode_targets", lambda: w.batch("WBS_ITEM"))
    _violates(db, "ck_ib_flow_anchor", lambda: w.batch(anchor_bfc_node_id=w.anchor()))
    _violates(db, "ck_ib_flow_format", lambda: w.batch(source_format="vb-process-flow/1.0"))


# ---- grants (§6.6, Q-17) ------------------------------------------------------------------

def test_app_role_can_purge_rows_but_never_a_batch(db, w):
    b = w.batch()
    w.row(b, sheet_row_no=2)
    assert db.execute(text("DELETE FROM import_row WHERE import_batch_id = :b"), {"b": b}).rowcount == 1
    _denied(db, lambda: db.execute(text("DELETE FROM import_batch WHERE import_batch_id = :b"), {"b": b}))


@pytest.mark.parametrize("column, value", [
    ("project_id", 0), ("target_entity", "'ISSUE'"),
    ("uploaded_by_user_id", 0), ("uploaded_at", "now()"), ("anchor_bfc_node_id", "NULL"),
    ("source_format", "'csv'"), ("import_mode", "NULL"), ("updated_at", "now()"),
])
def test_the_import_trail_is_write_once_for_the_app_role(db, w, column, value):
    b = w.batch()
    _denied(db, lambda: db.execute(text(f"UPDATE import_batch SET {column} = {value} "
                                        "WHERE import_batch_id = :b"), {"b": b}))


def test_the_purge_can_blank_the_file_name(db, w):
    """S4-11/Q6: a file name can identify a person, so the purge (as vb_app) overwrites it."""
    b = w.batch(file_name="J Smith - salary review.xlsx")
    db.execute(text("UPDATE import_batch SET file_name = '(purged)', rows_purged_at = now() "
                    "WHERE import_batch_id = :b"), {"b": b})
    assert db.execute(text("SELECT file_name FROM import_batch WHERE import_batch_id = :b"),
                      {"b": b}).scalar_one() == "(purged)"
    _denied(db, lambda: db.execute(text("UPDATE import_batch SET file_name = '(purged)', "
                                        "uploaded_by_user_id = uploaded_by_user_id "
                                        "WHERE import_batch_id = :b"), {"b": b}))


def test_the_lifecycle_columns_stay_updatable(db, w):
    b = w.batch()
    db.execute(text("SELECT 1 FROM import_batch WHERE import_batch_id = :b FOR UPDATE"), {"b": b})
    before = db.execute(text("SELECT updated_at FROM import_batch WHERE import_batch_id = :b"),
                        {"b": b}).scalar_one()
    db.commit()                                     # now() is per transaction
    batch = db.get(ImportBatch, b)
    batch.status_code_id = _code(db, "IMPORT_STATUS", "VALIDATED")
    batch.row_count, batch.insert_count = 3, 3
    batch.file_warning_detail = [ERROR]
    db.commit()                                     # the ORM bumps row_version with the grant it has
    row = db.execute(text("SELECT row_version, updated_at FROM import_batch WHERE import_batch_id = :b"),
                     {"b": b}).one()
    assert row.row_version == 2 and row.updated_at > before    # the trigger, not the app
