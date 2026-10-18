"""Slice 14 request / response shapes (§9; docs/slice14_issue_spec.md). Derived values never come in (law 6)."""
from pydantic import BaseModel, Field

from schemas.common import Orm
from schemas.scope import Name, _Patch

Title = Field(default=None, max_length=200)


class StakeholderIn(BaseModel):
    stakeholder_name: str = Name()
    job_title: str | None = Title
    org_unit_id: int | None = None
    is_bpo: bool = False


class StakeholderPatch(_Patch):
    """Omit a field to leave it. `org_unit_id: null` takes the person out of any unit (I-2)."""
    stakeholder_name: str | None = Name(default=None)
    job_title: str | None = Title
    org_unit_id: int | None = None
    is_bpo: bool | None = None


class StakeholderOut(Orm):
    stakeholder_id: int
    project_id: int
    stakeholder_name: str
    job_title: str | None
    org_unit_id: int | None
    is_bpo: bool
    is_active: bool
    row_version: int
