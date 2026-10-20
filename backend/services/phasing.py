"""Waves (D-18; docs/slice15_phasing_spec.md, slice15_phasing_schema.md; W-1…W-9).

Shown as "Wave" on every screen (W-1); the code keeps `phase`. This module is the one owner of waves, a solution's
split across them and solution dependencies.

consistency_check lines (spec R1, T6), each must be empty — the independent proof that the service rules hold:
`solution_phase_split_not_100`, `solution_dependency_cycle`, `solution_phase_under_inactive`,
`solution_dependency_under_inactive`."""
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, aliased

from models import Phase, Solution, SolutionDependency, SolutionPhase


# ---- consistency_check proofs ----------------------------------------------------------------------------------------
def split_not_100(db: Session, project_id: int | None) -> list[dict]:
    """W-5: a live split totals exactly 100 or has no rows. Must be empty."""
    total = func.sum(SolutionPhase.portion_pct)
    q = (select(Solution.solution_id, Solution.solution_number, total)
         .join(Solution, Solution.solution_id == SolutionPhase.solution_id)
         .where(SolutionPhase.is_active)
         .group_by(Solution.solution_id, Solution.solution_number)
         .having(total != 100))
    if project_id is not None:
        q = q.where(SolutionPhase.project_id == project_id)
    return [{"solution_id": i, "solution_number": n, "total_pct": str(t)}
            for i, n, t in db.execute(q.order_by(Solution.solution_id)).all()]


_CYCLE = """
WITH RECURSIVE reach(start_id, at_id, path) AS (
    SELECT solution_id, depends_on_solution_id, ARRAY[solution_id, depends_on_solution_id]
      FROM solution_dependency WHERE is_active {where}
    UNION ALL
    SELECT r.start_id, d.depends_on_solution_id, r.path || d.depends_on_solution_id
      FROM reach r JOIN solution_dependency d ON d.solution_id = r.at_id AND d.is_active
     WHERE r.at_id <> r.start_id AND NOT d.depends_on_solution_id = ANY(r.path[2:])
)
SELECT DISTINCT r.start_id, s.solution_number FROM reach r JOIN solution s ON s.solution_id = r.start_id
 WHERE r.at_id = r.start_id ORDER BY r.start_id
"""


def dependency_cycle(db: Session, project_id: int | None) -> list[dict]:
    """D-18: no live dependency path leads back to where it started. Must be empty; the `path` guard ends the walk
    even on corrupt data. Every solution on a cycle is listed."""
    where = "AND project_id = :p" if project_id is not None else ""
    rows = db.execute(text(_CYCLE.format(where=where)), {"p": project_id} if project_id is not None else {}).all()
    return [{"solution_id": i, "solution_number": n} for i, n in rows]


def split_under_inactive(db: Session, project_id: int | None) -> list[dict]:
    """R1: a live split row whose solution or wave is retired. Must be empty."""
    q = (select(SolutionPhase.solution_phase_id, Solution.solution_number, Phase.phase_code)
         .join(Solution, Solution.solution_id == SolutionPhase.solution_id)
         .join(Phase, Phase.phase_id == SolutionPhase.phase_id)
         .where(SolutionPhase.is_active, ~(Solution.is_active & Phase.is_active)))
    if project_id is not None:
        q = q.where(SolutionPhase.project_id == project_id)
    return [{"solution_phase_id": i, "solution_number": s, "phase_code": p}
            for i, s, p in db.execute(q.order_by(SolutionPhase.solution_phase_id)).all()]


def dependency_under_inactive(db: Session, project_id: int | None) -> list[dict]:
    """R1: a live dependency whose either solution is retired. Must be empty."""
    need, prereq = aliased(Solution), aliased(Solution)
    q = (select(SolutionDependency.solution_dependency_id, need.solution_number, prereq.solution_number)
         .join(need, need.solution_id == SolutionDependency.solution_id)
         .join(prereq, prereq.solution_id == SolutionDependency.depends_on_solution_id)
         .where(SolutionDependency.is_active, ~(need.is_active & prereq.is_active)))
    if project_id is not None:
        q = q.where(SolutionDependency.project_id == project_id)
    return [{"solution_dependency_id": i, "solution_number": a, "depends_on_solution_number": b}
            for i, a, b in db.execute(q.order_by(SolutionDependency.solution_dependency_id)).all()]
