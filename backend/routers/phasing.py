"""Slice 15 routes (docs/slice15_phasing_spec.md §4): waves, a solution's split across them, solution dependencies and
the wave plan. Shown as "Wave" on every screen (W-1); the paths keep `phase`.

Reads are project_ctx / object_guard at VIEW; every write needs EDIT and component PHASING (W-3), named in
ROUTE_COMPONENTS; a write under /solutions names SOLUTION too, which PHASING needs anyway (OR-2). A row of a project
you cannot see is a 404."""
from fastapi import Depends
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser, Phase, Solution, SolutionDependency
from routers.guards import GuardedRouter, object_guard, project_ctx
from schemas.phasing import (DependenciesOut, DependencyIn, DependencyOut, PhaseIn, PhaseOut, PhasePatch, PlanOut,
                             ReorderIn, SplitIn, SplitOut)
from services import lifecycle, phasing

router = GuardedRouter(tags=["phasing"])
_read = project_ctx("VIEW")
_edit = project_ctx("EDIT", "PHASING")
_ph_r, _ph_w = object_guard(Phase, "VIEW"), object_guard(Phase, "EDIT", component="PHASING")
_sol_r, _sol_w = object_guard(Solution, "VIEW"), object_guard(Solution, "EDIT", component=("SOLUTION", "PHASING"))


def _uid(user: AppUser) -> int:
    return user.app_user_id


# ---- waves -----------------------------------------------------------------------------------------------------------
@router.get("/projects/{project_id}/phases", response_model=list[PhaseOut], **_read.route)
def list_phases(project_id: int, include_retired: bool = False, db: Session = Depends(get_db)):
    return phasing.list_phases(db, project_id, include_retired)


@router.post("/projects/{project_id}/phases", response_model=PhaseOut, status_code=201, **_edit.route)
def create_phase(project_id: int, body: PhaseIn, user: AppUser = Depends(current_user),
                 db: Session = Depends(get_db)):
    return phasing.create_phase(db, _uid(user), project_id, body.model_dump())


@router.post("/projects/{project_id}/phases/reorder", response_model=list[PhaseOut], **_edit.route)
def reorder_phases(project_id: int, body: ReorderIn, user: AppUser = Depends(current_user),
                   db: Session = Depends(get_db)):
    return phasing.reorder_phases(db, _uid(user), project_id, [(o.id, o.row_version) for o in body.order])


@router.get("/phases/{id}", response_model=PhaseOut, **_ph_r.route)
def read_phase(id: int, phase: Phase = Depends(_ph_r.dep)):
    return phase


@router.patch("/phases/{id}", response_model=PhaseOut, **_ph_w.route)
def update_phase(id: int, body: PhasePatch, phase: Phase = Depends(_ph_w.dep), user: AppUser = Depends(current_user),
                 db: Session = Depends(get_db)):
    return phasing.update_phase(db, _uid(user), phase, body.row_version,
                                body.model_dump(exclude_unset=True, exclude={"row_version"}))


@router.delete("/phases/{id}", status_code=204, **_ph_w.route)
def retire_phase(id: int, row_version: int, phase: Phase = Depends(_ph_w.dep), user: AppUser = Depends(current_user),
                 db: Session = Depends(get_db)):
    """For a wave created in error; refused while a solution is split into it (lifecycle, through the FK). The normal
    end of a wave is its status, COMPLETE or CANCELLED."""
    lifecycle.retire(db, _uid(user), phase, row_version)


@router.patch("/phases/{id}/restore", response_model=PhaseOut, **_ph_w.route)
def restore_phase(id: int, phase: Phase = Depends(_ph_w.dep), user: AppUser = Depends(current_user),
                  db: Session = Depends(get_db)):
    return phasing.restore_phase(db, _uid(user), phase)


# ---- a solution's split (W-5, T1) ------------------------------------------------------------------------------------
@router.get("/solutions/{id}/phase-split", response_model=SplitOut, **_sol_r.route)
def read_split(id: int, solution: Solution = Depends(_sol_r.dep), db: Session = Depends(get_db)):
    return phasing.split_out(db, solution)


@router.put("/solutions/{id}/phase-split", response_model=SplitOut, **_sol_w.route)
def save_split(id: int, body: SplitIn, solution: Solution = Depends(_sol_w.dep), user: AppUser = Depends(current_user),
               db: Session = Depends(get_db)):
    return phasing.save_split(db, _uid(user), solution, [(b.solution_phase_id, b.row_version) for b in body.based_on],
                              [(r.phase_id, r.portion_pct) for r in body.rows])


# ---- dependencies (schema §4) ----------------------------------------------------------------------------------------
@router.get("/solutions/{id}/dependencies", response_model=DependenciesOut, **_sol_r.route)
def list_dependencies(id: int, solution: Solution = Depends(_sol_r.dep), db: Session = Depends(get_db)):
    return phasing.dependencies_of(db, solution)


@router.post("/solutions/{id}/dependencies", response_model=DependencyOut, status_code=201, **_sol_w.route)
def link_dependency(id: int, body: DependencyIn, solution: Solution = Depends(_sol_w.dep),
                    user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return phasing.link_solution_dependency(db, _uid(user), solution, body.depends_on_solution_id, body.note)


@router.delete("/solutions/{id}/dependencies/{link_id}", status_code=204, **_sol_w.route)
def unlink_dependency(id: int, link_id: int, row_version: int, solution: Solution = Depends(_sol_w.dep),
                      user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    """Scoped to the path solution: another solution's link is a 404 (criterion 9)."""
    row = lifecycle.child_of(db, SolutionDependency, link_id, "solution_id", solution.solution_id)
    phasing.unlink_solution_dependency(db, _uid(user), row, row_version)


# ---- the wave plan ---------------------------------------------------------------------------------------------------
@router.get("/projects/{project_id}/phase-plan", response_model=PlanOut, **_read.route)
def phase_plan(project_id: int, db: Session = Depends(get_db)):
    return phasing.plan(db, project_id)
