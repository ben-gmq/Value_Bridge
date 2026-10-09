"""consistency_check wiring: every line is present, and the 4a lines report what their owners report."""
from services import consistency
from services.consistency import consistency_check
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture


def test_the_report_carries_the_purge_and_the_fieldless_entity_lines(client, ed, db):
    r = client.post(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"], json={"de_name": "Lonely"})
    assert r.status_code == 201, r.text
    out = consistency_check(ed["p"], db)
    assert set(out) == {"purge_overdue", "entities_without_fields"}
    assert [e["de_name"] for e in out["entities_without_fields"]] == ["Lonely"]
    assert consistency_check(None, db)["entities_without_fields"] == []   # per project only
    assert not (set(out) - consistency.INFORMATIONAL - consistency.WARNINGS)  # no line can refuse a freeze yet
