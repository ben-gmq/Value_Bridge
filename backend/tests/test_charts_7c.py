"""Slice 7c (D-38, D-46, D-47, D-49; slice7_schema §9): the two charts, the performer, triggers, the
derived order and the completeness rule, copying a chart, and the 0039–0046 data steps on real data."""
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import ProgrammingError

from models import AuditEvent
from services import process_flow
from tests.conftest import BACKEND, OWNER_URL
from tests.test_scope_api import API, ed, entity  # noqa: F401 — ed is a fixture


def node(client, ed, name, parent=None, process=False, bfc_set="TO_BE", expect=201):
    r = client.post(f"{API}/projects/{ed['p']}/bfc-nodes", headers=ed["h"],
                    json={"node_name": name, "parent_bfc_node_id": parent, "is_process": process, "bfc_set": bfc_set})
    assert r.status_code == expect, r.text
    return r.json()


def step_in(client, ed, bfc_set="TO_BE", names=("Area", "Function"), step="Step"):
    a = node(client, ed, names[0], bfc_set=bfc_set)
    b = node(client, ed, names[1], a["bfc_node_id"])
    return a, b, node(client, ed, step, b["bfc_node_id"], process=True)


def io(client, ed, step, de, direction):
    r = client.post(f"{API}/bfc-nodes/{step['bfc_node_id']}/data-entities", headers=ed["h"],
                    json={"data_entity_id": de["data_entity_id"], "direction": direction})
    assert r.status_code == 201, r.text


def fresh(client, ed, n):
    return client.get(f"{API}/bfc-nodes/{n['bfc_node_id']}", headers=ed["h"]).json()


def perform(client, ed, n, kind, code=None, label=None, expect=200):
    r = client.put(f"{API}/bfc-nodes/{n['bfc_node_id']}/performer", headers=ed["h"], json={
        "row_version": fresh(client, ed, n)["row_version"], "performer_kind": kind, "code": code,
        "performer_label": label})
    assert r.status_code == expect, r.text
    return r.json()


def org(client, ed, code="SALES", role="CLERK"):
    u = client.post(f"{API}/projects/{ed['p']}/org-units", headers=ed["h"],
                    json={"org_unit_code": code, "org_unit_name": code.title()}).json()
    r = client.post(f"{API}/projects/{ed['p']}/org-roles", headers=ed["h"],
                    json={"org_unit_id": u["org_unit_id"], "org_role_code": role, "org_role_name": role.title()}).json()
    return u, r


def switch(client, world, pid, codes):
    url = f"{API}/projects/{pid}/components"
    prev = client.put(url, headers=world["admin"], json={"component_codes": codes}).json()
    r = client.put(url, headers=world["admin"], json={"component_codes": codes, "confirm_hash": prev["confirm_hash"]})
    assert r.status_code == 200 and r.json()["applied"], r.text


# ---- the two charts (D-47) -------------------------------------------------------------------------
def test_each_chart_has_its_own_tree_and_codes_and_an_as_is_process_has_no_br(client, ed):
    _a, _b, tb = step_in(client, ed)
    _a2, _b2, ai = step_in(client, ed, "AS_IS", ("Area", "Function"), "Step")     # same names: other chart
    assert tb["hier_code"] == ai["hier_code"] == "01.01.01"
    to_be = client.get(f"{API}/projects/{ed['p']}/bfc-tree", headers=ed["h"]).json()
    as_is = client.get(f"{API}/projects/{ed['p']}/bfc-tree", headers=ed["h"], params={"bfc_set": "AS_IS"}).json()
    assert {n["bfc_set_code"] for n in to_be} == {"TO_BE"} and {n["bfc_set_code"] for n in as_is} == {"AS_IS"}
    assert [n["br_number"] for n in to_be if n["is_process"]] == ["BR-0001"]
    assert [n["br_number"] for n in as_is if n["is_process"]] == [None]           # S7-2
    child = node(client, ed, "Child", ai["parent_bfc_node_id"])
    assert child["bfc_set_code"] == "AS_IS"                                       # takes its parent's chart


def test_the_as_is_chart_needs_its_component(client, world, ed):
    switch(client, world, ed["p"], ["SOLUTION", "FUNCTION_REQUIREMENT", "EFFORT", "APPLICATION", "TO_BE_DFD"])
    r = client.post(f"{API}/projects/{ed['p']}/bfc-nodes", headers=ed["h"],
                    json={"node_name": "Old way", "parent_bfc_node_id": None, "bfc_set": "AS_IS"})
    assert r.status_code == 409 and r.headers["X-VB-Error"] == "COMPONENT_OFF"
    node(client, ed, "New way")                                                   # the to-be chart is always on


def test_as_is_support_only_on_as_is_steps(client, ed):
    _a, _b, tb = step_in(client, ed)
    _a2, _b2, ai = step_in(client, ed, "AS_IS")
    app = client.post(f"{API}/projects/{ed['p']}/applications", headers=ed["h"], json={
        "application_code": "SAP", "application_name": "SAP", "lifecycle_code": "AS_IS"}).json()
    r = client.post(f"{API}/bfc-nodes/{tb['bfc_node_id']}/applications", headers=ed["h"],
                    json={"application_id": app["application_id"]})
    assert r.status_code == 422                                                   # Q-23
    r = client.post(f"{API}/bfc-nodes/{ai['bfc_node_id']}/applications", headers=ed["h"],
                    json={"application_id": app["application_id"]})
    assert r.status_code == 201, r.text


# ---- the performer (D-46) --------------------------------------------------------------------------
def test_performer_by_code_or_ai_label_audited_and_it_blocks_retiring_its_target(client, ed, db):
    _a, _b, s = step_in(client, ed)
    unit, role = org(client, ed)
    out = perform(client, ed, s, "ORG_ROLE", "clerk")                              # codes, case-insensitive
    assert out["performer_kind"] == "ORG_ROLE" and out["performer_org_role_id"] == role["org_role_id"]
    perform(client, ed, s, "ORG_ROLE", "NOPE", expect=422)
    perform(client, ed, s, "AI", expect=422)                                        # an AI needs a name
    perform(client, ed, s, "AI", label="Invoice matcher")
    perform(client, ed, s, "ORG_UNIT", "SALES")
    r = client.delete(f"{API}/org-units/{unit['org_unit_id']}", headers=ed["h"],
                      params={"row_version": unit["row_version"]})
    assert r.status_code == 409                                                   # R2-D2: it performs a step
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PERFORMER_SET")
                    .order_by(AuditEvent.audit_event_id)).all()
    assert [e.detail["to"]["kind"] for e in ev] == ["ORG_ROLE", "AI", "ORG_UNIT"]
    parent = client.get(f"{API}/bfc-nodes/{s['parent_bfc_node_id']}", headers=ed["h"]).json()
    r = client.put(f"{API}/bfc-nodes/{parent['bfc_node_id']}/performer", headers=ed["h"],
                   json={"row_version": parent["row_version"], "performer_kind": "AI", "performer_label": "x"})
    assert r.status_code == 422                                                   # only a process


def test_demoting_a_process_names_its_performer(client, ed):
    _a, b, s = step_in(client, ed)
    perform(client, ed, s, "AI", label="Bot")
    br = client.get(f"{API}/projects/{ed['p']}/business-requirements", headers=ed["h"]).json()[0]
    client.delete(f"{API}/business-requirements/{br['br_id']}", headers=ed["h"], params={"row_version": br["row_version"]})
    r = client.patch(f"{API}/bfc-nodes/{s['bfc_node_id']}/process", headers=ed["h"],
                     json={"row_version": fresh(client, ed, s)["row_version"], "is_process": False})
    assert r.status_code == 409 and "performer" in r.json()["detail"]


# ---- triggers (D-49) ---------------------------------------------------------------------------------
def test_triggers_catalogue_links_and_retire_with_the_step(client, ed):
    _a, _b, s = step_in(client, ed)
    t = client.post(f"{API}/projects/{ed['p']}/process-triggers", headers=ed["h"], json={
        "trigger_name": "Month-end close", "trigger_kind": "TIME", "schedule_note": "last day 18:00"}).json()
    assert client.post(f"{API}/projects/{ed['p']}/process-triggers", headers=ed["h"], json={
        "trigger_name": " month-end CLOSE", "trigger_kind": "TIME"}).status_code == 409
    assert client.post(f"{API}/projects/{ed['p']}/process-triggers", headers=ed["h"], json={
        "trigger_name": "Calls", "trigger_kind": "EVENT", "schedule_note": "9am"}).status_code == 422
    link = client.post(f"{API}/bfc-nodes/{s['bfc_node_id']}/triggers", headers=ed["h"],
                       json={"process_trigger_id": t["process_trigger_id"]})
    assert link.status_code == 201 and link.json()["trigger_row"]["trigger_name"] == "Month-end close"
    r = client.delete(f"{API}/process-triggers/{t['process_trigger_id']}", headers=ed["h"],
                      params={"row_version": t["row_version"]})
    assert r.status_code == 409                                                   # a live step names it
    prev = client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}/retire-preview", headers=ed["h"]).json()
    assert "Trigger: Month-end close" in [o["label"] for o in prev["owned"]]
    assert client.post(f"{API}/bfc-nodes/{s['bfc_node_id']}/retire-with-dependents", headers=ed["h"],
                       json={"confirm_hash": prev["confirm_hash"]}).status_code == 204
    assert client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}/triggers", headers=ed["h"]).json() == []
    assert client.post(f"{API}/bfc-nodes/{s['bfc_node_id']}/restore-with-dependents", headers=ed["h"]).status_code == 200
    assert len(client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}/triggers", headers=ed["h"]).json()) == 1


# ---- derived order, rank and completeness (D-38) --------------------------------------------------------
def test_order_is_derived_from_data_with_a_loop_and_a_branch(client, ed):
    a, b, s1 = step_in(client, ed, step="Receive")
    s2 = node(client, ed, "Check", b["bfc_node_id"], process=True)
    s3 = node(client, ed, "Approve", b["bfc_node_id"], process=True)
    s4 = node(client, ed, "Reject", b["bfc_node_id"], process=True)
    order, app, rej = (entity(client, ed, n) for n in ("Order", "Approved order", "Rejected order"))
    io(client, ed, s1, order, "O")
    io(client, ed, s2, order, "I"); io(client, ed, s2, app, "O"); io(client, ed, s2, rej, "O")
    io(client, ed, s3, app, "I"); io(client, ed, s3, order, "O")                   # a loop back to Check
    io(client, ed, s4, rej, "I")
    g = client.get(f"{API}/bfc-nodes/{a['bfc_node_id']}/dfd", headers=ed["h"]).json()
    pairs = {(o["from_bfc_node_id"], o["to_bfc_node_id"]) for o in g["order"]}
    ids = {k: n["bfc_node_id"] for k, n in (("r", s1), ("c", s2), ("a", s3), ("x", s4))}
    assert {(ids["r"], ids["c"]), (ids["c"], ids["a"]), (ids["c"], ids["x"]), (ids["a"], ids["c"])} <= pairs
    rank = {p["bfc_node_id"]: p["rank"] for p in g["processes"]}
    assert rank[ids["r"]] == 0 and rank[ids["c"]] == rank[ids["a"]] == 1 and rank[ids["x"]] == 2   # SCC shares a rank
    assert g["completeness"]["missing_output"] == [{**{k: v for k, v in s4.items() if k in ("bfc_node_id", "hier_code", "node_name")}, "bfc_set_code": "TO_BE"}]
    assert ids["r"] in {r["bfc_node_id"] for r in g["completeness"]["missing_input"]}


def test_completeness_blocks_only_charts_whose_dfd_is_on(client, world, ed, db):
    from services.consistency import FREEZE_BLOCKING_WARNINGS, consistency_check
    _a, _b, s = step_in(client, ed)
    out = consistency_check(ed["p"], db)
    assert [r["bfc_node_id"] for r in out["process_missing_input"]] == [s["bfc_node_id"]]
    assert {"process_missing_input", "process_missing_output"} <= set(FREEZE_BLOCKING_WARNINGS)
    t = client.post(f"{API}/projects/{ed['p']}/process-triggers", headers=ed["h"],
                    json={"trigger_name": "Customer calls", "trigger_kind": "EVENT"}).json()
    client.post(f"{API}/bfc-nodes/{s['bfc_node_id']}/triggers", headers=ed["h"], json={"process_trigger_id": t["process_trigger_id"]})
    db.expire_all()
    assert consistency_check(ed["p"], db)["process_missing_input"] == []          # a trigger is an input (D-49)
    link = client.get(f"{API}/bfc-nodes/{s['bfc_node_id']}/triggers", headers=ed["h"]).json()[0]
    client.delete(f"{API}/bfc-nodes/{s['bfc_node_id']}/triggers/{link['bfc_node_trigger_id']}", headers=ed["h"],
                  params={"row_version": link["row_version"]})
    client.delete(f"{API}/process-triggers/{t['process_trigger_id']}", headers=ed["h"],
                  params={"row_version": t["row_version"]})            # M2: the catalogue must be empty first
    switch(client, world, ed["p"], ["SOLUTION", "FUNCTION_REQUIREMENT", "EFFORT", "APPLICATION"])
    db.expire_all()
    out = consistency_check(ed["p"], db)
    assert out["process_missing_input"] == [] and out["process_missing_output"] == []   # S7-3: rule is off


# ---- copying a chart (Q-24) ----------------------------------------------------------------------------------
def test_copy_to_be_into_an_empty_as_is_chart_with_preview_and_audit(client, ed, db):
    a, b, s = step_in(client, ed)
    _u, _r = org(client, ed)
    perform(client, ed, s, "ORG_ROLE", "CLERK")
    de = entity(client, ed, "Order")
    io(client, ed, s, de, "O")
    url = f"{API}/projects/{ed['p']}/bfc-sets/AS_IS/copy-from/TO_BE"
    prev = client.post(url, headers=ed["h"], json={}).json()
    assert prev["applied"] is False and prev["nodes"] == 3 and prev["processes"] == 1 and prev["step_data"] == 1
    assert client.get(f"{API}/projects/{ed['p']}/bfc-tree", headers=ed["h"], params={"bfc_set": "AS_IS"}).json() == []
    r = client.post(url, headers=ed["h"], json={"confirm_hash": prev["confirm_hash"]})
    assert r.status_code == 200 and r.json()["applied"] is True
    as_is = client.get(f"{API}/projects/{ed['p']}/bfc-tree", headers=ed["h"], params={"bfc_set": "AS_IS"}).json()
    copied = next(n for n in as_is if n["is_process"])
    assert copied["hier_code"] == s["hier_code"] and copied["performer_kind"] == "ORG_ROLE" and copied["br_number"] is None
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "BFC_SET_COPIED")).one()
    assert ev.detail["id_map"][str(s["bfc_node_id"])] == copied["bfc_node_id"]
    assert client.post(url, headers=ed["h"], json={}).status_code == 409               # target no longer empty
    assert client.post(f"{API}/projects/{ed['p']}/bfc-sets/TO_BE/copy-from/TO_BE", headers=ed["h"],
                       json={}).status_code == 422


def test_copy_as_is_into_to_be_mints_a_draft_br_per_process(client, ed):
    step_in(client, ed, "AS_IS")
    url = f"{API}/projects/{ed['p']}/bfc-sets/TO_BE/copy-from/AS_IS"
    prev = client.post(url, headers=ed["h"], json={}).json()
    assert prev["new_requirements"] == 1
    client.post(url, headers=ed["h"], json={"confirm_hash": prev["confirm_hash"]})
    brs = client.get(f"{API}/projects/{ed['p']}/business-requirements", headers=ed["h"]).json()
    assert [b["status_code"] for b in brs] == ["DRAFT"]


# ---- 0041 / 0045 on real data ---------------------------------------------------------------------------------
def _cfg() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    os.environ["VB_ALEMBIC_URL"] = OWNER_URL
    return cfg


def _plant_step_role(c, p, step_id, org_role_id, code, at=None, by=None):
    """A step role as pre-10d code wrote it (live, or retired with `at`), as the owner."""
    return c.execute(text(
        "INSERT INTO bfc_node_org_role (project_id, bfc_node_id, org_role_id, raci_code_id, raci_behaviour, created_by, "
        "is_active, deleted_at, deleted_by) SELECT :p, :s, :r, code_id, behaviour_code, 1, :live, :at, :by "
        "FROM code_master WHERE category = 'RACI_TYPE' AND code = :c AND project_id IS NULL "
        "RETURNING bfc_node_org_role_id"),
        {"p": p, "s": step_id, "r": org_role_id, "c": code, "live": at is None, "at": at, "by": by}).scalar()


def test_0041_backfills_performers_from_responsible_and_0045_retires_arrows(client, ed, db):
    """Built at head, stepped back to 0040, arrows and RESPONSIBLE roles planted as the owner, then
    upgraded: the lane survives as the performer and every arrow is retired, audited, SELECT-only."""
    _a, b, s1 = step_in(client, ed)
    s2 = node(client, ed, "Second", b["bfc_node_id"], process=True)
    _u, role = org(client, ed)
    cfg = _cfg()
    command.downgrade(cfg, "0040")
    eng = create_engine(OWNER_URL)
    try:
        with eng.begin() as c:
            _plant_step_role(c, ed["p"], s1["bfc_node_id"], role["org_role_id"], "R")    # D-64: the API refuses it now
            c.execute(text("INSERT INTO bfc_node_flow (project_id, from_bfc_node_id, to_bfc_node_id, flow_type, created_by) "
                           "VALUES (:p, :a, :b, 'SEQUENCE', 1)"), {"p": ed["p"], "a": s1["bfc_node_id"], "b": s2["bfc_node_id"]})
        command.upgrade(cfg, "head")
        with eng.connect() as c:
            perf = c.execute(text("SELECT performer_kind, performer_org_role_id FROM bfc_node WHERE bfc_node_id = :n"),
                             {"n": s1["bfc_node_id"]}).one()
            assert tuple(perf) == ("ORG_ROLE", role["org_role_id"])
            assert c.execute(text("SELECT count(*) FROM bfc_node_flow WHERE is_active")).scalar() == 0
            ev = c.execute(text("SELECT detail FROM audit_event WHERE event_type = 'FLOW_EDGES_RETIRED'")).scalar_one()
            assert ev["count"] == 1 and ev["decision"] == "D-38"
            # …and 0052 then moved the step role onto the step's BR (D-64)
            assert c.execute(text("SELECT count(*) FROM br_org_role r JOIN business_requirement b USING (br_id) "
                                  "WHERE b.bfc_node_id = :n AND r.is_active AND r.org_role_id = :r"),
                             {"n": s1["bfc_node_id"], "r": role["org_role_id"]}).scalar() == 1
    finally:
        command.upgrade(cfg, "head")
        eng.dispose()
    with pytest.raises(ProgrammingError):
        db.execute(text("UPDATE bfc_node_flow SET note = 'x'"))
    db.rollback()
    assert process_flow.missing_io(db, ed["p"])["missing_output"]              # sanity: the service still reads


# ---- sara 7c review --------------------------------------------------------------------------------------------
def test_copy_refuses_to_make_rows_live_in_an_off_component(client, world, ed):
    """M1 (DR7-P2): an as-is → to-be copy carrying a performer needs TO_BE_DFD on."""
    _a, _b, s = step_in(client, ed, "AS_IS")
    perform(client, ed, s, "AI", label="Bot")
    switch(client, world, ed["p"], ["SOLUTION", "FUNCTION_REQUIREMENT", "EFFORT", "APPLICATION", "AS_IS"])
    url = f"{API}/projects/{ed['p']}/bfc-sets/TO_BE/copy-from/AS_IS"
    prev = client.post(url, headers=ed["h"], json={}).json()
    r = client.post(url, headers=ed["h"], json={"confirm_hash": prev["confirm_hash"]})
    assert r.status_code == 409 and r.headers["X-VB-Error"] == "COMPONENT_OFF"
    assert client.get(f"{API}/projects/{ed['p']}/bfc-tree", headers=ed["h"]).json() == []


def test_the_trigger_catalogue_blocks_switching_both_dfds_off_and_needs_one_on(client, world, ed):
    """M2 (§12 auditor Q3) and L5: the catalogue serves both charts."""
    t = client.post(f"{API}/projects/{ed['p']}/process-triggers", headers=ed["h"],
                    json={"trigger_name": "Month-end", "trigger_kind": "TIME"}).json()
    base = ["SOLUTION", "FUNCTION_REQUIREMENT", "EFFORT", "APPLICATION"]
    prev = client.put(f"{API}/projects/{ed['p']}/components", headers=world["admin"], json={"component_codes": base}).json()
    assert any("trigger catalogue" in b["message"] for b in prev["blockers"])
    switch(client, world, ed["p"], [*base, "AS_IS"])                                    # one DFD on: allowed
    r = client.patch(f"{API}/process-triggers/{t['process_trigger_id']}", headers=ed["h"],
                     json={"row_version": t["row_version"], "trigger_name": "Month end"})
    assert r.status_code == 200
    assert client.delete(f"{API}/process-triggers/{t['process_trigger_id']}", headers=ed["h"],
                         params={"row_version": r.json()["row_version"]}).status_code == 204
    switch(client, world, ed["p"], base)                                                # catalogue now empty
    for call in (lambda: client.post(f"{API}/projects/{ed['p']}/process-triggers", headers=ed["h"],
                                     json={"trigger_name": "X", "trigger_kind": "EVENT"}),
                 lambda: client.patch(f"{API}/process-triggers/{t['process_trigger_id']}/restore", headers=ed["h"])):
        r = call()
        assert r.status_code == 409 and r.headers["X-VB-Error"] == "COMPONENT_OFF"


def test_a_trigger_restore_whose_name_is_taken_is_a_clear_409(client, ed):
    """L6."""
    t = client.post(f"{API}/projects/{ed['p']}/process-triggers", headers=ed["h"],
                    json={"trigger_name": "Calls", "trigger_kind": "EVENT"}).json()
    client.delete(f"{API}/process-triggers/{t['process_trigger_id']}", headers=ed["h"], params={"row_version": t["row_version"]})
    client.post(f"{API}/projects/{ed['p']}/process-triggers", headers=ed["h"], json={"trigger_name": "calls", "trigger_kind": "EVENT"})
    r = client.patch(f"{API}/process-triggers/{t['process_trigger_id']}/restore", headers=ed["h"])
    assert r.status_code == 409 and "already exists" in r.json()["detail"]


def test_a_step_retired_before_0041_and_0045_restores_with_its_lane_and_without_its_arrow(client, ed, db):
    """M4 (§9.12 risk 2, DR7-P3): a step retired with its RESPONSIBLE link and an arrow before the
    migrations gets its performer from the shared deleted_at, and restoring it skips the arrow."""
    _a, b, s1 = step_in(client, ed)
    s2 = node(client, ed, "Second", b["bfc_node_id"], process=True)
    _u, role = org(client, ed)
    prev = client.get(f"{API}/bfc-nodes/{s2['bfc_node_id']}/retire-preview", headers=ed["h"]).json()
    assert client.post(f"{API}/bfc-nodes/{s2['bfc_node_id']}/retire-with-dependents", headers=ed["h"],
                       json={"confirm_hash": prev["confirm_hash"]}).status_code == 204
    cfg = _cfg()
    command.downgrade(cfg, "0040")
    eng = create_engine(OWNER_URL)
    try:
        with eng.begin() as c:
            at = c.execute(text("SELECT deleted_at FROM bfc_node WHERE bfc_node_id = :n"), {"n": s2["bfc_node_id"]}).scalar()
            flow = c.execute(text(
                "INSERT INTO bfc_node_flow (project_id, from_bfc_node_id, to_bfc_node_id, flow_type, created_by, "
                "is_active, deleted_at) VALUES (:p, :a, :b, 'SEQUENCE', 1, false, :at) RETURNING bfc_node_flow_id"),
                {"p": ed["p"], "a": s1["bfc_node_id"], "b": s2["bfc_node_id"], "at": at}).scalar()
            ev = c.execute(text("SELECT app_user_id, detail FROM audit_event WHERE event_type = 'STEP_RETIRED_WITH_DEPENDENTS' "
                                "AND target_id = :n ORDER BY audit_event_id DESC LIMIT 1"), {"n": s2["bfc_node_id"]}).one()
            # the RESPONSIBLE step role a pre-10d retire took with it (D-64: the API refuses one on a to-be step now)
            bnor = _plant_step_role(c, ed["p"], s2["bfc_node_id"], role["org_role_id"], "R", at, ev.app_user_id)
            detail = {**ev.detail, "rows": [*ev.detail["rows"], ["bfc_node_flow", flow], ["bfc_node_org_role", bnor]]}
            c.execute(text("INSERT INTO audit_event (app_user_id, project_id, event_type, target_table, target_id, detail) "
                           "VALUES (:u, :p, 'STEP_RETIRED_WITH_DEPENDENTS', 'bfc_node', :n, CAST(:d AS jsonb))"),
                      {"u": ev.app_user_id, "p": ed["p"], "n": s2["bfc_node_id"], "d": __import__("json").dumps(detail)})
        command.upgrade(cfg, "head")
    finally:
        command.upgrade(cfg, "head")
        eng.dispose()
    r = client.post(f"{API}/bfc-nodes/{s2['bfc_node_id']}/restore-with-dependents", headers=ed["h"])
    assert r.status_code == 200, r.text
    restored = fresh(client, ed, s2)
    assert restored["is_active"] and restored["performer_kind"] == "ORG_ROLE" \
        and restored["performer_org_role_id"] == role["org_role_id"]
    assert db.execute(text("SELECT is_active FROM bfc_node_flow WHERE bfc_node_flow_id = :f"), {"f": flow}).scalar() is False
    # 0052 (Q-3): the step role came back on the BR, and the step row stayed retired
    assert db.execute(text("SELECT is_active FROM bfc_node_org_role WHERE bfc_node_org_role_id = :i"),
                      {"i": bnor}).scalar() is False
    assert db.execute(text("SELECT count(*) FROM br_org_role r JOIN business_requirement b USING (br_id) "
                           "WHERE b.bfc_node_id = :n AND r.is_active AND r.org_role_id = :r"),
                      {"n": s2["bfc_node_id"], "r": role["org_role_id"]}).scalar() == 1
