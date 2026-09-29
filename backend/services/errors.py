"""Shared error handling (playbook §7). The backend always answers with a `detail` string."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

log = logging.getLogger("vb")

CONFLICT = "Updated by another user. Please refresh."
# A stale row_version is the one 409 the UI answers with ConflictDialog; every other 409
# (blockers, duplicates, retired rows) shows its detail. The header tells them apart.
STALE_HEADERS = {"X-VB-Error": "STALE"}


def _flatten(exc: RequestValidationError) -> str:
    """M5: one readable `detail` string, which is all the frontend ever reads (§7)."""
    parts = []
    for e in exc.errors()[:5]:
        loc = ".".join(str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path"))
        msg = str(e.get("msg", "is invalid")).removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) or "The request is invalid."


def install(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return JSONResponse({"detail": _flatten(exc)}, status_code=422)

    @app.exception_handler(StaleDataError)
    async def _stale(_: Request, __: StaleDataError):
        return JSONResponse({"detail": CONFLICT}, status_code=409, headers=STALE_HEADERS)   # D-6

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError):
        code = getattr(exc.orig, "sqlstate", None)
        if code == "23505":                                                  # unique violation
            return JSONResponse({"detail": "That already exists. Refresh and check the "
                                           "existing record."}, status_code=409)   # P10
        if code in ("23502", "23514"):                                       # NOT NULL / CHECK
            log.warning("integrity violation: %s", code)                      # L5 — a 422, not 409
            return JSONResponse({"detail": "That value is not allowed here."}, status_code=422)
        if code == "23503":                                                  # FK
            log.warning("integrity violation: %s", code)
            return JSONResponse({"detail": "That change conflicts with related records."},
                                status_code=409)
        log.exception("integrity error")
        return JSONResponse({"detail": "Something went wrong."}, status_code=500)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse({"detail": "Something went wrong."}, status_code=500)
