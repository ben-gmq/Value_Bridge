"""Slice Decisions request / response shapes (docs/slice_decisions_spec.md §7). Derived values never come in (law 6):
no number, recorder or created time — a `created_by` or `decision_number` sent in a body is dropped by the model."""
from datetime import date, datetime

from pydantic import BaseModel, Field

from schemas.common import Orm
from schemas.issue import CodeIn
from schemas.scope import Name

LongText = Field(min_length=1, max_length=20000)


class DecisionIn(BaseModel):
    """The decided-on date defaults to today (ICT). `supersedes_decision_id` makes it a correction (DC-2)."""
    title: str = Name()
    decision_text: str = LongText
    alternative_rejected: str = LongText
    dimension_code: str = CodeIn
    decided_on: date | None = None
    analysis_code: str | None = Field(default=None, max_length=40)
    supersedes_decision_id: int | None = None


class DecisionOut(Orm):
    decision_id: int
    project_id: int
    decision_number: str
    title: str
    decision_text: str
    alternative_rejected: str
    dimension_code: str
    analysis_code: str | None
    decided_on: date
    decided_by_user_id: int
    decided_by_name: str | None = None
    supersedes_decision_id: int | None
    supersedes_number: str | None = None
    superseded_by_id: int | None = None
    superseded_by_number: str | None = None
    created_at: datetime
