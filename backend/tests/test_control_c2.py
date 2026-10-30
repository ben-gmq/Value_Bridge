"""Control-C piece C2: the FTC company defaults and resetting a project's rules to them (docs/slice_control_c_spec.md
§8 tests 3, 4; CC-4, CC-6; acceptance 79, 192). Grade 2; the riskiest concern is the platform-admin gate, tested from
three refused identities. No mutation harness (its own approved task)."""
from decimal import Decimal

from sqlalchemy import select, text

from models import AuditEvent
from tests.conftest import login, owner_engine
from tests.test_control import edit, panel, role, row, rules
from tests.test_project_admin import add
from tests.test_scope_api import API, ed  # noqa: F401 — ed is a fixture

URL = f"{API}/control-rules/defaults"


def defaults(client, h):
    r = client.get(URL, headers=h)
    assert r.status_code == 200, r.text
    return {d["analysis_code"]: d for d in r.json()}


def set_default(client, h, code, expect=200, **over):
    cur = defaults(client, h)[code]
    body = {f: cur[f] for f in ("threshold_value", "escalate_value", "prescribed_action", "escalation_path")}
    body.update({"change_rationale": "Close-out review of the last engagement", "row_version": cur["row_version"]})
    body.update(over)
    r = client.patch(f"{URL}/{code}", headers=h, json=body)
    assert r.status_code == expect, r.text
    return r.json()


def preview(client, ed, headers=None, expect=200):
    r = client.get(f"{API}/projects/{ed['p']}/control-rules/reset-preview", headers=headers or ed["h"])
    assert r.status_code == expect, r.text
    return r.json()


def do_reset(client, ed, stamp, reason="Client asked to start from the FTC standard", headers=None, expect=200):
    r = client.post(f"{API}/projects/{ed['p']}/control-rules/reset", headers=headers or ed["h"],
                    json={"change_rationale": reason, "stamp": stamp})
    assert r.status_code == expect, r.text
    return r.json()


def new_project(client, world, code):
    r = client.post(f"{API}/projects", headers=world["admin"],
                    json={"project_code": code, "project_name": f"Project {code}", "client_id": world["client_id"],
                          "component_codes": ["SOLUTION"], "is_restricted": False})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


# ---- 3. company defaults (CC-6) --------------------------------------------------------------------------------------
def test_only_a_platform_admin_reads_or_edits_the_company_defaults(client, world, ed):
    assert add(client, world["admin"], ed["p"], world["users"]["owner"], "ADMIN").status_code == 201
    body = {"threshold_value": "1", "escalate_value": None, "prescribed_action": None, "escalation_path": None,
            "change_rationale": "x", "row_version": 1}
    for who in ("owner@example.test", "editor@example.test", "outsider@example.test"):    # project ADMIN, editor, staff
        h = login(client, who)
        assert client.get(URL, headers=h).status_code == 403, who
        assert client.patch(f"{URL}/coverage", headers=h, json=body).status_code == 403, who
    assert client.get(URL).status_code == 401
    assert set(defaults(client, world["admin"])) >= {"priced_diff", "process_change_intensity"}


def test_a_default_edit_needs_a_reason_and_a_current_version_and_never_takes_an_owner(client, world, ed):
    a = world["admin"]
    set_default(client, a, "priced_diff", expect=422, change_rationale="  ")
    set_default(client, a, "priced_diff", expect=422, escalate_value="4")              # not beyond the threshold
    set_default(client, a, "priced_diff", expect=422, owner_org_role_id=1)             # R1-D1: extra field refused
    set_default(client, a, "priced_diff", expect=422, is_enabled=False)
    stale = defaults(client, a)["priced_diff"]["row_version"]
    out = set_default(client, a, "priced_diff", threshold_value="7", escalation_path="Steering committee chair")
    assert (out["threshold_value"], out["row_version"], out["owner"]) == ("7.00", stale + 1, None)
    set_default(client, a, "priced_diff", expect=409, row_version=stale)
    h = out["history"][0]
    assert (h["from"], h["to"], h["text_changed"], h["by"]) == ({"threshold_value": "5"}, {"threshold_value": "7"},
                                                                ["escalation_path"], "Admin")
    assert h["change_rationale"] == "Close-out review of the last engagement"
    before = len(out["history"])
    assert len(set_default(client, a, "priced_diff")["history"]) == before           # no change: nothing written


def test_the_audit_has_no_project_and_keeps_text_only_as_changed(client, world, ed, db):
    set_default(client, world["admin"], "coverage", prescribed_action="Name the gap owner")
    e = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "CONTROL_RULE_CHANGED")
                   .order_by(AuditEvent.audit_event_id.desc())).first()
    assert e.project_id is None and e.detail["house"] is True
    assert e.detail["text_changed"] == ["prescribed_action"] and "Name the gap owner" not in str(e.detail)


def test_a_default_edit_leaves_running_projects_alone_and_reaches_the_next_one(client, world, ed):
    """Acceptance 79."""
    set_default(client, world["admin"], "interface_load", threshold_value="30", escalate_value="40")
    assert Decimal(rules(client, ed)["interface_load"]["threshold_value"]) == 25
    pid = new_project(client, world, "NEXT")
    got = {r["analysis_code"]: r for r in client.get(f"{API}/projects/{pid}/control-rules",
                                                     headers=world["admin"]).json()}
    assert (Decimal(got["interface_load"]["threshold_value"]), Decimal(got["interface_load"]["escalate_value"])) == \
        (30, 40)


# ---- 4. reset (CC-4) -------------------------------------------------------------------------------------------------
def test_reset_overwrites_numbers_and_text_keeps_owner_and_on_off_and_adds_missing_rules_off(client, world, ed, db):
    pmo = role(client, ed)
    edit(client, ed, "priced_diff", threshold_value="15", escalate_value="20", owner_org_role_id=pmo["org_role_id"],
         escalation_path="Sponsor, then steering")
    edit(client, ed, "solution_matrix", is_enabled=False, prescribed_action="Our own words")
    with owner_engine().begin() as c:
        c.execute(text(f"DELETE FROM control_rule WHERE project_id = {ed['p']} AND analysis_code = 'coverage'"))
    untouched = rules(client, ed)["interface_load"]["row_version"]
    pv = preview(client, ed)
    assert {c["analysis_code"]: c["fields"] for c in pv["changes"]} == {
        "priced_diff": ["threshold_value", "escalate_value", "escalation_path"],
        "solution_matrix": ["prescribed_action"]}
    assert pv["added"] == ["coverage"]
    pd = next(c for c in pv["changes"] if c["analysis_code"] == "priced_diff")
    assert (pd["current"]["escalation_path"], pd["default"]["escalation_path"]) == ("Sponsor, then steering", None)
    assert do_reset(client, ed, pv["stamp"]) == {"changed": ["priced_diff", "solution_matrix"], "added": ["coverage"]}
    got = rules(client, ed)
    assert (Decimal(got["priced_diff"]["threshold_value"]), got["priced_diff"]["owner_org_role_id"],
            got["priced_diff"]["escalation_path"], got["priced_diff"]["is_enabled"]) == (5, pmo["org_role_id"], None,
                                                                                         True)
    assert (got["solution_matrix"]["is_enabled"], got["solution_matrix"]["prescribed_action"]) == \
        (False, "Commission the org/process workstream, or lower the benefit forecast")
    assert got["coverage"]["is_enabled"] is False and got["interface_load"]["row_version"] == untouched
    e = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "CONTROL_RULES_RESET")).one()
    assert (e.project_id, e.detail["changed"], e.detail["added"]) == (ed["p"], ["priced_diff", "solution_matrix"],
                                                                      ["coverage"])
    assert "Sponsor, then steering" not in str(e.detail)                               # CT-3
    mark = row(panel(client, ed), "priced_diff")["reset"]
    assert mark["change_rationale"] == "Client asked to start from the FTC standard"
    assert row(panel(client, ed), "interface_load")["reset"] is None
    edit(client, ed, "priced_diff", threshold_value="6", change_rationale="Client agreed 6 % at steering")
    assert row(panel(client, ed), "priced_diff")["reset"] is None                      # round 2 N2: a person edited it
    edit(client, ed, "priced_diff", threshold_value="5", change_rationale="Back to the FTC number")
    pv2 = preview(client, ed)
    assert (pv2["changes"], pv2["added"]) == ([], [])
    assert do_reset(client, ed, pv2["stamp"]) == {"changed": [], "added": []}         # nothing to change: no audit
    assert db.scalar(select(AuditEvent.audit_event_id).where(AuditEvent.event_type == "CONTROL_RULES_RESET")
                     .order_by(AuditEvent.audit_event_id.desc()).offset(1).limit(1)) is None


def test_a_rule_or_default_changed_since_the_preview_refuses_the_whole_reset(client, world, ed, db):
    edit(client, ed, "priced_diff", threshold_value="15", escalate_value="20")
    pv = preview(client, ed)
    edit(client, ed, "interface_load", threshold_value="30")      # R1-P1: a rule the preview did not list
    do_reset(client, ed, pv["stamp"], expect=409)
    pv = preview(client, ed)
    set_default(client, world["admin"], "coverage", prescribed_action="New FTC words")      # a house row
    do_reset(client, ed, pv["stamp"], expect=409)
    assert Decimal(rules(client, ed)["priced_diff"]["threshold_value"]) == 15                # nothing written
    assert db.scalar(select(AuditEvent).where(AuditEvent.event_type == "CONTROL_RULES_RESET")) is None
    do_reset(client, ed, preview(client, ed)["stamp"], reason=" ", expect=422)


def test_a_viewer_cannot_preview_or_reset_and_an_outsider_sees_nothing(client, ed):
    stamp = preview(client, ed)["stamp"]
    preview(client, ed, headers=ed["rv"], expect=403)
    do_reset(client, ed, stamp, headers=ed["rv"], expect=403)
    preview(client, ed, headers=ed["out"], expect=404)
    do_reset(client, ed, stamp, headers=ed["out"], expect=404)
