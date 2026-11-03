"""Slice Change requests request shapes (docs/slice_change_requests_spec.md §4). Derived values never come in (law 6):
no number, status, raiser, price, budget days or decision id — a field like that sent in a body is dropped by the
model. Responses are built by services/change_request.py (`cr_out`, `detail`)."""
from datetime import date

from pydantic import BaseModel, Field

from schemas.issue import CodeIn
from schemas.scope import Name, _Patch

LongText = Field(min_length=1, max_length=20000)
Ref = Field(default=None, min_length=1, max_length=200)


class CrIn(BaseModel):
    """Starts DRAFT. The target defaults to nothing: the screen offers the agreed baseline first."""
    title: str = Name()
    rationale: str = LongText
    origin_code: str = CodeIn
    against_baseline_id: int


class CrPatch(_Patch):
    """The target is fixed once raised (spec §1)."""
    title: str | None = Name(default=None)
    rationale: str | None = Field(default=None, min_length=1, max_length=20000)
    origin_code: str | None = Field(default=None, min_length=1, max_length=40)


class SeedIn(BaseModel):
    """Exactly one of br_id / fr_id (CR-1: the seeds are BRs and FRs only)."""
    br_id: int | None = None
    fr_id: int | None = None
    impact_type_code: str = CodeIn


class SeedsIn(_Patch):
    seeds: list[SeedIn] = Field(max_length=500)


class AnalyseIn(_Patch):
    pass


class DecideIn(_Patch):
    """APPROVED with an increase needs a cut (an approved decrease on the same baseline), a budget record, or both
    (CR-3). The budget days are computed, never sent."""
    outcome_code: str = CodeIn
    decided_on: date | None = None
    rationale: str = LongText
    alternative_rejected: str = LongText
    displaces_cr_id: int | None = None
    budget_reference: str | None = Ref
    budget_approved_by: str | None = Ref


class CorrectionIn(_Patch):
    """A decided CR's decision corrected: a superseding decision with the same outcome."""
    decided_on: date | None = None
    rationale: str = LongText
    alternative_rejected: str = LongText
