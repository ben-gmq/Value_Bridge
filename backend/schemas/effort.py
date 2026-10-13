"""Slice 6c request / response shapes. effort_days is never a request field (VB law 6)."""
from decimal import Decimal

from pydantic import BaseModel, Field


class RateCellIn(BaseModel):
    fr_type_code: str = Field(min_length=1, max_length=40)
    complexity_code: str = Field(min_length=1, max_length=40)
    standard_days: Decimal                       # range, decimals and NaN checked by the service (422)
    row_version: int | None = None               # absent only for a cell that does not exist yet


class RateCardIn(BaseModel):
    change_rationale: str | None = Field(default=None, max_length=4000)
    cells: list[RateCellIn] = Field(min_length=1, max_length=200)
    confirm_high: bool = False                   # S6c-7: a rate above 60 days


class RateCellOut(BaseModel):
    fr_type_code: str
    fr_type_label: str
    complexity_code: str
    complexity_label: str
    effort_rate_id: int | None
    standard_days: Decimal | None
    row_version: int | None
    change_rationale: str | None
    unconfirmed_default: bool
    high: bool
    not_at_current_rate: int
    not_at_current_rate_days: Decimal


class CodeLabel(BaseModel):
    code: str
    label: str


class RateCardOut(BaseModel):
    types: list[CodeLabel]
    complexities: list[CodeLabel]
    cells: list[RateCellOut]


class RateChangeLine(BaseModel):
    effort_rate_id: int
    fr_type_code: str
    complexity_code: str
    from_days: str | None = Field(default=None, alias="from")
    to: str
    not_at_current_rate: int

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class RateCardChangeOut(BaseModel):
    changes: list[RateChangeLine]


class ComplexityIn(BaseModel):
    row_version: int
    complexity_code: str | None = Field(default=None, max_length=40)


class TypeTotal(BaseModel):
    fr_type_code: str
    fr_type_label: str
    count: int
    days: Decimal


class SolutionTotal(BaseModel):
    solution_id: int | None
    solution_number: str | None
    solution_name: str | None
    count: int
    days: Decimal


class CountDays(BaseModel):
    count: int
    days: Decimal


class EffortSummaryOut(BaseModel):
    total_days: Decimal
    rated_count: int
    unrated_count: int
    by_type: list[TypeTotal]
    by_solution: list[SolutionTotal]
    rejected: CountDays
    on_unconfirmed_default: int
    not_at_current_rate: CountDays
    untraced: CountDays                 # slice10b Q-18: information, never in a total
