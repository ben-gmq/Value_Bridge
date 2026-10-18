"""Slice 14 request / response shapes (§9; docs/slice14_issue_spec.md). Derived values never come in (law 6)."""
from datetime import date, datetime

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


Text_ = Field(default=None, max_length=20000)
CodeIn = Field(min_length=1, max_length=40)


class IssueIn(BaseModel):
    """No status, number, recorder or resolution: raise starts OPEN (R2) and the rest is derived (law 6)."""
    title: str = Name()
    description: str | None = Text_
    severity_code: str = CodeIn
    issue_type_code: str = CodeIn
    raised_by_stakeholder_id: int
    raised_date: date | None = None           # I-6: defaults to today (ICT)
    target_date: date | None = None


class IssuePatch(_Patch):
    """Omit a field to leave it. status_code moves only among open statuses (R2); `target_date: null` clears it."""
    title: str | None = Name(default=None)
    description: str | None = Text_
    severity_code: str | None = Field(default=None, min_length=1, max_length=40)
    issue_type_code: str | None = Field(default=None, min_length=1, max_length=40)
    status_code: str | None = Field(default=None, min_length=1, max_length=40)
    raised_by_stakeholder_id: int | None = None
    raised_date: date | None = None
    target_date: date | None = None


class ResolveIn(BaseModel):
    row_version: int
    status_code: str = CodeIn
    resolution: str = Field(min_length=1, max_length=20000)


class ReopenIn(BaseModel):
    row_version: int


class IssueOut(Orm):
    issue_id: int
    project_id: int
    issue_number: str
    title: str
    description: str | None
    severity_code: str
    issue_type_code: str
    status_code: str
    status_behaviour: str
    raised_by_stakeholder_id: int
    recorded_by_user_id: int
    raised_date: date
    target_date: date | None
    resolution: str | None
    resolved_at: datetime | None
    resolved_by_user_id: int | None
    is_active: bool
    row_version: int
