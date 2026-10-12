"""Grade 1 — the hash-spec bump (slice10b_schema §5.3, Q-14): a baseline frozen before an entity joined the
freeze set still passes its integrity check after the entity is added, and its digest is byte-identical to
what the pre-10b algorithm produced.

The golden digest below is a LITERAL copy of the pre-10b `freeze_set.digest` over a baseline's shadows (the
24 spec-1 entities, every one of them, in freeze order). It deliberately does not call the new code, so a
change to the new digest that would break old baselines cannot also move the reference it is compared to."""
import hashlib

import pytest

from sqlalchemy import text

from tests.test_baseline import bid, diff, freeze, owner_exec, scope
from tests.test_function_requirement_api import fr
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol

PRE_10B_ENTITIES = ("org_unit", "org_role", "bfc_node", "data_entity", "data_field", "external_entity",
                    "process_trigger", "bfc_node_data_entity", "bfc_node_org_role", "bfc_node_external_flow",
                    "bfc_node_trigger", "business_requirement", "br_data_entity", "br_org_role", "application",
                    "solution", "br_solution", "function_requirement", "fr_interface", "fr_interface_data_entity",
                    "application_solution", "application_bfc_node", "effort_rate", "project_component")


def golden_pre_10b_digest(db, baseline_id: int) -> str:
    """The pre-10b algorithm, verbatim in effect: sha256 over "table=<id:hash,...>" lines joined by \\n."""
    parts = []
    for table in PRE_10B_ENTITIES:
        agg = db.execute(text(f"SELECT coalesce(string_agg(source_id::text || ':' || content_hash, ',' "
                              f"ORDER BY source_id), '') FROM baseline_{table} WHERE baseline_id = :b"),
                         {"b": baseline_id}).scalar()
        parts.append(f"{table}={agg}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def freeze_at_spec_1(client, ed, monkeypatch):
    """A freeze exactly as the pre-10b code made it: hash spec 1, only the spec-1 entities."""
    from services import freeze_set
    monkeypatch.setattr(freeze_set, "CURRENT_HASH_SPEC", 1)
    monkeypatch.setattr("services.baseline.CURRENT_HASH_SPEC", 1)
    try:
        return bid(freeze(client, ed))
    finally:
        monkeypatch.undo()


def stored(db, baseline_id):
    return db.execute(text("SELECT content_digest, hash_spec_version FROM baseline WHERE baseline_id = :b"),
                      {"b": baseline_id}).one()


def test_the_spec_1_set_is_exactly_the_pre_10b_set():
    from services import freeze_set
    assert freeze_set.SPEC_1_ENTITIES == PRE_10B_ENTITIES
    assert tuple(e.table for e in freeze_set.at_spec(1)) == PRE_10B_ENTITIES
    assert freeze_set.CURRENT_HASH_SPEC >= 2


def test_a_spec_1_baseline_matches_the_golden_digest_and_still_verifies(client, ed, db, monkeypatch):
    w = scope(client, ed)
    s = sol(client, ed)
    assert link(client, ed, w["br1"]["br_id"], s["solution_id"]).status_code == 201
    fr(client, ed, solution_id=s["solution_id"])
    v1 = freeze_at_spec_1(client, ed, monkeypatch)
    digest, spec = stored(db, v1)
    assert spec == 1
    assert digest == golden_pre_10b_digest(db, v1)           # what the old code wrote, byte for byte
    detail = client.get(f"{API}/baselines/{v1}", headers=ed["h"]).json()
    assert detail["intact"] is True
    # an entity that joined after spec 1 reads "not frozen at this spec", never 0
    for e in PRE_10B_ENTITIES:
        assert detail["counts"][e] is not None
    for e, n in detail["counts"].items():
        if e not in PRE_10B_ENTITIES:
            assert n is None
    # the live scope keeps moving; the old baseline neither changes nor fails
    fr(client, ed, name="Credit form", solution_id=s["solution_id"])
    assert client.get(f"{API}/baselines/{v1}", headers=ed["h"]).json()["intact"] is True
    diff(client, ed, v1, "live")                               # 200: require_intact passed
    assert stored(db, v1)[0] == golden_pre_10b_digest(db, v1)


def test_a_current_spec_baseline_verifies_beside_a_spec_1_one(client, ed, db, monkeypatch):
    scope(client, ed)
    v1 = freeze_at_spec_1(client, ed, monkeypatch)
    v2 = bid(freeze(client, ed))
    from services.freeze_set import CURRENT_HASH_SPEC
    assert stored(db, v2)[1] == CURRENT_HASH_SPEC
    for b in (v1, v2):
        assert client.get(f"{API}/baselines/{b}", headers=ed["h"]).json()["intact"] is True
    d = diff(client, ed, v1, v2)
    assert sum(d["summary"].values()) == 0, d["summary"]       # nothing changed between them


def test_tampering_with_a_spec_1_baseline_still_fails(client, ed, monkeypatch):
    scope(client, ed)
    v1 = freeze_at_spec_1(client, ed, monkeypatch)
    owner_exec("ALTER TABLE baseline_bfc_node DISABLE TRIGGER trg_baseline_bfc_node_immutable;"
               "UPDATE baseline_bfc_node SET node_name = 'Rewritten' WHERE baseline_id = :b;"
               "ALTER TABLE baseline_bfc_node ENABLE TRIGGER trg_baseline_bfc_node_immutable", b=v1)
    assert client.get(f"{API}/baselines/{v1}", headers=ed["h"]).json()["intact"] is False


# ---- the first diff after 10b (§5.3, DR10b-P1/D1/D2) ---------------------------------------------

def _mapped(client, ed):
    """BR-1 answered by a solution tagged on two FRs: two derived paths, backfilled as links."""
    w = scope(client, ed)
    s = sol(client, ed)
    assert link(client, ed, w["br1"]["br_id"], s["solution_id"]).status_code == 201
    a = fr(client, ed, name="Order form", solution_id=s["solution_id"])
    b = fr(client, ed, name="Order report", fr_type="REPORT", solution_id=s["solution_id"])
    return w, s, a, b


def _backfill(client, ed, w, *frs):
    """What 0051 writes for these paths: one link per (BR, FR), no note."""
    for f in frs:
        r = client.post(f"{API}/business-requirements/{w['br1']['br_id']}/function-requirements", headers=ed["h"],
                        json={"fr_id": f["fr_id"]})
        assert r.status_code == 201, r.text


def links_of(d):
    return d["entities"]["br_function_requirement"]


def test_a_pre_10b_side_derives_its_links_in_every_direction(client, ed, monkeypatch):
    w, s, a, b = _mapped(client, ed)
    v1 = freeze_at_spec_1(client, ed, monkeypatch)
    v1b = freeze_at_spec_1(client, ed, monkeypatch)
    _backfill(client, ed, w, a, b)
    v2 = bid(freeze(client, ed))
    for x, y, derived in ((v1, v1b, ["a", "b"]), (v1, v2, ["a"]), (v2, v1, ["b"]), (v1, "live", ["a"])):
        d = diff(client, ed, x, y)
        assert links_of(d)["rows"] == [], (x, y, links_of(d)["rows"])        # zero false link changes
        assert links_of(d)["derived_sides"] == derived
        assert sum(d["summary"].values()) == 0, (x, y, d["summary"])
    # a real new link shows as exactly one ADDED, against a derived side too
    c = fr(client, ed, name="Credit batch", fr_type="BATCH")
    _backfill(client, ed, w, c)
    for x in (v1, v2):
        rows = links_of(diff(client, ed, x, "live"))["rows"]
        assert [r["change"] for r in rows] == ["ADDED"], rows
        assert w["br1"]["br_number"] in rows[0]["label"] and c["fr_number"] in rows[0]["label"]


def test_a_note_written_after_a_v1_baseline_reads_changed(client, ed, monkeypatch):
    w, s, a, b = _mapped(client, ed)
    v1 = freeze_at_spec_1(client, ed, monkeypatch)
    _backfill(client, ed, w, a, b)
    row = next(r for r in client.get(f"{API}/business-requirements/{w['br1']['br_id']}/function-requirements",
                                     headers=ed["h"]).json() if r["fr_id"] == a["fr_id"])
    r = client.patch(f"{API}/business-requirements/{w['br1']['br_id']}/function-requirements/"
                     f"{row['br_function_requirement_id']}", headers=ed["h"],
                     json={"row_version": row["row_version"], "coverage_note": "only the validation half"})
    assert r.status_code == 200
    rows = links_of(diff(client, ed, v1, "live"))["rows"]
    assert [(r["change"], r["fields"], r["after"]) for r in rows] == [
        ("CHANGED", ["coverage_note"], {"coverage_note": "only the validation half"})]


def test_priced_untraced_reads_the_derived_links(client, ed, monkeypatch):
    from tests.test_effort_api import rate
    w, s, a, b = _mapped(client, ed)
    for f in (a, b):
        assert rate(client, ed, f, "SIMPLE").status_code == 200
    v1 = freeze_at_spec_1(client, ed, monkeypatch)
    _backfill(client, ed, w, a, b)
    loose = fr(client, ed, name="Loose form")                               # untraced, added
    assert rate(client, ed, loose, "SIMPLE").status_code == 200
    cur = client.get(f"{API}/function-requirements/{b['fr_id']}", headers=ed["h"]).json()
    rows = client.get(f"{API}/business-requirements/{w['br1']['br_id']}/function-requirements", headers=ed["h"]).json()
    rb = next(r for r in rows if r["fr_id"] == b["fr_id"])
    client.delete(f"{API}/business-requirements/{w['br1']['br_id']}/function-requirements/"
                  f"{rb['br_function_requirement_id']}", headers=ed["h"], params={"row_version": rb["row_version"]})
    cur = client.get(f"{API}/function-requirements/{b['fr_id']}", headers=ed["h"]).json()
    assert client.delete(f"{API}/function-requirements/{b['fr_id']}", headers=ed["h"],
                         params={"row_version": cur["row_version"]}).status_code == 204
    p = diff(client, ed, v1, "live", priced=True)["pricing"]
    lines = {x["fr_name"]: x for x in p["lines"]}
    assert lines["Order report"]["change"] == "REMOVED" and lines["Order report"]["untraced"] is False  # traced in v1
    assert lines["Loose form"]["untraced"] is True
    assert p["totals"]["untraced_days"] == pytest.approx(lines["Loose form"]["delta_days"])
    assert p["totals"]["unassigned_days"] == pytest.approx(lines["Loose form"]["delta_days"])


def test_tampering_with_a_frozen_link_fails_the_check(client, ed):
    w, s, a, b = _mapped(client, ed)
    _backfill(client, ed, w, a)
    v2 = bid(freeze(client, ed))
    owner_exec("ALTER TABLE baseline_br_function_requirement DISABLE TRIGGER "
               "trg_baseline_br_function_requirement_immutable;"
               "UPDATE baseline_br_function_requirement SET coverage_note = 'slipped in' WHERE baseline_id = :b;"
               "ALTER TABLE baseline_br_function_requirement ENABLE TRIGGER "
               "trg_baseline_br_function_requirement_immutable", b=v2)
    assert client.get(f"{API}/baselines/{v2}", headers=ed["h"]).json()["intact"] is False


def test_a_link_row_smuggled_into_a_spec_1_baseline_fails_the_check(client, ed, monkeypatch):
    w, s, a, b = _mapped(client, ed)
    v1 = freeze_at_spec_1(client, ed, monkeypatch)
    _backfill(client, ed, w, a)
    owner_exec("ALTER TABLE baseline_br_function_requirement DISABLE TRIGGER "
               "trg_baseline_br_function_requirement_insert_guard;"
               "INSERT INTO baseline_br_function_requirement (baseline_id, source_id, br_id, fr_id, content_hash) "
               "SELECT :b, br_function_requirement_id, br_id, fr_id, repeat('0', 64) FROM br_function_requirement;"
               "ALTER TABLE baseline_br_function_requirement ENABLE TRIGGER "
               "trg_baseline_br_function_requirement_insert_guard", b=v1)
    assert client.get(f"{API}/baselines/{v1}", headers=ed["h"]).json()["intact"] is False
