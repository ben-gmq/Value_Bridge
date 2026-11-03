"""Slice Benefits — benefits in the baseline (hash spec 7; docs/slice_benefits_spec.md §7, criteria 9–10; BN-5).
Grade 1: a mistake here changes the digest of a signed baseline or lets a frozen benefit be altered unseen, so each
claim is proven on stored digests.

Proven: a spec-6 baseline frozen before benefits existed keeps its digest and reads them as new structure, outside
every summary; a spec-7 freeze holds every live benefit and link and verifies; a changed target and a changed % count
in benefit_summary, never in the scope summary; with BENEFIT off the two tables freeze no rows; a frozen benefit or
link row cannot be altered or deleted, as the app or the owner."""
import pytest
from sqlalchemy import text

from services import freeze_set
from tests.conftest import ALL_COMPONENTS
from tests.test_baseline import bid, diff, freeze, scope
from tests.test_benefit_api import benefit, edit, put
from tests.test_components import switch
from tests.test_control import role
from tests.test_migration_0053 import owner, x  # noqa: F401 — owner is a fixture
from tests.test_process_volume import freeze_at_spec
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import sol


def _world(client, ed):
    scope(client, ed)
    b = benefit(client, ed, role(client, ed))
    s = sol(client, ed, "Billing")
    return b, s, put(client, ed, b, s, 50)


def _stored(db, b):
    return db.execute(text("SELECT content_digest, hash_spec_version FROM baseline WHERE baseline_id = :b"),
                      {"b": b}).one()


def test_a_spec_6_baseline_keeps_its_digest_and_reads_benefits_as_new_structure(client, ed, db, monkeypatch):
    scope(client, ed)
    v6 = freeze_at_spec(client, ed, monkeypatch, 6)
    before = _stored(db, v6)
    assert before.hash_spec_version == 6
    put(client, ed, benefit(client, ed, role(client, ed)), sol(client, ed, "Billing"), 50)
    detail = client.get(f"{API}/baselines/{v6}", headers=ed["h"]).json()
    assert detail["intact"] is True
    assert detail["counts"]["benefit"] is None and detail["counts"]["benefit_solution"] is None   # never frozen
    assert freeze_set.digest(db, ed["p"], frozenset(), v6, 6) == before.content_digest
    v7 = bid(freeze(client, ed))
    assert _stored(db, v7).hash_spec_version == 7
    d = diff(client, ed, v6, v7)
    assert d["entities"]["benefit"]["not_frozen_in"] == "a" and d["entities"]["benefit"]["joined_at_spec"] == 7
    assert d["benefit_summary"]["ADDED"] == 0 and d["issue_summary"]["ADDED"] == 0
    assert d["summary"]["ADDED"] == 3                   # org unit, org role, solution are scope; benefits are not
    assert _stored(db, v6).content_digest == before.content_digest


def test_a_spec_7_freeze_holds_benefits_and_links_and_verifies(client, ed, db):
    b, _, lnk = _world(client, ed)
    v = bid(freeze(client, ed))
    detail = client.get(f"{API}/baselines/{v}", headers=ed["h"]).json()
    assert detail["intact"] is True
    assert (detail["counts"]["benefit"], detail["counts"]["benefit_solution"]) == (1, 1)
    row = db.execute(text("SELECT benefit_number, status_code, status_label, target_value FROM baseline_benefit "
                          "WHERE baseline_id = :b"), {"b": v}).one()
    assert (row.benefit_number, row.status_code, str(row.target_value)) == ("BEN-0001", "FORECAST", "160.00")
    src = db.execute(text("SELECT source_id, contribution_pct FROM baseline_benefit_solution WHERE baseline_id = :b"),
                     {"b": v}).one()
    assert (src.source_id, str(src.contribution_pct)) == (lnk["benefit_solution_id"], "50.00")


def test_a_changed_target_and_percent_count_apart_from_scope(client, ed, db):
    """Criterion 10 / BN-5: a re-forecast benefit or a changed % is not a scope change."""
    b, s, _ = _world(client, ed)
    v = bid(freeze(client, ed))
    edit(client, ed, b, target_value="200")
    put(client, ed, b, s, 40)
    d = diff(client, ed, v, "live")
    assert [r["change"] for r in d["entities"]["benefit"]["rows"]] == ["CHANGED"]
    assert [r["change"] for r in d["entities"]["benefit_solution"]["rows"]] == ["CHANGED"]
    assert d["benefit_summary"]["CHANGED"] == 2
    assert d["summary"] == {"ADDED": 0, "CHANGED": 0, "REMOVED": 0, "MOVED": 0}
    v2 = bid(freeze(client, ed))
    assert _stored(db, v).content_digest != _stored(db, v2).content_digest


def test_benefit_off_freezes_no_rows(client, ed, world):
    scope(client, ed)
    switch(client, world, ed["p"], [c for c in ALL_COMPONENTS if c != "BENEFIT"])
    v = bid(freeze(client, ed))
    counts = client.get(f"{API}/baselines/{v}", headers=ed["h"]).json()["counts"]
    assert counts["benefit"] == 0 and counts["benefit_solution"] == 0


@pytest.mark.parametrize("table", ["baseline_benefit", "baseline_benefit_solution"])
def test_frozen_rows_refuse_update_and_delete_as_app_and_owner(client, ed, db, owner, table):
    _world(client, ed)
    v = bid(freeze(client, ed))
    for stmt in (f"UPDATE {table} SET project_id = project_id WHERE baseline_id = {v}",
                 f"DELETE FROM {table} WHERE baseline_id = {v}"):
        with pytest.raises(Exception):
            db.execute(text(stmt))
        db.rollback()
        with pytest.raises(Exception):
            x(owner, stmt)
