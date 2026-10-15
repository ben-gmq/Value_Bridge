"""DFD, completeness, performer, trigger and chart-copy shapes (D-38, D-46, D-47, D-49;
slice7_schema §9). project_id comes from the route, never the body."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from schemas.common import Orm

SetCode = Literal["TO_BE", "AS_IS"]


class StepRef(BaseModel):
    bfc_node_id: int
    hier_code: str
    node_name: str
    bfc_set_code: str = "TO_BE"


class TableRow(BaseModel):
    table: str
    id: int


Light = Literal["READY", "PARTIAL", "NOT_READY"]
RuleElement = Literal["STARTED", "DATA_IN", "DATA_OUT", "EXTERNAL", "ORDER"]     # D-70 (services/dfd_rule.ELEMENTS)


class ProcessReadiness(BaseModel):
    light: Light
    missing: list[RuleElement]                  # rule elements the process misses: red, blocks the freeze (Q-13)
    advised: list[RuleElement] = []             # recommended elements outside the rule it misses: yellow only


class ReadinessOut(BaseModel):
    """D-68 / D-70: the light per live process of one chart, against the chart's rule."""
    bfc_set_code: str
    rule_applies: bool                  # false → the chart's DFD is off: no light anywhere (S7-3)
    rule: list[RuleElement]
    recommended: list[RuleElement] = []
    processes: dict[int, ProcessReadiness]


class ProcessCompletenessOut(BaseModel):
    bfc_set_code: str
    rule_applies: bool                  # the chart's DFD component is on (S7-3)
    # freeze-blocking while the rule applies, one list per element of the chart's rule (D-38, D-70)
    missing_input: list[StepRef]        # STARTED
    missing_output: list[StepRef]       # DATA_OUT
    missing_data_in: list[StepRef] = []     # DATA_IN
    missing_order: list[StepRef] = []       # ORDER
    diagram_missing_external: list[StepRef] = []   # EXTERNAL: diagrams (D-54 parents) with no outside party (Q-6, Q-16)
    no_performer: list[StepRef]         # a warning only (D-46)
    step_without_br: list[StepRef]      # to-be only; a warning (SR-3)
    crud_without_io: list[int]          # br_data_entity ids — must be empty
    ext_without_io: list[int]           # bfc_node_external_flow ids — must be empty
    live_link_on_retired_step: list[TableRow]   # must be empty (docs/step_retire_spec.md §4)
    readiness: ReadinessOut             # D-68: the same predicates as missing_input / missing_output


# ---- the graph (D-21) and saved positions (D-30) ----
ObjectType = Literal["STEP", "ENTITY", "EXTERNAL", "EVENT", "TRIGGER"]   # EVENT: read-only history


class LayoutItem(BaseModel):
    object_type: ObjectType
    object_id: int
    x: float = Field(ge=-99_999_999, le=99_999_999)
    y: float = Field(ge=-99_999_999, le=99_999_999)
    w: float | None = Field(default=None, gt=0, le=99_999_999)
    h: float | None = Field(default=None, gt=0, le=99_999_999)
    collapsed: bool = False


# ---- the DFD (§9.8) ----
class DfdLane(BaseModel):
    lane_key: str                          # ORG_UNIT:12 / ORG_ROLE:7 / APPLICATION:3 / AI:<label> / UNASSIGNED
    kind: str
    ref_id: int | None
    code: str | None
    name: str | None
    unit_name: str | None = None


class DfdSystem(BaseModel):
    application_id: int
    application_code: str
    application_name: str


class DfdProcess(StepRef):
    lane_key: str
    br_number: str | None
    systems: list[DfdSystem]
    rank: int
    data_processing_desc: str | None


class DfdStore(BaseModel):
    data_entity_id: int
    de_number: str
    de_name: str


class DfdExternal(BaseModel):
    external_entity_id: int
    ext_number: str
    ext_name: str


class DfdTrigger(BaseModel):
    process_trigger_id: int
    trigger_name: str
    trigger_kind: str
    schedule_note: str | None


class DfdFlow(BaseModel):
    kind: Literal["STORE", "EXTERNAL", "TRIGGER"]
    bfc_node_id: int
    direction: Literal["I", "O"]           # the step's point of view: I = into the step
    data_entity_id: int | None
    external_entity_id: int | None
    process_trigger_id: int | None
    label: str | None                      # DE name, else flow_label, else the trigger's name
    # D-65 (13d): the ONE row behind the flow — step I/O, external flow or trigger link — so the canvas
    # can remove it through that row's existing unlink route (DR13-P3). Derived order has none.
    link_id: int
    row_version: int


class DfdOrder(BaseModel):
    from_bfc_node_id: int
    to_bfc_node_id: int
    data_entity_ids: list[int]


class DfdBoundaryRef(StepRef):
    data_entity_id: int


class DfdBoundary(BaseModel):
    in_: list[DfdBoundaryRef] = Field(alias="in")
    out: list[DfdBoundaryRef]

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class DfdCompleteness(BaseModel):
    missing_input: list[StepRef]
    missing_output: list[StepRef]
    missing_data_in: list[StepRef] = []
    missing_order: list[StepRef] = []
    no_performer: list[StepRef]
    advised: dict[int, list[RuleElement]] = {}     # recommended elements outside the rule it misses: information only


class DfdGraphOut(BaseModel):
    scope: StepRef
    lanes: list[DfdLane]
    processes: list[DfdProcess]
    stores: list[DfdStore]
    externals: list[DfdExternal]
    triggers: list[DfdTrigger]
    flows: list[DfdFlow]
    order: list[DfdOrder]                  # derived from data, never stored (D-38)
    order_source: Literal["DERIVED", "CHART"] = "DERIVED"   # CHART: no derived order, ranked in chart order (DR13-P4)
    boundary: DfdBoundary
    completeness: DfdCompleteness
    cross_area: list[int]                  # data_entity_ids, within the chart
    layout: list[LayoutItem]


# ---- the performer (D-46) and triggers (D-49) ----
PerformerKind = Literal["ORG_UNIT", "ORG_ROLE", "APPLICATION", "AI"]


class PerformerIn(BaseModel):
    row_version: int
    performer_kind: PerformerKind | None = None    # None clears it
    code: str | None = Field(default=None, max_length=40)       # org unit / org role / application code
    performer_label: str | None = Field(default=None, max_length=200)   # names an AI performer


class PerformerOut(BaseModel):
    kind: str
    code: str | None
    name: str | None
    ref_id: int | None


TriggerKind = Literal["TIME", "EVENT"]


class TriggerIn(BaseModel):
    trigger_name: str = Field(min_length=1, max_length=200)
    trigger_kind: TriggerKind
    schedule_note: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


class TriggerPatch(BaseModel):
    row_version: int
    trigger_name: str | None = Field(default=None, min_length=1, max_length=200)
    trigger_kind: TriggerKind | None = None
    schedule_note: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


class TriggerOut(Orm):
    process_trigger_id: int
    project_id: int
    trigger_name: str
    trigger_kind: str
    schedule_note: str | None
    description: str | None
    is_active: bool
    row_version: int


class StepTriggerIn(BaseModel):
    process_trigger_id: int
    note: str | None = Field(default=None, max_length=2000)


class StepTriggerOut(Orm):
    bfc_node_trigger_id: int
    bfc_node_id: int
    process_trigger_id: int
    note: str | None
    row_version: int
    trigger_row: TriggerOut


class SetCopyIn(BaseModel):
    confirm_hash: str | None = None        # omit for the preview


class SetCopyOut(BaseModel):
    from_: str = Field(alias="from")
    to: str
    nodes: int
    processes: int
    step_data: int
    external_flows: int
    triggers: int
    step_roles: int
    supporting_systems: int
    new_requirements: int
    confirm_hash: str
    applied: bool

    model_config = {"populate_by_name": True, "serialize_by_alias": True}



# ---- process volume (D-67, slice 13c) ------------------------------------------------------------------------
class VolumeIn(BaseModel):
    """PATCH /bfc-nodes/{id}/volume: a figure sent as null clears it, a figure left out keeps its value. Hours and
    FTE are derived, so a body naming them is refused (extra="forbid" → 422, law 6). Ranges, decimals and the
    pairs are checked by services/process_volume (422)."""
    model_config = {"extra": "forbid"}
    row_version: int
    runs_per_period: Decimal | None = None
    volume_period_code: str | None = Field(default=None, max_length=10)
    transactions_per_run: Decimal | None = None
    transaction_unit_code: str | None = Field(default=None, max_length=40)    # a code, never a label (C8)
    seconds_per_transaction: Decimal | None = None


class VolumeOut(BaseModel):
    bfc_node_id: int
    row_version: int
    is_process: bool
    runs_per_period: Decimal | None
    volume_period_code: str | None
    transactions_per_run: Decimal | None
    transaction_unit_code: str | None
    transaction_unit_label: str | None
    seconds_per_transaction: Decimal | None
    working_days_per_year: int
    hours_per_working_day: Decimal
    annual_hours: Decimal | None          # derived on read, never stored (law 6)
    fte: Decimal | None
    incomplete: list[str]


class FteBasisIn(BaseModel):
    model_config = {"extra": "forbid"}
    row_version: int
    working_days_per_year: int
    hours_per_working_day: Decimal


class FteBasisOut(Orm):
    project_id: int
    row_version: int
    working_days_per_year: int
    hours_per_working_day: Decimal


class AreaTotalsOut(BaseModel):
    processes: int
    complete: int
    incomplete: list[dict]
    annual_hours: Decimal
    fte: Decimal


class AreaMatchOut(BaseModel):
    hier_code: str
    as_is_name: str
    to_be_name: str
    as_is: AreaTotalsOut
    to_be: AreaTotalsOut
    saved_hours: Decimal
    saved_fte: Decimal


class AreaUnmatchedOut(BaseModel):
    chart: str
    hier_code: str
    name: str
    reason: Literal["CODE_SAME_NAME_DIFFERS", "NAME_ELSEWHERE", "ONLY_AS_IS", "ONLY_TO_BE"]
    other_code: str | None
    totals: AreaTotalsOut


class VolumeLevelOut(BaseModel):
    level: int
    matched: list[AreaMatchOut]
    unmatched: list[AreaUnmatchedOut]


class VolumeSummaryOut(BaseModel):
    working_days_per_year: int
    hours_per_working_day: Decimal
    has_as_is: bool
    levels: list[VolumeLevelOut]
