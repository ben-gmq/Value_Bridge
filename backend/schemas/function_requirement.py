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
    br_id: int | None = None          # slice10b Q-20: create and link to this BR in one transaction
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


class EffortChange(BaseModel):
    previous_days: Decimal | None = None
    new_days: Decimal | None = None


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
    br_count: int = 0                 # slice10b §6.10: live BR links
    # D-28 and friends: never errors. Plain codes, or D-52 drift as {"code", "frs": ["FR-0007"]}.
    warnings: list[str | dict] = []
    effort_change: EffortChange | None = None   # DR6c-P2: set when a type change moved effort_days


class DriftWarning(BaseModel):
    """slice10b §2.2: a warning naming the FRs an action affected — never an error, never a write."""
    code: str
    frs: list[str]


class BrFrOut(BaseModel):
    """One live BR ↔ FR link (D-52, slice10b §6.2): the link, the FR, and the FR's solution tag (may be none)."""
    br_function_requirement_id: int
    row_version: int
    coverage_note: str | None
    br_id: int
    fr_id: int
    fr_number: str
    fr_name: str
    fr_type_code: str
    fr_type_behaviour: str
    fr_row_version: int
    solution_id: int | None
    solution_number: str | None
    solution_name: str | None
    tag_answers_this_br: bool
    warnings: list[DriftWarning] = []


class BrFrIn(BaseModel):
    fr_id: int
    coverage_note: str | None = Note


class BrFrPatch(BaseModel):
    row_version: int
    coverage_note: str | None = Note


class BrFrSolutionIn(BaseModel):
    """`solution_id: null` clears the tag. The FR's row_version, since the tag is the FR's column."""
    solution_id: int | None                 # required: send null to clear
    fr_row_version: int


class WarningsOut(BaseModel):
    warnings: list[DriftWarning] = []


class FrBrOut(BaseModel):
    """One live BR an FR serves (the FR page's traceability)."""
    br_function_requirement_id: int
    row_version: int
    coverage_note: str | None
    br_id: int
    br_number: str
    hier_code: str
    node_name: str
    tag_answers_br: bool
