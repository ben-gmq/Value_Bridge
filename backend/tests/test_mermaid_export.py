"""Slice 3c, reworked by slice 7c: Mermaid text export of the DFD and the ERD (design §7.12b R2-S7;
slice 3 spec §7 3c, criteria 19, 20, 20a, 22, and A-S3-5; slice7_schema §9.8). The process-flow
exporter left with the arrows (D-38, 0045).

Grade 2 — the text is pasted into a client's deck tool, so every label must stay inert. The
hostile names travel through the real API into both exporters — as a step, a performer lane (a
position and an AI label), a store, a party, a flow label, a trigger, a field and a relationship;
the one name the API cannot store (300 characters) is fed to the exporters as a graph dict.

A-S3-5: "the output renders" is proven structurally — every line of every export matches one
of the shapes listed in SHAPES below, and every label is a quoted string with no raw quote in
it. Criterion 21 (a real paste into a Mermaid renderer) is Ben's manual check."""
import re

import pytest
from fastapi import HTTPException

from services import render
from tests.test_dfd_api import ext_flow, io, party, performer, starts, trigger
from tests.test_erd_api import field, fk, pk
from tests.test_scope_api import API, ed, entity, node  # noqa: F401 — ed is a fixture

BANNED = ("click", "call", "href", "%%{init", "style", "classDef", "linkStyle", "class")
HOSTILE = [
    'x"] --> Y[click',
    '%%{init: {"securityLevel": "loose"}}%%',
    'tick `click` tock',
    'wrap click s1 call',
    '#' * 200,                                   # the longest name the API stores
]

L = r'"[^"\n]*"'                                 # a label: quoted, no raw quote inside
SHAPES = {
    "dfd": [
        r"flowchart LR",
        rf"    subgraph l\d+\[{L}\]",           # one lane per performer (D-46)
        rf"        s\d+\(\[{L}\]\)",              # a process, inside its lane
        r"    end",
        rf"    d\d+\[\({L}\)\]",                 # a store
        rf"    x\d+\[{L}\]",                     # a party
        rf"    t\d+\(\({L}\)\)",                 # a trigger, a circle (D-49)
        rf"    [dxt]\d+ -->(\|{L}\|)? s\d+",
        rf"    s\d+ -->(\|{L}\|)? [dx]\d+",
        rf"    outside\[{L}\]",                  # the boundary box
        r"    outside -\.-> d\d+",
        r"    d\d+ -\.-> outside",
        r"    s\d+ -\.-> s\d+",                  # the derived order, only with order=true
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
    path = {"dfd": f"bfc-nodes/{target}/dfd/export", "erd": f"projects/{target}/erd/export"}[kind]
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
    assert " " not in text and " " not in text and "\r" not in text
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


def graph_dict(**kw):
    """A minimal DFD dict, the shape generate_dfd returns, for the exporter-only tests."""
    return {"lanes": [], "processes": [], "stores": [], "externals": [], "triggers": [], "flows": [],
            "order": [], "boundary": {"in": [], "out": []}, **kw}


@pytest.fixture
def diagram(client, ed):
    """Sales › Order capture: two steps in named lanes (positions), one unassigned; the order
    s1 → s2 → s3 derived from their data; a trigger and a party into s1; a reader of the sales
    order in another branch (a boundary stub)."""
    l1 = node(client, ed, "Sales")
    parent = node(client, ed, "Order capture", l1["bfc_node_id"])
    other = node(client, ed, "Billing", l1["bfc_node_id"])
    s = {k: node(client, ed, n, parent["bfc_node_id"], is_process=True)
         for k, n in (("s1", "Receive order"), ("s2", "Check credit"), ("s3", "Reject order"))}
    s["far"] = node(client, ed, "Raise invoice", other["bfc_node_id"], is_process=True)
    clerk, credit = role_named(client, ed, "CLERK", "Sales clerk"), role_named(client, ed, "CREDIT", "Credit desk")
    performer(client, ed, s["s1"], "ORG_ROLE", "CLERK")
    performer(client, ed, s["s2"], "ORG_ROLE", "CREDIT")
    order, check = entity(client, ed, "Sales order"), entity(client, ed, "Credit check")
    io(client, ed, s["s1"], order, "O")
    io(client, ed, s["s2"], order, "I")
    io(client, ed, s["s2"], check, "O")
    io(client, ed, s["s3"], check, "I")
    io(client, ed, s["far"], order, "I")
    calls = trigger(client, ed, "Customer calls", "EVENT")
    starts(client, ed, s["s1"], calls)
    cust = party(client, ed, "Customer")
    ext_flow(client, ed, s["s1"], cust, "I", label="phones in")
    return {"l1": l1, "parent": parent, "steps": s, "lanes": (clerk, credit), "order": order,
            "check": check, "trigger": calls, "party": cust}


# ---- criterion 19, reworked (§9.8): lanes are performers, triggers are circles ------------------

def test_one_subgraph_per_performer_lane_with_its_processes(client, ed, diagram):
    s = diagram["steps"]
    text = text_of(client, ed, "dfd", diagram["parent"]["bfc_node_id"], headers=ed["rv"])
    assert_inert(text, "dfd")
    lines = text.splitlines()
    assert lines[0] == "flowchart LR"
    assert [x for x in lines if x.startswith("    subgraph")] == [
        '    subgraph l1["Sales clerk · Finance"]', '    subgraph l2["Credit desk · Finance"]',
        '    subgraph l3["Unassigned"]']
    assert lines.count("    end") == 3
    for lane, key, name in (("l1", "s1", "01.01.01 Receive order"), ("l2", "s2", "01.01.02 Check credit"),
                            ("l3", "s3", "01.01.03 Reject order")):
        block = text.split(f"    subgraph {lane}[", 1)[1].split("    end", 1)[0]
        assert f'        s{s[key]["bfc_node_id"]}(["{name}"])' in block.splitlines()
    assert f's{s["far"]["bfc_node_id"]}' not in text                    # another branch: only a stub


def test_flows_triggers_parties_and_boundary_stubs(client, ed, diagram):
    s, order, check = diagram["steps"], diagram["order"], diagram["check"]
    t, x = diagram["trigger"]["process_trigger_id"], diagram["party"]["external_entity_id"]
    lines = text_of(client, ed, "dfd", diagram["parent"]["bfc_node_id"]).splitlines()
    d, c = f"d{order['data_entity_id']}", f"d{check['data_entity_id']}"
    s1, s2, s3 = (f"s{s[k]['bfc_node_id']}" for k in ("s1", "s2", "s3"))
    for want in (f'    {d}[("{order["de_number"]} Sales order")]', f'    {c}[("{check["de_number"]} Credit check")]',
                 f'    x{x}["{diagram["party"]["ext_number"]} Customer"]', f'    t{t}(("Customer calls"))',
                 f'    {s1} -->|"Sales order"| {d}', f'    {d} -->|"Sales order"| {s2}',
                 f'    {s2} -->|"Credit check"| {c}', f'    {c} -->|"Credit check"| {s3}',
                 f"    t{t} --> {s1}",                                    # a trigger edge carries no label
                 f'    x{x} -->|"phones in"| {s1}',
                 '    outside["Outside this diagram"]', f"    {d} -.-> outside"):
        assert want in lines, want
    assert not [ln for ln in lines if re.fullmatch(r"    s\d+ -\.-> s\d+", ln)]       # order only when asked


def test_the_derived_order_is_drawn_dashed_only_when_asked(client, ed, diagram):
    s = diagram["steps"]
    text = text_of(client, ed, "dfd", diagram["parent"]["bfc_node_id"], order="true")
    assert_inert(text, "dfd")
    s1, s2, s3 = (s[k]["bfc_node_id"] for k in ("s1", "s2", "s3"))
    assert [ln for ln in text.splitlines() if re.fullmatch(r"    s\d+ -\.-> s\d+", ln)] == \
        [f"    s{s1} -.-> s{s2}", f"    s{s2} -.-> s{s3}"]


# ---- criterion 20 (design 137): hostile names in both exporters ---------------------------------

@pytest.fixture
def hostile(client, ed):
    """Every hostile name as a step, a lane (an AI label or a position), a store, a party, a flow
    label, a trigger, a field and a relationship."""
    l1 = node(client, ed, "Sales")
    parent = node(client, ed, "Order capture", l1["bfc_node_id"])
    steps, des = [], []
    for i, name in enumerate(HOSTILE):
        st = node(client, ed, name, parent["bfc_node_id"], is_process=True)
        if i % 2:
            role_named(client, ed, f"H{i}", name)
            performer(client, ed, st, "ORG_ROLE", f"H{i}")
        else:
            performer(client, ed, st, "AI", label=name)
        de, who = entity(client, ed, name), party(client, ed, name)
        io(client, ed, st, de, "O")
        if des:
            io(client, ed, st, des[-1], "I")                       # derived order: each reads the last
        ext_flow(client, ed, st, who, "I", label=name)             # no DE: labelled with flow_label
        starts(client, ed, st, trigger(client, ed, name, "EVENT"))
        steps.append(st), des.append(de)
    keyed = entity(client, ed, "Keyed")
    pk(client, ed, keyed, "keyed_id", data_type_code="STRING")
    for i, name in enumerate(HOSTILE):
        field(client, ed, keyed, name)
        fk(client, ed, des[i], name, keyed)                        # the FK name is the edge label (sara L6)
    # A hostile reader in another branch: a boundary stub (sara L6).
    other = node(client, ed, "Fulfilment", l1["bfc_node_id"])
    far = node(client, ed, HOSTILE[0], other["bfc_node_id"], is_process=True)
    io(client, ed, far, des[-1], "I")
    return {"parent": parent}


@pytest.mark.parametrize("kind,params", [("dfd", {}), ("dfd", {"order": "true"}), ("erd", {})])
def test_hostile_names_export_as_inert_quoted_labels(client, ed, hostile, kind, params):
    target = ed["p"] if kind == "erd" else hostile["parent"]["bfc_node_id"]
    text = text_of(client, ed, kind, target, **params)
    assert_inert(text, kind)
    assert "#35;#35;#35;" in text                                   # the '#' run survives, escaped
    assert "x#quot;#93; --#gt; Y#91;click" in text                 # the break-out attempt is text
    assert "init: #123;#quot;securityLevel#quot;: #quot;loose#quot;#125;" in text
    assert "tick #96;click#96; tock" in text and "wrap click s1 call" in text
    if kind == "dfd":
        lanes = [ln for ln in text.splitlines() if ln.startswith("    subgraph")]
        assert len(lanes) == len(HOSTILE)
        assert '    subgraph l' in lanes[0] and "x#quot;#93; --#gt; Y#91;click" in "".join(lanes)
        assert "#96;click#96;" in "".join(ln for ln in text.splitlines() if re.match(r"    t\d+\(\(", ln))


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
    dfd = render.export_dfd(graph_dict(
        lanes=[{"lane_key": "AI:x", "kind": "AI", "code": None, "name": long}],
        processes=[{"bfc_node_id": 1, "hier_code": "01", "node_name": long, "lane_key": "AI:x"}],
        triggers=[{"process_trigger_id": 4, "trigger_name": long}],
        flows=[{"kind": "TRIGGER", "bfc_node_id": 1, "direction": "I", "process_trigger_id": 4,
                "data_entity_id": None, "external_entity_id": None, "label": long}]))
    assert_inert(dfd, "dfd")
    assert dfd.count("#35;") == 200 + (200 - 3) + 200                # lane, "01 " + name, trigger


def test_escape_order_and_every_breaking_character():
    assert render.escape_mermaid(None) == '""' and render.escape_mermaid("") == '""'
    assert render.escape_mermaid("a\r\nb\tc\vd\fe\x85f g h") == '"a  b c d e f g h"'
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
    lane = [{"lane_key": "UNASSIGNED", "kind": "UNASSIGNED", "code": None, "name": None}]
    graphs = [
        (render.export_dfd, graph_dict(lanes=lane, processes=[{"bfc_node_id": 1, "hier_code": "01",
                                                                "node_name": bad, "lane_key": "UNASSIGNED"}])),
        (render.export_dfd, graph_dict(lanes=[{"lane_key": "AI:b", "kind": "AI", "code": None, "name": bad}])),
        (render.export_dfd, graph_dict(triggers=[{"process_trigger_id": 1, "trigger_name": bad}])),
        (render.export_erd, {"entities": [{"data_entity_id": 1, "de_number": "DE-0001", "de_name": bad,
                                           "fields": []}], "relationships": [], "outside_refs": []}),
    ]
    for fn, g in graphs:
        with pytest.raises(HTTPException) as err:
            fn(g)
        assert err.value.status_code == 500


def test_every_dfd_label_goes_through_the_one_escape(monkeypatch):
    """§7.12b: no second label path — each lane, process, store, party, trigger, flow and the
    boundary box is passed to escape_mermaid exactly once."""
    seen = []
    real = render.escape_mermaid
    monkeypatch.setattr(render, "escape_mermaid", lambda t: seen.append(t) or real(t))
    g = graph_dict(
        lanes=[{"lane_key": "AI:bot", "kind": "AI", "code": None, "name": "bot"}],
        processes=[{"bfc_node_id": 1, "hier_code": "01", "node_name": "step", "lane_key": "AI:bot"}],
        stores=[{"data_entity_id": 2, "de_number": "DE-0002", "de_name": "store"}],
        externals=[{"external_entity_id": 3, "ext_number": "EXT-0003", "ext_name": "party"}],
        triggers=[{"process_trigger_id": 4, "trigger_name": "trig"}],
        flows=[{"kind": "STORE", "bfc_node_id": 1, "direction": "O", "data_entity_id": 2,
                "external_entity_id": None, "process_trigger_id": None, "label": "store"},
               {"kind": "EXTERNAL", "bfc_node_id": 1, "direction": "I", "data_entity_id": None,
                "external_entity_id": 3, "process_trigger_id": None, "label": "said"}],
        boundary={"in": [], "out": [{"data_entity_id": 2}]})
    render.export_dfd(g)
    assert seen == ["bot", "01 step", "DE-0002 store", "EXT-0003 party", "trig", "store", "said",
                    render.OUTSIDE_LANE]


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

@pytest.mark.parametrize("kind", ["dfd", "erd"])
def test_json_is_422_naming_the_import_slice_and_an_invisible_target_is_404(client, ed, diagram, kind):
    target = ed["p"] if kind == "erd" else diagram["parent"]["bfc_node_id"]
    r = export(client, ed, kind, target, format="json")
    assert r.status_code == 422 and "import slice" in r.json()["detail"]
    assert export(client, ed, kind, target, format="png").status_code == 422
    assert export(client, ed, kind, target, headers=ed["out"]).status_code == 404
    assert export(client, ed, kind, target, headers=ed["out"], format="json").status_code == 404
    assert export(client, ed, kind, 99999999).status_code == 404
    assert export(client, ed, kind, target, headers=ed["rv"]).status_code == 200    # a read


def test_the_export_is_the_same_scope_rules_as_the_graph(client, ed, diagram):
    s1 = diagram["steps"]["s1"]["bfc_node_id"]
    assert export(client, ed, "dfd", s1).status_code == 422                         # a step
    assert export(client, ed, "dfd", s1, order="true").status_code == 422
    assert export(client, ed, "erd", ed["p"], subject_area=99999999).status_code == 404
    assert client.get(f"{API}/bfc-nodes/{diagram['parent']['bfc_node_id']}/process-flow/export",
                      headers=ed["h"]).status_code == 404                           # the arrows' exporter is gone


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
