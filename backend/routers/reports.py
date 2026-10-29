"""Slice 1f routes (docs/slice1f_spec.md §2): the client reports. Every read is project_ctx(VIEW) with no component —
a part whose component is off comes back None (A1), so a project you cannot see is 404 and nothing is 409."""
from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser, Project
from routers.guards import GuardedRouter, project_ctx
from schemas.reports import ApplicationGapOut, CoverageOut, PrintStampOut, SolutionMatrixOut, TraceabilityOut
from services import reports, xlsx

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


@router.get("/projects/{project_id}/application-gap", response_model=ApplicationGapOut, **_read.route)
def application_gap(project_id: int, level: int = 1, db: Session = Depends(get_db)):
    return reports.application_gap(db, project_id, level)


@router.get("/projects/{project_id}/interfaces/export", **_read.route)
def interface_export(project_id: int, source: int | None = None, target: int | None = None, status: str | None = None,
                     user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    """§3.5: the interface list under the screen's filters as .xlsx. The file name carries only the project id."""
    content = reports.interface_workbook(db, project_id, user.display_name, source, target, status)
    return Response(content, media_type=xlsx.XLSX_MEDIA_TYPE,
                    headers={"Content-Disposition": f'attachment; filename="vb-interfaces-{project_id}.xlsx"'})


@router.get("/projects/{project_id}/print-stamp", response_model=PrintStampOut, **_read.route)
def print_stamp(project_id: int, report: str, generated_at: str, request: Request, filters: str | None = None,
                user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    """§3.6: a GET that writes one REPORT_PRINTED audit row (A2). The screen calls it once per press of Print / PDF."""
    ip = request.client.host if request.client else None
    return reports.print_stamp(db, user, db.get(Project, project_id), report, filters, generated_at, ip)
