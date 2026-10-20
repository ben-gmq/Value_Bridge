"""Slice 15 — waves in the baseline (hash spec 6; criterion 7; Q-58). Grade 1: a mistake here changes the digest of
every signed baseline or leaves a spec-6 one unverifiable, so each claim is proven on stored digests.

Proven: a baseline frozen at spec 5 keeps its digest and verifies after waves exist, and its comparison with a spec-6
one lists the wave tables as new structure; a spec-6 freeze holds every live wave, split and dependency and verifies;
a reorder shows as MOVED, a status change not at all, a changed split as CHANGED; a frozen wave cannot be altered;
with PHASING off and nothing live, the three tables freeze no rows."""
import pytest
from sqlalchemy import text

from services import freeze_set
from tests.test_baseline import bid, diff, freeze, owner_exec, scope
from tests.test_phasing_api import depend, put_split, wave
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import sol


def _world(client, ed):
    scope(client, ed)
    a, b = sol(client, ed, "ERP"), sol(client, ed, "Workflow")
    w1, w2 = wave(client, ed, "W1"), wave(client, ed, "W2", "Manufacturing")
    assert put_split(client, ed, a, [(w1, 40), (w2, 60)]).status_code == 200
    assert depend(client, ed, b, a).status_code == 201
    return a, b, w1, w2


def _stored(db, b):
    return db.execute(text("SELECT content_digest, hash_spec_version FROM baseline WHERE baseline_id = :b"),
                      {"b": b}).one()


def test_a_spec_5_baseline_keeps_its_digest_and_reads_waves_as_new_structure(client, ed, db, monkeypatch):
    scope(client, ed)
    monkeypatch.setattr(freeze_set, "CURRENT_HASH_SPEC", 5)
    monkeypatch.setattr("services.baseline.CURRENT_HASH_SPEC", 5)
    try:
        v5 = bid(freeze(client, ed))
    finally:
        monkeypatch.undo()
    before = _stored(db, v5)
    assert before.hash_spec_version == 5
    a, b = sol(client, ed, "ERP"), sol(client, ed, "Workflow")
    w1 = wave(client, ed, "W1")
    put_split(client, ed, a, [(w1, 100)])
    depend(client, ed, b, a)                                                  # waves now exist in the project
    detail = client.get(f"{API}/baselines/{v5}", headers=ed["h"]).json()
    assert detail["intact"] is True                                           # still verifies
    for t in ("phase", "solution_phase", "solution_dependency"):
        assert detail["counts"][t] is None, t                                 # never frozen, not 0
    assert freeze_set.digest(db, ed["p"], frozenset(), v5, 5) == before.content_digest
    v6 = bid(freeze(client, ed))
    assert _stored(db, v6).hash_spec_version == 6
    assert client.get(f"{API}/baselines/{v6}", headers=ed["h"]).json()["intact"] is True
    d = diff(client, ed, v5, v6)
    assert d["entities"]["phase"]["not_frozen_in"] == "a" and d["entities"]["phase"]["joined_at_spec"] == 6
    assert _stored(db, v5).content_digest == before.content_digest            # and the old digest never moved


def test_a_spec_6_freeze_holds_waves_splits_and_dependencies_with_the_status_copied_not_hashed(client, ed, db):
    a, b, w1, _ = _world(client, ed)
    v = bid(freeze(client, ed))
    detail = client.get(f"{API}/baselines/{v}", headers=ed["h"]).json()
    assert detail["intact"] is True
    assert (detail["counts"]["phase"], detail["counts"]["solution_phase"], detail["counts"]["solution_dependency"]) \
        == (2, 2, 1)
    row = db.execute(text("SELECT phase_code, seq_no, status_code, status_label FROM baseline_phase "
                          "WHERE baseline_id = :b AND source_id = :s"), {"b": v, "s": w1["phase_id"]}).one()
    assert (row.phase_code, row.seq_no, row.status_code) == ("W1", 1, "PLANNED")
    hashed = freeze_set.BY_TABLE["phase"].hash_columns[6]
    assert hashed == ("phase_code", "phase_name", "start_date", "end_date")   # Q-58
    assert freeze_set.BY_TABLE["phase"].position_columns == ("seq_no",)
    assert "portion_pct" in freeze_set.BY_TABLE["solution_phase"].hash_columns[6]


def test_a_reorder_is_moved_a_status_change_is_nothing_and_a_new_split_is_changed(client, ed, db):
    a, _, w1, w2 = _world(client, ed)
    v = bid(freeze(client, ed))
    cur = {w["phase_id"]: w for w in client.get(f"{API}/projects/{ed['p']}/phases", headers=ed["h"]).json()}
    r = client.post(f"{API}/projects/{ed['p']}/phases/reorder", headers=ed["h"],
                    json={"order": [{"id": w2["phase_id"], "row_version": cur[w2["phase_id"]]["row_version"]},
                                    {"id": w1["phase_id"], "row_version": cur[w1["phase_id"]]["row_version"]}]})
    assert r.status_code == 200
    w1_now = client.get(f"{API}/phases/{w1['phase_id']}", headers=ed["h"]).json()
    assert client.patch(f"{API}/phases/{w1['phase_id']}", headers=ed["h"],
                        json={"row_version": w1_now["row_version"], "status_code": "IN_DELIVERY"}).status_code == 200
    d = diff(client, ed, v, "live")
    assert sorted(x["change"] for x in d["entities"]["phase"]["rows"]) == ["MOVED", "MOVED"]
    assert d["entities"]["solution_phase"]["rows"] == []
    assert put_split(client, ed, a, [(w1, 50), (w2, 50)]).status_code == 200
    d = diff(client, ed, v, "live")
    assert sorted(x["change"] for x in d["entities"]["solution_phase"]["rows"]) == ["CHANGED", "CHANGED"]
    v2 = bid(freeze(client, ed))
    assert client.get(f"{API}/baselines/{v2}", headers=ed["h"]).json()["intact"] is True
    assert _stored(db, v).content_digest != _stored(db, v2).content_digest


def test_a_frozen_wave_cannot_be_altered(client, ed):
    _world(client, ed)
    v = bid(freeze(client, ed))
    for t, col in (("baseline_phase", "phase_name"), ("baseline_solution_phase", "portion_pct"),
                   ("baseline_solution_dependency", "note")):
        with pytest.raises(Exception, match=f"UPDATE on {t} is not allowed: the row is immutable"):
            owner_exec(f"UPDATE {t} SET {col} = {col} WHERE baseline_id = :b", b=v)


def test_with_phasing_off_and_nothing_live_the_three_tables_freeze_no_rows(client, ed, world):
    from tests.conftest import ALL_COMPONENTS
    from tests.test_components import switch
    scope(client, ed)
    switch(client, world, ed["p"], [c for c in ALL_COMPONENTS if c != "PHASING"])
    v = bid(freeze(client, ed))
    counts = client.get(f"{API}/baselines/{v}", headers=ed["h"]).json()["counts"]
    assert (counts["phase"], counts["solution_phase"], counts["solution_dependency"]) == (0, 0, 0)
