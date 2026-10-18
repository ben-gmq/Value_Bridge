"""The project dashboard's scope figures (mockup "Program dashboard", requirement tiles and the per-area table):
for each level-1 area of the to-be chart — processes, requirements, how many are confirmed, reach a functional
requirement or have a solution, and the FRs and effort behind them. Read-only; every number from live rows."""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BfcNode, BrFunctionRequirement, BrSolution, BusinessRequirement, FunctionRequirement, Solution
from services import baseline, issue as issue_service, process_flow
from services.consistency import consistency_check

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
    # sara M2: the total row is computed here, over DISTINCT FRs — an FR traced from two areas counts in each area's
    # row but once in the total, and an untraced FR is in no area. The tiles read the whole register.
    days = lambda ids: float(sum((live_frs[i].effort_days or Decimal(0)) for i in ids))      # noqa: E731
    totals["frs"] = len(live_frs)
    totals["frs_traced"] = len(traced)
    totals["frs_without_br"] = len(set(live_frs) - traced)
    totals["effort_days"] = days(live_frs)
    totals["traced_effort_days"] = days(traced)
    totals["untraced_effort_days"] = days(set(live_frs) - traced)

    # Slice 12 (docs/slice12_kpis.md, S12-1). S7: the to-be processes per area that are not Ready under the chart's
    # DFD rule — red blocks the next freeze, amber misses a recommended element — read through the same reader as the
    # light (process_flow.readiness), so the tile and the chart never disagree. No DFD on → no figure (None).
    ready = process_flow.readiness(db, project_id, "TO_BE")
    for r in out:
        r["not_ready_red"] = r["not_ready_amber"] = 0
    by_code = {r["hier_code"]: r for r in out}
    for node_id, p in ready["processes"].items():
        r = by_code.get(area_of.get(node_id))
        if r is not None and p["light"] != process_flow.READY:
            r["not_ready_red" if p["light"] == process_flow.NOT_READY else "not_ready_amber"] += 1
    totals["dfd_on"] = ready["rule_applies"]
    for k in ("not_ready_red", "not_ready_amber"):
        totals[k] = sum(r[k] for r in out) if ready["rule_applies"] else None
    # S8, S10: whole-project figures, from the consistency report the freeze itself reads.
    report = consistency_check(project_id, db)
    errors, blocking, warnings = baseline.gate_report(report)
    totals["entities_without_fields"] = len(report["entities_without_fields"])
    totals["entities_keys_only"] = len(report["entities_keys_only"])
    totals["freeze_errors"] = sum(len(v) for v in errors.values())
    totals["freeze_blocking"] = sum(len(v) for v in blocking.values())
    totals["freeze_warnings"] = sum(len(v) for v in warnings.values())
    # M3 (slice 14, I-13): open issues, and of them severity CRITICAL only — the dashboard's own figures.
    counts = issue_service.open_counts(issue_service.list_issues(db, project_id, open_only=True))
    totals["issues_open"], totals["issues_critical"] = counts["open"], counts["critical"]
    return {"areas": out, "totals": totals}
