"""Slice 2 request / response shapes for flow edges. project_id comes from the route, never
the body; the ends are create-only (S2-2)."""
from typing import Literal

from pydantic import BaseModel, Field

from schemas.common import Orm

FlowType = Literal["SEQUENCE", "CONDITIONAL", "PARALLEL", "HANDOFF"]


class ProcessFlowIn(BaseModel):
    from_bfc_node_id: int | None = None
    to_bfc_node_id: int | None = None
    flow_type: FlowType
    condition_label: str | None = Field(default=None, max_length=200)
    seq_no: int | None = Field(default=None, ge=1, le=99)
    note: str | None = Field(default=None, max_length=2000)


class ProcessFlowPatch(BaseModel):
    row_version: int
    flow_type: FlowType | None = None
    condition_label: str | None = Field(default=None, max_length=200)
    seq_no: int | None = Field(default=None, ge=1, le=99)
    note: str | None = Field(default=None, max_length=2000)


class ProcessFlowOut(Orm):
    bfc_node_flow_id: int
    project_id: int
    from_bfc_node_id: int | None
    to_bfc_node_id: int | None
    flow_type: str
    condition_label: str | None
    seq_no: int | None
    note: str | None
    row_version: int


class StepRef(BaseModel):
    bfc_node_id: int
    hier_code: str
    node_name: str


class TableRow(BaseModel):
    table: str
    id: int


class FlowCompletenessOut(BaseModel):
    orphan_steps: list[StepRef]
    no_start: list[StepRef]
    no_end: list[StepRef]
    no_output: list[StepRef]
    no_lane: list[StepRef]
    crud_without_io: list[int]          # br_data_entity ids — must be empty
    ext_without_io: list[int]           # bfc_node_external_flow ids — must be empty
    edge_count: int
    step_without_br: list[StepRef]      # a warning (SR-3): the first step of a demote
    live_link_on_retired_step: list[TableRow]   # must be empty (docs/step_retire_spec.md §4)


# ---- the graph (D-21) and saved positions (D-30) ----
ObjectType = Literal["STEP", "ENTITY", "EXTERNAL", "EVENT"]


class LayoutItem(BaseModel):
    object_type: ObjectType
    object_id: int
    x: float = Field(ge=-99_999_999, le=99_999_999)
    y: float = Field(ge=-99_999_999, le=99_999_999)
    w: float | None = Field(default=None, gt=0, le=99_999_999)
    h: float | None = Field(default=None, gt=0, le=99_999_999)
    collapsed: bool = False


class FlowBox(BaseModel):
    bfc_node_id: int
    hier_code: str
    node_name: str
    data_processing_desc: str | None
    br_number: str | None
    lane_org_role_id: int | None


class FlowEdge(BaseModel):
    bfc_node_flow_id: int
    from_bfc_node_id: int | None
    to_bfc_node_id: int | None
    flow_type: str
    condition_label: str | None
    seq_no: int | None
    row_version: int
    is_external: bool


class FlowLane(BaseModel):
    org_role_id: int
    org_role_code: str
    org_role_name: str
    org_unit_name: str | None


class FlowStore(BaseModel):
    data_entity_id: int
    de_number: str
    de_name: str
    reads: list[int]
    writes: list[int]


class FlowExternalLink(BaseModel):
    bfc_node_id: int
    direction: str
    data_entity_id: int | None
    flow_label: str | None


class FlowExternal(BaseModel):
    external_entity_id: int
    ext_number: str
    ext_name: str
    flows: list[FlowExternalLink]


class ProcessFlowGraphOut(BaseModel):
    scope: StepRef
    variant: str
    nodes: list[FlowBox]
    edges: list[FlowEdge]
    outside: list[StepRef]
    lanes: list[FlowLane]
    stores: list[FlowStore]
    externals: list[FlowExternal]
    layout: list[LayoutItem]
    can_suggest: bool                      # the suggest rule holds (docs/draft_arrows_spec.md §4)


# ---- suggest a flow's arrows: preview, then keep (docs/draft_arrows_spec.md) ----
class SuggestedArrow(BaseModel):
    from_bfc_node_id: int | None           # None = a start event
    to_bfc_node_id: int | None             # None = an end event
    flow_type: Literal["SEQUENCE"]


class SuggestOut(BaseModel):
    arrows: list[SuggestedArrow]
    confirm_hash: str


class KeepIn(BaseModel):
    """The body only confirms; the server derives the arrows again (VB law 6)."""
    confirm_hash: str = Field(min_length=64, max_length=64)


class KeepOut(BaseModel):
    created: list[int]                     # bfc_node_flow ids
    restored: list[int]


# ---- the DFD (D-31, slice 3a) ----
class DfdStore(BaseModel):
    data_entity_id: int
    de_number: str
    de_name: str


class DfdExternal(BaseModel):
    external_entity_id: int
    ext_number: str
    ext_name: str


class DfdFlow(BaseModel):
    kind: Literal["STORE", "EXTERNAL"]
    bfc_node_id: int
    direction: Literal["I", "O"]           # the step's point of view: I = into the step
    data_entity_id: int | None
    external_entity_id: int | None
    bfc_node_data_entity_id: int | None    # the source row, one of the two
    bfc_node_external_flow_id: int | None
    label: str | None                      # DE name, else flow_label, else none


class DfdGraphOut(BaseModel):
    scope: StepRef
    processes: list[StepRef]
    stores: list[DfdStore]
    externals: list[DfdExternal]
    flows: list[DfdFlow]
    cross_area: list[int]                  # data_entity_ids (A-S3-2, project-wide)
    layout: list[LayoutItem]
