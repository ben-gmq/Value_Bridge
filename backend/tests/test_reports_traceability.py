"""Traceability report (docs/slice1f_spec.md §3.1, function 68, criteria 10 and 10a). Grade 2: a wrong row reaches a
client deck or the vendor scope list and is corrected by fixing the data once someone checks it. Each rule is proven
on a built fixture.

Deliberately uncovered (spec §5): very large projects (no performance test); the print layout (browser pass)."""
from tests.test_application_api import allocate, app
from tests.test_br_fr import lnk, rows, set_components, two_brs, unlnk
from tests.test_function_requirement_api import fr
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol


def report(client, ed, headers=None, expect=200):
    r = client.get(f"{API}/projects/{ed['p']}/traceability", headers=headers or ed["rv"])
    assert r.status_code == expect, r.text
    return r.json()


def _set_status(client, ed, s, status):
    cur = client.get(f"{API}/solutions/{s['solution_id']}", headers=ed["h"]).json()
    r = client.patch(f"{API}/solutions/{s['solution_id']}", headers=ed["h"],
                     json={"row_version": cur["row_version"], "status_code": status})
    assert r.status_code == 200, r.text


def test_an_fr_on_two_brs_is_two_rows_grouped_by_type_in_behaviour_order(client, ed):
    """Criterion 10a; groups FORM before INTERFACE (behaviour order), rows by step then BR."""
    b1, b2, _, _ = two_brs(client, ed)
    feed = fr(client, ed, "Order feed", "INTERFACE")
    form = fr(client, ed, "Order form", "FORM")
    for b in (b2, b1):
        lnk(client, ed, b, feed)
    lnk(client, ed, b1, form)
    out = report(client, ed)
    assert [g["behaviour"] for g in out["groups"]] == ["FORM", "INTERFACE"]
    feed_rows = out["groups"][1]["rows"]
    assert [r["br_number"] for r in feed_rows] == [b1["br_number"], b2["br_number"]]     # by step, then BR
    assert {r["fr_number"] for r in feed_rows} == {feed["fr_number"]}
    assert feed_rows[0]["step_name"] == "Take order" and feed_rows[1]["step_name"] == "Approve order"
    assert out["untraced"] == []


def test_an_fr_reached_only_through_a_solution_is_no_row_and_untraced_is_listed(client, ed):
    """D-52: the solution is not a path to a BR; the FR shows in the untraced group with its tag."""
    b1, _, _, _ = two_brs(client, ed)
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    assert link(client, ed, b1["br_id"], s["solution_id"]).status_code == 201
    loose = fr(client, ed, "Portal page", solution_id=s["solution_id"])
    out = report(client, ed)
    assert out["groups"] == []
    assert [(r["fr_number"], r["solution"]["solution_number"], r["tag_answers_br"]) for r in out["untraced"]] == [
        (loose["fr_number"], s["solution_number"], None)]


def test_tag_flags_and_applications(client, ed):
    """tag_answers_br false when the tag is not a solution of that BR; REJECTED carries its own flag (D4) and
    never counts as an answer; the tag's applications ride along."""
    b1, b2, _, _ = two_brs(client, ed)
    s = sol(client, ed, "Order portal", "TECHNOLOGY")
    assert link(client, ed, b1["br_id"], s["solution_id"]).status_code == 201
    a = app(client, ed, "PORTAL", "Order portal app", "TO_BE")
    assert allocate(client, ed, s, a).status_code == 201
    f = fr(client, ed, "Portal page", solution_id=s["solution_id"])
    lnk(client, ed, b1, f)
    lnk(client, ed, b2, f)
    rows = {r["br_number"]: r for r in report(client, ed)["groups"][0]["rows"]}
    assert rows[b1["br_number"]]["tag_answers_br"] is True
    assert rows[b2["br_number"]]["tag_answers_br"] is False                   # flagged: not a solution of that BR
    assert rows[b1["br_number"]]["applications"] == [{"application_code": "PORTAL",
                                                      "application_name": "Order portal app"}]
    assert rows[b1["br_number"]]["rejected_solution"] is False
    _set_status(client, ed, s, "REJECTED")
    rows = {r["br_number"]: r for r in report(client, ed)["groups"][0]["rows"]}
    assert rows[b1["br_number"]]["tag_answers_br"] is False and rows[b1["br_number"]]["rejected_solution"] is True
    assert len(rows) == 2                                                     # the FR stays on the list


def test_answered_without_software(client, ed):
    """Criterion 10: a PEOPLE solution on two BRs with no FR reads as a complete answer; a TECHNOLOGY one with no FR
    is a coverage line instead (D5); a REJECTED one is not an answer; one carrying an FR is not listed."""
    b1, b2, _, _ = two_brs(client, ed)
    people = sol(client, ed, "Approval matrix", "PEOPLE")
    tech = sol(client, ed, "Order portal", "TECHNOLOGY")
    gone = sol(client, ed, "Old habit", "PROCESS")
    used = sol(client, ed, "Checklist", "PROCESS")
    for b in (b1, b2):
        assert link(client, ed, b["br_id"], people["solution_id"]).status_code == 201
    for s in (tech, gone, used):
        assert link(client, ed, b1["br_id"], s["solution_id"]).status_code == 201
    _set_status(client, ed, gone, "REJECTED")
    fr(client, ed, "Checklist form", solution_id=used["solution_id"])
    out = report(client, ed)["answered_without_software"]
    assert [(r["solution_number"], r["br_numbers"]) for r in out] == [
        (people["solution_number"], sorted([b1["br_number"], b2["br_number"]]))]


def test_components_off_are_null_not_empty(client, ed, world):
    """A1: a part whose component is off is null, so it never reads "no gaps". A component with live rows cannot be
    switched off, so each state is set before its rows exist."""
    b1, _, _, _ = two_brs(client, ed)
    set_components(client, world, ed["p"], ["SOLUTION"])
    out = report(client, ed)
    assert (out["groups"], out["untraced"], out["answered_without_software"]) == (None, None, None)
    set_components(client, world, ed["p"], ["FUNCTION_REQUIREMENT"])
    lnk(client, ed, b1, fr(client, ed))
    out = report(client, ed)
    row = out["groups"][0]["rows"][0]
    assert (row["solution"], row["applications"], row["tag_answers_br"]) == (None, None, None)
    assert out["answered_without_software"] is None
    set_components(client, world, ed["p"], ["FUNCTION_REQUIREMENT", "SOLUTION"])
    out = report(client, ed)
    assert out["groups"][0]["rows"][0]["applications"] is None and out["answered_without_software"] == []


def test_unlinked_and_retired_rows_move_out_and_an_outsider_gets_404(client, ed):
    """A retired link drops the row and leaves the FR untraced; a retired FR leaves the report."""
    b1, _, _, _ = two_brs(client, ed)
    f = fr(client, ed)
    lnk(client, ed, b1, f)
    unlnk(client, ed, b1, rows(client, ed, b1)[0])
    out = report(client, ed)
    assert out["groups"] == [] and [r["fr_number"] for r in out["untraced"]] == [f["fr_number"]]
    cur = client.get(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"]).json()
    r = client.delete(f"{API}/function-requirements/{f['fr_id']}", headers=ed["h"],
                      params={"row_version": cur["row_version"]})
    assert r.status_code == 204, r.text
    assert report(client, ed)["untraced"] == []
    report(client, ed, headers=ed["out"], expect=404)
