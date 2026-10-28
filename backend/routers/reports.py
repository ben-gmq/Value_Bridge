"""Slice 1f routes (docs/slice1f_spec.md §2): the client reports. Every read is project_ctx(VIEW) with no component —
a part whose component is off comes back None (A1), so a project you cannot see is 404 and nothing is 409."""
from fastapi import Depends
from sqlalchemy.orm import Session

from database import get_db
from routers.guards import GuardedRouter, project_ctx
from schemas.reports import CoverageOut, SolutionMatrixOut, TraceabilityOut
from services import reports

router = GuardedRouter(tags=["reports"])
_read = project_ctx("VIEW")


@router.get("/projects/{project_id}/traceability", response_model=TraceabilityOut, **_read.route)
def traceability(project_id: int, db: Session = Depends(get_db)):
    return reports.traceability(db, project_id)


@router.get("/projects/{project_id}/coverage", response_model=CoverageOut, **_read.route)
def coverage(project_id: int, db: Session = Depends(get_db)):
    return reports.coverage(db, project_id)


@router.get("/projects/{project_id}/solution-matrix", response_model=SolutionMatrixOut, **_read.route)
def solution_matrix(project_id: int, db: Session = Depends(get_db)):
    return reports.solution_matrix(db, project_id)
