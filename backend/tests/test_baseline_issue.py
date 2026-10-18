"""Slice 14 — issues in the baseline (hash spec 5; criterion 8; I-5, I-8, I-14, I-15). Grade 1: a mistake here changes
the digest of every signed baseline or leaves a spec-5 one unverifiable, so each claim is proven on stored digests.

Proven: a baseline frozen at spec 4 keeps its digest and verifies after issues exist, and its comparison with a spec-5
one lists issues as new structure, not scope; a spec-5 freeze holds every live issue and link with status and
resolution hashed and verifies; resolving shows CHANGED, counted apart from scope (I-14); unlink + relink is no change
(the same source row, S1-7); a frozen issue row cannot be altered; with ISSUE off the two tables freeze no rows;
a comparison shows the raiser's current name (I-15)."""
import pytest
from sqlalchemy import text

from services import freeze_set
from tests.test_baseline import bid, diff, freeze, scope
from tests.test_issue_api import edit, get_issue, issue, link, resolve, stakeholder, unlink
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture


def _issue_world(client, ed):
    w = scope(client, ed)
    s = stakeholder(client, ed, "Anan")
    i = issue(client, ed, s, "Credit field missing", severity_code="CRITICAL")
    lnk = link(client, ed, i, w["br1"])
    return w, s, i, lnk


def _stored(db, b):
    return db.execute(text("SELECT content_digest, hash_spec_version FROM baseline WHERE baseline_id = :b"),
                      {"b": b}).one()


def test_a_spec_4_baseline_keeps_its_digest_and_reads_issues_as_new_structure(client, ed, db, monkeypatch):
    scope(client, ed)
    monkeypatch.setattr(freeze_set, "CURRENT_HASH_SPEC", 4)
    monkeypatch.setattr("services.baseline.CURRENT_HASH_SPEC", 4)
    try:
        v4 = bid(freeze(client, ed))
    finally:
        monkeypatch.undo()
    before = _stored(db, v4)
    assert before.hash_spec_version == 4
    s = stakeholder(client, ed, "Anan")
    issue(client, ed, s)                                                      # issues now exist in the project
    detail = client.get(f"{API}/baselines/{v4}", headers=ed["h"]).json()
    assert detail["intact"] is True                                           # still verifies
    assert detail["counts"]["issue"] is None and detail["counts"]["issue_br"] is None   # never frozen, not 0
    assert freeze_set.digest(db, ed["p"], frozenset(), v4, 4) == before.content_digest
    v5 = bid(freeze(client, ed))
    assert _stored(db, v5).hash_spec_version == 5
    assert client.get(f"{API}/baselines/{v5}", headers=ed["h"]).json()["intact"] is True
    d = diff(client, ed, v4, v5)
    assert d["entities"]["issue"]["not_frozen_in"] == "a" and d["entities"]["issue"]["joined_at_spec"] == 5
    assert d["issue_summary"]["ADDED"] == 0 and d["summary"]["ADDED"] == 0  # new structure, neither scope nor issues
    assert _stored(db, v4).content_digest == before.content_digest            # and the old digest never moved


def test_a_spec_5_freeze_holds_issues_and_links_with_status_and_resolution_hashed(client, ed, db):
    _, _, i, lnk = _issue_world(client, ed)
    v = bid(freeze(client, ed))
    detail = client.get(f"{API}/baselines/{v}", headers=ed["h"]).json()
    assert detail["intact"] is True
    assert (detail["counts"]["issue"], detail["counts"]["issue_br"]) == (1, 1)
    row = db.execute(text("SELECT status_code, status_label, severity_code, resolution, raised_by_stakeholder_id "
                          "FROM baseline_issue WHERE baseline_id = :b"), {"b": v}).one()
    assert (row.status_code, row.severity_code, row.resolution) == ("OPEN", "CRITICAL", None)
    assert "status_code" in freeze_set.BY_TABLE["issue"].hash_columns[5]                       # I-5
    assert "resolution" in freeze_set.BY_TABLE["issue"].hash_columns[5]
    assert "recorded_by_user_id" not in freeze_set.BY_TABLE["issue"].hash_columns[5]          # copied, not hashed
    src = db.execute(text("SELECT source_id FROM baseline_issue_br WHERE baseline_id = :b"), {"b": v}).scalar_one()
    assert src == lnk["issue_br_id"]


def test_resolving_shows_changed_apart_from_scope_and_relinking_is_no_change(client, ed, db):
    w, _, i, lnk = _issue_world(client, ed)
    v = bid(freeze(client, ed))
    assert unlink(client, ed, i, lnk).status_code == 204
    again = link(client, ed, i, w["br1"])
    assert again["issue_br_id"] == lnk["issue_br_id"]
    assert resolve(client, ed, i, resolution="Field added").status_code == 200
    d = diff(client, ed, v, "live")
    rows = d["entities"]["issue"]["rows"]
    assert [(r["change"], set(r["fields"]) >= {"status_code", "resolution"}) for r in rows] == [("CHANGED", True)]
    assert d["entities"]["issue_br"]["rows"] == []                             # relink: the same row, no change
    assert d["issue_summary"]["CHANGED"] == 1                                  # I-14
    assert d["summary"] == {"ADDED": 0, "CHANGED": 0, "REMOVED": 0, "MOVED": 0}   # scope untouched
    v2 = bid(freeze(client, ed))
    assert client.get(f"{API}/baselines/{v2}", headers=ed["h"]).json()["intact"] is True
    assert _stored(db, v).content_digest != _stored(db, v2).content_digest    # the status is in the digest


def test_a_comparison_shows_the_raisers_current_name(client, ed):
    w, s, i, _ = _issue_world(client, ed)
    other = stakeholder(client, ed, "Bee")
    v = bid(freeze(client, ed))
    assert edit(client, ed, i, raised_by_stakeholder_id=other["stakeholder_id"]).status_code == 200
    rv = client.get(f"{API}/stakeholders/{s['stakeholder_id']}", headers=ed["h"]).json()["row_version"]
    client.patch(f"{API}/stakeholders/{s['stakeholder_id']}", headers=ed["h"],
                 json={"row_version": rv, "stakeholder_name": "Anan Renamed"})
    row = diff(client, ed, v, "live")["entities"]["issue"]["rows"][0]
    assert (row["before"]["raised_by_stakeholder_id"], row["after"]["raised_by_stakeholder_id"]) == \
        ("Anan Renamed", "Bee")                                                # I-15: today's names
    assert get_issue(client, ed, i)["raised_by_stakeholder_id"] == other["stakeholder_id"]


def test_a_frozen_issue_cannot_be_altered(client, ed, db):
    from tests.test_baseline import owner_exec
    _issue_world(client, ed)
    v = bid(freeze(client, ed))
    with pytest.raises(Exception, match="UPDATE on baseline_issue is not allowed: the row is immutable"):
        owner_exec("UPDATE baseline_issue SET resolution = 'rewritten' WHERE baseline_id = :b", b=v)
    with pytest.raises(Exception, match="UPDATE on baseline_issue_br is not allowed: the row is immutable"):
        owner_exec("UPDATE baseline_issue_br SET br_id = br_id WHERE baseline_id = :b", b=v)


def test_with_issue_off_live_issues_refuse_the_freeze_and_none_freeze_no_rows(client, ed, world, db):
    """A gate never drops a live row silently ([Q-12]): the app cannot switch ISSUE off under live issues (R10), so
    they are put back as the owner after the switch, and the freeze must refuse naming them (sara D L1). With none
    live, the two tables freeze no rows."""
    from tests.conftest import ALL_COMPONENTS
    from tests.test_baseline import owner_exec
    from tests.test_components import switch
    _, s, i, lnk = _issue_world(client, ed)
    assert client.delete(f"{API}/issues/{i['issue_id']}/brs/{lnk['issue_br_id']}", headers=ed["h"],
                         params={"row_version": lnk["row_version"]}).status_code == 204
    rv = get_issue(client, ed, i)["row_version"]
    assert client.delete(f"{API}/issues/{i['issue_id']}", headers=ed["h"],
                         params={"row_version": rv}).status_code == 204
    srv = client.get(f"{API}/stakeholders/{s['stakeholder_id']}", headers=ed["h"]).json()["row_version"]
    assert client.delete(f"{API}/stakeholders/{s['stakeholder_id']}", headers=ed["h"],
                         params={"row_version": srv}).status_code == 204
    switch(client, world, ed["p"], [c for c in ALL_COMPONENTS if c != "ISSUE"])
    v = bid(freeze(client, ed))                                               # none live: nothing frozen
    counts = client.get(f"{API}/baselines/{v}", headers=ed["h"]).json()["counts"]
    assert (counts["issue"], counts["issue_br"]) == (0, 0)
    owner_exec("UPDATE stakeholder SET is_active = true, deleted_at = NULL, deleted_by = NULL; "
               "UPDATE issue SET is_active = true, deleted_at = NULL, deleted_by = NULL")
    p = client.get(f"{API}/projects/{ed['p']}/baselines/next", headers=ed["h"], params={"bump": "MINOR"}).json()
    r = client.post(f"{API}/projects/{ed['p']}/baselines/freeze", headers=ed["h"],
                    json={"bump": "MINOR", "confirm_text": p["confirm_text"], "preview_digest": p["preview_digest"]})
    off = r.json()["detail"]["freeze_blocking"]["rows_in_off_component"] if r.status_code == 409 else []
    assert r.status_code == 409 and any(x["component"] == "ISSUE" and "ISS-0001" in x["sample"] for x in off), r.text
