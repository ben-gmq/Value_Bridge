"""DFD, completeness, performer, trigger and chart-copy shapes (D-38, D-46, D-47, D-49;
slice7_schema §9). project_id comes from the route, never the body."""
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
RuleElement = Literal["STARTED", "DATA_OUT"]     # 13a: the fixed D-38 rule; 13b widens it (sara L4)


class ProcessReadiness(BaseModel):
    light: Light
    missing: list[RuleElement]                  # rule element codes the process does not meet (13a: STARTED, DATA_OUT)


class ReadinessOut(BaseModel):
    """D-68 (slice 13a): the light per live process of one chart, against the fixed D-38 rule."""
    bfc_set_code: str
    rule_applies: bool                  # false → the chart's DFD is off: no light anywhere (S7-3)
    rule: list[str]
    processes: dict[int, ProcessReadiness]


class ProcessCompletenessOut(BaseModel):
    bfc_set_code: str
    rule_applies: bool                  # the chart's DFD component is on (S7-3)
    missing_input: list[StepRef]        # freeze-blocking while the rule applies (D-38)
    missing_output: list[StepRef]       # freeze-blocking while the rule applies (D-38)
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
    no_performer: list[StepRef]


class DfdGraphOut(BaseModel):
    scope: StepRef
    lanes: list[DfdLane]
    processes: list[DfdProcess]
    stores: list[DfdStore]
    externals: list[DfdExternal]
    triggers: list[DfdTrigger]
    flows: list[DfdFlow]
    order: list[DfdOrder]                  # derived from data, never stored (D-38)
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

