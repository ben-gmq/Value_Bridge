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


class GapStep(BaseModel):
    bfc_node_id: int
    hier_code: str
    node_name: str


class GapApplication(BaseModel):
    application_id: int
    application_code: str
    application_name: str


class GapRow(BaseModel):
    area_code: str
    area_name: str
    step: GapStep
    application: GapApplication


class GapByToBe(BaseModel):
    step: GapStep
    application: GapApplication


class GapUnmatched(BaseModel):
    chart: str
    hier_code: str
    name: str
    reason: str                          # ONLY_AS_IS / ONLY_TO_BE / CODE_SAME_NAME_DIFFERS / NAME_ELSEWHERE
    other_code: str | None


class GapCounts(BaseModel):
    as_is_processes: int
    support_links: int
    to_be_allocations: int


class ApplicationGapOut(BaseModel):
    """§3.4: per system inside each matched area (RP-1). Every part is None with APPLICATION, AS_IS or SOLUTION off."""
    generated_at: str
    level: int
    counts: GapCounts | None             # the inputs, so an empty project never reads "no gap" (D3)
    unallocated: list[GapRow] | None
    unsupported: list[GapRow] | None
    retiring: list[GapApplication] | None
    as_is_support_by_to_be: list[GapByToBe] | None
    unmatched: list[GapUnmatched] | None


class PrintStampOut(BaseModel):
    """§3.6: what every printed page carries (D-42). generated_at is the report response's own time (P3)."""
    report: str
    project_code: str
    project_name: str
    is_live: bool
    generated_at: str
    generated_at_text: str                 # the same ICT text the Excel stamp prints
    generated_by: str
    filters: str | None
