"""Value Bridge API. Auth at the root (/auth), everything else under one /api/v1 prefix set
here — routers declare only their own sub-paths (FTC-PC pattern)."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers import admin, auth, bulk, process_flow, projects, scope
from routers.guards import GuardedRouter
from services import errors
from services.body_limit import BodyLimitMiddleware

logging.basicConfig(level=logging.INFO)
settings = get_settings()          # refuses to start without the required env (§9.1)

_docs = settings.enable_api_docs
app = FastAPI(title="Value Bridge API", version="0.1.0",
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
api.include_router(scope.router)
api.include_router(process_flow.router)
api.include_router(bulk.router)

app.include_router(auth.router)
app.include_router(api)
