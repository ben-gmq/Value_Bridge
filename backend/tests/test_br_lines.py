"""Slice 11a — numbered requirement lines (D-59, docs/slice11_schema.md §1, §4, §5).

Grade 1 for one concern only: a baseline is the scope record a dispute quotes, so a frozen line must be in the
baseline, hashed over exactly the agreed columns (checked here against an independent computation, not the code
under test), immutable, and an older baseline must keep verifying once lines exist. Everything else is grade 2."""
import hashlib

import pytest
from sqlalchemy import text
from services.freeze_set import CURRENT_HASH_SPEC

from tests.test_baseline import bid, diff, freeze, owner_exec, patch_br, preview, scope
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture

KINDS = ("RULE", "CALCULATION", "VALIDATION", "OUTPUT", "CONTROL")


def add(client, ed, br, kind="RULE", text_="Only active customers may get credit.", priority=None, expect=201,
        headers=None, **extra):
    r = client.post(f"{API}/business-requirements/{br['br_id']}/lines", headers=headers or ed["h"],
                    json={"line_kind_code": kind, "priority_code": priority, "line_text": text_, **extra})
    assert r.status_code == expect, r.text
    return r.json()


def lines(client, ed, br, **q):
    r = client.get(f"{API}/business-requirements/{br['br_id']}/lines", headers=ed["h"], params=q)
    assert r.status_code == 200, r.text
    return r.json()


def edit(client, ed, br, line, expect=200, **body):
    r = client.patch(f"{API}/business-requirements/{br['br_id']}/lines/{line['br_requirement_line_id']}",
                     headers=ed["h"], json={"row_version": line["row_version"], **body})
    assert r.status_code == expect, r.text
    return r.json()


def retire(client, ed, br, line, expect=204):
    r = client.delete(f"{API}/business-requirements/{br['br_id']}/lines/{line['br_requirement_line_id']}",
                      headers=ed["h"], params={"row_version": line["row_version"]})
    assert r.status_code == expect, r.text


def order(client, ed, br, ls, expect=200):
    r = client.put(f"{API}/business-requirements/{br['br_id']}/lines/order", headers=ed["h"],
                   json={"lines": [{"br_requirement_line_id": x["br_requirement_line_id"],
                                    "row_version": x["row_version"]} for x in ls]})
    assert r.status_code == expect, r.text
    return r.json()


def br_detail(client, ed, br):
    return client.get(f"{API}/business-requirements/{br['br_id']}", headers=ed["h"]).json()


def expected_hash(values) -> str:
    """slice8 §7.7, computed independently: each value as <char_length>:<text>, NULL as \\x1e, joined by \\x1f."""
    parts = ["\x1e" if v is None else f"{len(str(v))}:{v}" for v in values]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


# ---- numbering ---------------------------------------------------------------------------------------------

def test_lines_are_numbered_at_save_and_the_number_is_never_sent_or_reused(client, ed):
    br = scope(client, ed)["br1"]
    one = add(client, ed, br)
    two = add(client, ed, br, "CALCULATION", "Remaining limit = limit − open items.", "MUST")
    assert (one["line_no"], two["line_no"]) == (1, 2)
    assert two["line_label"] == f"{br['br_number']}.2"
    assert (one["seq_no"], two["seq_no"]) == (1, 2)
    add(client, ed, br, line_no=7, expect=422)                          # law 6: never from the body
    add(client, ed, br, seq_no=1, expect=422)
    retire(client, ed, br, two)
    three = add(client, ed, br, "OUTPUT", "The decision goes back to Sales.")
    assert three["line_no"] == 3                                        # 2 is retired, never reused
    assert [x["line_no"] for x in lines(client, ed, br)] == [1, 3]
    assert [x["line_no"] for x in lines(client, ed, br, include_retired=True)] == [1, 3, 2]


def test_kind_and_priority_are_codes_from_their_lists(client, ed):
    br = scope(client, ed)["br1"]
    for k in KINDS:
        add(client, ed, br, k)
    add(client, ed, br, "SOMETHING", expect=400)
    add(client, ed, br, priority="URGENT", expect=400)
    add(client, ed, br, text_="   ", expect=422)
    add(client, ed, br, text_="", expect=422)


def test_editing_a_line_keeps_its_number_and_a_stale_edit_is_409(client, ed):
    br = scope(client, ed)["br1"]
    ln = add(client, ed, br, priority="SHOULD")
    up = edit(client, ed, br, ln, line_text="Only customers with an active account may get credit.",
              line_kind_code="VALIDATION", priority_code=None)
    assert (up["line_no"], up["line_kind_code"], up["priority_code"]) == (1, "VALIDATION", None)
    edit(client, ed, br, ln, line_text="stale", expect=409)
    edit(client, ed, br, up, line_text=None, expect=422)
    edit(client, ed, br, up, line_no=9, expect=422)


def test_the_requirement_priority_is_derived_from_its_live_lines(client, ed):
    br = scope(client, ed)["br1"]
    assert br_detail(client, ed, br)["priority_code"] is None
    add(client, ed, br, priority="COULD")
    should = add(client, ed, br, priority="SHOULD")
    add(client, ed, br)                                                 # not yet prioritised: ignored
    assert br_detail(client, ed, br)["priority_code"] == "SHOULD"
    retire(client, ed, br, should)
    assert br_detail(client, ed, br)["priority_code"] == "COULD"


def test_reordering_needs_every_live_line_once_and_never_renumbers(client, ed):
    br = scope(client, ed)["br1"]
    a, b, c = (add(client, ed, br, text_=t) for t in ("A", "B", "C"))
    order(client, ed, br, [a, b], expect=422)                           # missing one
    order(client, ed, br, [a, b, c, a], expect=422)                     # twice
    out = order(client, ed, br, [c, a, b])
    assert [(x["line_text"], x["line_no"], x["seq_no"]) for x in out] == [("C", 3, 1), ("A", 1, 2), ("B", 2, 3)]
    order(client, ed, br, [a, b, c], expect=409)                        # versions moved on: stale


def test_a_restored_line_keeps_its_number_and_goes_to_the_end(client, ed):
    br = scope(client, ed)["br1"]
    a, b = add(client, ed, br, text_="A"), add(client, ed, br, text_="B")
    retire(client, ed, br, a)
    add(client, ed, br, text_="C")
    r = client.patch(f"{API}/business-requirements/{br['br_id']}/lines/{a['br_requirement_line_id']}/restore",
                     headers=ed["h"])
    assert r.status_code == 200, r.text
    assert [(x["line_text"], x["line_no"]) for x in lines(client, ed, br)] == [("B", 2), ("C", 3), ("A", 1)]


def test_a_line_of_another_requirement_is_404_and_viewers_cannot_write(client, ed):
    w = scope(client, ed)
    ln = add(client, ed, w["br1"])
    r = client.patch(f"{API}/business-requirements/{w['br2']['br_id']}/lines/{ln['br_requirement_line_id']}",
                     headers=ed["h"], json={"row_version": ln["row_version"], "line_text": "x"})
    assert r.status_code == 404
    add(client, ed, w["br1"], headers=ed["rv"], expect=403)
    assert client.get(f"{API}/business-requirements/{w['br1']['br_id']}/lines", headers=ed["rv"]).status_code == 200
    assert client.get(f"{API}/business-requirements/{w['br1']['br_id']}/lines", headers=ed["out"]).status_code == 404


def test_the_legacy_text_fields_are_read_only(client, ed):
    br = scope(client, ed)["br1"]
    cur = br_detail(client, ed, br)
    for field in ("business_logic", "output_expectation"):
        r = client.patch(f"{API}/business-requirements/{br['br_id']}", headers=ed["h"],
                         json={"row_version": cur["row_version"], field: "x"})
        assert r.status_code == 422, r.text
    assert patch_br(client, ed, br, br_statement="Grant credit within limit")["br_statement"] == "Grant credit within limit"


def test_lines_retire_and_restore_with_their_process(client, ed):
    w = scope(client, ed)
    br, s = w["br1"], w["s1"]
    keep = add(client, ed, br, text_="kept")
    gone = add(client, ed, br, text_="already retired")
    retire(client, ed, br, gone)
    prev = client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}/retire-preview", headers=ed["h"]).json()
    assert keep["line_label"] in str(prev)                              # the preview names the line
    r = client.post(f"{API}/bfc-nodes/{s['bfc_node_id']}/retire-with-dependents", headers=ed["h"],
                    json={"confirm_hash": prev["confirm_hash"]})
    assert r.status_code == 204, r.text
    assert lines(client, ed, br) == []
    r = client.post(f"{API}/bfc-nodes/{s['bfc_node_id']}/restore-with-dependents", headers=ed["h"])
    assert r.status_code == 200, r.text
    assert [x["line_text"] for x in lines(client, ed, br)] == [keep["line_text"]]   # the earlier retire stands


# ---- baselines (grade 1) -----------------------------------------------------------------------------------

def test_a_frozen_baseline_holds_every_live_line_hashed_on_the_agreed_columns(client, ed, db):
    w = scope(client, ed)
    br = w["br1"]
    a = add(client, ed, br, "RULE", "Only active customers may get credit.", "MUST")
    b = add(client, ed, br, "OUTPUT", "The decision goes back to Sales.")
    c = add(client, ed, br, "CONTROL", "retired before the freeze")
    retire(client, ed, br, c)
    f = freeze(client, ed)
    v = bid(f)
    assert f["baseline"]["hash_spec_version"] == CURRENT_HASH_SPEC     # a fresh freeze: the current spec (5 since slice 14)
    rows = db.execute(text("SELECT source_id, br_id, line_no, seq_no, line_kind_code, priority_code, line_text, "
                           "content_hash FROM baseline_br_requirement_line WHERE baseline_id = :b ORDER BY source_id"),
                      {"b": v}).mappings().all()
    assert [r["source_id"] for r in rows] == [a["br_requirement_line_id"], b["br_requirement_line_id"]]
    for r in rows:
        assert r["content_hash"] == expected_hash((r["br_id"], r["line_no"], r["line_kind_code"],
                                                   r["priority_code"], r["line_text"]))
    detail = client.get(f"{API}/baselines/{v}", headers=ed["h"]).json()
    assert detail["intact"] is True and detail["counts"]["br_requirement_line"] == 2
    # frozen means frozen, at the database, even for the owner role
    with pytest.raises(Exception):
        owner_exec("UPDATE baseline_br_requirement_line SET line_text = 'x' WHERE baseline_id = :b", b=v)
    with pytest.raises(Exception):
        owner_exec("DELETE FROM baseline_br_requirement_line WHERE baseline_id = :b", b=v)


def test_the_digest_covers_the_lines(client, ed, db):
    """The same scope with one line's text differing produces a different digest: lines are inside it."""
    br = scope(client, ed)["br1"]
    ln = add(client, ed, br, text_="A")
    p1 = preview(client, ed)["preview_digest"]
    edit(client, ed, br, ln, line_text="B")
    assert preview(client, ed)["preview_digest"] != p1


def test_a_line_edit_reads_changed_and_a_reorder_reads_moved(client, ed):
    br = scope(client, ed)["br1"]
    a, b = add(client, ed, br, text_="A"), add(client, ed, br, text_="B")
    v = bid(freeze(client, ed))
    edit(client, ed, br, a, line_text="A2", priority_code="MUST")
    a2 = next(x for x in lines(client, ed, br) if x["line_no"] == 1)
    b2 = next(x for x in lines(client, ed, br) if x["line_no"] == 2)
    order(client, ed, br, [b2, a2])
    d = diff(client, ed, v, "live")
    rows = {r["source_id"]: r for r in d["entities"]["br_requirement_line"]["rows"]}
    assert rows[a["br_requirement_line_id"]]["change"] == "CHANGED"
    assert set(rows[a["br_requirement_line_id"]]["fields"]) == {"priority_code", "line_text"}
    assert rows[b["br_requirement_line_id"]]["change"] == "MOVED"
    assert "not_frozen_in" not in d["entities"]["br_requirement_line"]


def test_a_spec_3_baseline_still_verifies_and_lines_read_as_new_structure_not_scope(client, ed, db, monkeypatch):
    """§5.1, criterion 189: a baseline frozen before lines joined keeps its digest and verifies; diffed against today
    its lines are listed as added, flagged as not frozen in it, and kept out of the scope summary."""
    br = scope(client, ed)["br1"]
    from services import freeze_set
    monkeypatch.setattr(freeze_set, "CURRENT_HASH_SPEC", 3)
    monkeypatch.setattr("services.baseline.CURRENT_HASH_SPEC", 3)
    try:
        v3 = bid(freeze(client, ed))
    finally:
        monkeypatch.undo()
    stored = db.execute(text("SELECT content_digest, hash_spec_version FROM baseline WHERE baseline_id = :b"),
                        {"b": v3}).one()
    assert stored.hash_spec_version == 3
    add(client, ed, br, text_="A")
    add(client, ed, br, text_="B")
    detail = client.get(f"{API}/baselines/{v3}", headers=ed["h"]).json()
    assert detail["intact"] is True
    assert detail["counts"]["br_requirement_line"] is None              # not frozen at that spec, never 0
    from services import freeze_set as fs
    assert fs.digest(db, ed["p"], frozenset(), v3, 3) == stored.content_digest
    d = diff(client, ed, v3, "live")
    entry = d["entities"]["br_requirement_line"]
    assert entry["not_frozen_in"] == "a" and entry["joined_at_spec"] == 4
    assert {r["change"] for r in entry["rows"]} == {"ADDED"} and len(entry["rows"]) == 2
    assert d["summary"]["ADDED"] == 0                                   # new structure, not new scope
    v4 = bid(freeze(client, ed))
    assert client.get(f"{API}/baselines/{v4}", headers=ed["h"]).json()["intact"] is True
    d = diff(client, ed, v3, v4)
    assert d["entities"]["br_requirement_line"]["not_frozen_in"] == "a"


# ---- the one-off backfill ----------------------------------------------------------------------------------

def test_the_backfill_copies_legacy_text_once_and_numbers_after_existing_lines(client, ed, db, world):
    from database import SessionLocal
    from services import br_lines
    w = scope(client, ed)
    br1, br2 = w["br1"], w["br2"]
    add(client, ed, br1, text_="Written by a person before the deploy")
    owner_exec("UPDATE business_requirement SET business_logic = 'Legacy logic', output_expectation = 'Legacy out' "
               "WHERE br_id = :b", b=br1["br_id"])
    owner_exec("UPDATE business_requirement SET business_logic = '  ' WHERE br_id = :b", b=br2["br_id"])
    admin_email = "admin@example.test"
    with SessionLocal() as s:
        first = {r["project_id"]: r["count"] for r in br_lines.backfill(s, admin_email)}
    assert first[ed["p"]] == 2
    got = [(x["line_no"], x["line_kind_code"], x["priority_code"], x["line_text"]) for x in lines(client, ed, br1)]
    assert got == [(1, "RULE", None, "Written by a person before the deploy"), (2, "RULE", None, "Legacy logic"),
                   (3, "OUTPUT", None, "Legacy out")]
    assert lines(client, ed, br2) == []                                 # blank text copies nothing
    assert br_detail(client, ed, br1)["business_logic"] == "Legacy logic"   # never cleared
    with SessionLocal() as s:
        again = {r["project_id"]: r["count"] for r in br_lines.backfill(s, admin_email)}
    assert again[ed["p"]] is None and len(lines(client, ed, br1)) == 3       # a rerun is a no-op
    ev = db.execute(text("SELECT detail FROM audit_event WHERE event_type = 'BR_LINES_BACKFILLED' "
                         "AND project_id = :p"), {"p": ed["p"]}).scalars().all()
    assert len(ev) == 1 and ev[0]["count"] == 2 and len(ev[0]["line_ids"]) == 2


def test_the_backfill_refuses_anyone_but_an_active_platform_admin(client, ed):
    from database import SessionLocal
    from services import br_lines
    with SessionLocal() as s, pytest.raises(SystemExit):
        br_lines.backfill(s, "editor@example.test")


def test_a_line_change_exposes_the_effort_of_the_requirements_frs(client, ed):
    """sara H2: what a BR says lives in its lines, so a line added, changed or removed after a freeze exposes the
    effort of the FRs that BR maps to; a reorder alone does not."""
    from tests.test_effort_api import rate
    from tests.test_function_requirement_api import fr
    w = scope(client, ed)
    br = w["br1"]
    f = fr(client, ed, name="Credit check screen")
    assert rate(client, ed, f, "COMPLEX").status_code == 200
    r = client.post(f"{API}/business-requirements/{br['br_id']}/function-requirements", headers=ed["h"],
                    json={"fr_id": f["fr_id"]})
    assert r.status_code == 201, r.text
    a, b = add(client, ed, br, text_="A"), add(client, ed, br, text_="B")
    v = bid(freeze(client, ed))
    assert diff(client, ed, v, "live", priced=True)["pricing"]["totals"]["effort_exposed_days"] == 0
    order(client, ed, br, [b, a])                                       # moved only: nothing exposed
    assert diff(client, ed, v, "live", priced=True)["pricing"]["totals"]["effort_exposed_days"] == 0
    a2 = next(x for x in lines(client, ed, br) if x["line_no"] == 1)
    edit(client, ed, br, a2, line_text="A, now stricter", priority_code="MUST")
    exposed = diff(client, ed, v, "live", priced=True)["pricing"]["totals"]["effort_exposed_days"]
    assert exposed > 0
