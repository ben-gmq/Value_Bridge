"""Control-C piece C1: where change lands and master data candidates, their panel rows (docs/slice_control_c_spec.md §8
tests 1, 2, 6; CC-1, CC-2). Grade 2: a wrong figure reaches a steering meeting and is corrected once noticed.

Deliberately uncovered: weighting by solution category (CC-1 keeps every change equal); speed at the design bound
beyond one timed run."""
from sqlalchemy import select, text

from models import ControlRule
from services import control
from tests.conftest import owner_engine
from tests.test_br_fr import set_components
from tests.test_control import edit, panel, row
from tests.test_scope_api import API, ed, entity, node  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol


def intensity(client, ed, headers=None, expect=200):
    r = client.get(f"{API}/projects/{ed['p']}/change-intensity", headers=headers or ed["rv"])
    assert r.status_code == expect, r.text
    return r.json()


def master(client, ed, headers=None, expect=200):
    r = client.get(f"{API}/projects/{ed['p']}/master-data", headers=headers or ed["rv"])
    assert r.status_code == expect, r.text
    return r.json()


def brs_by_step(client, ed):
    return {b["bfc_node_id"]: b for b in client.get(f"{API}/projects/{ed['p']}/business-requirements",
                                                   headers=ed["h"]).json()}


def area(client, ed, name, steps):
    """An L1 area with one L2 group and `steps` process steps; returns the L1 node and the step ids."""
    top = node(client, ed, name)
    group = node(client, ed, f"{name} group", top["bfc_node_id"])["bfc_node_id"]
    return top, [node(client, ed, f"{name} step {i}", group, is_process=True)["bfc_node_id"] for i in range(steps)]


def change(client, ed, step_ids, s):
    by_step = brs_by_step(client, ed)
    for step in step_ids:
        assert link(client, ed, by_step[step]["br_id"], s["solution_id"]).status_code == 201


# ---- 1. where change lands (CC-1) ------------------------------------------------------------------------------------
def test_changed_steps_per_area_one_count_per_step_and_the_50_70_boundaries(client, ed):
    sales, s_steps = area(client, ed, "Sales", 4)
    fin, f_steps = area(client, ed, "Finance", 3)
    tech, people = sol(client, ed, "Portal", "TECHNOLOGY"), sol(client, ed, "Training", "PEOPLE")
    change(client, ed, s_steps[:2], tech)
    change(client, ed, s_steps[:1], people)                     # two solutions on one step: still one step
    change(client, ed, f_steps[:2], tech)
    out = intensity(client, ed)
    got = {a["area_name"]: a for a in out["areas"]}
    assert (got["Sales"]["changed_steps"], got["Sales"]["steps"], got["Sales"]["share"]) == (2, 4, "50.00")
    assert got["Sales"]["by_category"]["TECHNOLOGY"] == 2 and got["Sales"]["by_category"]["PEOPLE"] == 1
    assert got["Sales"]["bfc_node_id"] == sales["bfc_node_id"] and got["Finance"]["bfc_node_id"] == fin["bfc_node_id"]
    h = out["headline"]
    assert (h["measured"], h["top_area"], h["areas_at_top"], h["changed_steps"], h["areas"]) == \
        ("50.00", "Sales", 2, 4, 2)                              # a tie: the first in chart order, and how many
    assert row(panel(client, ed), "process_change_intensity")["verdict"] == "GREEN"     # equal to the threshold
    change(client, ed, s_steps[2:3], tech)
    r = row(panel(client, ed), "process_change_intensity")
    assert (r["measured"], r["verdict"], r["figures"]["top_area"]) == ("60.00", "FLAG", "Sales")
    change(client, ed, s_steps[3:], tech)
    assert row(panel(client, ed), "process_change_intensity")["verdict"] == "FLAG"   # 4 of 6 = 66.67
    edit(client, ed, "process_change_intensity", escalate_value="66")
    assert row(panel(client, ed), "process_change_intensity")["verdict"] == "ESCALATE"
    intensity(client, ed, headers=ed["out"], expect=404)


def test_rejected_and_retired_solutions_do_not_count_and_an_area_is_its_node_not_its_code(client, ed):
    _, s_steps = area(client, ed, "Sales", 2)
    _, f_steps = area(client, ed, "Finance", 2)
    tech = sol(client, ed, "Portal", "TECHNOLOGY")
    change(client, ed, s_steps + f_steps[:1], tech)
    dropped = sol(client, ed, "Dropped", "PROCESS")
    change(client, ed, f_steps[1:], dropped)
    r = client.patch(f"{API}/solutions/{dropped['solution_id']}", headers=ed["h"],
                     json={"row_version": dropped["row_version"], "status_code": "REJECTED"})
    assert r.status_code == 200, r.text
    before = {a["bfc_node_id"]: a["changed_steps"] for a in intensity(client, ed)["areas"]}
    assert sorted(before.values()) == [1, 2]
    node(client, ed, "Aardvark")                                # a new L1 renumbers the others' hier_codes
    after = intensity(client, ed)
    assert {a["bfc_node_id"]: a["changed_steps"] for a in after["areas"] if a["steps"]} == before
    gone = sol(client, ed, "Gone", "TECHNOLOGY")
    with owner_engine().begin() as c:                           # a retired solution's links are not changes
        c.execute(text(f"UPDATE solution SET is_active = false WHERE solution_id = {tech['solution_id']}"))
    h = intensity(client, ed)["headline"]
    assert (h["measured"], h["reason"]) == (None, "NO_CHANGES") and gone


def test_change_intensity_not_measured_cases(client, ed, world):
    set_components(client, world, ed["p"], ["FUNCTION_REQUIREMENT"])
    out = intensity(client, ed)
    assert (out["headline"]["reason"], out["areas"]) == ("SOLUTION_OFF", None)
    assert row(panel(client, ed), "process_change_intensity")["verdict"] == "NOT_MEASURED"
    set_components(client, world, ed["p"], ["FUNCTION_REQUIREMENT", "SOLUTION"])
    _, s_steps = area(client, ed, "Sales", 2)
    assert intensity(client, ed)["headline"]["reason"] == "FEWER_THAN_TWO_AREAS"
    change(client, ed, s_steps, sol(client, ed, "Portal", "TECHNOLOGY"))
    assert intensity(client, ed)["headline"]["reason"] == "FEWER_THAN_TWO_AREAS"     # one area always 100 %
    area(client, ed, "Finance", 1)
    assert intensity(client, ed)["headline"]["measured"] == "100.00"
    assert row(panel(client, ed), "process_change_intensity")["verdict"] == "ESCALATE"


# ---- 2. master data candidates (CC-2) --------------------------------------------------------------------------------
def _uses(client, ed, step_ids, de):
    by_step = brs_by_step(client, ed)
    for step in step_ids:
        r = client.post(f"{API}/business-requirements/{by_step[step]['br_id']}/data-entities", headers=ed["h"],
                        json={"data_entity_id": de["data_entity_id"], "crud_code": "R"})
        assert r.status_code == 201, r.text


def _note(client, ed, de, text_):
    cur = client.get(f"{API}/data-entities/{de['data_entity_id']}", headers=ed["h"]).json()
    r = client.patch(f"{API}/data-entities/{de['data_entity_id']}", headers=ed["h"],
                     json={"row_version": cur["row_version"], "business_owner_note": text_})
    assert r.status_code == 200, r.text


def test_three_areas_make_a_candidate_two_do_not_and_a_blank_note_is_no_owner(client, ed):
    assert master(client, ed)["headline"]["reason"] == "NO_ENTITIES_USED"
    steps = [area(client, ed, n, 2)[1] for n in ("Sales", "Finance", "Supply", "People")]
    customer, product, ledger = (entity(client, ed, n) for n in ("Customer", "Product", "Ledger"))
    _uses(client, ed, [steps[0][0], steps[0][1], steps[1][0]], ledger)          # two areas: not a candidate
    _uses(client, ed, [steps[0][0], steps[1][0], steps[2][0]], customer)        # three
    _uses(client, ed, [s[0] for s in steps], product)                           # four
    _note(client, ed, product, "   ")
    out = master(client, ed)
    got = {e["de_name"]: e for e in out["entities"]}
    assert set(got) == {"Customer", "Product"}
    assert (len(got["Product"]["areas"]), got["Product"]["br_count"], got["Product"]["business_owner_note"]) == \
        (4, 4, None)
    assert [a["area_name"] for a in got["Customer"]["areas"]] == ["Sales", "Finance", "Supply"]
    assert out["headline"] == {"measured": "2", "reason": None, "candidates": 2, "entities_used": 3}
    r = row(panel(client, ed), "master_data_candidates")
    assert (r["measured"], r["verdict"]) == ("2.00", "FLAG")
    _note(client, ed, customer, "Head of Sales Ops")
    _note(client, ed, product, "Product data lead")
    r = row(panel(client, ed), "master_data_candidates")
    assert (r["measured"], r["verdict"], r["figures"]["candidates"]) == ("0.00", "GREEN", 2)
    _note(client, ed, product, "")
    edit(client, ed, "master_data_candidates", threshold_value="0", escalate_value="0.5")
    assert row(panel(client, ed), "master_data_candidates")["verdict"] == "ESCALATE"
    master(client, ed, headers=ed["out"], expect=404)


def test_a_retired_requirement_or_entity_drops_out(client, ed):
    steps = [area(client, ed, n, 1)[1][0] for n in ("Sales", "Finance", "Supply")]
    customer = entity(client, ed, "Customer")
    _uses(client, ed, steps, customer)
    assert master(client, ed)["headline"]["measured"] == "1"
    br = brs_by_step(client, ed)[steps[2]]
    with owner_engine().begin() as c:              # the link is left live: only the BR's own state is read
        c.execute(text(f"UPDATE business_requirement SET is_active = false WHERE br_id = {br['br_id']}"))
    out = master(client, ed)
    assert (out["entities"], out["headline"]["measured"]) == ([], "0")         # two areas left
    with owner_engine().begin() as c:
        c.execute(text(f"UPDATE data_entity SET is_active = false WHERE data_entity_id = {customer['data_entity_id']}"))
    assert master(client, ed)["headline"]["reason"] == "NO_ENTITIES_USED"


# ---- 6. seed and panel -----------------------------------------------------------------------------------------------
def test_the_two_rules_backfill_off_and_measured_and_a_new_project_has_them_on(client, ed, db):
    got = {r.analysis_code: r for r in db.scalars(select(ControlRule).where(ControlRule.project_id == ed["p"]))}
    assert got["process_change_intensity"].is_enabled and got["master_data_candidates"].is_enabled
    house = {r.analysis_code: r for r in db.scalars(select(ControlRule).where(ControlRule.project_id.is_(None)))}
    assert (house["process_change_intensity"].comparison, house["process_change_intensity"].threshold_value,
            house["process_change_intensity"].escalate_value) == ("PCT_GT", 50, 70)
    assert (house["master_data_candidates"].comparison, house["master_data_candidates"].threshold_value,
            house["master_data_candidates"].escalate_value) == ("GT", 0, 5)
    with owner_engine().begin() as c:                            # stage a running project from before Control-C
        c.execute(text(f"DELETE FROM control_rule WHERE project_id = {ed['p']} AND analysis_code IN "
                       "('process_change_intensity', 'master_data_candidates')"))
    out = control.backfill(db, "admin@example.test")
    assert {"project_id": ed["p"], "added": ["process_change_intensity", "master_data_candidates"]} in out["projects"]
    p = panel(client, ed)
    for code in ("process_change_intensity", "master_data_candidates"):
        r = row(p, code)
        assert (r["is_enabled"], r["verdict"], r["off_state"]) == (False, None, "NOT_YET_AGREED")
        assert r["reason"] in ("FEWER_THAN_TWO_AREAS", "NO_ENTITIES_USED")     # measured, not skipped
    assert control.backfill(db, "admin@example.test")["projects"][0]["added"] == []
