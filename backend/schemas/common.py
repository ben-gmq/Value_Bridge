"""Pydantic schemas. *In = request, *Out = response. No response model carries password_hash."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Email = Field(max_length=254)


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth / users ----
class LoginIn(BaseModel):
    email: str = Email
    password: str = Field(max_length=200)
    remember_me: bool = False


class SetupIn(BaseModel):
    email: str = Email
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=10, max_length=200)


class UserOut(Orm):
    app_user_id: int
    email: str
    display_name: str
    is_active: bool
    is_platform_admin: bool
    user_kind: str                   # D-40: USER (edit) / VIEWER (read only)
    last_login_at: datetime | None
    row_version: int


UserKind = Literal["USER", "VIEWER"]


class UserIn(BaseModel):
    email: str = Email
    display_name: str = Field(min_length=1, max_length=200)
    initial_password: str = Field(min_length=10, max_length=200)
    user_kind: UserKind                              # required, no API default (§8.2)


class UserKindIn(BaseModel):
    user_kind: UserKind
    row_version: int


class PlatformAdminIn(BaseModel):
    is_platform_admin: bool
    rationale: str = Field(min_length=1, max_length=500)
    row_version: int
    user_kind: UserKind | None = None                # required when removing admin rights (DR7-S6)


class MeOut(BaseModel):
    user: UserOut
    scope: str                        # PLATFORM_ADMIN / STAFF (D-40)
    user_kind: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- clients / programs / projects ----
class ClientIn(BaseModel):
    client_code: str = Field(min_length=1, max_length=30)
    client_name: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=100)


class ClientOut(Orm):
    client_id: int
    client_code: str
    client_name: str
    industry: str | None


class ProgramIn(BaseModel):
    client_id: int
    program_code: str = Field(min_length=1, max_length=30)
    program_name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ProgramOut(Orm):
    program_id: int
    client_id: int
    program_code: str
    program_name: str
    description: str | None
    row_version: int


DfdElement = Literal["STARTED", "DATA_IN", "DATA_OUT", "EXTERNAL", "ORDER"]     # D-70: services/dfd_rule.ELEMENTS


class ProjectIn(BaseModel):
    client_id: int
    project_code: str = Field(min_length=1, max_length=30)
    project_name: str = Field(min_length=1, max_length=200)
    program_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    # D-37: the components, closed under their dependencies (422 otherwise). The template is
    # provenance only, recorded in the audit; the UI pre-fills the list from it.
    component_codes: list[str] = Field(max_length=20)
    is_restricted: bool                  # asked with no default (§8.10 risk 1, OR-6)
    template_code: str | None = Field(default=None, max_length=40)
    data_model_depth: Literal["KEYS_ONLY", "FULL"] = "FULL"          # D-39
    # D-70 (Q-4): each chart's DFD rule; a chart left out starts with the recommended set (dfd_rule.RECOMMENDED)
    dfd_rule: dict[Literal["TO_BE", "AS_IS"], list[DfdElement]] | None = None


class ProjectPatch(BaseModel):
    row_version: int
    project_name: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("project_name")
    @classmethod
    def _not_null(cls, v):          # L5: omit the field to leave it; null is not a name
        if v is None:
            raise ValueError("project_name cannot be empty")
        return v


class ProjectOut(Orm):
    project_id: int
    client_id: int
    program_id: int | None
    project_code: str
    project_name: str
    start_date: date | None
    end_date: date | None
    data_model_depth: str
    is_restricted: bool
    working_days_per_year: int = 240                  # D-67: the FTE basis (slice 13c)
    hours_per_working_day: float = 8.0
    row_version: int
    my_access_level: str | None = None   # VIEW / EDIT / ADMIN, on the single-project read (§8.6)


class ComponentOut(BaseModel):
    code: str
    label: str
    enabled: bool
    requires: list[str]
    available: bool


class TemplateOut(BaseModel):
    code: str
    label: str
    components: list[str]


class ComponentsIn(BaseModel):
    component_codes: list[str] = Field(max_length=20)
    confirm_hash: str | None = None      # omit for the preview (OR-2: shown the list first)


class ComponentBlockerOut(BaseModel):
    component: str
    reason: str
    message: str
    by: list[str] = []
    count: int | None = None
    sample: list[str] = []


class ComponentsChangeOut(BaseModel):
    turn_on: list[str]
    added_by_dependency: list[str]
    turn_off: list[str]
    blockers: list[ComponentBlockerOut]
    confirm_hash: str
    applied: bool


# ---- the DFD rule (D-70, slice13_schema §2.5) ----
class DfdRuleChart(BaseModel):
    bfc_set_code: Literal["TO_BE", "AS_IS"]
    codes: list[DfdElement]
    rule_applies: bool                    # the chart's DFD component is on (S7-3)
    fallback: bool                        # no live rule row: the D-38 rule applies (DR13-D3)
    recommended: list[DfdElement]


class DfdRuleElement(BaseModel):
    code: DfdElement
    locked: bool                          # always required (STARTED)
    requires: list[DfdElement]            # ORDER needs DATA_IN and DATA_OUT (option A)
    per_diagram: bool                     # EXTERNAL: checked per diagram, never in a light (Q-6, Q-16)


class DfdRuleOut(BaseModel):
    project_id: int
    row_version: int                      # the project's: the one token for the whole rule
    charts: list[DfdRuleChart]
    catalogue: list[DfdRuleElement]


class DfdRulePreviewIn(BaseModel):
    model_config = {"extra": "forbid"}
    bfc_set_code: Literal["TO_BE", "AS_IS"]
    codes: list[DfdElement] = Field(max_length=5)


class DfdRulePreviewOut(BaseModel):
    bfc_set_code: str
    codes: list[DfdElement]
    current: list[DfdElement]
    rule_applies: bool
    ready: int
    partly: int
    not_ready: int
    would_block: int                      # processes the next freeze would refuse on
    would_block_diagrams: int             # diagrams with no outside party, under EXTERNAL
    preview_digest: str


class DfdRuleIn(DfdRulePreviewIn):
    row_version: int
    preview_digest: str = Field(min_length=64, max_length=64)


class DepthIn(BaseModel):
    row_version: int
    data_model_depth: Literal["KEYS_ONLY", "FULL"]


class ProgramMoveIn(BaseModel):
    project_id: int
    confirm_hash: str | None = None      # omit for the preview (R2-S3)


# ---- access ----
class MemberIn(BaseModel):
    user_id: int
    access_level: Literal["EDIT", "VIEW"]
    member_note: str | None = Field(default=None, max_length=500)


class MemberPatch(BaseModel):
    access_level: Literal["EDIT", "VIEW"]
    row_version: int


class MemberOut(BaseModel):
    project_member_id: int
    user_id: int
    display_name: str
    user_kind: str
    access_level: str
    effective_level: str                 # the lower of the kind's cap and the membership level
    member_note: str | None
    row_version: int


class KeptMemberOut(MemberOut):
    level_drops: bool = False            # DR10c-S1: restricting lowers this member's level (e.g. a USER kept at VIEW)


class MemberAddOut(MemberOut):
    warnings: list[str] = []


class PersonOut(BaseModel):
    user_id: int
    display_name: str
    user_kind: str


class EffectiveAccessOut(BaseModel):
    is_restricted: bool
    admins: list[PersonOut]
    members: list[MemberOut]
    staff: dict[str, int] | None         # counts by kind while unrestricted


class RestrictionIn(BaseModel):
    is_restricted: bool
    confirm_hash: str | None = None      # omit for the preview


class RestrictionOut(BaseModel):
    restricted: bool
    changed: bool
    loses: list[PersonOut]
    gains: list[PersonOut]
    keeps: list[KeptMemberOut]           # DR7-D2: who keeps access, and why
    confirm_hash: str
    applied: bool


class CodeOut(Orm):
    code_id: int
    category: str
    code: str
    label: str
    behaviour_code: str | None
    sort_order: int
    is_system: bool
    project_id: int | None
