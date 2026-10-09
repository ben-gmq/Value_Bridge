"""Slice 5 request / response shapes (§9). solution_number, project_id and status on create are
derived and appear only in *Out models (VB law 6, DR1-S2)."""
from pydantic import BaseModel, Field

from schemas.common import Orm
from schemas.scope import Name, _Patch

Note = Field(default=None, max_length=4000)


class SolutionIn(BaseModel):
    solution_name: str = Name()
    category_code: str = Field(min_length=1, max_length=40)
    description: str | None = Note
    benefit_note: str | None = Note
    effort_note: str | None = Note


class SolutionPatch(_Patch):
    solution_name: str | None = Name(default=None)
    category_code: str | None = Field(default=None, min_length=1, max_length=40)
    status_code: str | None = Field(default=None, min_length=1, max_length=40)
    description: str | None = Note
    benefit_note: str | None = Note
    effort_note: str | None = Note


class SolutionOut(Orm):
    solution_id: int
    project_id: int
    solution_number: str
    solution_name: str
    description: str | None
    category_code: str
    status_code: str
    benefit_note: str | None
    effort_note: str | None
    is_active: bool
    row_version: int


class SolutionListOut(SolutionOut):
    live_br_count: int = 0


class BrSolutionIn(BaseModel):
    solution_id: int
    coverage_note: str | None = Note


class BrSolutionPatch(BaseModel):
    row_version: int
    coverage_note: str | None = Note


class _LinkOut(BaseModel):
    br_solution_id: int
    br_id: int
    solution_id: int
    coverage_note: str | None
    row_version: int


class BrSolutionOut(_LinkOut):
    """A link seen from its BR: the solution it names, with that solution's status (S5-2)."""
    solution_number: str
    solution_name: str
    category_code: str
    status_code: str


class SolutionBrOut(_LinkOut):
    """A link seen from its solution: the BR and the step it belongs to."""
    br_number: str
    hier_code: str
    node_name: str
