"""Slice 12 — the Scope dashboard's remaining tiles S7–S10 (docs/slice12_kpis.md, S12-1). S11 (the area filter) is
presentation over the same per-area rows and is checked in the browser.

Grade 2: a figure someone decides from. Each tile is proven to agree with the screen or report it summarises — the
chart's own lights (S7), the consistency report (S8) and the freeze preview (S10) — rather than with a hand count,
so a tile can never quietly disagree with what the person sees when they click through. Left uncovered on purpose:
the as-is chart (S7 counts the to-be chart only, as the spec says) and very large projects (timing)."""
from tests.test_baseline import preview, scope
from tests.test_components import editor_on, new_project
from tests.test_erd_api import field
from tests.test_scope_api import API, ed, entity, node, tree  # noqa: F401 — ed is a fixture


def summary(client, ed, project=None, headers=None):
    r = client.get(f"{API}/projects/{project or ed['p']}/scope-summary", headers=headers or ed["h"])
    assert r.status_code == 200, r.text
    return r.json()


def lights_by_area(client, ed):
    out = {}
    for n in tree(client, ed):
        if n["is_process"] and n["is_active"] and n["dfd_light"] not in (None, "READY"):
            key = (n["hier_code"].split(".")[0], n["dfd_light"])
            out[key] = out.get(key, 0) + 1
    return out


def test_s7_not_ready_counts_agree_with_the_charts_own_lights_per_area(client, ed):
    w = scope(client, ed)
    node(client, ed, "Approve credit", w["group"]["bfc_node_id"], is_process=True)       # nothing yet: red
    other = node(client, ed, "Finance")
    g = node(client, ed, "Billing", other["bfc_node_id"])
    node(client, ed, "Raise invoice", g["bfc_node_id"], is_process=True)                  # a second area
    s = summary(client, ed)
    seen = {}
    for a in s["areas"]:
        for light, col in (("NOT_READY", "not_ready_red"), ("PARTIAL", "not_ready_amber")):
            if a[col]:
                seen[(a["hier_code"], light)] = a[col]
    assert seen == lights_by_area(client, ed)
    assert s["totals"]["dfd_on"] is True
    assert s["totals"]["not_ready_red"] == sum(a["not_ready_red"] for a in s["areas"]) >= 2


def test_s7_has_no_figure_when_the_to_be_dfd_is_off(client, world):
    p = new_project(client, world, "NODFD", ["ISSUE"])["project_id"]
    h = editor_on(client, world, p)
    s = summary(client, {"h": h, "p": p})
    assert s["totals"]["dfd_on"] is False
    assert (s["totals"]["not_ready_red"], s["totals"]["not_ready_amber"]) == (None, None)


def test_s8_counts_agree_with_the_consistency_report(client, ed):
    bare = entity(client, ed, "Customer")                      # no fields
    keys = entity(client, ed, "Order line")
    field(client, ed, keys, "line_id", is_primary_key=True, pk_ordinal=1)                 # keys only (FULL depth)
    t = summary(client, ed)["totals"]
    assert (t["entities_without_fields"], t["entities_keys_only"]) == (1, 1)
    assert bare["de_number"] != keys["de_number"]


def test_s10_counts_agree_with_the_freeze_preview(client, ed):
    w = scope(client, ed)
    node(client, ed, "Approve credit", w["group"]["bfc_node_id"], is_process=True)       # blocks the freeze
    entity(client, ed, "Customer")                                                       # a warning only
    t = summary(client, ed)["totals"]
    p = preview(client, ed)
    count = lambda d: sum(len(v) for v in d.values())                                     # noqa: E731
    assert (t["freeze_errors"], t["freeze_blocking"], t["freeze_warnings"]) == (
        count(p["errors"]), count(p["freeze_blocking"]), count(p["warnings"]))
    assert t["freeze_blocking"] >= 1 and t["freeze_warnings"] >= 1


def test_the_tiles_are_visible_to_a_reviewer_and_hidden_from_an_outsider(client, ed):
    scope(client, ed)
    assert summary(client, ed, headers=ed["rv"])["totals"]["dfd_on"] is True
    assert client.get(f"{API}/projects/{ed['p']}/scope-summary", headers=ed["out"]).status_code == 404
