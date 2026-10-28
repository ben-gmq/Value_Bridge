"""Coverage report (docs/slice1f_spec.md §3.2, function 56; design §4.3 br_coverage_report). Grade 2: a missed or
false gap line reaches a client's scope review and is corrected once someone checks it. Each line is proven with one
row it lists and one it leaves out.

Deliberately uncovered (spec §5): very large projects (no performance test); the print layout (browser pass)."""
from tests.test_application_api import app
from tests.test_baseline import scope
from tests.test_br_flows import flow
from tests.test_br_fr import lnk, set_components, two_brs
from tests.test_function_requirement_api import fr
from tests.test_interface_api import put as put_iface
from tests.test_reports_traceability import _set_status
from tests.test_scope_api import API, ed, entity, node  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol
from tests.test_step_retire import _br


def lines(client, ed, headers=None, expect=200):
    r = client.get(f"{API}/projects/{ed['p']}/coverage", headers=headers or ed["rv"])
    assert r.status_code == expect, r.text
    return {ln["code"]: ln for ln in r.json()["lines"]} if expect == 200 else None


def nums(line, key):
    return [r[key] for r in line["rows"]]


def test_br_and_data_entity_lines(client, ed):
    """A BR with only a read, or nothing, has no output; an entity no live BR touches is the scope-gap list."""
    s = scope(client, ed)                                   # br1, br2 each read one entity and create the other
    b3, b4 = (_br(client, ed, node(client, ed, n, s["group"]["bfc_node_id"], is_process=True)["bfc_node_id"])
              for n in ("Check stock", "Ship order"))
    spare = entity(client, ed, "Customer")
    out = lines(client, ed)
    assert nums(out["br_without_output_de"], "br_number") == sorted([b3["br_number"], b4["br_number"]])
    assert nums(out["de_unreferenced"], "de_number") == [spare["de_number"]]
    assert out["de_unreferenced"]["rows"][0]["data_entity_id"] == spare["data_entity_id"]
    assert s["br1"]["br_number"] not in nums(out["br_without_output_de"], "br_number")
    assert [ln["severity"] for ln in (out["br_without_output_de"], out["de_unreferenced"])] == ["information"] * 2


def test_solution_and_fr_lines(client, ed):
    """br_without_solution skips an answered BR but not one answered only by a REJECTED solution (S5-2);
    br_without_fr, fr_without_br (a warning) and fr_without_solution each list one row and leave one out."""
    b1, b2, _, _ = two_brs(client, ed)
    good, gone = sol(client, ed, "Approval matrix", "PEOPLE"), sol(client, ed, "Old habit", "PROCESS")
    assert link(client, ed, b1["br_id"], good["solution_id"]).status_code == 201
    assert link(client, ed, b2["br_id"], gone["solution_id"]).status_code == 201
    _set_status(client, ed, gone, "REJECTED")
    tagged = fr(client, ed, "Approval form", solution_id=good["solution_id"])
    loose = fr(client, ed, "Loose form")
    lnk(client, ed, b1, tagged)
    out = lines(client, ed)
    assert nums(out["br_without_solution"], "br_number") == [b2["br_number"]]
    assert nums(out["br_without_fr"], "br_number") == [b2["br_number"]]
    assert nums(out["fr_without_br"], "fr_number") == [loose["fr_number"]]
    assert out["fr_without_br"]["severity"] == "warning"
    assert nums(out["fr_without_solution"], "fr_number") == [loose["fr_number"]]
    assert out["fr_without_br"]["rows"][0]["fr_id"] == loose["fr_id"]


def test_tag_lines_outside_reach_rejected_and_technology(client, ed):
    """An FR on BR1 tagged to BR2's solution is outside its BRs and a reach hint for BR2; a REJECTED tag is its own
    warning; a TECHNOLOGY answer with no FR is a warning (D5), one with an FR is not."""
    b1, b2, _, _ = two_brs(client, ed)
    s1, s2 = sol(client, ed, "Order portal", "TECHNOLOGY"), sol(client, ed, "Credit engine", "TECHNOLOGY")
    bare = sol(client, ed, "Data lake", "TECHNOLOGY")
    gone = sol(client, ed, "Old habit", "PROCESS")
    for b, s in ((b1, s1), (b2, s2), (b2, bare), (b1, gone)):
        assert link(client, ed, b["br_id"], s["solution_id"]).status_code == 201
    home = fr(client, ed, "Portal page", solution_id=s1["solution_id"])
    away = fr(client, ed, "Credit check", solution_id=s2["solution_id"])
    old = fr(client, ed, "Paper form", solution_id=gone["solution_id"])
    for f in (home, away, old):
        lnk(client, ed, b1, f)
    _set_status(client, ed, gone, "REJECTED")
    out = lines(client, ed)
    outside = [(r["fr_number"], r["solution_number"]) for r in out["fr_solution_outside_its_brs"]["rows"]]
    assert (away["fr_number"], s2["solution_number"]) in outside and home["fr_number"] not in dict(outside)
    assert [(r["fr_number"], r["br_number"]) for r in out["solution_reach_without_link"]["rows"]] == [
        (away["fr_number"], b2["br_number"])]
    assert [(r["fr_number"], r["solution_number"]) for r in out["fr_rejected_tag"]["rows"]] == [
        (old["fr_number"], gone["solution_number"])]
    assert nums(out["tech_solution_without_fr"], "solution_number") == [bare["solution_number"]]
    assert [out[c]["severity"] for c in ("fr_solution_outside_its_brs", "solution_reach_without_link",
                                         "fr_rejected_tag", "tech_solution_without_fr")] == [
        "warning", "information", "warning", "warning"]


def test_flow_uncovered_lists_the_flow_no_interface_fr_covers(client, ed):
    """br_flows.coverage: a flow with a linked interface FR on the same ends and entity drops out; the other stays."""
    s = scope(client, ed)
    crm = app(client, ed, code="SF-CRM", name="Salesforce", lifecycle="TO_BE")
    erp = app(client, ed, code="SAP-ECC", name="SAP ECC", lifecycle="BOTH")
    flow(client, ed, s["br1"], s["order"], crm, erp)
    open_flow = flow(client, ed, s["br1"], s["invoice"], erp, crm)
    i = fr(client, ed, "Order feed", "INTERFACE")
    assert put_iface(client, ed, i, crm, erp, [s["order"]]).status_code == 200
    lnk(client, ed, s["br1"], i)
    line = lines(client, ed)["flow_uncovered"]
    assert line["severity"] == "warning"
    assert [(r["br_system_flow_id"], r["de_number"], r["source_code"], r["target_code"]) for r in line["rows"]] == [
        (open_flow["br_system_flow_id"], s["invoice"]["de_number"], "SAP-ECC", "SF-CRM")]


def test_components_off_are_null_and_an_outsider_gets_404(client, ed, world):
    """A1: with only the base components on, every line that needs FR, SOLUTION or APPLICATION is null, not empty;
    flow_uncovered drops to information with FR off. A project you cannot see is 404."""
    two_brs(client, ed)
    set_components(client, world, ed["p"], ["APPLICATION"])
    out = lines(client, ed)
    for code in ("br_without_solution", "br_without_fr", "fr_without_br", "fr_without_solution",
                 "fr_solution_outside_its_brs", "solution_reach_without_link", "fr_rejected_tag",
                 "tech_solution_without_fr"):
        assert out[code]["rows"] is None, code
    assert out["flow_uncovered"] == {"code": "flow_uncovered", "severity": "information", "rows": []}
    assert len(out["br_without_output_de"]["rows"]) == 2 and out["de_unreferenced"]["rows"] == []
    set_components(client, world, ed["p"], ["SOLUTION"])
    out = lines(client, ed)                                 # SOLUTION alone: its own line only (sara 1f-2 L5)
    assert len(out["br_without_solution"]["rows"]) == 2 and out["br_without_fr"]["rows"] is None
    assert out["fr_without_solution"]["rows"] is None and out["tech_solution_without_fr"]["rows"] is None
    set_components(client, world, ed["p"], [])
    assert lines(client, ed)["flow_uncovered"]["rows"] is None
    lines(client, ed, headers=ed["out"], expect=404)
