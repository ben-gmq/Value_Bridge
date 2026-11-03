"""Slice Benefits request / response shapes (docs/slice_benefits_spec.md §6). Derived values never come in (law 6): no
number, status on create, behaviour, link total or value — a field like that sent in a body is dropped by the model."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from schemas.common import Orm
from schemas.issue import CodeIn, Text_
from schemas.scope import Name, _Patch

OptCode = Field(default=None, min_length=1, max_length=40)
Unit = Field(min_length=1, max_length=40)
Value = Field(max_digits=18, decimal_places=2)


class BenefitIn(BaseModel):
    """Create starts FORECAST (BN-3). Criterion 59: no accountable org role is a 422."""
    benefit_name: str = Name()
    description: str | None = Text_
    benefit_type_code: str = CodeIn
    measure_name: str = Name()
    measure_unit: str = Unit
    baseline_value: Decimal = Value
    target_value: Decimal = Value
    realisation_date: date | None = None
    accountable_org_role_id: int


class BenefitPatch(_Patch):
    """Omit a field to leave it; `null` clears an optional one."""
    benefit_name: str | None = Name(default=None)
    description: str | None = Text_
    benefit_type_code: str | None = OptCode
    measure_name: str | None = Name(default=None)
    measure_unit: str | None = Field(default=None, min_length=1, max_length=40)
    baseline_value: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    target_value: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    realisation_date: date | None = None
    accountable_org_role_id: int | None = None
    status_code: str | None = OptCode


class LinkIn(BaseModel):
    contribution_pct: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)


class LinkOut(BaseModel):
    benefit_solution_id: int
    benefit_id: int
    benefit_number: str
    benefit_name: str
    measure_unit: str
    solution_id: int
    solution_number: str
    solution_name: str
    solution_status_code: str | None
    solution_rejected: bool
    contribution_pct: str
    value: str
    row_version: int


class BenefitOut(Orm):
    benefit_id: int
    project_id: int
    benefit_number: str
    benefit_name: str
    description: str | None
    benefit_type_code: str
    measure_name: str
    measure_unit: str
    baseline_value: Decimal
    target_value: Decimal
    realisation_date: date | None
    accountable_org_role_id: int
    accountable_org_role_code: str | None = None
    status_code: str
    status_behaviour: str
    link_total_pct: str = "0.00"
    linked_solutions: list[str] = []
    links: list[LinkOut] = []
    created_at: datetime
    updated_at: datetime
    is_active: bool
    row_version: int
