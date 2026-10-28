"""Solution matrix (docs/slice1f_spec.md §3.3, function 66, criterion 10b). Grade 2: a wrong count reaches a client
deck and is corrected once someone checks it. The cell grain, the always-present columns, the unlinked row, the
REJECTED count and the TECHNOLOGY share are proven on one built fixture.

Deliberately uncovered (spec §5): very large projects; the print layout (browser pass)."""
from tests.test_br_fr import set_components, two_brs
from tests.test_reports_traceability import _set_status
from tests.test_scope_api import API, ed, node  # noqa: F401 — ed is a fixture
from tests.test_solution_api import link, sol
from tests.test_step_retire import _br

CATEGORIES = ["ORG_AND_RULES", "PEOPLE", "PROCESS", "DATA", "TECHNOLOGY"]


def matrix(client, ed, headers=None, expect=200):
    r = client.get(f"{API}/projects/{ed['p']}/solution-matrix", headers=headers or ed["rv"])
    assert r.status_code == expect, r.text
    return r.json()


def cell(out, area, code):
    row = next(r for r in out["rows"] if r["area_name"] == area)
    return (row["cells"][code]["solutions"], row["cells"][code]["brs"])


def test_cells_columns_unlinked_rejected_and_share(client, ed):
    """10b: every category is a column in code-list order, an empty one included. A solution on two BRs of one
    area is one solution, two BRs; one answering two areas counts in both rows and once in each row total."""
    b1, b2, _, _ = two_brs(client, ed)                                   # both under Sales
    fin = node(client, ed, "Finance")
    grp = node(client, ed, "Record to report", fin["bfc_node_id"])
    b3 = _br(client, ed, node(client, ed, "Close books", grp["bfc_node_id"], is_process=True)["bfc_node_id"])
    tech = sol(client, ed, "Order portal", "TECHNOLOGY")
    people = sol(client, ed, "Approval matrix", "PEOPLE")
    sol(client, ed, "Process map", "PROCESS")                            # on no BR: the unlinked row
    gone = sol(client, ed, "Old system", "TECHNOLOGY")
    for b, s in ((b1, tech), (b2, tech), (b1, people), (b3, people), (b1, gone)):
        assert link(client, ed, b["br_id"], s["solution_id"]).status_code == 201
    _set_status(client, ed, gone, "REJECTED")
    out = matrix(client, ed)
    assert [c["code"] for c in out["categories"]] == CATEGORIES
    assert [r["area_name"] for r in out["rows"]] == ["Sales", "Finance"]
    assert cell(out, "Sales", "TECHNOLOGY") == (1, 2)                   # the REJECTED one is not in the cell
    assert cell(out, "Sales", "PEOPLE") == (1, 1) and cell(out, "Finance", "PEOPLE") == (1, 1)
    assert all(cell(out, a, "ORG_AND_RULES") == (0, 0) for a in ("Sales", "Finance"))
    sales = out["rows"][0]
    assert sales["total"] == {"solutions": 2, "brs": 2}
    assert out["unlinked"]["PROCESS"] == {"solutions": 1, "brs": 0} and out["unlinked"]["TECHNOLOGY"]["solutions"] == 0
    assert out["totals"] == {"ORG_AND_RULES": 0, "PEOPLE": 1, "PROCESS": 1, "DATA": 0, "TECHNOLOGY": 1}
    assert (out["live_count"], out["rejected_count"]) == (3, 1)
    assert out["technology_share"] == 33.3


def test_solution_off_is_null_empty_is_no_share_and_an_outsider_gets_404(client, ed, world):
    """A1 with SOLUTION off; with it on and no solution the share is null rather than 0 %."""
    two_brs(client, ed)
    set_components(client, world, ed["p"], ["FUNCTION_REQUIREMENT"])
    out = matrix(client, ed)
    assert all(out[k] is None for k in ("categories", "rows", "unlinked", "totals", "live_count", "rejected_count",
                                       "technology_share"))
    set_components(client, world, ed["p"], ["SOLUTION"])
    out = matrix(client, ed)
    assert out["technology_share"] is None and out["rows"][0]["total"] == {"solutions": 0, "brs": 0}
    matrix(client, ed, headers=ed["out"], expect=404)
