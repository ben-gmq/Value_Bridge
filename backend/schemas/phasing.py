"""Slice 15 request / response shapes (docs/slice15_phasing_spec.md §4, §10). Shown to people as "Wave" (W-1); the
names here stay `phase`. Derived values never come in (law 6): no seq_no on create, no effort, no totals."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from schemas.common import Orm
from schemas.scope import Name, _Patch

PhaseCode = Field(min_length=1, max_length=20)
CodeIn = Field(min_length=1, max_length=40)


class PhaseIn(BaseModel):
    """The new wave goes to the end of the order."""
    phase_code: str = PhaseCode
    phase_name: str = Name()
    start_date: date | None = None
    end_date: date | None = None
    status_code: str = CodeIn


class PhasePatch(_Patch):
    """Omit a field to leave it; `start_date: null` clears a date."""
    phase_code: str | None = Field(default=None, min_length=1, max_length=20)
    phase_name: str | None = Name(default=None)
    start_date: date | None = None
    end_date: date | None = None
    status_code: str | None = Field(default=None, min_length=1, max_length=40)


class PhaseOut(Orm):
    phase_id: int
    project_id: int
    phase_code: str
    phase_name: str
    seq_no: int
    start_date: date | None
    end_date: date | None
    status_code: str | None
    is_active: bool
    row_version: int


class Versioned(BaseModel):
    id: int
    row_version: int


class ReorderIn(BaseModel):
    """Every live wave of the project exactly once, in the new order."""
    order: list[Versioned]


class SplitBasis(BaseModel):
    solution_phase_id: int
    row_version: int


class SplitRow(BaseModel):
    phase_id: int
    portion_pct: Decimal


class SplitIn(BaseModel):
    """T1: `based_on` is every live row the split was read from (the lost-update guard); `rows` is the new split,
    one row per wave, totalling exactly 100 or empty (W-5)."""
    based_on: list[SplitBasis]
    rows: list[SplitRow]


class SplitRowOut(BaseModel):
    solution_phase_id: int
    phase_id: int
    phase_code: str
    phase_name: str
    phase_status_code: str | None
    seq_no: int
    portion_pct: Decimal
    row_version: int


class SplitOut(BaseModel):
    solution_id: int
    rows: list[SplitRowOut]


class DependencyIn(BaseModel):
    depends_on_solution_id: int
    note: str | None = Field(default=None, max_length=2000)


class DependencyOut(BaseModel):
    solution_dependency_id: int
    solution_id: int
    solution_number: str
    depends_on_solution_id: int
    depends_on_solution_number: str
    depends_on_solution_name: str
    note: str | None
    is_active: bool
    row_version: int


class DependenciesOut(BaseModel):
    """What this solution needs, and what needs it (read-only)."""
    depends_on: list[DependencyOut]
    needed_by: list[DependencyOut]


class PlanSolution(BaseModel):
    solution_id: int
    solution_number: str
    solution_name: str
    portion_pct: Decimal | None
    days: Decimal                        # rounded so a line's solutions add up to the line (R6)


class PlanLine(BaseModel):
    """kind WAVE (one per live wave, in order), then UNPHASED, then UNASSIGNED; together the effort headline."""
    kind: str
    phase_id: int | None = None
    phase_code: str | None = None
    phase_name: str | None = None
    seq_no: int | None = None
    status_code: str | None = None
    cancelled: bool = False
    start_date: date | None = None
    end_date: date | None = None
    days: Decimal                        # rounded so the lines add up to total_shown (R6)
    solutions: list[PlanSolution]


class PlanWarning(BaseModel):
    kind: str                            # PREREQ_LATER, PREREQ_SAME_WAVE, PREREQ_UNSCHEDULED, REJECTED_WITH_SPLIT
    solution_number: str
    depends_on_solution_number: str | None


class PlanOut(BaseModel):
    total_days: Decimal
    total_shown: Decimal
    unrated_count: int
    current_phase_id: int | None
    lines: list[PlanLine]
    warnings: list[PlanWarning]
