"""Every model is imported here, and alembic/env.py imports this package — a model that is
not listed here is invisible to autogenerate (FTC-PC landmine 5)."""
from models.base import Base  # noqa: F401
from models.application import Application, ApplicationBfcNode, ApplicationSolution  # noqa: F401
from models.bfc import (  # noqa: F401
    BfcNode, BfcNodeDataEntity, BfcNodeExternalFlow, BfcNodeFlow, BfcNodeOrgRole, BfcNodeTrigger, ExternalEntity,
    ProcessTrigger,
)
from models.client_org import OrgRole, OrgUnit  # noqa: F401
from models.data_model import DataEntity, DataField  # noqa: F401
from models.diagram import DiagramLayout  # noqa: F401
from models.effort import EffortRate  # noqa: F401
from models.import_staging import ImportBatch, ImportRow  # noqa: F401
from models.function_requirement import (BrFunctionRequirement, FrInterface, FrInterfaceDataEntity,  # noqa: F401
                                         FunctionRequirement)
from models.identity import AppUser, AuditEvent, ProjectMember, UserAccessGrant  # noqa: F401
from models.requirement import (BrDataEntity, BrDataField, BrOrgRole, BrRequirementLine,  # noqa: F401
                                BrSystemFlow, BusinessRequirement)
from models.shared import CodeMaster, ProjectSequence  # noqa: F401
from models.solution import BrSolution, Solution  # noqa: F401
from models.tenancy import (Client, Program, Project, ProjectComponent, ProjectDfdRule,  # noqa: F401
                            ProjectTemplateComponent)
from models.baseline import SHADOW_TABLES, SHADOWED, Baseline  # noqa: F401,E402  last: shadows read every live table
