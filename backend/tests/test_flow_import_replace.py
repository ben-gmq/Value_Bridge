"""Slice 1e-b piece (b): new outside parties and flows, and replace mode (design §7.2b rules 6 and 8; spec §4 rules 8–10,
§10.1, §10.2, §10.5). Grade 2: replace soft-retires links of a client's flow, so every test here pins what is retired
and — as much — what is not: steps, BRs, parties, flows, data entities, catalogue triggers, unstated lists and steps
the file does not name. Every retirement is a soft delete and audited."""
import copy
import random

from sqlalchemy import select

from models import (AuditEvent, BfcNodeDataEntity, BfcNodeExternalFlow, BfcNodeTrigger, DataEntity, ExternalEntity,
                    ImportBatch, ProcessTrigger)
from tests.test_dfd_api import area, ext_flow, io, party, starts, trigger  # noqa: F401
from tests.test_flow_import import at, batches, codes, commit, export, flow, preview, rows, stage  # noqa: F401
from tests.test_scope_api import API, br_of, brs, ed, entity, node  # noqa: F401 — ed is a fixture


def replace(doc):
    doc = copy.deepcopy(doc)
    doc["mode"] = "replace"
    return doc


def live_io(db, step):
    return {(r.direction, r.data_entity_id) for r in db.scalars(select(BfcNodeDataEntity).where(
        BfcNodeDataEntity.bfc_node_id == step["bfc_node_id"], BfcNodeDataEntity.is_active))}


def live_triggers(db, step):
    return {r.process_trigger_id for r in db.scalars(select(BfcNodeTrigger).where(
        BfcNodeTrigger.bfc_node_id == step["bfc_node_id"], BfcNodeTrigger.is_active))}


def live_flows(db, step):
    return list(db.scalars(select(BfcNodeExternalFlow).where(
        BfcNodeExternalFlow.bfc_node_id == step["bfc_node_id"], BfcNodeExternalFlow.is_active)))


def commit_all(client, ed, pv, expect=200):
    b = pv["batch"]
    return commit(client, ed, pv, ack=b["insert_count"] or None, upd=b["update_count"] or None,
                  ret=b["retire_count"] or None, expect=expect)


def retired(pv):
    return [r for r in pv["rows"] if r["verdict"] == "RETIRE"]


# ---- §10.1: an unchanged export in replace mode retires nothing ---------------------------------------------------

def test_an_export_reimported_in_replace_mode_changes_nothing(client, ed, db, flow):
    doc = export(client, ed, flow["parent"])
    pv = stage(client, ed, flow["parent"], replace(doc), mode="replace")
    b = pv["batch"]
    assert (b["error_count"], b["insert_count"], b["update_count"], b["retire_count"]) == (0, 0, 0, 0), pv["rows"]
    assert {r["verdict"] for r in pv["rows"]} == {"MATCH"} and b["import_mode"] == "REPLACE"
    assert commit(client, ed, pv)["status"] == "COMMITTED"
    assert export(client, ed, flow["parent"]) == doc


# ---- §10.2 (FI-1): a list left out says nothing; only an explicit [] retires --------------------------------------

def test_triggers_left_out_are_kept_and_an_empty_list_retires_them(client, ed, db, flow):
    s1 = flow["s1"]
    for name in ("Month end", "Order e-mail"):
        starts(client, ed, s1, trigger(client, ed, name, "TIME" if name == "Month end" else "EVENT"))
    assert len(live_triggers(db, s1)) == 3
    doc = replace(export(client, ed, flow["parent"]))
    del doc["steps"][0]["triggers"]
    pv = stage(client, ed, flow["parent"], doc, mode="replace")
    assert pv["batch"]["retire_count"] == 0 and not retired(pv)

    doc["steps"][0]["triggers"] = []
    pv = stage(client, ed, flow["parent"], doc, mode="replace")
    gone = retired(pv)
    assert pv["batch"]["retire_count"] == 3 and {r["row_kind"] for r in gone} == {"STEP_TRIGGER"}
    assert all(r["source_path"] is None and r["target_label"].endswith(t) for r, t in
               zip(gone, ("Customer calls", "Month end", "Order e-mail")))
    assert "RETIRE 3" in commit(client, ed, pv, expect=422)["detail"]          # the count is acknowledged
    assert len(live_triggers(db, s1)) == 3
    done = commit(client, ed, pv, ret=3)
    db.expire_all()
    assert done["status"] == "COMMITTED" and live_triggers(db, s1) == set()
    assert db.scalar(select(ProcessTrigger).where(ProcessTrigger.trigger_name == "Month end")).is_active
    event = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "IMPORT_COMMITTED")
                       .order_by(AuditEvent.audit_event_id.desc())).first()
    assert event.detail["retire_count"] == 3 and event.detail["mode"] == "REPLACE"
    assert export(client, ed, flow["parent"])["steps"][0]["triggers"] == []


def test_inputs_and_outputs_retire_only_in_the_direction_the_file_states(client, ed, db, flow):
    s1 = flow["s1"]
    extra = entity(client, ed, "Price list")
    io(client, ed, s1, extra, "I")
    before = live_io(db, s1)
    doc = replace(export(client, ed, flow["parent"]))
    doc["steps"][0]["outputs"] = []                       # outputs stated empty, inputs not touched
    del doc["steps"][0]["inputs"]
    pv = stage(client, ed, flow["parent"], doc, mode="replace")
    assert [r["target_label"].split(" — ")[1] for r in retired(pv)] == \
        [f"output {flow['order']['de_number']} Sales order"]
    commit_all(client, ed, pv)
    db.expire_all()
    assert live_io(db, s1) == before - {("O", flow["order"]["data_entity_id"])}
    assert db.get(DataEntity, flow["order"]["data_entity_id"]).is_active          # the entity itself stays


# ---- §10.5 (FI-4) and the KEPT rule ---------------------------------------------------------------------------------

def test_io_named_only_by_the_steps_own_external_flow_is_matched_not_retired(client, ed, db, flow):
    s1 = flow["s1"]
    ext_flow(client, ed, s1, {"external_entity_id": live_flows(db, s1)[0].external_entity_id}, "O", flow["order"])
    doc = replace(export(client, ed, flow["parent"]))
    doc["steps"][0]["inputs"], doc["steps"][0]["outputs"] = [], []
    pv = stage(client, ed, flow["parent"], doc, mode="replace")
    assert pv["batch"]["retire_count"] == 0 and not [r for r in pv["rows"] if r["verdict"] == "KEPT"]
    implied = [r for r in rows(pv, "STEP_IO") if r["source_path"].startswith("/steps/0/external_flows/")]
    assert {r["verdict"] for r in implied} == {"MATCH"} and len(implied) == 2


def test_io_an_external_flow_or_a_br_crud_needs_is_kept_with_a_warning(client, ed, db, flow):
    s1, s2 = flow["s1"], flow["s2"]
    br = brs(client, ed)[br_of(client, ed, s2["bfc_node_id"])]
    r = client.post(f"{API}/business-requirements/{br['br_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": flow["order"]["data_entity_id"], "crud_code": "R"})
    assert r.status_code == 201, r.text
    doc = replace(export(client, ed, flow["parent"]))
    doc["steps"][0]["inputs"], doc["steps"][0]["external_flows"] = [], []      # the flow stays: never retired
    doc["steps"][1]["inputs"] = []
    pv = stage(client, ed, flow["parent"], doc, mode="replace")
    kept = [r for r in pv["rows"] if r["verdict"] == "KEPT"]
    assert pv["batch"]["retire_count"] == 0 and len(kept) == 2
    by_step = {r["target_label"].split(" — ")[0].split(" ", 1)[1]: r for r in kept}
    assert by_step["Receive order"]["warnings"][0]["code"] == "KEPT_DEPENDENT"
    assert "EXT-" in by_step["Receive order"]["warnings"][0]["message"]
    assert f"{br['br_number']} R" in by_step["Check credit"]["warnings"][0]["message"]
    commit_all(client, ed, pv)
    db.expire_all()
    assert ("I", flow["decision"]["data_entity_id"]) in live_io(db, s1) and len(live_flows(db, s1)) == 1
    assert ("I", flow["order"]["data_entity_id"]) in live_io(db, s2)


# ---- what replace never touches ------------------------------------------------------------------------------------

def test_replace_never_touches_steps_the_file_leaves_out_or_other_anchors(client, ed, db, flow):
    s1, s2 = flow["s1"], flow["s2"]
    elsewhere = node(client, ed, "Invoicing", flow["l1"]["bfc_node_id"])
    far = node(client, ed, "Send invoice", elsewhere["bfc_node_id"], is_process=True)
    io(client, ed, far, flow["order"], "I")
    io(client, ed, s2, flow["order"], "I")
    starts(client, ed, s2, trigger(client, ed, "Daily run", "TIME"))
    keep = (live_io(db, s2), live_triggers(db, s2), live_io(db, far))
    doc = replace(export(client, ed, flow["parent"]))
    doc["steps"] = [doc["steps"][0]]                                   # s2 left out of the file
    doc["steps"][0].update(inputs=[], outputs=[], triggers=[], external_flows=[])
    pv = stage(client, ed, flow["parent"], doc, mode="replace")
    assert {r["target_label"].split(" — ")[0] for r in retired(pv) + [r for r in pv["rows"] if r["verdict"] == "KEPT"]} \
        == {f"{s1['hier_code']} Receive order"}
    commit_all(client, ed, pv)
    db.expire_all()
    assert (live_io(db, s2), live_triggers(db, s2), live_io(db, far)) == keep
    assert db.scalars(select(ExternalEntity)).first().is_active and len(live_flows(db, s1)) == 1


# ---- acknowledgement and the re-check inside the lock --------------------------------------------------------------

def test_a_change_to_the_retire_set_after_the_preview_is_409_and_nothing_is_written(client, ed, db, flow):
    s1 = flow["s1"]
    doc = replace(export(client, ed, flow["parent"]))
    doc["steps"][0]["outputs"] = []
    pv = stage(client, ed, flow["parent"], doc, mode="replace")
    assert pv["batch"]["retire_count"] == 1
    io(client, ed, s1, entity(client, ed, "Packing slip"), "O")          # a colleague adds an output meanwhile
    before = live_io(db, s1)
    r = commit(client, ed, pv, ret=1, expect=409)
    assert "validate the file again" in r["detail"]
    db.expire_all()
    assert live_io(db, s1) == before


def test_a_retire_that_gains_a_dependent_after_the_preview_is_409(client, ed, db, flow):
    s1 = flow["s1"]
    doc = replace(export(client, ed, flow["parent"]))
    doc["steps"][0]["outputs"] = []
    pv = stage(client, ed, flow["parent"], doc, mode="replace")
    br = brs(client, ed)[br_of(client, ed, s1["bfc_node_id"])]
    r = client.post(f"{API}/business-requirements/{br['br_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": flow["order"]["data_entity_id"], "crud_code": "C"})
    assert r.status_code == 201, r.text
    commit(client, ed, pv, ret=1, expect=409)
    db.expire_all()
    assert ("O", flow["order"]["data_entity_id"]) in live_io(db, s1)


# ---- new parties and flows (rule 8, rule 10) -----------------------------------------------------------------------

def test_a_new_party_and_flow_are_created_with_their_io_and_round_trip(client, ed, db, flow):
    s2 = flow["s2"]
    doc = export(client, ed, flow["parent"])
    doc["external_entities"].append({"key": "B", "name": "Credit bureau", "kind": "SUPPLIER"})
    doc["steps"][1]["external_flows"] = [{"external": "B", "direction": "I", "data_entity": "Credit report"},
                                         {"external": "B", "direction": "I", "data_entity": "Credit report"}]
    doc["steps"].append({"key": "S9", "name": "Notify bureau",
                         "external_flows": [{"external": "B", "direction": "O", "data_entity": None}]})
    pv = stage(client, ed, flow["parent"], doc)
    assert pv["batch"]["error_count"] == 0, [r for r in pv["rows"] if r["errors"]]
    assert codes(at(pv, "EXTERNAL_FLOW", "/steps/1/external_flows/0"), "warnings") == ["REPEATED"]
    assert len(rows(pv, "EXTERNAL_FLOW")) == 3                          # the repeat is one flow
    commit_all(client, ed, pv)
    db.expire_all()
    bureau = db.scalar(select(ExternalEntity).where(ExternalEntity.ext_name == "Credit bureau"))
    assert bureau.is_active and bureau.ext_number.startswith("EXT-") and bureau.kind_code_row.code == "SUPPLIER"
    report = db.scalar(select(DataEntity).where(DataEntity.de_name == "Credit report"))
    assert [(f.direction, f.data_entity_id) for f in live_flows(db, s2)] == [("I", report.data_entity_id)]
    assert ("I", report.data_entity_id) in live_io(db, s2)                    # R2-D13: the flow ensured its I/O
    assert at(preview(client, ed, pv), "EXTERNAL_ENTITY", "/external_entities/1")["ext_number"] == bureau.ext_number
    again = stage(client, ed, flow["parent"], export(client, ed, flow["parent"]))
    assert (again["batch"]["insert_count"], again["batch"]["update_count"]) == (0, 0)


def test_a_bad_new_party_is_an_error_on_its_row(client, ed, flow):
    doc = export(client, ed, flow["parent"])
    doc["external_entities"] += [{"key": "B", "name": "Bank", "kind": "NOT-A-KIND"},
                                 {"key": "C", "name": "Courier"}, {"key": "D", "name": " courier "}]
    pv = stage(client, ed, flow["parent"], doc)
    assert codes(at(pv, "EXTERNAL_ENTITY", "/external_entities/1")) == ["KIND_UNKNOWN"]
    assert at(pv, "EXTERNAL_ENTITY", "/external_entities/2")["errors"] == []      # a kind is optional
    assert codes(at(pv, "EXTERNAL_ENTITY", "/external_entities/3")) == ["NAME_REPEATED"]


def test_a_retired_flow_is_restored_with_its_old_label(client, ed, db, flow):
    s2 = flow["s2"]
    customer = {"external_entity_id": live_flows(db, flow["s1"])[0].external_entity_id}
    made = ext_flow(client, ed, s2, customer, "O", flow["decision"], label="Decision letter")
    r = client.delete(f"{API}/bfc-nodes/{s2['bfc_node_id']}/external-flows/{made['bfc_node_external_flow_id']}",
                      headers=ed["h"], params={"row_version": made["row_version"]})
    assert r.status_code == 204, r.text
    doc = export(client, ed, flow["parent"])
    doc["steps"][1]["external_flows"] = [{"external": "X1", "direction": "O",
                                          "data_entity": flow["decision"]["de_number"]}]
    pv = stage(client, ed, flow["parent"], doc)
    assert at(pv, "EXTERNAL_FLOW", "/steps/1/external_flows/0")["verdict"] == "INSERT"
    commit_all(client, ed, pv)
    db.expire_all()
    back = db.get(BfcNodeExternalFlow, made["bfc_node_external_flow_id"])
    assert back.is_active and back.flow_label == "Decision letter"           # the same row, its label kept


# ---- every replace file that validates clean commits, and removes exactly what it staged --------------------------

def test_every_replace_file_that_validates_clean_commits_and_removes_exactly_its_retire_rows(client, ed, db, flow):
    rng = random.Random(1029)
    for name in ("Month end", "Order e-mail", "Daily run"):
        trig = trigger(client, ed, name, "TIME")
        for s in (flow["s1"], flow["s2"]):
            if rng.random() < 0.7:
                starts(client, ed, s, trig)
    for k in range(4):
        de = entity(client, ed, f"Doc {k}")
        for s in (flow["s1"], flow["s2"]):
            io(client, ed, s, de, rng.choice("IO"))
    total = 0
    for round_ in range(4):
        doc = replace(export(client, ed, flow["parent"]))
        for s in doc["steps"]:
            for key in ("inputs", "outputs", "triggers"):
                roll = rng.random()
                if roll < 0.25:
                    del s[key]
                elif roll < 0.5:
                    s[key] = []
                elif roll < 0.8:
                    s[key] = rng.sample(s[key], len(s[key]) // 2)
            if rng.random() < 0.3:
                s["external_flows"] = []
        steps = {"S1": flow["s1"], "S2": flow["s2"]}
        before = {k: (live_io(db, s), live_triggers(db, s)) for k, s in steps.items()}
        pv = stage(client, ed, flow["parent"], copy.deepcopy(doc), mode="replace")
        assert not [r for r in pv["rows"] if r["errors"]]
        assert pv["batch"]["insert_count"] == 0                     # replace removes, it never adds back here
        gone = {(r["row_kind"], r["target_label"]) for r in retired(pv)}
        commit_all(client, ed, pv)
        db.expire_all()
        after = {k: (live_io(db, s), live_triggers(db, s)) for k, s in steps.items()}
        lost = sum(len(before[k][0] - after[k][0]) + len(before[k][1] - after[k][1]) for k in steps)
        assert lost == len(gone) == pv["batch"]["retire_count"]
        total += lost
        assert all(after[k][0] <= before[k][0] and after[k][1] <= before[k][1] for k in steps)
        again = stage(client, ed, flow["parent"], replace(export(client, ed, flow["parent"])), mode="replace")
        assert again["batch"]["retire_count"] == 0
    assert total >= 5, total                                          # the rounds did retire something
    assert batches(db) >= 8
    assert db.scalar(select(ImportBatch).where(ImportBatch.import_mode == "REPLACE")) is not None
