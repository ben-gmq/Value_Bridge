"""Slice 1e-b piece (a1): the process flow as a `vb-process-flow/2.0` file — the published format (schema, worked
example, the Claude Enterprise prompt pack) and the export of one anchor's flow (design §7.2b, D-25; spec §4 rule 1,
§7). Grade 2: a wrong file reaches a client's AI conversion or a re-import. The re-import is piece (a2)."""
import pytest
from pydantic import ValidationError

from schemas.flow_file import FlowFile
from tests.test_charts_7c import switch
from tests.test_dfd_api import area, as_is_root, ext_flow, io, party, performer, starts, trigger  # noqa: F401
from tests.test_scope_api import API, _org_role, br_of, ed, entity, node  # noqa: F401 — ed is a fixture
from tests.test_dfd_drawing_13d import ALL_BUT_TO_BE_DFD


def export(client, ed, n, headers=None, expect=200):
    r = client.get(f"{API}/bfc-nodes/{n['bfc_node_id']}/process-flow-json", headers=headers or ed["h"])
    assert r.status_code == expect, r.text
    return r


def current(client, ed, n):
    return client.get(f"{API}/bfc-nodes/{n['bfc_node_id']}", headers=ed["h"]).json()


# ---- the export (spec §7) -------------------------------------------------------------------------

def test_the_export_writes_every_field_and_every_list_empty_as_an_empty_list(client, ed, area):
    parent, s1, s2 = area["parent"], area["s1"], area["s2"]
    _org_role(client, ed, "CLERK")
    performer(client, ed, s1, "ORG_ROLE", "CLERK")
    performer(client, ed, s2, "AI", label="Credit bot")
    order, decision = entity(client, ed, "Sales order"), entity(client, ed, "Customer order")
    io(client, ed, s1, decision, "I")
    io(client, ed, s1, order, "O")
    starts(client, ed, s1, trigger(client, ed, "Customer calls", "EVENT"))
    customer = party(client, ed, "Customer")
    ext_flow(client, ed, s1, customer, "I", decision)
    r = export(client, ed, parent, headers=ed["rv"])                       # a viewer may export
    assert r.headers["content-disposition"] == f'attachment; filename="vb-flow-tobe-{parent["hier_code"]}.json"'
    doc = r.json()
    FlowFile.model_validate(doc)                                           # the export meets its own format
    assert doc["format"] == "vb-process-flow/2.0" and doc["mode"] == "merge"
    assert doc["parent"] == {"hier_code": parent["hier_code"], "name": "Order capture"}
    assert doc["external_entities"] == [{"key": "X1", "ext_number": customer["ext_number"], "name": "Customer",
                                         "kind": None}]
    one, two = doc["steps"]
    assert one == {"key": "S1", "br_number": br_of(client, ed, s1["bfc_node_id"]), "hier_code": s1["hier_code"],
                   "row_version": current(client, ed, s1)["row_version"], "name": "Receive order",
                   "description": None, "performer": {"kind": "ORG_ROLE", "code": "CLERK"},
                   "triggers": [{"name": "Customer calls", "kind": "EVENT"}],
                   "inputs": [decision["de_number"]], "outputs": [order["de_number"]],
                   "external_flows": [{"external": "X1", "direction": "I", "data_entity": decision["de_number"]}]}
    assert two["performer"] == {"kind": "AI", "label": "Credit bot"}
    assert (two["triggers"], two["inputs"], two["outputs"], two["external_flows"]) == ([], [], [], [])


def test_only_the_anchors_live_direct_process_children_are_steps(client, ed, area):
    parent, s1 = area["parent"], area["s1"]
    node(client, ed, "Order sub-area", parent["bfc_node_id"])                     # not a process: not a step
    gone = node(client, ed, "Old step", parent["bfc_node_id"], is_process=True)
    url = f"{API}/bfc-nodes/{gone['bfc_node_id']}"
    prev = client.get(f"{url}/retire-preview", headers=ed["h"]).json()
    assert client.post(f"{url}/retire-with-dependents", headers=ed["h"],
                       json={"confirm_hash": prev["confirm_hash"]}).status_code == 204
    names = [s["name"] for s in export(client, ed, parent).json()["steps"]]
    assert names == ["Receive order", "Check credit"]
    # A step's own parent area (one level up) is not an anchor of these steps (FI-9).
    assert export(client, ed, area["l1"], expect=422)
    assert export(client, ed, s1, expect=422).json()["detail"].startswith("A process step has no flow")


def test_retired_links_are_left_out(client, ed, area):
    s1 = area["s1"]
    de = entity(client, ed)
    link = io(client, ed, s1, de, "I")
    r = client.delete(f"{API}/bfc-nodes/{s1['bfc_node_id']}/data-entities/{link['bfc_node_data_entity_id']}",
                      headers=ed["h"], params={"row_version": link["row_version"]})
    assert r.status_code in (200, 204), r.text
    assert export(client, ed, area["parent"]).json()["steps"][0]["inputs"] == []


def test_an_as_is_step_has_no_br_number(client, ed):
    root = as_is_root(client, ed)
    mid = node(client, ed, "Orders (as is)", root["bfc_node_id"])
    node(client, ed, "Take order", mid["bfc_node_id"], is_process=True)
    r = export(client, ed, mid)
    assert r.headers["content-disposition"].endswith(f'vb-flow-asis-{mid["hier_code"]}.json"')
    assert r.json()["steps"][0]["br_number"] is None


def test_no_steps_is_422_an_outsider_404_and_the_dfd_off_409(client, world, ed, area):
    empty = node(client, ed, "Empty area", area["l1"]["bfc_node_id"])
    assert "no process steps" in export(client, ed, empty, expect=422).json()["detail"]
    export(client, ed, area["parent"], headers=ed["out"], expect=404)
    switch(client, world, ed["p"], ALL_BUT_TO_BE_DFD)
    r = export(client, ed, area["parent"], expect=409)
    assert r.headers["X-VB-Error"] == "COMPONENT_OFF"


# ---- the published format (criteria 95, 144; VB-013) --------------------------------------------------

def test_the_schema_route_serves_the_schema_the_example_and_the_claude_enterprise_pack(client, ed):
    assert client.get(f"{API}/process-flow-json/schema").status_code == 401
    out = client.get(f"{API}/process-flow-json/schema", headers=ed["out"]).json()     # any signed-in user
    assert out["format"] == "vb-process-flow/2.0"
    assert out["schema"] == FlowFile.model_json_schema()
    FlowFile.model_validate(out["example"])                                           # criterion 95
    pack = out["prompt_pack"]
    assert out["approved_ai_service"].startswith("Claude Enterprise")
    head = pack.split("## Prompt", 1)[0]                                             # what the consultant reads first
    assert "Claude Enterprise under FTC's own account, and nothing else" in head      # FI-6, FI-10
    assert "Remove personal data yourself before you paste anything" in head          # FI-6
    assert "must not go into any other AI" in head                                    # VB-013
    assert '`br_number`, `hier_code` and `row_version` as `null`' in pack             # spec rule 11
    assert "Claude Enterprise under FTC's own account" in out["ai_rules"]             # a saved schema file keeps them
    assert "## Prompt" not in out["ai_rules"]


def _file(**step):
    return {"format": "vb-process-flow/2.0", "parent": {"hier_code": "01.01"},
            "steps": [{"key": "S1", "name": "Receive order", **step}]}


@pytest.mark.parametrize("doc", [
    {**_file(), "edges": []},                                       # D-38: no edges
    {**_file(), "lanes": []},                                       # D-38: no lanes
    {**_file(), "format": "vb-process-flow/1.0"},                   # 1.0 → re-export
    {**_file(), "steps": []},                                       # at least one step
    {**_file(), "mode": "append"},
    _file(key="S 1"),                                               # key pattern
    _file(name="x" * 201),
    _file(performer={"kind": "ORG_ROLE", "label": "Clerk"}),        # a coded performer needs its code
    _file(performer={"kind": "AI"}),                                # an AI needs its label
    _file(triggers=[{"name": "Month end"}]),                        # a trigger's kind is required
    _file(external_flows=[{"external": "X1", "direction": "both"}]),
    _file(colour="red"),                                            # unknown key on a step
])
def test_the_format_refuses_what_spec_rule_1_refuses(doc):
    with pytest.raises(ValidationError):
        FlowFile.model_validate(doc)


def test_the_format_names_the_same_performer_and_trigger_kinds_as_the_screen():
    """Sara L2: one vocabulary — a kind added on screen and missed here would refuse a valid export."""
    from typing import get_args
    from schemas.flow_file import AiPerformer, CodedPerformer, Trigger
    from services import bfc, trigger as trigger_service
    coded = get_args(CodedPerformer.model_fields["kind"].annotation)
    ai = get_args(AiPerformer.model_fields["kind"].annotation)
    assert set(coded) | set(ai) == set(bfc.PERFORMER_KINDS)
    assert set(get_args(Trigger.model_fields["kind"].annotation)) == set(trigger_service.KINDS)


def test_the_format_tells_left_out_from_null_and_empty():
    """FI-1, FI-2, FI-8: the import (a2) reads which keys a step carried, so the model must keep that apart."""
    left_out = FlowFile.model_validate(_file()).steps[0]
    stated = FlowFile.model_validate(_file(performer=None, triggers=[], description="")).steps[0]
    assert {"performer", "triggers", "description"} & left_out.model_fields_set == set()
    assert {"performer", "triggers", "description"} <= stated.model_fields_set
