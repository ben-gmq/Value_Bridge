"""Slice 6a request / response shapes (§9). fr_number, the type's behaviour, complexity and
effort_days are derived and appear only in *Out models (VB law 6)."""
from decimal import Decimal

from pydantic import BaseModel, Field

from schemas.common import Orm
from schemas.scope import Name, _Patch

Note = Field(default=None, max_length=4000)
CodeField = Field(min_length=1, max_length=40)


class FrIn(BaseModel):
    fr_name: str = Name()
    fr_type_code: str = CodeField
    solution_id: int | None = None
    description: str | None = Note
    acceptance_note: str | None = Note


class FrPatch(_Patch):
    """Omit a field to leave it; `solution_id: null` unlinks (D-28)."""
    fr_name: str | None = Name(default=None)
    fr_type_code: str | None = Field(default=None, min_length=1, max_length=40)
    fulfilment_status_code: str | None = Field(default=None, min_length=1, max_length=40)
    solution_id: int | None = None
    description: str | None = Note
    acceptance_note: str | None = Note


class FrOut(Orm):
    fr_id: int
    project_id: int
    fr_number: str
    fr_name: str
    description: str | None
    acceptance_note: str | None
    solution_id: int | None
    fr_type_code: str
    fr_type_behaviour: str
    complexity_code: str | None
    effort_days: Decimal | None
    fulfilment_status_code: str
    is_active: bool
    row_version: int
    warnings: list[str] = []          # D-28 and friends: never errors


class BrFrOut(BaseModel):
    """One row of v_br_function_requirement, with names: an FR serving a BR through a solution."""
    fr_id: int
    fr_number: str
    fr_name: str
    fr_type_code: str
    fr_type_behaviour: str
    solution_id: int
    solution_number: str
    solution_name: str
