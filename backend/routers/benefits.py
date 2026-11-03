"""Slice Benefits routes (docs/slice_benefits_spec.md §6). Reads are project_ctx / object_guard at VIEW; every write
needs EDIT and component BENEFIT (409 COMPONENT_OFF when off); link writes need SOLUTION too (the service checks it —
BENEFIT requires it, D-37). A benefit of a project you cannot see is a 404; so is a solution id of another project."""
from fastapi import Depends
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser, Benefit, Solution
from routers.guards import GuardedRouter, object_guard, project_ctx
from schemas.benefit import BenefitIn, BenefitOut, BenefitPatch, LinkIn, LinkOut
from services import benefit as benefit_service

router = GuardedRouter(tags=["benefits"])
_read = project_ctx("VIEW")
_edit = project_ctx("EDIT", "BENEFIT")
_r, _w = object_guard(Benefit, "VIEW"), object_guard(Benefit, "EDIT", component="BENEFIT")
_link = object_guard(Benefit, "EDIT", component=("BENEFIT", "SOLUTION"))
_sol = object_guard(Solution, "VIEW")


@router.get("/projects/{project_id}/benefits", response_model=list[BenefitOut], **_read.route)
def list_benefits(project_id: int, include_retired: bool = False, status: str | None = None, unit: str | None = None,
                  db: Session = Depends(get_db)):
    return benefit_service.list_benefits(db, project_id, include_retired, status=status, unit=unit)


@router.post("/projects/{project_id}/benefits", response_model=BenefitOut, status_code=201, **_edit.route)
def create_benefit(project_id: int, body: BenefitIn, user: AppUser = Depends(current_user),
                   db: Session = Depends(get_db)):
    b = benefit_service.create_benefit(db, user.app_user_id, project_id, body.model_dump())
    return benefit_service.decorate(db, b)


@router.get("/benefits/{id}", response_model=BenefitOut, **_r.route)
def read_benefit(id: int, b: Benefit = Depends(_r.dep), db: Session = Depends(get_db)):
    return benefit_service.decorate(db, b)


@router.patch("/benefits/{id}", response_model=BenefitOut, **_w.route)
def update_benefit(id: int, body: BenefitPatch, b: Benefit = Depends(_w.dep), user: AppUser = Depends(current_user),
                   db: Session = Depends(get_db)):
    b = benefit_service.update_benefit(db, user.app_user_id, b, body.row_version,
                                       body.model_dump(exclude_unset=True, exclude={"row_version"}))
    return benefit_service.decorate(db, b)


@router.delete("/benefits/{id}", status_code=204, **_w.route)
def retire_benefit(id: int, row_version: int, b: Benefit = Depends(_w.dep), user: AppUser = Depends(current_user),
                   db: Session = Depends(get_db)):
    """Refused while the benefit has live links (409 naming them)."""
    benefit_service.retire_benefit(db, user.app_user_id, b, row_version)


@router.patch("/benefits/{id}/restore", response_model=BenefitOut, **_w.route)
def restore_benefit(id: int, b: Benefit = Depends(_w.dep), user: AppUser = Depends(current_user),
                    db: Session = Depends(get_db)):
    return benefit_service.decorate(db, benefit_service.restore_benefit(db, user.app_user_id, b))


@router.put("/benefits/{id}/solutions/{solution_id}", response_model=LinkOut, **_link.route)
def link_solution(id: int, solution_id: int, body: LinkIn, b: Benefit = Depends(_link.dep),
                  user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    """Idempotent: the same % twice writes one audit event. BN-2: the benefit's live links total at most 100 %."""
    return benefit_service.link_out(benefit_service.link_solution(db, user.app_user_id, b, solution_id,
                                                                  body.contribution_pct))


@router.delete("/benefits/{id}/solutions/{solution_id}", status_code=204, **_link.route)
def unlink_solution(id: int, solution_id: int, b: Benefit = Depends(_link.dep), user: AppUser = Depends(current_user),
                    db: Session = Depends(get_db)):
    benefit_service.unlink_solution(db, user.app_user_id, b, solution_id)


@router.get("/solutions/{id}/benefits", response_model=list[LinkOut], **_sol.route)
def solution_benefits(id: int, s: Solution = Depends(_sol.dep), db: Session = Depends(get_db)):
    links = benefit_service.live_links(db, solution_id=s.solution_id)
    return [benefit_service.link_out(ln) for ln in sorted(links, key=lambda ln: ln.benefit_row.benefit_number)]


@router.get("/projects/{project_id}/value-ranking", **_read.route)
def value_ranking(project_id: int, db: Session = Depends(get_db)):
    return benefit_service.value_ranking(db, project_id)


@router.get("/projects/{project_id}/benefit-gap", **_read.route)
def benefit_gap(project_id: int, db: Session = Depends(get_db)):
    return benefit_service.benefit_gap_report(db, project_id)
