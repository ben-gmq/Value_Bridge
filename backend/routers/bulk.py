"""Slice 4a routes (§9 of docs/slice4a_spec.md): the one import pipeline — template, export,
validate, preview, commit. Every route declares one guard. A batch is addressed by its own id
under object_guard, so a batch in a project you cannot see is a 404.

The upload is the raw request body (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet),
never multipart, so nothing is spooled to disk (A-4a-7); BodyLimitMiddleware has already capped
it at 10 MB before this module runs. The display name arrives percent-encoded in X-VB-File-Name
(4a-R8) and is never used as a path or a Content-Disposition."""
from fastapi import Depends, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from auth.dependencies import current_user
from database import get_db
from models import AppUser, ImportBatch
from routers.guards import GuardedRouter, object_guard, project_ctx
from services import bulk, xlsx

router = GuardedRouter(tags=["bulk"])
_read = project_ctx("REVIEWER")
_edit = project_ctx("EDITOR")
_batch = object_guard(ImportBatch, "EDITOR", id_param="batch_id")


class CommitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_version: int
    acknowledged_inserts: int | None = Field(default=None, ge=0)


def _xlsx(content: bytes, name: str) -> Response:
    return Response(content, media_type=xlsx.XLSX_MEDIA_TYPE,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


async def _upload(request: Request) -> bytes:
    """The raw .xlsx body, already size-capped at ingress."""
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media != xlsx.XLSX_MEDIA_TYPE:
        raise HTTPException(415, "Send the .xlsx file itself as the request body.")
    return await request.body()


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/projects/{project_id}/bulk/templates/{target}", **_edit.route)
def template(project_id: int, target: str, db: Session = Depends(get_db)):
    t = bulk.target_for(target)
    return _xlsx(bulk.template(db, project_id, t), bulk.download_name(t, "template", project_id))


@router.get("/projects/{project_id}/bulk/{target}/export", **_read.route)
def export(project_id: int, target: str, db: Session = Depends(get_db)):
    t = bulk.target_for(target)
    return _xlsx(bulk.export(db, project_id, t), bulk.download_name(t, "export", project_id))


@router.post("/projects/{project_id}/bulk/{target}/validate", status_code=201, **_edit.route)
def validate(project_id: int, target: str, body: bytes = Depends(_upload),
             file_name: str | None = Header(default=None, alias="X-VB-File-Name"),
             user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    t = bulk.target_for(target)
    batch = bulk.validate(db, user.app_user_id, project_id, t, body, bulk.clean_file_name(file_name))
    return bulk.preview(db, batch)


@router.get("/bulk/batches/{batch_id}", **_batch.route)
def read_batch(batch_id: int, batch: ImportBatch = Depends(_batch.dep), db: Session = Depends(get_db)):
    return bulk.batch_out(db, batch)


@router.get("/bulk/batches/{batch_id}/preview", **_batch.route)
def preview(batch_id: int, batch: ImportBatch = Depends(_batch.dep), db: Session = Depends(get_db)):
    return bulk.preview(db, batch)


@router.post("/bulk/batches/{batch_id}/commit", **_batch.route)
def commit(batch_id: int, body: CommitIn, request: Request, user: AppUser = Depends(current_user),
           batch: ImportBatch = Depends(_batch.dep), db: Session = Depends(get_db)):
    done = bulk.commit(db, user.app_user_id, batch.import_batch_id, body.row_version,
                       body.acknowledged_inserts, _ip(request))
    return bulk.batch_out(db, done)
