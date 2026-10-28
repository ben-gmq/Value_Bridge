"""Slice 1f client reports (docs/slice1f_spec.md §3). Read-only and derived on every read from live rows. The caller
owns access: every route is project_ctx(VIEW).

A part that needs a component the project has switched off is None, never an empty list — an empty list would read
"no gaps" (spec A1)."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (Application, ApplicationSolution, BfcNode, BrFunctionRequirement, BrSolution,
                    BusinessRequirement, FunctionRequirement, Solution)
from models.shared import FR_BEHAVIOURS
from services import components, function_requirement as fr_service

BEHAVIOUR_ORDER = ("FORM", "BATCH", "INTERFACE", "REPORT", "OTHER")
assert set(BEHAVIOUR_ORDER) == set(FR_BEHAVIOURS)          # a new behaviour gets its place here (sara 1f L1)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hier_key(code: str) -> tuple:
    return tuple(int(p) if p.isdigit() else p for p in code.split("."))


class _Scope:
    """The live rows every report reads, loaded once per request. A BR counts only on a live to-be step; a link
    counts only when both of its ends are live."""

    def __init__(self, db: Session, project_id: int):
        self.on = components.enabled(db, project_id)
        self.steps = {n.bfc_node_id: n for n in db.scalars(select(BfcNode).where(
            BfcNode.project_id == project_id, BfcNode.is_active, BfcNode.bfc_set_code == "TO_BE"))}
        self.brs = {b.br_id: b for b in db.scalars(select(BusinessRequirement).where(
            BusinessRequirement.project_id == project_id, BusinessRequirement.is_active))
            if b.bfc_node_id in self.steps}
        self.frs = {f.fr_id: f for f in db.scalars(select(FunctionRequirement).where(
            FunctionRequirement.project_id == project_id, FunctionRequirement.is_active))}
        self.sols = {s.solution_id: s for s in db.scalars(select(Solution).where(
            Solution.project_id == project_id, Solution.is_active))}
        self.br_fr = [(br, fr) for br, fr in db.execute(select(BrFunctionRequirement.br_id, BrFunctionRequirement.fr_id)
                      .where(BrFunctionRequirement.project_id == project_id, BrFunctionRequirement.is_active))
                      if br in self.brs and fr in self.frs]
        self.br_sol = [(br, s) for br, s in db.execute(select(BrSolution.br_id, BrSolution.solution_id).where(
                       BrSolution.project_id == project_id, BrSolution.is_active))
                       if br in self.brs and s in self.sols]
        apps = {a.application_id: a for a in db.scalars(select(Application).where(
            Application.project_id == project_id, Application.is_active))}
        self.apps_of_sol: dict[int, list[dict]] = {}
        for app_id, sol_id in db.execute(select(ApplicationSolution.application_id, ApplicationSolution.solution_id)
                                         .where(ApplicationSolution.project_id == project_id,
                                                ApplicationSolution.is_active)):
            if app_id in apps:
                a = apps[app_id]
                self.apps_of_sol.setdefault(sol_id, []).append(
                    {"application_code": a.application_code, "application_name": a.application_name})
        for v in self.apps_of_sol.values():
            v.sort(key=lambda a: a["application_code"])

    def live_sol(self, sol_id: int | None) -> Solution | None:
        return self.sols.get(sol_id) if sol_id is not None else None

    def answers(self) -> set[tuple[int, int]]:
        """(BR, solution) pairs where the solution is a live, non-REJECTED answer of the BR (S5-2, D4)."""
        return {(b, s) for b, s in self.br_sol if self.sols[s].status_code != "REJECTED"}


def _sol_out(s: Solution | None) -> dict | None:
    if s is None:
        return None
    return {"solution_id": s.solution_id, "solution_number": s.solution_number, "solution_name": s.solution_name,
            "category_code": s.category_code, "status_code": s.status_code}


def _br_out(b: BusinessRequirement) -> dict:
    return {"br_id": b.br_id, "br_number": b.br_number, "br_statement": b.br_statement}


def _fr_out(f: FunctionRequirement) -> dict:
    return {"fr_id": f.fr_id, "fr_number": f.fr_number, "fr_name": f.fr_name, "fulfilment_status_code": f.fulfilment_status_code}


# ---- 3.1 traceability -------------------------------------------------------------------------------------------
def traceability(db: Session, project_id: int) -> dict:
    """One row per live (to-be step × BR on it × BR↔FR link × FR), grouped by FR type in behaviour order (criterion
    10a: an FR on three BRs is three rows; D-52: an FR reached only through a solution is none). Then the untraced
    FRs, and the non-technology solutions that answer a BR with no FR (criterion 10, D5)."""
    sc = _Scope(db, project_id)
    if "FUNCTION_REQUIREMENT" not in sc.on:
        return {"generated_at": _now(), "groups": None, "untraced": None, "answered_without_software": None}
    sol_on, app_on = "SOLUTION" in sc.on, "APPLICATION" in sc.on
    answers = sc.answers()

    def tag_part(f: FunctionRequirement, br_id: int | None) -> dict:
        if not sol_on:
            return {"solution": None, "applications": None, "tag_answers_br": None, "rejected_solution": None}
        s = sc.live_sol(f.solution_id)
        return {"solution": _sol_out(s),
                "applications": (sc.apps_of_sol.get(s.solution_id, []) if s else []) if app_on else None,
                "tag_answers_br": None if s is None or br_id is None else (br_id, s.solution_id) in answers,
                "rejected_solution": s is not None and s.status_code == "REJECTED"}

    groups: dict[int, dict] = {}
    for br_id, fr_id in sc.br_fr:
        f, b = sc.frs[fr_id], sc.brs[br_id]
        step = sc.steps[b.bfc_node_id]
        t = f.fr_type_code_row
        g = groups.setdefault(f.fr_type_code_id, {"fr_type_code": t.code, "fr_type_label": t.label,
                                                  "behaviour": f.fr_type_behaviour, "rows": []})
        g["rows"].append({"hier_code": step.hier_code, "step_name": step.node_name, **_br_out(b), **_fr_out(f),
                          **tag_part(f, br_id)})
    for g in groups.values():
        g["rows"].sort(key=lambda r: (_hier_key(r["hier_code"]), r["br_number"], r["fr_number"]))

    def order(g):
        b = g["behaviour"]
        return (BEHAVIOUR_ORDER.index(b) if b in BEHAVIOUR_ORDER else len(BEHAVIOUR_ORDER), g["fr_type_label"])
    linked = {fr for _, fr in sc.br_fr}
    untraced = sorted(({**_fr_out(f), **tag_part(f, None)} for f in sc.frs.values() if f.fr_id not in linked),
                      key=lambda r: r["fr_number"])
    without = None
    if sol_on:
        with_fr = {f.solution_id for f in sc.frs.values() if f.solution_id is not None}
        brs_of: dict[int, list[str]] = {}
        for b, s in answers:
            brs_of.setdefault(s, []).append(sc.brs[b].br_number)
        without = sorted(({**_sol_out(sc.sols[s]), "br_numbers": sorted(nums)} for s, nums in brs_of.items()
                          if s not in with_fr and sc.sols[s].category_code not in fr_service.TECH_CATEGORIES),
                         key=lambda r: r["solution_number"])
    return {"generated_at": _now(), "groups": sorted(groups.values(), key=order), "untraced": untraced,
            "answered_without_software": without}
