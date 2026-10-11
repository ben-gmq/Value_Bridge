"""consistency_check wiring: every line is present, and the 4a lines report what their owners report.
7c adds process_missing_input / process_missing_output (FREEZE_BLOCKING_WARNINGS, D-38) and
as_is_support_on_to_be (INFORMATIONAL, Q-23)."""
from services import consistency
from services.consistency import consistency_check
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture


def test_the_report_carries_the_purge_and_the_fieldless_entity_lines(client, ed, db):
    r = client.post(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"], json={"de_name": "Lonely"})
    assert r.status_code == 201, r.text
    out = consistency_check(ed["p"], db)
    assert set(out) == {"purge_overdue", "entities_without_fields", "brsol_under_inactive",
                        "fr_under_inactive_solution", "appsol_under_inactive", "appnode_under_inactive",
                        "as_is_allocated", "as_is_support_by_to_be", "interface_under_inactive",
                        "entities_keys_only", "rows_in_off_component",             # + 7a (D-39, DR7-P2)
                        "process_missing_input", "process_missing_output", "as_is_support_on_to_be"}   # + 7c
    assert [e["de_name"] for e in out["entities_without_fields"]] == ["Lonely"]
    assert consistency_check(None, db)["entities_without_fields"] == []   # per project only
    # The must-be-empty lines (Slices 5 and 6a) are the ones that can refuse a freeze.
    must_be_empty = {"brsol_under_inactive", "fr_under_inactive_solution", "appsol_under_inactive",
                     "appnode_under_inactive", "as_is_allocated", "interface_under_inactive"}
    assert set(out) - consistency.INFORMATIONAL - consistency.WARNINGS \
        - consistency.FREEZE_BLOCKING_WARNINGS == must_be_empty
    assert all(out[k] == [] for k in must_be_empty)
    assert consistency.FREEZE_BLOCKING_WARNINGS == {"process_missing_input", "process_missing_output",
                                                  "rows_in_off_component"}     # + slice 8 [Q-12]
    assert "as_is_support_on_to_be" in consistency.INFORMATIONAL
    assert not consistency.FREEZE_BLOCKING_WARNINGS & (consistency.INFORMATIONAL | consistency.WARNINGS)
    none = consistency_check(None, db)                                # per project only
    assert none["process_missing_input"] == none["process_missing_output"] == []


def test_the_process_io_lines_name_a_process_with_no_input_or_output(client, ed, db):
    """D-38: amber while editing — the lines list the gaps; the DFD tests prove the triggers and
    external inputs that close them."""
    a = client.post(f"{API}/projects/{ed['p']}/bfc-nodes", headers=ed["h"], json={"node_name": "Sales"}).json()
    b = client.post(f"{API}/projects/{ed['p']}/bfc-nodes", headers=ed["h"],
                    json={"node_name": "Orders", "parent_bfc_node_id": a["bfc_node_id"]}).json()
    s = client.post(f"{API}/projects/{ed['p']}/bfc-nodes", headers=ed["h"],
                    json={"node_name": "Take order", "parent_bfc_node_id": b["bfc_node_id"], "is_process": True}).json()
    out = consistency_check(ed["p"], db)
    assert [x["bfc_node_id"] for x in out["process_missing_input"]] == [s["bfc_node_id"]]
    assert [x["bfc_node_id"] for x in out["process_missing_output"]] == [s["bfc_node_id"]]
    de = client.post(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"], json={"de_name": "Order"}).json()
    for direction in ("I", "O"):
        r = client.post(f"{API}/bfc-nodes/{s['bfc_node_id']}/data-entities", headers=ed["h"],
                        json={"data_entity_id": de["data_entity_id"], "direction": direction})
        assert r.status_code == 201, r.text
    out = consistency_check(ed["p"], db)
    assert out["process_missing_input"] == out["process_missing_output"] == []
