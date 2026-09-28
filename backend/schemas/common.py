"""Pydantic schemas. *In = request, *Out = response. No response model carries password_hash."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth / users ----
class LoginIn(BaseModel):
    email: str
    password: str
    remember_me: bool = False


class SetupIn(BaseModel):
    email: str
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=10, max_length=200)


class UserOut(Orm):
    app_user_id: int
    email: str
    display_name: str
    is_active: bool
    is_platform_admin: bool
    last_login_at: datetime | None


class UserIn(BaseModel):
    email: str
    display_name: str = Field(min_length=1, max_length=200)
    initial_password: str = Field(min_length=10, max_length=200)
    is_platform_admin: bool = False


class GrantOut(Orm):
    user_access_grant_id: int
    project_id: int | None
    program_id: int | None
    granted_at: datetime
    row_version: int


class MeOut(BaseModel):
    user: UserOut
    grant: GrantOut | None
    role: str | None                 # the grant's role, or None for admins / no grant
    scope: str                        # PLATFORM_ADMIN / PROJECT / PROGRAM / NONE


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


class ProjectIn(BaseModel):
    client_id: int
    project_code: str = Field(min_length=1, max_length=30)
    project_name: str = Field(min_length=1, max_length=200)
    program_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None


class ProjectPatch(BaseModel):
    row_version: int
    project_name: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None


class ProjectOut(Orm):
    project_id: int
    client_id: int
    program_id: int | None
    project_code: str
    project_name: str
    start_date: date | None
    end_date: date | None
    row_version: int


class ProgramMoveIn(BaseModel):
    project_id: int
    confirm_hash: str | None = None      # omit for the preview (R2-S3)


# ---- access ----
class GrantIn(BaseModel):
    user_id: int
    project_role_code: str
    row_version: int | None = None       # required only for a role change on the same scope


class ReassignIn(BaseModel):
    user_id: int
    project_role_code: str
    rationale: str
    project_id: int | None = None
    program_id: int | None = None


class EffectiveAccessOut(BaseModel):
    grant_id: int | None
    user_id: int
    display_name: str
    email: str
    role: str
    source: str
    program: str | None
    granted_at: datetime | None
    row_version: int | None


class CodeOut(Orm):
    code_id: int
    category: str
    code: str
    label: str
    behaviour_code: str | None
    sort_order: int
    is_system: bool
    project_id: int | None
