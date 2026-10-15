"""The project dashboard's scope figures (mockup "Program dashboard", requirement tiles and the per-area table):
for each level-1 area of the to-be chart — processes, requirements, how many are confirmed, reach a functional
requirement or have a solution, and the FRs and effort behind them. Read-only; every number from live rows."""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BfcNode, BrFunctionRequirement, BrSolution, BusinessRequirement, FunctionRequirement, Solution

AGREED = {"CONFIRMED", "BASELINED"}


def _area(hier_code: str) -> str:
    return hier_code.split(".", 1)[0]


def summary(db: Session, project_id: int) -> dict:
    nodes = db.scalars(select(BfcNode).where(BfcNode.project_id == project_id, BfcNode.is_active,
                                             BfcNode.bfc_set_code == "TO_BE")).all()
    areas = {n.hier_code: n for n in nodes if n.level_no == 1}
    area_of = {n.bfc_node_id: _area(n.hier_code) for n in nodes if n.is_process}
    brs = [b for b in db.scalars(select(BusinessRequirement).where(BusinessRequirement.project_id == project_id,
                                                                 BusinessRequirement.is_active)).all()
           if b.bfc_node_id in area_of]
    live_frs = {f.fr_id: f for f in db.scalars(select(FunctionRequirement).where(
        FunctionRequirement.project_id == project_id, FunctionRequirement.is_active)).all()}
    live_sols = set(db.scalars(select(Solution.solution_id).where(Solution.project_id == project_id, Solution.is_active)))
    frs_of: dict[int, set[int]] = {}
    for link in db.scalars(select(BrFunctionRequirement).where(BrFunctionRequirement.project_id == project_id,
                                                             BrFunctionRequirement.is_active)):
        if link.fr_id in live_frs:
            frs_of.setdefault(link.br_id, set()).add(link.fr_id)
    with_sol = {s.br_id for s in db.scalars(select(BrSolution).where(BrSolution.project_id == project_id,
                                                                    BrSolution.is_active))
                if s.solution_id in live_sols}

    rows = {code: {"hier_code": code, "name": n.node_name, "processes": 0, "brs": 0, "confirmed": 0, "with_fr": 0,
                   "with_solution": 0, "fr_ids": set()} for code, n in areas.items()}
    for code in area_of.values():
        if code in rows:
            rows[code]["processes"] += 1
    for b in brs:
        r = rows.get(area_of[b.bfc_node_id])
        if r is None:
            continue
        r["brs"] += 1
        r["confirmed"] += b.status_code in AGREED
        r["with_fr"] += b.br_id in frs_of
        r["with_solution"] += b.br_id in with_sol
        r["fr_ids"] |= frs_of.get(b.br_id, set())
    out = []
    for r in sorted(rows.values(), key=lambda x: x["hier_code"]):
        ids = r.pop("fr_ids")
        r["frs"] = len(ids)
        r["effort_days"] = float(sum((live_frs[i].effort_days or Decimal(0)) for i in ids))
        out.append(r)
    traced = set().union(*frs_of.values()) if frs_of else set()
    totals = {k: sum(r[k] for r in out) for k in ("processes", "brs", "confirmed", "with_fr", "with_solution")}
    totals["frs"] = len(live_frs)
    totals["frs_without_br"] = len(set(live_frs) - traced)
    totals["effort_days"] = float(sum((f.effort_days or Decimal(0)) for f in live_frs.values()))
    return {"areas": out, "totals": totals}
