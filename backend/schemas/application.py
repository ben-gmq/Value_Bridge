"""Slice 6b-1 request / response shapes (§9). Counts and labels are derived (VB law 6)."""
from pydantic import BaseModel, Field

from schemas.common import Orm
from schemas.scope import Name, _Patch

Note = Field(default=None, max_length=4000)
AppCode = Field(min_length=1, max_length=30)


class ApplicationIn(BaseModel):
    application_code: str = AppCode
    application_name: str = Name()
    lifecycle_code: str = Field(min_length=1, max_length=40)
    kind_code: str | None = Field(default=None, max_length=40)
    vendor: str | None = Field(default=None, max_length=200)
    version_label: str | None = Field(default=None, max_length=50)
    description: str | None = Note


class ApplicationPatch(_Patch):
    """Omit a field to leave it. `kind_code: null` clears the kind (DR6b-P3)."""
    application_code: str | None = Field(default=None, min_length=1, max_length=30)
    application_name: str | None = Name(default=None)
    lifecycle_code: str | None = Field(default=None, min_length=1, max_length=40)
    kind_code: str | None = Field(default=None, max_length=40)
    vendor: str | None = Field(default=None, max_length=200)
    version_label: str | None = Field(default=None, max_length=50)
    description: str | None = Note


class Warning_(BaseModel):
    code: str
    items: list[str] = []


class ApplicationOut(Orm):
    application_id: int
    project_id: int
    application_code: str
    application_name: str
    vendor: str | None
    version_label: str | None
    app_kind_code: str | None
    lifecycle_code: str
    description: str | None
    is_active: bool
    row_version: int
    warnings: list[Warning_] = []


class ApplicationListOut(ApplicationOut):
    live_solution_count: int = 0
    live_step_count: int = 0


class AllocationIn(BaseModel):
    application_id: int
    note: str | None = Note


class SupportIn(BaseModel):
    application_id: int
    note: str | None = Note


class LinkNotePatch(BaseModel):
    row_version: int
    note: str | None = Note


class AllocationOut(BaseModel):
    application_solution_id: int
    application_id: int
    application_code: str
    application_name: str
    lifecycle_code: str
    solution_id: int
    solution_number: str
    solution_name: str
    note: str | None
    row_version: int


class SupportOut(BaseModel):
    application_bfc_node_id: int
    application_id: int
    application_code: str
    application_name: str
    lifecycle_code: str
    bfc_node_id: int
    hier_code: str
    node_name: str
    note: str | None
    row_version: int
    warnings: list[Warning_] = []
