"""consistency_check wiring: every line is present, and the 4a lines report what their owners report."""
from services import consistency
from services.consistency import consistency_check
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture


def test_the_report_carries_the_purge_and_the_fieldless_entity_lines(client, ed, db):
    r = client.post(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"], json={"de_name": "Lonely"})
    assert r.status_code == 201, r.text
    out = consistency_check(ed["p"], db)
    assert set(out) == {"purge_overdue", "entities_without_fields", "brsol_under_inactive",
                        "fr_under_inactive_solution", "appsol_under_inactive", "appnode_under_inactive",
                        "as_is_allocated", "as_is_support_by_to_be", "interface_under_inactive"}
    assert [e["de_name"] for e in out["entities_without_fields"]] == ["Lonely"]
    assert consistency_check(None, db)["entities_without_fields"] == []   # per project only
    # The must-be-empty lines (Slices 5 and 6a) are the ones that can refuse a freeze.
    must_be_empty = {"brsol_under_inactive", "fr_under_inactive_solution", "appsol_under_inactive",
                     "appnode_under_inactive", "as_is_allocated", "interface_under_inactive"}
    assert set(out) - consistency.INFORMATIONAL - consistency.WARNINGS == must_be_empty
    assert all(out[k] == [] for k in must_be_empty)
