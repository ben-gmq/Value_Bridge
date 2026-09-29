"""Every model is imported here, and alembic/env.py imports this package — a model that is
not listed here is invisible to autogenerate (FTC-PC landmine 5)."""
from models.base import Base  # noqa: F401
from models.bfc import ExternalEntity  # noqa: F401
from models.client_org import OrgRole, OrgUnit  # noqa: F401
from models.data_model import DataEntity, DataField  # noqa: F401
from models.identity import AppUser, AuditEvent, UserAccessGrant  # noqa: F401
from models.shared import CodeMaster, ProjectSequence  # noqa: F401
from models.tenancy import Client, Program, Project  # noqa: F401
