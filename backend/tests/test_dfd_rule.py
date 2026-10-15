"""Slice 13b (D-70; slice13_spec §4.2, §7.1–7.2, §10 B1–B10; slice13_schema §2; S13-1, S13-2): each chart of a project
chooses the DFD elements a process needs before a freeze. Grade 1 — it changes what blocks a freeze — so the gate is
proven over the same reader as the light (DR13-P1), the empty rule fails closed (DR13-D3) and the rule is copied onto
the baseline header, frozen for every role."""
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

from models import AuditEvent
from services import consistency, dfd_rule, process_flow
from tests.conftest import ALL_COMPONENTS, OWNER_URL
from tests.test_baseline import bid, freeze, preview, scope
from tests.test_charts_7c import switch
from tests.test_dfd_api import as_is_root, completeness, ext_flow, graph, io, party, starts, trigger
from tests.test_scope_api import API, ed, entity, node, tree  # noqa: F401 — ed is a fixture


def rule(client, ed, headers=None, expect=200):
    r = client.get(f"{API}/projects/{ed['p']}/dfd-rule", headers=headers or ed["h"])
    assert r.status_code == expect, r.text
    return r.json()


def codes_of(r, bfc_set="TO_BE"):
    return next(c for c in r["charts"] if c["bfc_set_code"] == bfc_set)["codes"]


def preview_rule(client, world, pid, codes, bfc_set="TO_BE", headers=None, expect=200):
    r = client.post(f"{API}/projects/{pid}/dfd-rule/preview", headers=headers or world["admin"],
                    json={"bfc_set_code": bfc_set, "codes": codes})
    assert r.status_code == expect, r.text
    return r.json()


def set_rule(client, world, pid, codes, bfc_set="TO_BE", headers=None, expect=200, digest=None, row_version=None):
    p = preview_rule(client, world, pid, codes, bfc_set) if digest is None else {"preview_digest": digest}
    rv = row_version if row_version is not None else client.get(f"{API}/projects/{pid}",
                                                                 headers=world["admin"]).json()["row_version"]
    r = client.put(f"{API}/projects/{pid}/dfd-rule", headers=headers or world["admin"],
                   json={"bfc_set_code": bfc_set, "codes": codes, "row_version": rv,
                         "preview_digest": p["preview_digest"]})
    assert r.status_code == expect, r.text
    return r.json()


def lights(client, ed, bfc_set="TO_BE"):
    return {n["bfc_node_id"]: (n["dfd_light"], n["dfd_missing"], n["dfd_advised"])
            for n in tree(client, ed, bfc_set=bfc_set)}


def group(client, ed):
    a = node(client, ed, "Sales")
    return node(client, ed, "Order to cash", a["bfc_node_id"])


def owner_sql(sql, **kw):
    eng = create_engine(OWNER_URL)
    try:
        with eng.begin() as c:
            return c.execute(text(sql), kw)
    finally:
        eng.dispose()


# ---- the starting rules (B1, Q-4, [Q-18]) -------------------------------------------------------------------

def test_a_new_project_starts_with_the_recommended_set_and_existing_ones_keep_todays(client, world, ed, db):
    r = client.post(f"{API}/projects", headers=world["admin"], json={
        "client_id": world["client_id"], "project_code": "NEW", "project_name": "New",
        "component_codes": ALL_COMPONENTS, "is_restricted": False})
    assert r.status_code == 201, r.text
    new = {"p": r.json()["project_id"], "h": world["admin"]}
    got = rule(client, new)
    assert codes_of(got, "TO_BE") == ["STARTED", "DATA_IN", "DATA_OUT", "ORDER"]
    assert codes_of(got, "AS_IS") == ["STARTED"]
    assert all(c["fallback"] is False and c["rule_applies"] for c in got["charts"])
    assert {c["code"]: (c["locked"], c["requires"], c["per_diagram"]) for c in got["catalogue"]} == {
        "STARTED": (True, [], False), "DATA_IN": (False, [], False), "DATA_OUT": (False, [], False),
        "EXTERNAL": (False, [], True), "ORDER": (False, ["DATA_IN", "DATA_OUT"], False)}
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PROJECT_CREATED",
                                             AuditEvent.project_id == new["p"])).one()
    assert ev.detail["dfd_rule"] == {"TO_BE": ["STARTED", "DATA_IN", "DATA_OUT", "ORDER"], "AS_IS": ["STARTED"]}
    # the harness's projects stand for every project at deploy: today's rule on both charts
    assert codes_of(rule(client, ed), "TO_BE") == codes_of(rule(client, ed), "AS_IS") == ["STARTED", "DATA_OUT"]
    bad = client.post(f"{API}/projects", headers=world["admin"], json={
        "client_id": world["client_id"], "project_code": "BAD", "project_name": "Bad",
        "component_codes": ALL_COMPONENTS, "is_restricted": False, "dfd_rule": {"TO_BE": ["DATA_OUT"]}})
    assert bad.status_code == 422                                     # STARTED is always required


# ---- changing the rule (B2, B3, B4, B5) ------------------------------------------------------------------

def test_dropping_data_out_unblocks_a_trigger_only_process_and_is_audited(client, world, ed, db):
    """B2: with DATA_OUT out of the rule a trigger-only process no longer blocks; it stays yellow because DATA_OUT is
    still recommended for the to-be chart (Q-13)."""
    w = scope(client, ed)
    s = node(client, ed, "Ship order", w["group"]["bfc_node_id"], is_process=True)
    starts(client, ed, s, trigger(client, ed, "Order paid"))
    assert lights(client, ed)[s["bfc_node_id"]][:2] == ("NOT_READY", ["DATA_OUT"])
    freeze(client, ed, expect=409)
    p = preview_rule(client, world, ed["p"], ["STARTED"])
    assert (p["would_block"], p["current"], p["codes"]) == (0, ["STARTED", "DATA_OUT"], ["STARTED"])
    out = set_rule(client, world, ed["p"], ["STARTED"])
    assert codes_of(out) == ["STARTED"] and codes_of(out, "AS_IS") == ["STARTED", "DATA_OUT"]   # per chart (Q-15)
    assert lights(client, ed)[s["bfc_node_id"]] == ("PARTIAL", [], ["DATA_IN", "DATA_OUT", "ORDER"])
    f = freeze(client, ed)
    assert f["baseline"]["dfd_rule_to_be"] == ["STARTED"] and f["baseline"]["dfd_rule_as_is"] == ["STARTED", "DATA_OUT"]
    ev = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PROJECT_DFD_RULE_CHANGED")).one()
    assert ev.detail == {"bfc_set_code": "TO_BE", "from": ["STARTED", "DATA_OUT"], "to": ["STARTED"],
                         "would_block": 0, "would_block_diagrams": 0}
    assert ev.app_user_id is not None and ev.project_id == ed["p"]
    # re-adding DATA_OUT restores the same row (S1-7), never a second one
    set_rule(client, world, ed["p"], ["STARTED", "DATA_OUT"])
    n = owner_sql("SELECT count(*), count(*) FILTER (WHERE is_active) FROM project_dfd_rule "
                  "WHERE project_id = :p AND bfc_set_code = 'TO_BE' AND element_code = 'DATA_OUT'", p=ed["p"]).one()
    assert tuple(n) == (1, 1)


def test_adding_data_in_previews_the_blockers_and_the_freeze_refuses_with_that_list(client, world, ed):
    """B3."""
    w = scope(client, ed)
    s = node(client, ed, "Ship order", w["group"]["bfc_node_id"], is_process=True)
    starts(client, ed, s, trigger(client, ed, "Order paid"))
    io(client, ed, s, entity(client, ed, "Shipment"), "O")
    assert freeze(client, ed)["baseline"]["version_label"] == "v1.0"           # passes today's rule
    p = preview_rule(client, world, ed["p"], ["STARTED", "DATA_IN", "DATA_OUT"])
    assert (p["would_block"], p["not_ready"], p["ready"] + p["partly"]) == (1, 1, 2)
    set_rule(client, world, ed["p"], ["STARTED", "DATA_IN", "DATA_OUT"])
    assert lights(client, ed)[s["bfc_node_id"]][:2] == ("NOT_READY", ["DATA_IN"])
    out = freeze(client, ed, expect=409)
    assert [r["bfc_node_id"] for r in out["detail"]["freeze_blocking"]["process_missing_data_in"]] == [s["bfc_node_id"]]
    assert completeness(client, ed)["missing_data_in"][0]["bfc_node_id"] == s["bfc_node_id"]


def test_an_invalid_set_is_422(client, world, ed):
    """B4: ORDER needs both data elements (option A); STARTED is locked; unknown codes are refused."""
    for codes in (["STARTED", "ORDER"], ["STARTED", "DATA_IN", "ORDER"], ["DATA_OUT"], ["STARTED", "TRIGGER"]):
        preview_rule(client, world, ed["p"], codes, expect=422)
        rv = client.get(f"{API}/projects/{ed['p']}", headers=world["admin"]).json()["row_version"]
        r = client.put(f"{API}/projects/{ed['p']}/dfd-rule", headers=world["admin"],
                       json={"bfc_set_code": "TO_BE", "codes": codes, "row_version": rv, "preview_digest": "0" * 64})
        assert r.status_code == 422, (codes, r.text)
    assert codes_of(rule(client, ed)) == ["STARTED", "DATA_OUT"]
    assert set_rule(client, world, ed["p"], ["STARTED", "DATA_IN", "DATA_OUT", "ORDER", "EXTERNAL"])["charts"][0][
        "codes"] == ["STARTED", "DATA_IN", "DATA_OUT", "EXTERNAL", "ORDER"]


def test_only_a_project_admin_changes_it_everyone_who_sees_the_project_reads_it(client, world, ed):
    """B5, Q-5: a non-admin preview or PUT is 403; a non-member of a restricted project gets 404 on all three."""
    good = preview_rule(client, world, ed["p"], ["STARTED"])
    for who in (ed["h"], ed["rv"]):                                   # an editor and a viewer member
        assert rule(client, ed, headers=who)["project_id"] == ed["p"]
        preview_rule(client, world, ed["p"], ["STARTED"], headers=who, expect=403)
        set_rule(client, world, ed["p"], ["STARTED"], headers=who, expect=403, digest=good["preview_digest"])
    rule(client, ed, headers=ed["out"], expect=404)
    preview_rule(client, world, ed["p"], ["STARTED"], headers=ed["out"], expect=404)
    set_rule(client, world, ed["p"], ["STARTED"], headers=ed["out"], expect=404, digest=good["preview_digest"])
    assert codes_of(rule(client, ed)) == ["STARTED", "DATA_OUT"]


def test_a_stale_row_version_or_a_changed_preview_is_409(client, world, ed):
    b = group(client, ed)
    s = node(client, ed, "Ship", b["bfc_node_id"], is_process=True)
    starts(client, ed, s, trigger(client, ed, "Daily"))
    p = preview_rule(client, world, ed["p"], ["STARTED", "DATA_IN", "DATA_OUT"])
    node(client, ed, "Pack", b["bfc_node_id"], is_process=True)       # the counts behind the preview moved
    set_rule(client, world, ed["p"], ["STARTED", "DATA_IN", "DATA_OUT"], digest=p["preview_digest"], expect=409)
    rv = client.get(f"{API}/projects/{ed['p']}", headers=world["admin"]).json()["row_version"]
    set_rule(client, world, ed["p"], ["STARTED"], row_version=rv - 1, expect=409)
    after = set_rule(client, world, ed["p"], ["STARTED"])
    assert after["row_version"] == rv + 1                             # the mapper bumps it, never the body (law 6)
    assert set_rule(client, world, ed["p"], ["STARTED"])["row_version"] == rv + 1     # same set: nothing written


# ---- the baseline header (B6, [Q-19]) -----------------------------------------------------------------------

def test_the_header_records_the_rule_and_is_frozen_for_every_role_and_an_old_baseline_reads_d38(client, world, ed,
                                                                                               monkeypatch):
    from tests.test_migration_0053 import pre_13c
    scope(client, ed)
    with monkeypatch.context() as m:
        pre_13c(m)                                     # a pre-13b baseline is pre-13c too: from spec 3 the rule is required
        f = freeze(client, ed)
    assert (f["baseline"]["dfd_rule_to_be"], f["baseline"]["dfd_rule_as_is"]) == (["STARTED", "DATA_OUT"],) * 2
    with pytest.raises(DBAPIError, match="frozen baseline column cannot change"):
        owner_sql("UPDATE baseline SET dfd_rule_to_be = ARRAY['STARTED']::varchar(12)[] WHERE baseline_id = :b",
                  b=bid(f))
    # a baseline frozen before 13b: both NULL (the D-38 rule); it still verifies
    owner_sql("ALTER TABLE baseline DISABLE TRIGGER trg_baseline_header_guard; "
              "UPDATE baseline SET dfd_rule_to_be = NULL, dfd_rule_as_is = NULL; "
              "ALTER TABLE baseline ENABLE TRIGGER trg_baseline_header_guard")
    d = client.get(f"{API}/baselines/{bid(f)}", headers=ed["h"]).json()
    assert d["intact"] is True and d["dfd_rule_to_be"] is None and d["dfd_rule_as_is"] is None
    with pytest.raises(DBAPIError, match="ck_baseline_dfd_rule_pair"):
        owner_sql("ALTER TABLE baseline DISABLE TRIGGER trg_baseline_header_guard; "
                  "UPDATE baseline SET dfd_rule_to_be = ARRAY['STARTED']::varchar(12)[]")
    v11 = freeze(client, ed)
    assert v11["baseline"]["dfd_rule_to_be"] == ["STARTED", "DATA_OUT"]


# ---- the marks and the light follow the rule (B7, Q-13) -----------------------------------------------------

def test_the_light_and_its_codes_follow_the_rule(client, world, ed):
    """B7: the element codes the panel's marks read come from the rule — DATA_IN is a rule gap only while the rule
    has it; outside the rule it is a recommendation (yellow), never a blocker."""
    b = group(client, ed)
    s = node(client, ed, "Pick", b["bfc_node_id"], is_process=True)
    starts(client, ed, s, trigger(client, ed, "Daily"))
    io(client, ed, s, entity(client, ed, "Pick list"), "O")
    assert lights(client, ed)[s["bfc_node_id"]] == ("PARTIAL", [], ["DATA_IN"])          # one process: ORDER passes
    set_rule(client, world, ed["p"], ["STARTED", "DATA_IN", "DATA_OUT"])
    assert lights(client, ed)[s["bfc_node_id"]] == ("NOT_READY", ["DATA_IN"], [])
    assert completeness(client, ed)["readiness"]["rule"] == ["STARTED", "DATA_IN", "DATA_OUT"]
    set_rule(client, world, ed["p"], ["STARTED", "DATA_OUT"])
    assert lights(client, ed)[s["bfc_node_id"]] == ("PARTIAL", [], ["DATA_IN"])


def test_order_joins_two_processes_through_their_data_and_a_lone_process_passes(client, world, ed):
    b = group(client, ed)
    a, c = (node(client, ed, n, b["bfc_node_id"], is_process=True) for n in ("Take", "Bill"))
    order, invoice, cust = entity(client, ed, "Order"), entity(client, ed, "Invoice"), entity(client, ed, "Customer")
    io(client, ed, a, cust, "I")
    io(client, ed, a, order, "O")
    io(client, ed, c, invoice, "O")
    io(client, ed, c, cust, "I")                                      # both read Customer: not an order
    set_rule(client, world, ed["p"], ["STARTED", "DATA_IN", "DATA_OUT", "ORDER"])
    got = lights(client, ed)
    assert got[a["bfc_node_id"]][:2] == got[c["bfc_node_id"]][:2] == ("NOT_READY", ["ORDER"])
    io(client, ed, c, order, "I")                                     # Bill reads what Take writes
    got = lights(client, ed)
    assert got[a["bfc_node_id"]] == got[c["bfc_node_id"]] == ("READY", [], [])


# ---- per chart (Q-15) and the as-is gap (B8, DR13-P1) ---------------------------------------------------------

def test_a_stricter_as_is_rule_never_changes_the_to_be_and_an_as_is_gap_still_refuses(client, world, ed):
    w = scope(client, ed)
    root = as_is_root(client, ed)
    desk = node(client, ed, "Order desk", root["bfc_node_id"])
    old = node(client, ed, "Key in order", desk["bfc_node_id"], is_process=True)
    starts(client, ed, old, trigger(client, ed, "Phone call"))
    io(client, ed, old, entity(client, ed, "Paper order"), "O")
    before = lights(client, ed)
    assert freeze(client, ed)["baseline"]["version_label"] == "v1.0"
    set_rule(client, world, ed["p"], ["STARTED", "DATA_IN", "DATA_OUT"], bfc_set="AS_IS")
    assert lights(client, ed) == before                                       # the to-be chart is untouched
    assert lights(client, ed, "AS_IS")[old["bfc_node_id"]][:2] == ("NOT_READY", ["DATA_IN"])
    out = freeze(client, ed, expect=409)
    assert [r["bfc_node_id"] for r in out["detail"]["freeze_blocking"]["process_missing_data_in"]] == [old["bfc_node_id"]]
    assert w["s1"]["bfc_node_id"] not in {r["bfc_node_id"] for r in
                                          out["detail"]["freeze_blocking"]["process_missing_data_in"]}


# ---- fails closed (B9, DR13-D3) and the cross-row rule ----------------------------------------------------

def test_a_chart_without_live_rule_rows_reads_d38_and_refuses_the_freeze(client, world, ed, db):
    scope(client, ed)
    with pytest.raises(DBAPIError, match="ck_pdr_started_locked"):
        owner_sql("UPDATE project_dfd_rule SET is_active = false WHERE project_id = :p", p=ed["p"])
    owner_sql("DELETE FROM project_dfd_rule WHERE project_id = :p AND bfc_set_code = 'TO_BE'", p=ed["p"])
    assert dfd_rule.codes(db, ed["p"], "TO_BE") == ("STARTED", "DATA_OUT")
    got = rule(client, ed)
    assert codes_of(got) == ["STARTED", "DATA_OUT"] and got["charts"][0]["fallback"] is True
    assert consistency.consistency_check(ed["p"], db)["project_without_dfd_rule"] == [
        {"project_id": ed["p"], "project_code": "SOLO", "bfc_set_code": "TO_BE"}]
    out = freeze(client, ed, expect=409)
    assert "project_without_dfd_rule" in out["detail"]["errors"]
    set_rule(client, world, ed["p"], ["STARTED", "DATA_OUT"])                   # an admin saves one
    assert consistency.consistency_check(ed["p"], db)["project_without_dfd_rule"] == []
    assert freeze(client, ed)["baseline"]["version_label"] == "v1.0"


def test_every_project_has_a_rule_and_an_order_without_data_in_is_listed(client, world, ed, db):
    scope(client, ed)
    assert consistency.consistency_check(None, db)["project_without_dfd_rule"] == []    # all projects, inactive too
    set_rule(client, world, ed["p"], ["STARTED", "DATA_IN", "DATA_OUT", "ORDER"])
    owner_sql("UPDATE project_dfd_rule SET is_active = false, deleted_at = now() WHERE project_id = :p "
              "AND bfc_set_code = 'TO_BE' AND element_code = 'DATA_IN'", p=ed["p"])        # raw SQL, no service
    assert consistency.consistency_check(ed["p"], db)["dfd_rule_invalid"] == [
        {"project_id": ed["p"], "bfc_set_code": "TO_BE", "element_code": "ORDER", "needs": ["DATA_IN", "DATA_OUT"]}]
    assert "dfd_rule_invalid" in freeze(client, ed, expect=409)["detail"]["errors"]


# ---- EXTERNAL: per diagram, never in a light (Q-6, Q-16) ---------------------------------------------------

def test_external_is_checked_per_diagram_and_never_changes_a_light(client, world, ed, db):
    w = scope(client, ed)
    before = lights(client, ed)
    p = preview_rule(client, world, ed["p"], ["STARTED", "DATA_OUT", "EXTERNAL"])
    assert (p["would_block"], p["would_block_diagrams"]) == (0, 1)
    set_rule(client, world, ed["p"], ["STARTED", "DATA_OUT", "EXTERNAL"])
    assert lights(client, ed) == before
    out = freeze(client, ed, expect=409)
    assert [r["bfc_node_id"] for r in out["detail"]["freeze_blocking"]["diagram_missing_external"]] == [
        w["group"]["bfc_node_id"]]
    assert [r["bfc_node_id"] for r in completeness(client, ed)["diagram_missing_external"]] == [w["group"]["bfc_node_id"]]
    ext_flow(client, ed, w["s1"], party(client, ed, "Customer"), "I", label="Order call")
    assert process_flow.diagrams_missing_external(db, ed["p"]) == []
    assert freeze(client, ed)["baseline"]["dfd_rule_to_be"] == ["STARTED", "DATA_OUT", "EXTERNAL"]


# ---- chart order (B10, DR13-P4) ------------------------------------------------------------------------------

def test_a_diagram_with_no_derived_order_ranks_in_chart_order(client, world, ed):
    b = group(client, ed)
    steps = [node(client, ed, n, b["bfc_node_id"], is_process=True) for n in ("First", "Second", "Third")]
    t = trigger(client, ed, "Daily")
    for s in steps:
        starts(client, ed, s, t)
    set_rule(client, world, ed["p"], ["STARTED"])
    g = graph(client, ed, b)
    assert g["order_source"] == "CHART" and g["order"] == []
    assert [(p["node_name"], p["rank"]) for p in g["processes"]] == [("First", 0), ("Second", 1), ("Third", 2)]
    # outside the rule, the recommended elements are information on the warnings panel, never a gap
    assert g["completeness"]["advised"][str(steps[1]["bfc_node_id"])] == ["DATA_IN", "DATA_OUT", "ORDER"]
    assert g["completeness"]["missing_output"] == [] and g["completeness"]["missing_data_in"] == []
    de = entity(client, ed, "Pick list")
    io(client, ed, steps[2], de, "O")
    io(client, ed, steps[0], de, "I")                                 # Third → First: the data decides
    g = graph(client, ed, b)
    assert g["order_source"] == "DERIVED"
    assert {p["node_name"]: p["rank"] for p in g["processes"]} == {"Third": 0, "First": 1, "Second": 0}


def test_a_rule_never_blocks_a_chart_whose_dfd_is_off(client, world, ed):
    """S7-3, unchanged by D-70: the rule is stored and shown, it just does not apply."""
    w = scope(client, ed)
    s = node(client, ed, "Ship", w["group"]["bfc_node_id"], is_process=True)
    set_rule(client, world, ed["p"], ["STARTED", "DATA_IN", "DATA_OUT"])
    assert preview(client, ed)["freeze_blocking"]["process_missing_data_in"][0]["bfc_node_id"] == s["bfc_node_id"]
    switch(client, world, ed["p"], ["SOLUTION", "FUNCTION_REQUIREMENT", "EFFORT", "APPLICATION", "AS_IS"])
    got = rule(client, ed)
    assert got["charts"][0]["rule_applies"] is False and codes_of(got) == ["STARTED", "DATA_IN", "DATA_OUT"]
    assert preview(client, ed)["freeze_blocking"] == {}
    assert preview_rule(client, world, ed["p"], ["STARTED", "DATA_IN", "DATA_OUT"])["would_block"] == 0
