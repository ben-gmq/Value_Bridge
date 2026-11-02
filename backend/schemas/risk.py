"""Slice Risks request / response shapes (docs/slice_risks_spec.md §7). Derived values never come in (law 6): no
number, score, weight, status on raise or issue link — an `exposure_score` sent in a body is dropped by the model."""
from datetime import date, datetime

from pydantic import BaseModel, Field

from schemas.common import Orm
from schemas.issue import CodeIn, IssueOut, Text_
from schemas.scope import Name, _Patch

OptCode = Field(default=None, min_length=1, max_length=40)


class RiskIn(BaseModel):
    """Raise starts OPEN; the raised date defaults to today (ICT)."""
    title: str = Name()
    description: str | None = Text_
    probability_code: str = CodeIn
    impact_code: str = CodeIn
    mitigation: str | None = Text_
    owner_org_role_id: int
    raised_date: date | None = None
    target_date: date | None = None
    bfc_node_id: int | None = None
    solution_id: int | None = None
    phase_id: int | None = None


class RiskPatch(_Patch):
    """Omit a field to leave it; `null` clears an optional one. A materialised risk takes only the four links."""
    title: str | None = Name(default=None)
    description: str | None = Text_
    probability_code: str | None = OptCode
    impact_code: str | None = OptCode
    status_code: str | None = OptCode
    mitigation: str | None = Text_
    owner_org_role_id: int | None = None
    raised_date: date | None = None
    target_date: date | None = None
    bfc_node_id: int | None = None
    solution_id: int | None = None
    phase_id: int | None = None


class MaterialiseIn(BaseModel):
    """RK-4: the issue's raiser is a stakeholder chosen here; R1-1: its own optional target date."""
    row_version: int
    raised_by_stakeholder_id: int
    severity_code: str = CodeIn
    issue_type_code: str = CodeIn
    target_date: date | None = None


class RiskOut(Orm):
    risk_id: int
    project_id: int
    risk_number: str
    title: str
    description: str | None
    probability_code: str
    probability_weight: str
    impact_code: str
    impact_weight: str
    exposure_score: int
    mitigation: str | None
    owner_org_role_id: int
    status_code: str
    status_behaviour: str
    raised_date: date
    target_date: date | None
    bfc_node_id: int | None
    solution_id: int | None
    phase_id: int | None
    materialised_issue_id: int | None
    materialised_issue_number: str | None = None
    created_at: datetime
    is_active: bool
    row_version: int


class MaterialisedOut(BaseModel):
    risk: RiskOut
    issue: IssueOut
