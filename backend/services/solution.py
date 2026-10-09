"""Solutions and the BRs they answer (§7.5, §4.3 link_br_solution, D-7). Spec:
docs/slice5_spec.md; schema: docs/slice5_schema.md. solution_number is minted at save.

A pairing retires and restores with its BR's step (S5-1, step_retire.OWNED_BY_BR). Retiring a
solution with live pairings is refused by lifecycle.retire, naming both ends (DR1-P1)."""
import logging

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import BfcNode, BrSolution, BusinessRequirement, Solution
from services import audit, lifecycle, numbering
from services.code_master import resolve, validate_required_code

log = logging.getLogger("vb")

# DR1-S2, law 6: the only columns a request may set. Never project_id, the number or the audit set.
EDITABLE = ("solution_name", "description", "benefit_note", "effort_note")


def _name(value: str) -> str:
    name = (value or "").strip()
    if not name:
        raise HTTPException(422, "solution_name cannot be empty")
    return name


def _check_name_free(db: Session, project_id: int, name: str, solution_id: int | None = None) -> None:
    """Q-1: unique among live solutions, as uq_solution_name_live normalises it. The index still
    decides a race (generic 409); this names the clash in the ordinary case."""
    q = select(Solution).where(Solution.project_id == project_id, Solution.is_active,
                               func.lower(func.btrim(Solution.solution_name)) == name.strip().lower())
    if solution_id is not None:
        q = q.where(Solution.solution_id != solution_id)
    clash = db.scalars(q).first()
    if clash is not None:
        raise HTTPException(409, f"{clash.solution_number} is already called {clash.solution_name}")


def list_solutions(db: Session, project_id: int, include_retired: bool = False) -> list[tuple[Solution, int]]:
    """Each solution with its count of live pairings."""
    counts = dict(db.execute(
        select(BrSolution.solution_id, func.count()).where(BrSolution.project_id == project_id,
                                                           BrSolution.is_active)
        .group_by(BrSolution.solution_id)).all())
    q = select(Solution).where(Solution.project_id == project_id)
    if not include_retired:
        q = q.where(Solution.is_active)
    return [(s, counts.get(s.solution_id, 0)) for s in db.scalars(q.order_by(Solution.solution_number))]


def create_solution(db: Session, actor_id: int, project_id: int, name: str, category_code: str,
                    fields: dict) -> Solution:
    name = _name(name)
    _check_name_free(db, project_id, name)
    category = validate_required_code(db, project_id, "SOLUTION_CATEGORY", category_code, "category_code")
    proposed = next((c for c in resolve(db, project_id, "SOLUTION_STATUS") if c.code == "PROPOSED"), None)
    if proposed is None:                                       # L6: detail in the log only
        log.error("SOLUTION_STATUS/PROPOSED missing for project %s", project_id)
        raise HTTPException(500, "Something went wrong.")
    sol = Solution(project_id=project_id, solution_number=numbering.next_number(db, project_id, "SOL"),
                   solution_name=name, category_code_id=category.code_id, status_code_id=proposed.code_id,
                   created_by=actor_id,
                   **{k: fields[k] for k in EDITABLE if k in fields and k != "solution_name"})
    db.add(sol)
    db.commit()
    db.refresh(sol)
    return sol


def update_solution(db: Session, actor_id: int, sol: Solution, row_version: int, fields: dict,
                    category_code: str | None, status_code: str | None) -> Solution:
    lifecycle.check_live(sol, row_version)
    if "solution_name" in fields:
        fields["solution_name"] = _name(fields["solution_name"])
        _check_name_free(db, sol.project_id, fields["solution_name"], sol.solution_id)
    for k in EDITABLE:
        if k in fields:
            setattr(sol, k, fields[k])
    if category_code is not None:
        sol.category_code_id = validate_required_code(db, sol.project_id, "SOLUTION_CATEGORY",
                                                      category_code, "category_code").code_id
    if status_code is not None:
        sol.status_code_id = validate_required_code(db, sol.project_id, "SOLUTION_STATUS",
                                                    status_code, "status_code").code_id
    sol.updated_by = actor_id
    db.commit()
    db.refresh(sol)                 # reload the code relationships with the new ids
    return sol


def restore_solution(db: Session, actor_id: int, sol: Solution) -> Solution:
    """Q-1: a live solution may have taken the name meanwhile → 409 naming it."""
    lifecycle.lock(db, sol)
    if sol.is_active:
        raise HTTPException(409, f"{lifecycle.label(sol)} is not retired")
    _check_name_free(db, sol.project_id, sol.solution_name, sol.solution_id)
    lifecycle.restore(db, actor_id, sol)
    db.refresh(sol)
    return sol


# ---- pairings (§4.3) --------------------------------------------------------------------------
def link(db: Session, actor_id: int, br: BusinessRequirement, solution_id: int,
         coverage_note: str | None) -> BrSolution:
    # DR1-S1: scoped to the BR's project BEFORE any lock, liveness check or label, so another
    # project's solution — live, retired or missing — is the same 404 and nothing of it leaks.
    sol = db.scalars(select(Solution).where(Solution.solution_id == solution_id,
                                            Solution.project_id == br.project_id)).one_or_none()
    if sol is None:
        raise HTTPException(404, "Not found")
    lifecycle.lock_for_share(db, db.get(BfcNode, br.bfc_node_id))    # SR-5: the step first,
    lifecycle.lock_for_share(db, br)                                 # then the BR,
    lifecycle.lock_for_share(db, sol)                                # then the solution (DR1-D1)
    for end in (br, sol):
        if not end.is_active:
            raise HTTPException(409, f"{lifecycle.label(end)} is retired. Restore it first.")
    row = db.scalars(select(BrSolution).where(BrSolution.br_id == br.br_id,
                                              BrSolution.solution_id == sol.solution_id)
                     .with_for_update(of=BrSolution)).one_or_none()      # DR1-P4
    if row is None:
        row = BrSolution(project_id=br.project_id, br_id=br.br_id, solution_id=sol.solution_id,
                         coverage_note=coverage_note, created_by=actor_id)
        db.add(row)
    elif row.is_active:
        raise HTTPException(409, f"{br.br_number} is already linked to {sol.solution_number}")
    else:                                                     # re-link restores (S1-7)
        lifecycle.relink(db, actor_id, row, detail={"previous_coverage_note": row.coverage_note})  # DR1-D2
        row.coverage_note = coverage_note
    # D-34 hook: once function_requirement exists, clear suggested_br_id here (Q-7).
    db.commit()
    db.refresh(row)
    return row


def edit_note(db: Session, actor_id: int, row: BrSolution, row_version: int,
              coverage_note: str | None) -> BrSolution:
    """S5-3: corrected in place; the statement it replaces stays in the audit trail."""
    lifecycle.check_live(row, row_version)
    if coverage_note == row.coverage_note:                     # sara L-3: no event for no change
        return row
    previous = row.coverage_note
    row.coverage_note = coverage_note
    row.updated_by = actor_id
    audit.record(db, "RECORD_UPDATED", actor_id=actor_id, project_id=row.project_id,
                 target_table=row.__table__.name, target_id=row.br_solution_id,
                 detail={"label": lifecycle.label(row), "previous_coverage_note": previous})
    db.commit()
    db.refresh(row)
    return row


def unlink(db: Session, actor_id: int, row: BrSolution, row_version: int) -> None:
    lifecycle.unlink(db, actor_id, row, row_version)


def links_of_br(db: Session, br: BusinessRequirement) -> list[dict]:
    rows = db.execute(select(BrSolution, Solution).join(Solution, Solution.solution_id == BrSolution.solution_id)
                      .where(BrSolution.br_id == br.br_id, BrSolution.is_active)
                      .order_by(Solution.solution_number)).all()
    return [{**_link(link), "solution_number": s.solution_number, "solution_name": s.solution_name,
             "category_code": s.category_code, "status_code": s.status_code} for link, s in rows]


def links_of_solution(db: Session, sol: Solution) -> list[dict]:
    rows = db.execute(select(BrSolution, BusinessRequirement, BfcNode)
                      .join(BusinessRequirement, BusinessRequirement.br_id == BrSolution.br_id)
                      .join(BfcNode, BfcNode.bfc_node_id == BusinessRequirement.bfc_node_id)
                      .where(BrSolution.solution_id == sol.solution_id, BrSolution.is_active)
                      .order_by(BusinessRequirement.br_number)).all()
    return [{**_link(link), "br_number": br.br_number, "hier_code": n.hier_code, "node_name": n.node_name}
            for link, br, n in rows]


def _link(row: BrSolution) -> dict:
    return {"br_solution_id": row.br_solution_id, "br_id": row.br_id, "solution_id": row.solution_id,
            "coverage_note": row.coverage_note, "row_version": row.row_version}


def brsol_under_inactive(db: Session, project_id: int | None) -> list[dict]:
    """consistency_check line (DR1-D1, §5.4.15 use 3): live pairings whose BR or solution is
    retired. Must be empty — the independent proof that link's lock order holds."""
    q = (select(BrSolution.br_solution_id, BusinessRequirement.br_number, Solution.solution_number)
         .join(BusinessRequirement, BusinessRequirement.br_id == BrSolution.br_id)
         .join(Solution, Solution.solution_id == BrSolution.solution_id)
         .where(BrSolution.is_active, ~(BusinessRequirement.is_active & Solution.is_active)))
    if project_id is not None:
        q = q.where(BrSolution.project_id == project_id)
    return [{"br_solution_id": i, "br_number": b, "solution_number": s}
            for i, b, s in db.execute(q.order_by(BrSolution.br_solution_id)).all()]


def as_br_link(db: Session, row: BrSolution) -> dict:
    """One link as links_of_br shows it — the shape the BR panel's POST and PATCH return."""
    s = db.get(Solution, row.solution_id)
    return {**_link(row), "solution_number": s.solution_number, "solution_name": s.solution_name,
            "category_code": s.category_code, "status_code": s.status_code}
