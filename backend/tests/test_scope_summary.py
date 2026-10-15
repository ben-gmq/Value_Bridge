"""The project dashboard's scope figures (services/scope_summary.py), over the showcase demo project, whose
numbers are counted by hand from seeds/demo_showcase.py: which process each FR was created on, and which
processes each solution covers."""
from sqlalchemy import select

from models import AppUser, BrFunctionRequirement, FunctionRequirement
from tests.conftest import PW

API = "/api/v1"


def _summary(client, world, db):
    from seeds.demo_showcase import build_showcase
    admin = db.scalar(select(AppUser).where(AppUser.email == "admin@example.test"))
    pid = build_showcase(db, admin, "example.test", PW)
    r = client.get(f"{API}/projects/{pid}/scope-summary", headers=world["admin"])
    assert r.status_code == 200, r.text
    return pid, r.json()


def test_figures_per_area_match_the_seed(client, world, db):
    _, s = _summary(client, world, db)
    by = {a["name"]: a for a in s["areas"]}
    assert list(by) == ["Sales", "Procurement", "Logistics", "Finance"]
    # (processes, requirements, reaching an FR, with a solution, distinct FRs)
    assert {k: (a["processes"], a["brs"], a["with_fr"], a["with_solution"], a["frs"]) for k, a in by.items()} == {
        "Sales": (7, 7, 6, 6, 7),             # Cancel order: added after v1.0, no solution or FR
        "Procurement": (5, 5, 4, 5, 4),       # Evaluate supplier: a solution, no FR
        "Logistics": (6, 6, 4, 6, 4),         # Count stock and Adjust stock: no FR
        "Finance": (7, 7, 5, 6, 7),           # Close the month: playbook only; Issue credit note: a bare draft
    }
    t = s["totals"]
    assert (t["processes"], t["brs"], t["with_fr"], t["with_solution"], t["frs"], t["frs_without_br"]) == (25, 25, 19, 23, 22, 0)
    assert t["effort_days"] == sum(a["effort_days"] for a in s["areas"]) > 0


def test_unlinking_an_fr_drops_reach_and_counts_it_as_untraced(client, world, db):
    pid, before = _summary(client, world, db)
    fr = db.scalar(select(FunctionRequirement).where(FunctionRequirement.project_id == pid,
                                                    FunctionRequirement.fr_name == "Supplier scorecard"))
    link = db.scalar(select(BrFunctionRequirement).where(BrFunctionRequirement.fr_id == fr.fr_id,
                                                        BrFunctionRequirement.is_active))
    r = client.delete(f"{API}/business-requirements/{link.br_id}/function-requirements/{link.br_function_requirement_id}",
                      headers=world["admin"], params={"row_version": link.row_version})       # soft (VB law 1)
    assert r.status_code == 200, r.text
    after = client.get(f"{API}/projects/{pid}/scope-summary", headers=world["admin"]).json()
    proc = lambda s: next(a for a in s["areas"] if a["name"] == "Procurement")      # noqa: E731
    assert (proc(after)["with_fr"], proc(after)["frs"]) == (proc(before)["with_fr"] - 1, proc(before)["frs"] - 1)
    assert after["totals"]["frs"] == before["totals"]["frs"]                    # still live, only untraced
    assert after["totals"]["frs_without_br"] == before["totals"]["frs_without_br"] + 1
