"""Shared error handling (playbook §7). The backend always answers with a `detail` string."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

log = logging.getLogger("vb")

CONFLICT = "Updated by another user. Please refresh."


def install(app: FastAPI) -> None:
    @app.exception_handler(StaleDataError)
    async def _stale(_: Request, __: StaleDataError):
        return JSONResponse({"detail": CONFLICT}, status_code=409)            # D-6

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError):
        code = getattr(exc.orig, "sqlstate", None)
        if code == "23505":                                                  # unique violation
            return JSONResponse({"detail": "That already exists. Refresh and check the "
                                           "existing record."}, status_code=409)   # P10
        if code in ("23503", "23514"):                                       # FK / CHECK
            log.warning("integrity violation: %s", code)
            return JSONResponse({"detail": "That change conflicts with related records."},
                                status_code=409)
        log.exception("integrity error")
        return JSONResponse({"detail": "Something went wrong."}, status_code=500)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse({"detail": "Something went wrong."}, status_code=500)
