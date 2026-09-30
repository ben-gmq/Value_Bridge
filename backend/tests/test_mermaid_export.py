"""Slice 3c: Mermaid text export of the three diagrams (design §7.2a export_process_flow,
§7.12b R2-S7; slice 3 spec §7 3c, criteria 19, 20, 20a, 22, and A-S3-5).

Grade 2 — the text is pasted into a client's deck tool, so every label must stay inert. The
hostile names travel through the real API into all three exporters; the one name the API
cannot store (300 characters) is fed to the exporters as a graph dict.

A-S3-5: "the output renders" is proven structurally — every line of every export matches one
of the shapes listed in SHAPES below, and every label is a quoted string with no raw quote in
it. Criterion 21 (a real paste into a Mermaid renderer) is Ben's manual check."""
import re

import pytest
from fastapi import HTTPException

from services import render
from tests.test_dfd_api import ext_flow, io, party
from tests.test_erd_api import field, fk, pk
from tests.test_process_flow_api import edge
from tests.test_scope_api import API, ed, entity, node  # noqa: F401 — ed is a fixture

BANNED = ("click", "call", "href", "%%{init", "style", "classDef", "linkStyle", "class")
HOSTILE = [
    'x"] --> Y[click',
    '%%{init: {"securityLevel": "loose"}}%%',
    'tick `click` tock',
    'wrap\u2028click s1 call',
    '#' * 200,                                   # the longest name the API stores
]

L = r'"[^"\n]*"'                                 # a label: quoted, no raw quote inside
SHAPES = {
    "flow": [
        r"flowchart LR",
        rf"    subgraph (l\d+|outside)\[{L}\]",
        rf"        s\d+\[{L}\]",
        r'        e\d+\(\(" "\)\)',
        r"    end",
        rf"    d\d+\[\({L}\)\]",
        rf"    x\d+\[{L}\]",
        rf"    [se]\d+ (-->|-\.->)(\|{L}\|)? [se]\d+",
        r"    [dx]\d+ -\.- s\d+",
        r"    s\d+ -\.- [dx]\d+",
    ],
    "dfd": [
        r"flowchart LR",
        rf"    s\d+\(\[{L}\]\)",
        rf"    d\d+\[\({L}\)\]",
        rf"    x\d+\[{L}\]",
        rf"    [dx]\d+ -->(\|{L}\|)? s\d+",
        rf"    s\d+ -->(\|{L}\|)? [dx]\d+",
    ],
    "erd": [
        r"erDiagram",
        rf"    E\d+\[{L}\]( \{{)?",
        rf"        [A-Z_]+ a_\d+( PK| FK| PK, FK)? {L}",
        rf"        unknown a_\d+( PK| FK| PK, FK)? {L}",
        r"    \}",
        rf"    E\d+ (\|\||\|o)(--|\.\.)(o\||o\{{) E\d+ : {L}",
    ],
}


def export(client, ed, kind, target, headers=None, **params):
    path = {"flow": f"bfc-nodes/{target}/process-flow/export", "dfd": f"bfc-nodes/{target}/dfd/export",
            "erd": f"projects/{target}/erd/export"}[kind]
    return client.get(f"{API}/{path}", headers=headers or ed["h"], params={"format": "mermaid", **params})


def text_of(client, ed, kind, target, **params):
    r = export(client, ed, kind, target, **params)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")
    return r.text


def assert_inert(text, kind):
    """Criterion 20 and A-S3-5: no banned first token, every line a known shape, no raw
    separator character anywhere (splitlines() also breaks on U+2028 / U+0085)."""
    lines = text.splitlines()
    for line in lines:
        first = (line.split() or [""])[0]
        assert not any(first.startswith(b) for b in BANNED), line
        assert any(re.fullmatch(p, line) for p in SHAPES[kind]), f"unknown shape: {line!r}"
    assert "%%" not in text and "`" not in text
    assert "\u2028" not in text and "\u2029" not in text and "\r" not in text
    assert text.endswith("\n") and text.count("\n") == len(lines)


def role_named(client, ed, code, name):
    units = client.get(f"{API}/projects/{ed['p']}/org-units", headers=ed["h"]).json()
    unit = units[0]["org_unit_id"] if units else client.post(
        f"{API}/projects/{ed['p']}/org-units", headers=ed["h"],
        json={"org_unit_code": "FIN", "org_unit_name": "Finance"}).json()["org_unit_id"]
    r = client.post(f"{API}/projects/{ed['p']}/org-roles", headers=ed["h"],
                    json={"org_unit_id": unit, "org_role_code": code, "org_role_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def responsible(client, ed, step, org_role):
    r = client.post(f"{API}/bfc-nodes/{step['bfc_node_id']}/org-roles", headers=ed["h"],
                    json={"org_role_id": org_role["org_role_id"], "raci_code": "R"})
    assert r.status_code == 201, r.text


@pytest.fixture
def flow(client, ed):
    """Sales › Order capture: two named-lane steps, one unassigned step, start and end events,
    a conditional branch, and a handoff to a step in another branch (outside the frame)."""
    l1 = node(client, ed, "Sales")
    parent = node(client, ed, "Order capture", l1["bfc_node_id"])
    other = node(client, ed, "Billing", l1["bfc_node_id"])
    s = {k: node(client, ed, n, parent["bfc_node_id"], is_process=True)
         for k, n in (("s1", "Receive order"), ("s2", "Check credit"), ("s3", "Reject order"))}
    s["far"] = node(client, ed, "Raise invoice", other["bfc_node_id"], is_process=True)
    clerk, credit = role_named(client, ed, "CLERK", "Sales clerk"), role_named(client, ed, "CREDIT", "Credit desk")
    responsible(client, ed, s["s1"], clerk)
    responsible(client, ed, s["s2"], credit)
    e = {"start": edge(client, ed, None, s["s1"]),
         "seq": edge(client, ed, s["s1"], s["s2"]),
         "ng": edge(client, ed, s["s2"], s["s3"], "CONDITIONAL", "Credit NG"),
         "ok": edge(client, ed, s["s2"], s["far"], "HANDOFF"),
         "end": edge(client, ed, s["s3"], None)}
    return {"l1": l1, "parent": parent, "steps": s, "edges": e, "lanes": (clerk, credit)}


# ---- criterion 19 (design 88): lanes and condition labels --------------------------------------

def test_one_subgraph_per_lane_and_the_condition_on_the_conditional_edge(client, ed, flow):
    s, e = flow["steps"], flow["edges"]
    text = text_of(client, ed, "flow", flow["parent"]["bfc_node_id"], headers=ed["rv"])
    assert_inert(text, "flow")
    lines = text.splitlines()
    assert lines[0] == "flowchart LR"
    assert [x for x in lines if x.startswith("    subgraph")] == [
        '    subgraph l1["Sales clerk · Finance"]', '    subgraph l2["Credit desk · Finance"]',
        '    subgraph l3["Unassigned"]', '    subgraph outside["Outside this flow"]']
    assert lines.count("    end") == 4
    assert f'    s{s["s2"]["bfc_node_id"]} -->|"Credit NG"| s{s["s3"]["bfc_node_id"]}' in lines
    assert f'    s{s["s1"]["bfc_node_id"]} --> s{s["s2"]["bfc_node_id"]}' in lines
    assert f'    s{s["s2"]["bfc_node_id"]} -.-> s{s["far"]["bfc_node_id"]}' in lines     # HANDOFF dashed
    # each step sits inside its own lane's block
    block = text.split('subgraph l2["Credit desk · Finance"]', 1)[1].split("    end", 1)[0]
    assert f's{s["s2"]["bfc_node_id"]}["01.01.02 Check credit"]' in block
    assert e["ng"]["condition_label"] == "Credit NG"


def test_start_and_end_events_and_outside_nodes_have_generated_ids(client, ed, flow):
    s, e = flow["steps"], flow["edges"]
    text = text_of(client, ed, "flow", flow["parent"]["bfc_node_id"])
    lines = text.splitlines()
    start, end = f"e{e['start']['bfc_node_flow_id']}", f"e{e['end']['bfc_node_flow_id']}"
    assert f'        {start}((" "))' in lines and f'        {end}((" "))' in lines
    assert f"    {start} --> s{s['s1']['bfc_node_id']}" in lines
    assert f"    s{s['s3']['bfc_node_id']} --> {end}" in lines
    # the start event is drawn in its step's lane (as on the canvas), the end in the unassigned one
    assert start in text.split('subgraph l1[', 1)[1].split("    end", 1)[0]
    assert end in text.split('subgraph l3[', 1)[1].split("    end", 1)[0]
    outside = text.split('subgraph outside[', 1)[1].split("    end", 1)[0]
    assert f's{s["far"]["bfc_node_id"]}["01.02.01 Raise invoice"]' in outside


def test_the_flow_draws_its_stores_and_parties_as_dotted_associations(client, ed, flow):
    s1 = flow["steps"]["s1"]
    order, cust = entity(client, ed, "Sales order"), party(client, ed, "Customer")
    ext_flow(client, ed, s1, cust, "I", order)                     # also the (s1, order, I) I/O row
    io(client, ed, flow["steps"]["s2"], order, "O")
    text = text_of(client, ed, "flow", flow["parent"]["bfc_node_id"])
    assert_inert(text, "flow")
    d, x = f"d{order['data_entity_id']}", f"x{cust['external_entity_id']}"
    lines = text.splitlines()
    assert f'    {d}[("{order["de_number"]} Sales order")]' in lines
    assert f'    {x}["{cust["ext_number"]} Customer"]' in lines
    assert f"    {d} -.- s{s1['bfc_node_id']}" in lines
    assert f"    s{flow['steps']['s2']['bfc_node_id']} -.- {d}" in lines
    assert f"    {x} -.- s{s1['bfc_node_id']}" in lines


# ---- criterion 20 (design 137): hostile names in all three exporters ---------------------------

@pytest.fixture
def hostile(client, ed):
    """Every hostile name as a step, a lane, a condition, a DE, a field, a party and a flow label."""
    l1 = node(client, ed, "Sales")
    parent = node(client, ed, "Order capture", l1["bfc_node_id"])
    steps, des, parties = [], [], []
    for i, name in enumerate(HOSTILE):
        st = node(client, ed, name, parent["bfc_node_id"], is_process=True)
        responsible(client, ed, st, role_named(client, ed, f"H{i}", name))
        de, who = entity(client, ed, name), party(client, ed, name)
        io(client, ed, st, de, "O")
        ext_flow(client, ed, st, who, "I", label=name)             # no DE: labelled with flow_label
        steps.append(st), des.append(de), parties.append(who)
    for i, st in enumerate(steps[1:]):
        edge(client, ed, steps[i], st, "CONDITIONAL", HOSTILE[i])
    keyed = entity(client, ed, "Keyed")
    pk(client, ed, keyed, "keyed_id", data_type_code="STRING")
    for i, name in enumerate(HOSTILE):
        field(client, ed, keyed, name)
        fk(client, ed, des[i], name, keyed)                        # the FK name is the edge label (sara L6)
    # A hand-off to a hostile step in another branch: the `outside` node of the flow (sara L6).
    other = node(client, ed, "Fulfilment", l1["bfc_node_id"])
    far = node(client, ed, HOSTILE[0], other["bfc_node_id"], is_process=True)
    edge(client, ed, steps[-1], far, "HANDOFF", None)
    return {"parent": parent}


@pytest.mark.parametrize("kind", ["flow", "dfd", "erd"])
def test_hostile_names_export_as_inert_quoted_labels(client, ed, hostile, kind):
    target = ed["p"] if kind == "erd" else hostile["parent"]["bfc_node_id"]
    text = text_of(client, ed, kind, target)
    assert_inert(text, kind)
    assert "#35;#35;#35;" in text                                   # the '#' run survives, escaped
    assert "x#quot;#93; --#gt; Y#91;click" in text                 # the break-out attempt is text
    assert "init: #123;#quot;securityLevel#quot;: #quot;loose#quot;#125;" in text
    assert "tick #96;click#96; tock" in text and "wrap click s1 call" in text


def test_a_300_character_name_is_capped_at_200_before_escaping():
    long = "#" * 300
    assert render.escape_mermaid(long) == '"' + "#35;" * 200 + '"'
    g = {"entities": [{"data_entity_id": 1, "de_number": "DE-0001", "de_name": long,
                       "fields": [{"field_name": long, "data_type_code": None,
                                   "is_primary_key": True, "is_foreign_key": False}]}],
         "relationships": [], "outside_refs": []}
    text = render.export_erd(g)
    assert_inert(text, "erd")
    # 200 raw characters per label, never more: the alias spends 8 on "DE-0001 ", the field none
    assert text.count("#35;") == 192 + 200
    dfd = render.export_dfd({"processes": [{"bfc_node_id": 1, "hier_code": "01", "node_name": long}],
                             "stores": [], "externals": [], "flows": []})
    assert_inert(dfd, "dfd")


def test_escape_order_and_every_breaking_character():
    assert render.escape_mermaid(None) == '""' and render.escape_mermaid("") == '""'
    assert render.escape_mermaid("a\r\nb\tc\vd\fe\x85f\u2028g\u2029h") == '"a  b c d e f g h"'
    assert render.escape_mermaid("50%% off %%%") == '"50 off %"'
    assert render.escape_mermaid('#"<>`[](){}|;') == \
        '"#35;#quot;#lt;#gt;#96;#91;#93;#40;#41;#123;#125;#124;#59;"'
    assert render.escape_mermaid("#35;") == '"#35;35#59;"'          # one pass: no double escape
    assert render.escape_mermaid("é" * 250) == '"' + "é" * 200 + '"'


def test_the_guard_stops_a_banned_line_with_a_500():
    for bad in ("flowchart LR\n    click s1 href \"x\"", "  %%{init: {}}%%", "classDef x fill:red",
                "erDiagram\nstyle E1 color:red", "\tlinkStyle 0 stroke:red", "call alert()"):
        with pytest.raises(HTTPException) as err:
            render._guard(bad)
        assert err.value.status_code == 500
    assert render._guard("flowchart LR\n    s1[\"click\"]") == "flowchart LR\n    s1[\"click\"]"


def test_a_renderer_that_skips_the_escape_is_stopped_by_the_guard(monkeypatch):
    """The guard is the last step of every exporter, so a renderer bug never reaches a deck."""
    monkeypatch.setattr(render, "escape_mermaid", lambda t: f'"{t}"')
    bad = "a\nclick s1 href x"
    graphs = {
        render.export_dfd: {"processes": [{"bfc_node_id": 1, "hier_code": "01", "node_name": bad}],
                            "stores": [], "externals": [], "flows": []},
        render.export_process_flow: {"lanes": [], "outside": [], "stores": [], "externals": [], "edges": [],
                                     "nodes": [{"bfc_node_id": 1, "hier_code": "01", "node_name": bad,
                                                "lane_org_role_id": None}]},
        render.export_erd: {"entities": [{"data_entity_id": 1, "de_number": "DE-0001", "de_name": bad,
                                          "fields": []}], "relationships": [], "outside_refs": []},
    }
    for fn, g in graphs.items():
        with pytest.raises(HTTPException) as err:
            fn(g)
        assert err.value.status_code == 500


# ---- criterion 20a + R2-NEW-3: the erDiagram attribute rows ------------------------------------

def test_japanese_field_names_are_distinct_generated_attributes(client, ed):
    cust, order = entity(client, ed, "顧客"), entity(client, ed, "注文")
    cust_id = pk(client, ed, cust, "顧客ID", data_type_code="STRING")
    pk(client, ed, order, "注文番号", data_type_code="STRING")
    fk(client, ed, order, "顧客ID", cust, cust_id, is_mandatory=True)
    field(client, ed, order, "注文ID")                                  # no data type
    text = text_of(client, ed, "erd", ed["p"])
    assert_inert(text, "erd")
    block = text.split(f'E{order["data_entity_id"]}["{order["de_number"]} 注文"] {{\n', 1)[1].split("    }", 1)[0]
    assert block.splitlines() == ['        STRING a_1 PK "注文番号"', '        unknown a_2 FK "顧客ID"',
                                  '        unknown a_3 "注文ID"']
    assert f'    E{cust["data_entity_id"]} ||..o{{ E{order["data_entity_id"]} : "顧客ID"' in text.splitlines()


def test_a_field_that_is_both_key_and_foreign_key_says_pk_fk_and_draws_identifying(client, ed):
    order, line = entity(client, ed, "Order"), entity(client, ed, "Order line")
    order_id = pk(client, ed, order, "order_id", data_type_code="INTEGER")
    fk(client, ed, line, "order_id", order, order_id, is_primary_key=True, pk_ordinal=1,
       is_mandatory=True, data_type_code="INTEGER")
    text = text_of(client, ed, "erd", ed["p"])
    assert_inert(text, "erd")
    assert '        INTEGER a_1 PK, FK "order_id"' in text.splitlines()
    # the FK set is the child's whole key: child 1 (zero or one, A-S3-8), identifying, parent 1
    assert f'    E{order["data_entity_id"]} ||--o| E{line["data_entity_id"]} : "order_id"' in text.splitlines()


def test_a_type_code_that_is_not_plain_upper_case_exports_unknown():
    g = {"entities": [{"data_entity_id": 3, "de_number": "DE-0003", "de_name": "T",
                       "fields": [{"field_name": n, "data_type_code": c, "is_primary_key": False,
                                   "is_foreign_key": False}
                                  for n, c in (("a", "VARCHAR2"), ("b", "string"), ("c", "DATE_TIME"),
                                               ("d", 'X" click'), ("e", ""))]}],
         "relationships": [], "outside_refs": []}
    rows = [x.split()[0] for x in render.export_erd(g).splitlines() if " a_" in x]
    assert rows == ["unknown", "unknown", "DATE_TIME", "unknown", "unknown"]


def test_an_area_export_draws_outside_parents_as_declared_stubs(client, ed):
    l1 = node(client, ed, "Sales")
    area = node(client, ed, "Order capture", l1["bfc_node_id"])
    st = node(client, ed, "Receive order", area["bfc_node_id"], is_process=True)
    addr, order = entity(client, ed, "Address"), entity(client, ed, "Order")
    addr_id = pk(client, ed, addr, "address_id")
    fk(client, ed, order, "ship_to_address_id", addr, addr_id)
    io(client, ed, st, order, "O")
    text = text_of(client, ed, "erd", ed["p"], subject_area=area["bfc_node_id"])
    assert_inert(text, "erd")
    lines = text.splitlines()
    assert f'    E{addr["data_entity_id"]}["{addr["de_number"]} Address"]' in lines        # stub, no block
    assert f'    E{addr["data_entity_id"]} |o..o{{ E{order["data_entity_id"]} : "ship_to_address_id"' in lines


# ---- criterion 22: formats and visibility ------------------------------------------------------

@pytest.mark.parametrize("kind", ["flow", "dfd", "erd"])
def test_json_is_422_naming_the_import_slice_and_an_invisible_target_is_404(client, ed, flow, kind):
    target = ed["p"] if kind == "erd" else flow["parent"]["bfc_node_id"]
    r = export(client, ed, kind, target, format="json")
    assert r.status_code == 422 and "import slice" in r.json()["detail"]
    assert export(client, ed, kind, target, format="png").status_code == 422
    assert export(client, ed, kind, target, headers=ed["out"]).status_code == 404
    assert export(client, ed, kind, target, headers=ed["out"], format="json").status_code == 404
    assert export(client, ed, kind, 99999999).status_code == 404
    assert export(client, ed, kind, target, headers=ed["rv"]).status_code == 200    # a read


def test_the_export_is_the_same_scope_rules_as_the_graph(client, ed, flow):
    s1 = flow["steps"]["s1"]["bfc_node_id"]
    assert export(client, ed, "flow", s1).status_code == 422                        # a step
    assert export(client, ed, "dfd", s1).status_code == 422
    assert export(client, ed, "flow", flow["parent"]["bfc_node_id"], variant="NOPE").status_code == 422
    assert text_of(client, ed, "flow", flow["parent"]["bfc_node_id"], variant="TO_BE").startswith("flowchart LR")
    assert export(client, ed, "erd", ed["p"], subject_area=99999999).status_code == 404


def test_a_hostile_out_of_area_parent_stays_inert(client, ed):
    """The ERD stub label is user text too (sara L6)."""
    l1 = node(client, ed, "Sales")
    area = node(client, ed, "Order capture", l1["bfc_node_id"])
    st = node(client, ed, "Receive order", area["bfc_node_id"], is_process=True)
    evil, order = entity(client, ed, HOSTILE[0]), entity(client, ed, "Order")
    fk(client, ed, order, HOSTILE[1], evil, pk(client, ed, evil, "evil_id"))
    io(client, ed, st, order, "O")
    text = text_of(client, ed, "erd", ed["p"], subject_area=area["bfc_node_id"])
    assert_inert(text, "erd")
    assert "x#quot;#93; --#gt; Y#91;click" in text


@pytest.mark.parametrize("line", ["CLICK s1 href", "Style s1 fill:red", "%%{ init: {} }%%",
                                  "%%{wrap}%%", "---", "  ClassDef x fill:red"])
def test_the_guard_is_case_insensitive_and_refuses_every_opener(line):
    with pytest.raises(HTTPException) as e:
        render._guard(f"flowchart LR\n{line}\n")
    assert e.value.status_code == 500


def test_a_directive_word_type_code_exports_unknown():
    g = {"entities": [{"data_entity_id": 3, "de_number": "DE-0003", "de_name": "T",
                       "fields": [{"field_name": n, "data_type_code": c, "is_primary_key": False,
                                   "is_foreign_key": False} for n, c in (("a", "CLASS"), ("b", "STYLE"))]}],
         "relationships": [], "outside_refs": []}
    rows = [x.split()[0] for x in render.export_erd(g).splitlines() if " a_" in x]
    assert rows == ["unknown", "unknown"]


def test_invisible_format_characters_are_removed():
    """A right-to-left override or a zero-width space cannot make a label read differently (sara L3)."""
    assert render.escape_mermaid("Pay\u202eyap\u200b me\ufeff") == '"Payyap me"'
