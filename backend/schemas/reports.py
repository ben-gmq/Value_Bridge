"""Slice 1f report shapes (docs/slice1f_spec.md §3). Responses only — the reports take no body. A part whose component
is off is None, never an empty list (A1)."""
from pydantic import BaseModel


class SolutionRef(BaseModel):
    solution_id: int
    solution_number: str
    solution_name: str
    category_code: str | None
    status_code: str | None


class ApplicationRef(BaseModel):
    application_code: str
    application_name: str


class _FrTag(BaseModel):
    fr_id: int
    fr_number: str
    fr_name: str
    fulfilment_status_code: str | None
    solution: SolutionRef | None
    applications: list[ApplicationRef] | None
    tag_answers_br: bool | None          # None: no tag, untraced, or SOLUTION off
    rejected_solution: bool | None


class TraceRow(_FrTag):
    hier_code: str
    step_name: str
    br_id: int
    br_number: str
    br_statement: str | None


class TraceGroup(BaseModel):
    fr_type_code: str
    fr_type_label: str
    behaviour: str
    rows: list[TraceRow]


class AnsweredWithoutSoftware(SolutionRef):
    br_numbers: list[str]


class TraceabilityOut(BaseModel):
    generated_at: str
    groups: list[TraceGroup] | None
    untraced: list[_FrTag] | None
    answered_without_software: list[AnsweredWithoutSoftware] | None


class CoverageLine(BaseModel):
    """One gap kind (spec §3.2). A row's keys depend on the kind: the ids and numbers of the BR, FR, solution, flow
    or data entity it names."""
    code: str
    severity: str                         # warning | information
    rows: list[dict[str, str | int | None]] | None


class CoverageOut(BaseModel):
    generated_at: str
    lines: list[CoverageLine]


class CategoryRef(BaseModel):
    code: str
    label: str


class MatrixCell(BaseModel):
    solutions: int
    brs: int


class MatrixRow(BaseModel):
    bfc_node_id: int
    hier_code: str
    area_name: str
    cells: dict[str, MatrixCell]          # keyed by category code, every category present
    total: MatrixCell                      # a solution counted once per row


class SolutionMatrixOut(BaseModel):
    generated_at: str
    categories: list[CategoryRef] | None
    rows: list[MatrixRow] | None
    unlinked: dict[str, MatrixCell] | None
    totals: dict[str, int] | None
    live_count: int | None                # live non-REJECTED solutions: the share's denominator (Q7)
    rejected_count: int | None
    technology_share: float | None        # None also when there is no live solution
