"""Slice 1e-b piece (a2): re-importing a `vb-process-flow/2.0` file in merge mode (design §7.2b, D-25; spec §4 rules
1–8 and 10–17, §7, §10). Grade 2: a wrong flow reaches a client deliverable, but every change is audited and merge
never retires anything. New outside parties and flows, and replace mode, are piece (b): test_flow_import_replace."""
import copy
import json
import random

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from models import AuditEvent, BfcNode, BusinessRequirement, BfcNodeDataEntity, BfcNodeTrigger, DataEntity, ImportBatch, ProcessTrigger
from tests.test_charts_7c import switch
from tests.test_dfd_api import area, as_is_root, ext_flow, io, party, performer, starts, trigger  # noqa: F401
from tests.test_scope_api import API, _org_role, br_of, ed, entity, node  # noqa: F401 — ed is a fixture
from tests.test_dfd_drawing_13d import ALL_BUT_TO_BE_DFD


def export(client, ed, n):
    r = client.get(f"{API}/bfc-nodes/{n['bfc_node_id']}/process-flow-json", headers=ed["h"])
    assert r.status_code == 200, r.text
    return r.json()


def stage(client, ed, anchor, doc, mode="merge", expect=201, raw=None):
    r = client.post(f"{API}/projects/{ed['p']}/bulk/process-flow/validate", params={
        "anchor_bfc_node_id": anchor["bfc_node_id"], "mode": mode},
        headers={**ed["h"], "Content-Type": "application/json", "X-VB-File-Name": "flow.json"},
        content=raw if raw is not None else json.dumps(doc).encode())
    assert r.status_code == expect, r.text
    return r.json()


def commit(client, ed, pv, ack=None, upd=None, expect=200, ret=None):
    b = pv["batch"]
    r = client.post(f"{API}/bulk/batches/{b['import_batch_id']}/commit", headers=ed["h"],
                    json={"row_version": b["row_version"], "acknowledged_inserts": ack, "acknowledged_updates": upd,
                          "acknowledged_retires": ret})
    assert r.status_code == expect, r.text
    return r.json()


def preview(client, ed, pv):
    return client.get(f"{API}/bulk/batches/{pv['batch']['import_batch_id']}/preview", headers=ed["h"]).json()


def rows(pv, kind=None):
    return [r for r in pv["rows"] if kind is None or r["row_kind"] == kind]


def at(pv, kind, path):
    return next(r for r in pv["rows"] if r["row_kind"] == kind and r["source_path"] == path)


def codes(row, which="errors"):
    return [m["code"] for m in row[which]]


def current(client, ed, n):
    return client.get(f"{API}/bfc-nodes/{n['bfc_node_id']}", headers=ed["h"]).json()


def rename(client, ed, n, **fields):
    cur = current(client, ed, n)
    r = client.patch(f"{API}/bfc-nodes/{n['bfc_node_id']}", headers=ed["h"],
                     json={"row_version": cur["row_version"], **fields})
    assert r.status_code == 200, r.text


def batches(db):
    return db.scalar(select(func.count()).select_from(ImportBatch).where(ImportBatch.target_entity == "PROCESS_FLOW"))


@pytest.fixture
def flow(client, ed, area):
    """The area's two steps with a performer, a trigger, inputs and outputs and an external flow."""
    s1, s2 = area["s1"], area["s2"]
    _org_role(client, ed, "CLERK")
    performer(client, ed, s1, "ORG_ROLE", "CLERK")
    performer(client, ed, s2, "AI", label="Credit bot")
    order, decision = entity(client, ed, "Sales order"), entity(client, ed, "Customer order")
    io(client, ed, s1, decision, "I")
    io(client, ed, s1, order, "O")
    starts(client, ed, s1, trigger(client, ed, "Customer calls", "EVENT"))
    ext_flow(client, ed, s1, party(client, ed, "Customer"), "I", decision)
    return {**area, "order": order, "decision": decision}


# ---- §10.1: an export re-imported changes nothing; replace waits for piece (b) ------------------------------------

def test_an_export_reimported_unchanged_changes_nothing(client, ed, flow):
    doc = export(client, ed, flow["parent"])
    pv = stage(client, ed, flow["parent"], doc)
    b = pv["batch"]
    assert (b["error_count"], b["insert_count"], b["update_count"]) == (0, 0, 0), pv["rows"]
    assert {r["verdict"] for r in pv["rows"]} == {"MATCH"}
    assert {r["row_kind"] for r in pv["rows"]} == {"STEP", "PERFORMER", "TRIGGER", "STEP_TRIGGER", "DATA_ENTITY",
                                                   "STEP_IO", "EXTERNAL_ENTITY", "EXTERNAL_FLOW"}
    assert b["target"] == "process-flow" and b["import_mode"] == "MERGE"
    done = commit(client, ed, pv)
    assert done["status"] == "COMMITTED"
    assert export(client, ed, flow["parent"]) == doc                         # nothing moved, not even a version


def test_a_file_cannot_turn_itself_into_a_replace_or_out_of_one(client, ed, db, flow):
    """R2-P3: the mode is chosen on screen; the file's own must agree, both ways, with nothing staged."""
    doc = export(client, ed, flow["parent"])
    before = batches(db)
    assert "you chose replace" in stage(client, ed, flow["parent"], doc, mode="replace", expect=422)["detail"]
    doc["mode"] = "replace"
    assert "you chose merge" in stage(client, ed, flow["parent"], doc, expect=422)["detail"]
    assert batches(db) == before


def test_an_as_is_flow_round_trips_by_name(client, ed):
    root = as_is_root(client, ed)
    area_ = node(client, ed, "Orders (as is)", root["bfc_node_id"])
    s = node(client, ed, "Take the call", area_["bfc_node_id"], is_process=True)
    io(client, ed, s, entity(client, ed, "Call note"), "O")
    doc = export(client, ed, area_)
    assert doc["steps"][0]["br_number"] is None and doc["steps"][0]["hier_code"] == s["hier_code"]
    pv = stage(client, ed, area_, doc)
    assert (pv["batch"]["error_count"], pv["batch"]["insert_count"], pv["batch"]["update_count"]) == (0, 0, 0)
    assert codes(at(pv, "STEP", "/steps/0"), "warnings") == ["MATCHED_BY_NAME"]
    doc["steps"][0]["name"] = "Answer the call"                               # an as-is step is matched by name
    assert codes(at(stage(client, ed, area_, doc), "STEP", "/steps/0")) == ["AS_IS_NOT_FOUND"]
    doc["steps"][0].update(name="Take the call", hier_code="09.09.09")        # FI-11: a cross-check, compared
    assert codes(at(stage(client, ed, area_, doc), "STEP", "/steps/0")) == ["MOVED"]
    doc["steps"][0].update(name="Answer the call", hier_code=None, row_version=None)   # no hier_code: a new step
    pv = stage(client, ed, area_, doc)
    assert pv["batch"]["error_count"] == 0 and at(pv, "STEP", "/steps/0")["verdict"] == "INSERT"


# ---- new steps, their BR, links, catalogue rows (rules 2, 3, 7, 13, 17) ------------------------------------------

def test_a_new_step_is_created_with_its_br_performer_description_triggers_and_io(client, ed, db, flow):
    doc = export(client, ed, flow["parent"])
    doc["steps"].append({"key": "S9", "name": "Ship order", "description": "Pick, pack and ship.",
                         "performer": {"kind": "ORG_ROLE", "code": "clerk"},
                         "triggers": [{"name": "Credit approved", "kind": "EVENT"},
                                      {"name": "Customer calls", "kind": "EVENT"}],
                         "inputs": [flow["order"]["de_number"]], "outputs": ["Delivery note"]})
    pv = stage(client, ed, flow["parent"], doc)
    assert pv["batch"]["error_count"] == 0, [r for r in pv["rows"] if r["errors"]]
    new = {(r["row_kind"], r["source_path"]) for r in pv["rows"] if r["verdict"] == "INSERT"}
    assert new == {("STEP", "/steps/2"), ("TRIGGER", "/steps/2/triggers/0"), ("STEP_TRIGGER", "/steps/2/triggers/0"),
                   ("STEP_TRIGGER", "/steps/2/triggers/1"), ("STEP_IO", "/steps/2/inputs/0"),
                   ("DATA_ENTITY", "/steps/2/outputs/0"), ("STEP_IO", "/steps/2/outputs/0")}
    assert codes(at(pv, "TRIGGER", "/steps/2/triggers/0"), "warnings") == ["NEW_TRIGGER"]
    assert codes(at(pv, "DATA_ENTITY", "/steps/2/outputs/0"), "warnings") == ["NEW_DATA_ENTITY"]
    commit(client, ed, pv, expect=422)                                         # the inserts must be acknowledged
    done = commit(client, ed, pv, ack=7)
    assert done["insert_count"] == 7
    out = export(client, ed, flow["parent"])["steps"][2]
    assert (out["name"], out["description"], out["performer"]) == ("Ship order", "Pick, pack and ship.",
                                                                   {"kind": "ORG_ROLE", "code": "CLERK"})
    assert out["br_number"] and out["br_number"] == at(preview(client, ed, pv), "STEP", "/steps/2")["br_number"]
    assert sorted(t["name"] for t in out["triggers"]) == ["Credit approved", "Customer calls"]
    note = db.scalar(select(DataEntity).where(DataEntity.de_name == "Delivery note"))
    assert out["inputs"] == [flow["order"]["de_number"]] and out["outputs"] == [note.de_number]


def test_a_new_de_and_its_input_share_one_pointer(client, ed, flow):
    """§10.6 (FI-5)."""
    doc = export(client, ed, flow["parent"])
    doc["steps"][0]["inputs"] = ["Price list"]
    pv = stage(client, ed, flow["parent"], doc)
    assert at(pv, "DATA_ENTITY", "/steps/0/inputs/0")["verdict"] == "INSERT"
    assert at(pv, "STEP_IO", "/steps/0/inputs/0")["verdict"] == "INSERT"
    commit(client, ed, pv, ack=2)
    names = {de["de_name"] for de in client.get(f"{API}/projects/{ed['p']}/data-entities", headers=ed["h"]).json()}
    assert "Price list" in names
    # merge never retires: the input the file left out of the list is still there (§7.2b rule 8)
    assert flow["decision"]["de_number"] in export(client, ed, flow["parent"])["steps"][0]["inputs"]


def test_triggers_keep_their_kind_and_a_new_name_given_two_kinds_is_an_error(client, ed, flow):
    """Rule 7."""
    doc = export(client, ed, flow["parent"])
    doc["steps"][0]["triggers"] = [{"name": "customer  CALLS", "kind": "TIME"}]
    doc["steps"][1]["triggers"] = [{"name": "Month end", "kind": "TIME"}]
    doc["steps"][0]["triggers"].append({"name": "Month end", "kind": "EVENT"})
    pv = stage(client, ed, flow["parent"], doc)
    assert at(pv, "TRIGGER", "/steps/0/triggers/0")["verdict"] == "MATCH"
    assert codes(at(pv, "TRIGGER", "/steps/0/triggers/0"), "warnings") == ["KIND_KEPT"]
    assert codes(at(pv, "TRIGGER", "/steps/0/triggers/1")) == ["TWO_KINDS"]


def test_new_parties_and_flows_stage_as_inserts_and_an_unknown_ext_number_is_an_error(client, ed, flow):
    """Rule 8 (piece b): a new name is a new party, a new flow is an insert; an unknown number is an error."""
    doc = export(client, ed, flow["parent"])
    doc["external_entities"].append({"key": "X2", "name": "Bank", "kind": "SUPPLIER"})
    doc["external_entities"].append({"key": "X3", "ext_number": "EXT-0999", "name": "Ghost"})
    doc["steps"][1]["external_flows"] = [{"external": "X1", "direction": "O", "data_entity": None}]
    pv = stage(client, ed, flow["parent"], doc)
    bank = at(pv, "EXTERNAL_ENTITY", "/external_entities/1")
    assert (bank["verdict"], bank["errors"], codes(bank, "warnings")) == ("INSERT", [], ["NEW_PARTY"])
    assert codes(at(pv, "EXTERNAL_ENTITY", "/external_entities/2")) == ["PARTY_UNKNOWN"]
    new_flow = at(pv, "EXTERNAL_FLOW", "/steps/1/external_flows/0")
    assert (new_flow["verdict"], new_flow["errors"]) == ("INSERT", [])
    assert at(pv, "EXTERNAL_FLOW", "/steps/0/external_flows/0")["verdict"] == "MATCH"


# ---- performer and description (rules 3, 12; §10.3, §10.12) -----------------------------------------------------

def test_an_unknown_performer_keeps_the_current_one_and_null_clears_it(client, ed, db, flow):
    doc = export(client, ed, flow["parent"])
    doc["steps"][0]["performer"] = {"kind": "ORG_ROLE", "code": "NOBODY"}
    pv = stage(client, ed, flow["parent"], doc)
    assert codes(at(pv, "PERFORMER", "/steps/0/performer"), "warnings") == ["UNKNOWN_PERFORMER"]
    assert at(pv, "STEP", "/steps/0")["verdict"] == "MATCH"
    doc["steps"][0]["performer"] = None
    pv = stage(client, ed, flow["parent"], doc)
    step = at(pv, "STEP", "/steps/0")
    assert step["verdict"] == "UPDATE"
    assert step["changes"] == [{"column": "performer", "before": "ORG_ROLE CLERK", "after": None, "cleared": True}]
    commit(client, ed, pv, upd=1)
    assert export(client, ed, flow["parent"])["steps"][0]["performer"] is None
    # performer left out: kept (FI-2)
    doc = export(client, ed, flow["parent"])
    del doc["steps"][1]["performer"]
    assert at(stage(client, ed, flow["parent"], doc), "STEP", "/steps/1")["verdict"] == "MATCH"


def test_a_description_left_out_is_kept_and_an_empty_one_clears_it(client, ed, flow):
    rename(client, ed, flow["s1"], data_processing_desc="Keyed in by the clerk.")
    doc = export(client, ed, flow["parent"])
    del doc["steps"][0]["description"]
    assert at(stage(client, ed, flow["parent"], doc), "STEP", "/steps/0")["verdict"] == "MATCH"
    doc["steps"][0]["description"] = "  "
    pv = stage(client, ed, flow["parent"], doc)
    assert at(pv, "STEP", "/steps/0")["changes"] == [{"column": "description", "before": "Keyed in by the clerk.",
                                                      "after": None, "cleared": True}]
    commit(client, ed, pv, upd=1)
    assert current(client, ed, flow["s1"])["data_processing_desc"] is None


def test_description_and_performer_change_together_on_one_step(client, ed, flow):
    """Rule 17 (D6): each call takes the step's row_version after the one before it."""
    doc = export(client, ed, flow["parent"])
    doc["steps"][1].update(description="Scored by the bot.", performer={"kind": "ORG_ROLE", "code": "CLERK"},
                           name="Check credit limit")
    pv = stage(client, ed, flow["parent"], doc)
    assert [c["column"] for c in at(pv, "STEP", "/steps/1")["changes"]] == ["name", "description", "performer"]
    commit(client, ed, pv, upd=1)
    out = export(client, ed, flow["parent"])["steps"][1]
    assert (out["name"], out["description"], out["performer"]) == ("Check credit limit", "Scored by the bot.",
                                                                   {"kind": "ORG_ROLE", "code": "CLERK"})


# ---- identity and scope (rules 1, 4, 5, 11; §10.4, §10.7, §10.10, §10.11) ----------------------------------------

def test_stale_steps_are_errors_named_with_their_current_values_and_the_rest_stage(client, ed, area):
    parent = area["parent"]
    more = [node(client, ed, n, parent["bfc_node_id"], is_process=True) for n in ("Pack", "Ship", "Bill")]
    doc = export(client, ed, parent)
    rename(client, ed, area["s1"], node_name="Receive the order")
    rename(client, ed, more[0], data_processing_desc="Pack it well.")
    pv = stage(client, ed, parent, doc)
    stale = [r for r in rows(pv, "STEP") if "STALE" in codes(r)]
    assert [r["source_path"] for r in stale] == ["/steps/0", "/steps/2"]
    assert stale[0]["errors"][0]["params"]["name"] == "Receive the order"
    assert stale[1]["errors"][0]["params"]["description"] == "Pack it well."
    assert [r["is_valid"] for r in rows(pv, "STEP")] == [False, True, False, True, True]
    assert "Fix 2 rows" in commit(client, ed, pv, expect=422)["detail"]


def test_a_br_number_without_its_version_is_an_error_and_the_step_is_unchanged(client, ed, flow):
    """§10.10 (D1, rule 11)."""
    doc = export(client, ed, flow["parent"])
    doc["steps"][0].update(row_version=None, name="Something else")
    pv = stage(client, ed, flow["parent"], doc)
    assert codes(at(pv, "STEP", "/steps/0")) == ["BR_NEEDS_VERSION"]
    assert current(client, ed, flow["s1"])["node_name"] == "Receive order"


def test_a_br_outside_the_anchors_own_steps_is_an_error(client, ed, area):
    """§10.11 (FI-9): a grandchild's BR is not the anchor's step."""
    l1 = area["l1"]
    sub = node(client, ed, "Returns", l1["bfc_node_id"])
    mine = node(client, ed, "Log return", sub["bfc_node_id"], is_process=True)
    doc = export(client, ed, sub)
    doc["parent"]["hier_code"] = area["parent"]["hier_code"]
    pv = stage(client, ed, area["parent"], doc)
    assert codes(at(pv, "STEP", "/steps/0")) == ["BR_OUT_OF_SCOPE"]
    assert at(pv, "STEP", "/steps/0")["errors"][0]["params"]["br_number"] == br_of(client, ed, mine["bfc_node_id"])


def test_a_moved_step_and_a_hier_code_without_a_br_number_are_errors(client, ed, flow):
    doc = export(client, ed, flow["parent"])
    doc["steps"][0]["hier_code"] = "09.09.09"
    doc["steps"][1].update(br_number=None, row_version=None)
    pv = stage(client, ed, flow["parent"], doc)
    assert codes(at(pv, "STEP", "/steps/0")) == ["MOVED"]
    assert codes(at(pv, "STEP", "/steps/1")) == ["HIER_WITHOUT_BR"]


def test_a_step_named_like_a_live_non_process_child_is_an_error_at_validate(client, ed, area):
    """§10.7 (rule 5): never a 409 at commit."""
    node(client, ed, "Order history", area["parent"]["bfc_node_id"])
    doc = export(client, ed, area["parent"])
    doc["steps"].append({"key": "S3", "name": "order HISTORY"})
    doc["steps"].append({"key": "S4", "name": "Check  credit "})                  # matches the live step by name
    doc["steps"].append({"key": "S5", "name": "Receive order"})                  # BR S1 already took it
    pv = stage(client, ed, area["parent"], doc)
    assert codes(at(pv, "STEP", "/steps/2")) == ["NAME_TAKEN"]
    assert codes(at(pv, "STEP", "/steps/3")) == ["TWO_STEPS_ONE_NODE", "NAME_REPEATED"]
    assert codes(at(pv, "STEP", "/steps/4")) == ["TWO_STEPS_ONE_NODE", "NAME_REPEATED"]


# ---- the file itself (§10.9): 422, nothing staged -----------------------------------------------------------------

@pytest.mark.parametrize("spoil, says", [
    (lambda d: d["steps"][0].update(edges=[]), "Extra inputs"),
    (lambda d: d.update(lanes=[]), "Extra inputs"),
    (lambda d: d.update(format="vb-process-flow/1.0"), "1.0 file"),
    (lambda d: d["parent"].update(hier_code="99"), "This file is for 99"),
    (lambda d: d["steps"][1].update(key="S1"), "share the key"),
    (lambda d: d.update(steps=[]), "at least 1"),
])
def test_a_bad_file_is_refused_with_nothing_staged(client, ed, db, flow, spoil, says):
    doc = export(client, ed, flow["parent"])
    spoil(doc)
    before = batches(db)
    assert says in stage(client, ed, flow["parent"], doc, expect=422)["detail"]
    assert batches(db) == before


def test_unreadable_json_is_refused(client, ed, flow):
    good = json.dumps(export(client, ed, flow["parent"]))
    assert "not a readable JSON" in stage(client, ed, flow["parent"], None, raw=b"{nope", expect=422)["detail"]
    nan = good.replace('"row_version": ', '"row_version": NaN, "x": ', 1).encode()
    assert "not a readable JSON" in stage(client, ed, flow["parent"], None, raw=nan, expect=422)["detail"]
    dup = good.replace('"mode": "merge"', '"mode": "merge", "mode": "merge"').encode()
    assert "appears twice" in stage(client, ed, flow["parent"], None, raw=dup, expect=422)["detail"]
    deep = b"[" * 100_000 + b"]" * 100_000
    assert stage(client, ed, flow["parent"], None, raw=deep, expect=422)
    r = client.post(f"{API}/projects/{ed['p']}/bulk/process-flow/validate",
                    params={"anchor_bfc_node_id": flow["parent"]["bfc_node_id"]},
                    headers={**ed["h"], "Content-Type": "text/plain"}, content=good.encode())
    assert r.status_code == 415


def test_an_anchor_from_another_project_is_404_and_nothing_is_written_there(client, world, ed, db):
    """sara H2: the route's project is the editor's; the anchor is the only other way in. An anchor in another
    project — here one the editor can see — is 404, nothing staged, nothing written into that project."""
    other = {"h": world["admin"], "p": world["p_sales"]}
    a = node(client, other, "Sales elsewhere")
    b = node(client, other, "Orders elsewhere", a["bfc_node_id"])
    node(client, other, "Take order", b["bfc_node_id"], is_process=True)
    doc = export(client, other, b)
    doc["steps"].append({"key": "SX", "name": "Planted step"})
    count = select(func.count()).select_from(BfcNode).where(BfcNode.project_id == world["p_sales"])
    before, staged_before = db.scalar(count), batches(db)
    assert stage(client, ed, b, doc, expect=404)["detail"] == "Not found"
    assert (db.scalar(count), batches(db)) == (before, staged_before)


def test_a_failed_apply_leaves_nothing_behind(client, ed, db, flow, monkeypatch):
    """sara M1: one writer failing on the last row rolls back every row before it — the new DE, trigger, step and
    its BR — and the batch is rejected with the error on that row."""
    from services import flow_import

    def refuse(*_a, **_k):
        raise HTTPException(409, "refused for the test")
    doc = export(client, ed, flow["parent"])
    doc["steps"].append({"key": "S9", "name": "Ship order", "triggers": [{"name": "Truck arrives", "kind": "EVENT"}],
                         "outputs": ["Delivery note"]})
    pv = stage(client, ed, flow["parent"], doc)
    counts = [select(func.count()).select_from(m).where(m.project_id == ed["p"])
              for m in (BfcNode, DataEntity, ProcessTrigger, BusinessRequirement)]
    before = [db.scalar(c) for c in counts]
    monkeypatch.setattr(flow_import.trigger, "link", refuse)
    assert "could not be applied" in commit(client, ed, pv, ack=pv["batch"]["insert_count"], expect=422)["detail"]
    db.expire_all()
    assert [db.scalar(c) for c in counts] == before
    after = preview(client, ed, pv)
    assert after["batch"]["status"] == "REJECTED"
    assert codes(at(after, "STEP_TRIGGER", "/steps/2/triggers/0")) == ["APPLY_FAILED"]


def test_a_multi_line_description_round_trips_and_a_blank_ai_label_is_an_error(client, ed, flow):
    """sara H1 (a description is kept as given) and M2 (a blank AI label is caught at validate, not at commit)."""
    rename(client, ed, flow["s1"], data_processing_desc="Line one.\n\n  Line two.")
    doc = export(client, ed, flow["parent"])
    pv = stage(client, ed, flow["parent"], doc)
    assert (pv["batch"]["update_count"], pv["batch"]["error_count"]) == (0, 0)
    doc["steps"][1]["performer"] = {"kind": "AI", "label": "  "}
    assert codes(at(stage(client, ed, flow["parent"], doc), "PERFORMER", "/steps/1/performer")) == ["NAME_REQUIRED"]


def test_a_viewer_cannot_import_and_an_outsider_sees_nothing(client, ed, flow):
    doc = export(client, ed, flow["parent"])
    for who, status in (("rv", 403), ("out", 404)):
        r = client.post(f"{API}/projects/{ed['p']}/bulk/process-flow/validate",
                        params={"anchor_bfc_node_id": flow["parent"]["bfc_node_id"]},
                        headers={**ed[who], "Content-Type": "application/json"}, content=json.dumps(doc).encode())
        assert r.status_code == status, r.text


# ---- cleaning and matching (rule 13; §10.13) ----------------------------------------------------------------------

def test_one_cleaning_one_match(client, ed, db, flow):
    doc = export(client, ed, flow["parent"])
    doc["steps"][1]["inputs"] = ["Sales order ", flow["order"]["de_number"]]
    pv = stage(client, ed, flow["parent"], doc)
    assert all(r["verdict"] != "INSERT" for r in rows(pv, "DATA_ENTITY"))         # no new DE
    io_rows = [r for r in rows(pv, "STEP_IO") if r["source_path"].startswith("/steps/1/")]
    assert len(io_rows) == 1 and codes(io_rows[0], "warnings") == ["REPEATED"]
    commit(client, ed, pv, ack=1)
    assert db.scalar(select(func.count()).select_from(DataEntity).where(DataEntity.de_name.ilike("sales order%"))) == 1


def test_a_name_matching_two_live_records_once_cleaned_is_an_error(client, ed, flow):
    """N2 (VB-005): 'Month  end' and 'month end' are two live triggers; the file's 'Month end' names both."""
    trigger(client, ed, "Month  end")
    trigger(client, ed, "month end ")
    doc = export(client, ed, flow["parent"])
    doc["steps"][1]["triggers"] = [{"name": "Month end", "kind": "TIME"}]
    assert codes(at(stage(client, ed, flow["parent"], doc), "TRIGGER", "/steps/1/triggers/0")) == ["NAME_AMBIGUOUS"]


# ---- version pinned, updates acknowledged and audited (rules 14, 15; §10.14, §10.15) ------------------------------

def test_an_edit_after_the_preview_rejects_the_commit_and_survives(client, ed, db, flow):
    doc = export(client, ed, flow["parent"])
    doc["steps"][0]["description"] = "From the file."
    pv = stage(client, ed, flow["parent"], doc)
    rename(client, ed, flow["s1"], data_processing_desc="A colleague's text.")
    assert "rejected" in commit(client, ed, pv, upd=1, expect=422)["detail"]
    assert current(client, ed, flow["s1"])["data_processing_desc"] == "A colleague's text."
    after = preview(client, ed, pv)
    assert after["batch"]["status"] == "REJECTED"
    assert codes(at(after, "STEP", "/steps/0")) == ["STALE"]


def test_updates_must_be_acknowledged_and_their_before_texts_are_audited(client, ed, db, area):
    parent = area["parent"]
    node(client, ed, "Pack", parent["bfc_node_id"], is_process=True)
    rename(client, ed, area["s1"], data_processing_desc="Old one.")
    doc = export(client, ed, parent)
    for i, s in enumerate(doc["steps"]):
        s["description"] = f"New {i}."
    pv = stage(client, ed, parent, doc)
    assert pv["batch"]["update_count"] == 3
    assert "CHANGE 3 existing steps" in commit(client, ed, pv, expect=422)["detail"]
    commit(client, ed, pv, upd=2, expect=422)
    commit(client, ed, pv, upd=3)
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "IMPORT_COMMITTED")
                    .order_by(AuditEvent.audit_event_id.desc())).first()
    assert ev.detail["entity"] == "PROCESS_FLOW" and ev.detail["update_count"] == 3
    assert [(u["name_before"], u["description_before"]) for u in ev.detail["updated_steps"]] == [
        ("Receive order", "Old one."), ("Check credit", None), ("Pack", None)]
    done = preview(client, ed, pv)                                             # the stored before, after commit
    assert at(done, "STEP", "/steps/0")["changes"][0]["before"] == "Old one."


# ---- what the file did not name (rule 16; §10.16) ------------------------------------------------------------------

def test_a_live_step_left_out_is_kept_and_a_close_new_name_warns(client, ed, area):
    doc = export(client, ed, area["parent"])
    doc["steps"] = [doc["steps"][0], {"key": "S7", "name": "Check customer credit"}]
    pv = stage(client, ed, area["parent"], doc)
    assert [m["code"] for m in pv["batch"]["file_warnings"]] == ["NOT_IN_FILE"]
    assert pv["batch"]["file_warnings"][0]["params"]["name"] == "Check credit"
    assert codes(at(pv, "STEP", "/steps/1"), "warnings") == ["POSSIBLE_DUPLICATE"]


# ---- the component (P3; §10.17) ----------------------------------------------------------------------------------

def test_the_anchors_dfd_component_off_refuses_validate_and_commit(client, world, ed, db, area):
    """P3: the component is the anchor's chart's DFD component, at validate and at commit. AS_IS cannot be switched
    off while as-is rows live, so the to-be chart's TO_BE_DFD (no DFD links yet) proves the same rule."""
    doc = export(client, ed, area["parent"])
    doc["steps"][0]["description"] = "Changed."
    pv = stage(client, ed, area["parent"], doc)
    switch(client, world, ed["p"], ALL_BUT_TO_BE_DFD)                                 # TO_BE_DFD off
    r = client.post(f"{API}/bulk/batches/{pv['batch']['import_batch_id']}/commit", headers=ed["h"],
                    json={"row_version": pv["batch"]["row_version"], "acknowledged_updates": 1})
    assert r.status_code == 409 and r.headers["X-VB-Error"] == "COMPONENT_OFF", r.text
    assert preview(client, ed, pv)["batch"]["status"] == "VALIDATED"            # refused, not applied
    assert current(client, ed, area["s1"])["data_processing_desc"] is None
    before = batches(db)
    stage(client, ed, area["parent"], doc, expect=409)
    assert batches(db) == before


# ---- §10.8: every row that validates clean commits ---------------------------------------------------------------

def test_every_file_that_validates_clean_commits(client, ed, db, flow):
    """A seeded random mix of new steps, renames, new and known data entities and triggers, performers and
    descriptions — whatever stages clean must commit, and the result must export back as staged."""
    rng = random.Random(1028)
    for round_ in range(4):
        doc = export(client, ed, flow["parent"])
        live_des = [flow["order"]["de_number"], flow["decision"]["de_number"], "Sales order"]
        for s in doc["steps"]:
            if rng.random() < 0.5:
                s["description"] = rng.choice(["", f"Round {round_}.", None])
            if rng.random() < 0.5:
                s["inputs"] = rng.sample(live_des, 2) + [f"Doc {round_}"]
            if rng.random() < 0.3:
                s["performer"] = rng.choice([None, {"kind": "AI", "label": f"Bot {round_}"},
                                             {"kind": "ORG_ROLE", "code": "CLERK"}])
        for k in range(rng.randint(0, 2)):
            doc["steps"].append({"key": f"N{round_}{k}", "name": f"New step {round_}.{k}",
                                 "triggers": [{"name": rng.choice(["Customer calls", f"Tick {round_}"]),
                                               "kind": "EVENT"}],
                                 "outputs": [rng.choice(live_des + [f"Out {round_}.{k}"])]})
        pv = stage(client, ed, flow["parent"], copy.deepcopy(doc))
        bad = [r for r in pv["rows"] if r["errors"]]
        assert not bad, bad
        b = pv["batch"]
        commit(client, ed, pv, ack=b["insert_count"] or None, upd=b["update_count"] or None)
        again = stage(client, ed, flow["parent"], export(client, ed, flow["parent"]))
        assert (again["batch"]["insert_count"], again["batch"]["update_count"]) == (0, 0)
    assert db.scalar(select(func.count()).select_from(BfcNode).where(
        BfcNode.parent_bfc_node_id == flow["parent"]["bfc_node_id"], BfcNode.is_active)) >= 2
    assert db.scalar(select(func.count()).select_from(BfcNodeDataEntity)) > 0
    assert db.scalar(select(func.count()).select_from(BfcNodeTrigger)) > 0
    assert db.scalar(select(func.count()).select_from(ProcessTrigger)) >= 1
