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


class FlowCompletenessOut(BaseModel):
    orphan_steps: list[StepRef]
    no_start: list[StepRef]
    no_end: list[StepRef]
    no_output: list[StepRef]
    no_lane: list[StepRef]
    edge_count: int
