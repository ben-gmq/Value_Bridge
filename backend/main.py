"""Value Bridge API. Auth at the root (/auth), everything else under one /api/v1 prefix set
here — routers declare only their own sub-paths (FTC-PC pattern)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import SessionLocal
from routers import admin, auth, baselines, bulk, code_lists, issues, phasing, process_flow, projects, scope
from routers.guards import GuardedRouter
from services import errors, instance
from services.body_limit import BodyLimitMiddleware

logging.basicConfig(level=logging.INFO)
settings = get_settings()          # refuses to start without the required env (§9.1)


@asynccontextmanager
async def lifespan(_app):
    """Slice 16 (schema §3.4): refuse to serve a database whose archive identity is not this host's."""
    with SessionLocal() as db:
        instance.check_startup(db, settings.vb_instance_id)
    yield


_docs = settings.enable_api_docs
app = FastAPI(title="Value Bridge API", version="0.1.0", lifespan=lifespan,
              docs_url="/docs" if _docs else None, redoc_url=None,
              openapi_url="/openapi.json" if _docs else None)
# Added first, so CORS wraps it: a 413 still carries the CORS headers the browser needs.
app.add_middleware(BodyLimitMiddleware, default_cap=settings.max_body_bytes)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_url], allow_credentials=False,
                   allow_methods=["*"], allow_headers=["Authorization", "Content-Type", "X-VB-File-Name"],
                   expose_headers=["X-VB-Error", "Content-Disposition"])   # the 409 kind the UI reads
errors.install(app)

api = GuardedRouter(prefix="/api/v1")
api.include_router(admin.router)
api.include_router(projects.router)
api.include_router(code_lists.router)
api.include_router(scope.router)
api.include_router(issues.router)
api.include_router(phasing.router)
api.include_router(process_flow.router)
api.include_router(bulk.router)
api.include_router(baselines.router)

app.include_router(auth.router)
app.include_router(api)
