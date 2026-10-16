"""Slice 1 request / response shapes. Derived values — numbers, level_no, seq_no, hier_code,
direction, raci_behaviour, fk_group_no, created_by — appear only in *Out models (VB law 6)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.common import Orm
from schemas.process_flow import Light, RuleElement

def Name(**kw):
    return Field(min_length=1, max_length=200, **kw)


def Code(**kw):
    return Field(min_length=1, max_length=30, **kw)


Direction = Literal["I", "O"]


class _Patch(BaseModel):
    row_version: int

    @field_validator("*", mode="before")
    @classmethod
    def _no_null_names(cls, v, info):   # omit a field to leave it; null is not a name (L5)
        if v is None and info.field_name.endswith(("_name", "_code")) and info.field_name not in (
                "kind_code", "data_type_code", "level_code", "status_code"):
            raise ValueError(f"{info.field_name} cannot be empty")
        return v


# ---- BFC ----
class BfcNodeIn(BaseModel):
    parent_bfc_node_id: int | None = None
    node_name: str = Name()
    is_process: bool = False
    purpose_desc: str | None = Field(default=None, max_length=4000)
    bfc_set: Literal["TO_BE", "AS_IS"] = "TO_BE"     # a root's chart (D-47); a child takes its parent's


class BfcNodePatch(_Patch):
    node_name: str | None = Name(default=None)
    purpose_desc: str | None = Field(default=None, max_length=4000)
    data_processing_desc: str | None = Field(default=None, max_length=4000)


class ReorderIn(BaseModel):
    row_version: int
    new_seq_no: int = Field(ge=1, le=99)


class ProcessIn(BaseModel):
    row_version: int
    is_process: bool


class RowRef(BaseModel):
    table: str
    id: int
    label: str


class RetirePreviewOut(BaseModel):
    """docs/step_retire_spec.md §9: what a retire with dependents takes with it."""
    owned: list[RowRef]
    blockers: list[RowRef]
    confirm_hash: str
    # slice10b §4.2: FRs whose solution tag will answer none of their remaining BRs (information, not hashed)
    tag_drift: list[str] = []


class RetireConfirmIn(BaseModel):
    confirm_hash: str = Field(min_length=64, max_length=64)


class RestoreCountOut(BaseModel):
    restored: int


class BfcNodeOut(Orm):
    bfc_node_id: int
    project_id: int
    parent_bfc_node_id: int | None
    level_no: int
    seq_no: int
    hier_code: str
    node_name: str
    is_process: bool
    purpose_desc: str | None
    data_processing_desc: str | None
    bfc_set_code: str = "TO_BE"                      # D-47
    performer_kind: str | None = None                # D-46: ORG_UNIT / ORG_ROLE / APPLICATION / AI
    performer_org_unit_id: int | None = None
    performer_org_role_id: int | None = None
    performer_application_id: int | None = None
    performer_label: str | None = None
    is_active: bool
    row_version: int
    warnings: list[str] = []


class Stamp(Orm):
    """Who last saved the row, and when (services/stamp.py) — on single-row reads only."""
    updated_at: datetime | None = None
    updated_by_name: str | None = None


class BfcNodeDetailOut(BfcNodeOut, Stamp):
    pass


class TreeNodeOut(BfcNodeOut):
    br_number: str | None
    # D-68 (slice 13a): live process rows of a chart whose DFD is on; null elsewhere
    dfd_light: Light | None = None
    dfd_missing: list[RuleElement] | None = None
    dfd_advised: list[RuleElement] | None = None     # Q-13: recommended elements it misses (yellow, never blocking)


class BrOut(Orm):
    br_id: int
    project_id: int
    bfc_node_id: int
    br_number: str
    br_statement: str | None
    business_logic: str | None
    output_expectation: str | None
    status_code: str
    is_active: bool
    row_version: int


class BrDetailOut(BrOut, Stamp):
    priority_code: str | None = None       # D-59: derived from the live lines, never stored


# ---- requirement lines (D-59, slice11_schema §1) ----
class BrLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_kind_code: str = Field(min_length=1, max_length=40)
    priority_code: str | None = Field(default=None, max_length=40)
    line_text: str = Field(min_length=1, max_length=8000)   # sara M1: backfilled legacy text is up to 8000


class BrLinePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_version: int
    line_kind_code: str | None = Field(default=None, min_length=1, max_length=40)
    priority_code: str | None = Field(default=None, max_length=40)          # null clears it
    line_text: str | None = Field(default=None, min_length=1, max_length=8000)

    @field_validator("line_kind_code", "line_text", mode="before")
    @classmethod
    def _not_null(cls, v, info):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be empty")
        return v


class BrLineOut(Orm):
    br_requirement_line_id: int
    br_id: int
    line_no: int
    line_label: str
    seq_no: int
    line_kind_code: str
    priority_code: str | None
    line_text: str
    is_active: bool
    row_version: int


class BrLineOrderItem(BaseModel):
    br_requirement_line_id: int
    row_version: int


class BrLineOrderIn(BaseModel):
    lines: list[BrLineOrderItem] = Field(max_length=500)


class ProcessOut(BaseModel):
    node: BfcNodeOut
    business_requirement: BrOut | None


class BrPatch(_Patch):
    # D-59: the legacy business_logic / output_expectation are read-only now — sending them is a 422.
    model_config = ConfigDict(extra="forbid")
    br_statement: str | None = Field(default=None, max_length=8000)
    status_code: str | None = Field(default=None, max_length=40)


# ---- step I/O, CRUD, external flows ----
class StepIoIn(BaseModel):
    data_entity_id: int
    direction: Direction


class StepIoOut(Orm):
    bfc_node_data_entity_id: int
    bfc_node_id: int
    data_entity_id: int
    direction: str
    note: str | None
    row_version: int


class HandOffIn(BaseModel):
    """D-65 (13d): process A hands one data entity to process B. Nothing derived is accepted (VB law 6)."""
    to_bfc_node_id: int
    data_entity_id: int


class HandOffOut(BaseModel):
    output: StepIoOut                      # A's output row
    input: StepIoOut                       # B's input row
    already: bool                          # both were already live: nothing was written


class BrDataEntityIn(BaseModel):
    data_entity_id: int
    crud_code: Literal["C", "R", "U", "D"]
    usage_note: str | None = Field(default=None, max_length=2000)


class BrDataEntityOut(Orm):
    br_data_entity_id: int
    br_id: int
    data_entity_id: int
    crud_code: str
    direction: str
    usage_note: str | None
    row_version: int


# ---- system-to-system flows on a BR (D-61, slice11_schema §3) ----
class BrFlowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_entity_id: int
    source_application_id: int
    target_application_id: int
    flow_note: str | None = Field(default=None, max_length=2000)


class BrFlowPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_version: int
    flow_note: str | None = Field(max_length=2000)


class BrFlowOut(BaseModel):
    br_system_flow_id: int
    br_id: int
    data_entity_id: int
    source_application_id: int
    target_application_id: int
    flow_note: str | None
    row_version: int
    covered_by: list[str]            # derived on every read: the FR numbers that carry it (§3.1)
    info: list[str]                  # information only: flow_entity_not_used_by_br, flow_touches_as_is_only_application


class BrFlowsToFrIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flow_ids: list[int] = Field(min_length=1, max_length=200)
    fr_type_code: str = Field(min_length=1, max_length=40)        # an interface-behaviour type (S11-5)
    fr_name: str = Name()


class BrFlowsToFrOut(BaseModel):
    fr_id: int
    fr_number: str
    warnings: list[str | dict] = []      # as the FR screen's create returns them (e.g. a duplicate name)


# ---- the CRUD grid with attribute ticks (D-60b, slice11_schema §2) ----
class BrDataFieldOut(Orm):
    br_data_field_id: int
    br_id: int
    data_entity_id: int
    data_field_id: int
    crud_code: str
    usage_note: str | None
    row_version: int


class GridInfo(BaseModel):
    code: str
    data_entity_id: int
    crud_code: str


class BrGridOut(BaseModel):
    entities: list[BrDataEntityOut]
    attributes: list[BrDataFieldOut]
    info: list[GridInfo]


class GridEntityTick(BaseModel):
    data_entity_id: int
    crud_code: Literal["C", "R", "U", "D"]


class GridAttributeTick(BaseModel):
    data_field_id: int
    crud_code: Literal["C", "R", "U"]                  # Delete stays entity-level (Q-8)
    usage_note: str | None = Field(max_length=2000)    # required (null allowed): the PUT is the whole state (sara L2)


class GridKnown(BaseModel):
    table: Literal["br_data_entity", "br_data_field"]
    id: int
    row_version: int


class BrGridIn(BaseModel):
    """The whole grid as the screen leaves it, and every live row the screen was showing (`known`), so a change made
    by someone else since is a 409, never overwritten."""
    model_config = ConfigDict(extra="forbid")
    entity_ticks: list[GridEntityTick] = Field(max_length=2000)
    attribute_ticks: list[GridAttributeTick] = Field(max_length=5000)
    known: list[GridKnown] = Field(max_length=7000)

    @field_validator("entity_ticks", "attribute_ticks")
    @classmethod
    def _once_each(cls, v, info):                      # sara L3: a tick sent twice is refused, never collapsed
        keys = [(t.data_entity_id if info.field_name == "entity_ticks" else t.data_field_id, t.crud_code) for t in v]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{info.field_name}: each tick may appear once")
        return v


class ExternalFlowIn(BaseModel):
    external_entity_id: int
    direction: Direction
    data_entity_id: int | None = None
    flow_label: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class ExternalFlowOut(Orm):
    bfc_node_external_flow_id: int
    bfc_node_id: int
    external_entity_id: int
    direction: str
    data_entity_id: int | None
    flow_label: str | None
    note: str | None
    row_version: int


# ---- RACI ----
class RaciIn(BaseModel):
    org_role_id: int
    raci_code: str = Field(min_length=1, max_length=40)


class RaciOut(Orm):
    org_role_id: int
    raci_code: str
    raci_behaviour: str
    row_version: int


class StepRaciOut(RaciOut):
    bfc_node_org_role_id: int
    bfc_node_id: int


class BrRaciOut(RaciOut):
    br_org_role_id: int
    br_id: int


# ---- data entities ----
class DataEntityIn(BaseModel):
    de_name: str = Name()
    description: str | None = Field(default=None, max_length=4000)
    business_owner_note: str | None = Field(default=None, max_length=4000)


class DataEntityPatch(_Patch):
    de_name: str | None = Name(default=None)
    description: str | None = Field(default=None, max_length=4000)
    business_owner_note: str | None = Field(default=None, max_length=4000)


class DataEntityOut(Orm):
    data_entity_id: int
    project_id: int
    de_number: str
    de_name: str
    description: str | None
    business_owner_note: str | None
    is_active: bool
    row_version: int


class DataEntityListOut(DataEntityOut):
    live_field_count: int = 0        # 4a-R10: the Data page marks an entity with none "no fields yet"


class DataEntityUseOut(BaseModel):
    br_id: int
    br_number: str
    hier_code: str
    node_name: str
    crud: str                        # e.g. "RU" — letters in C, R, U, D order


class _FieldSpec(BaseModel):
    data_type_code: str | None = Field(default=None, max_length=40)
    length_val: int | None = Field(default=None, ge=1)
    precision_val: int | None = Field(default=None, ge=1)
    scale_val: int | None = Field(default=None, ge=0)
    is_mandatory: bool | None = None
    is_primary_key: bool = False
    pk_ordinal: int | None = Field(default=None, ge=1, le=32)
    ref_data_entity_id: int | None = None
    ref_data_field_id: int | None = None
    fk_group: Literal["new"] | int = "new"      # S1-7: name the relationship, never its number
    description: str | None = Field(default=None, max_length=4000)


class DataFieldIn(_FieldSpec):
    field_name: str = Name()


class DataFieldPatch(_FieldSpec):
    row_version: int
    field_name: str | None = Name(default=None)
    is_primary_key: bool | None = None


class DataFieldOut(Orm):
    data_field_id: int
    data_entity_id: int
    seq_no: int
    field_name: str
    data_type_code: str | None
    length_val: int | None
    precision_val: int | None
    scale_val: int | None
    is_mandatory: bool | None
    is_primary_key: bool
    pk_ordinal: int | None
    is_foreign_key: bool
    ref_data_entity_id: int | None
    ref_data_field_id: int | None
    fk_group_no: int | None
    description: str | None
    is_active: bool
    row_version: int


# ---- external parties ----
class ExternalEntityIn(BaseModel):
    ext_name: str = Name()
    kind_code: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=4000)


class ExternalEntityPatch(_Patch):
    ext_name: str | None = Name(default=None)
    kind_code: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=4000)


class ExternalEntityOut(Orm):
    external_entity_id: int
    project_id: int
    ext_number: str
    ext_name: str
    kind_code: str | None
    description: str | None
    is_active: bool
    row_version: int


# ---- client organisation ----
class OrgUnitIn(BaseModel):
    parent_org_unit_id: int | None = None
    org_unit_code: str = Code()
    org_unit_name: str = Name()
    level_code: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=4000)


class OrgUnitPatch(_Patch):
    org_unit_code: str | None = Code(default=None)
    org_unit_name: str | None = Name(default=None)
    level_code: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=4000)


class OrgUnitOut(Orm):
    org_unit_id: int
    project_id: int
    parent_org_unit_id: int | None
    level_no: int
    level_code: str
    org_unit_code: str
    org_unit_name: str
    seq_no: int
    description: str | None
    is_active: bool
    row_version: int


class OrgRoleIn(BaseModel):
    org_unit_id: int
    org_role_code: str = Code()
    org_role_name: str = Name()
    responsibility_desc: str | None = Field(default=None, max_length=4000)
    headcount: int | None = Field(default=None, ge=0)


class OrgRolePatch(_Patch):
    org_unit_id: int | None = None
    org_role_code: str | None = Code(default=None)
    org_role_name: str | None = Name(default=None)
    responsibility_desc: str | None = Field(default=None, max_length=4000)
    headcount: int | None = Field(default=None, ge=0)


class OrgRoleOut(Orm):
    org_role_id: int
    project_id: int
    org_unit_id: int
    org_role_code: str
    org_role_name: str
    responsibility_desc: str | None
    headcount: int | None
    is_active: bool
    row_version: int


class ScopeAreaOut(BaseModel):
    hier_code: str
    name: str
    processes: int
    brs: int
    confirmed: int
    with_fr: int
    with_solution: int
    frs: int
    effort_days: float
    not_ready_red: int = 0            # S7: to-be processes whose light is red (blocks the freeze) …
    not_ready_amber: int = 0          # … or amber (a recommended element missing)


class ScopeTotalsOut(BaseModel):
    processes: int
    brs: int
    confirmed: int
    with_fr: int
    with_solution: int
    frs: int
    frs_traced: int                   # distinct FRs reached from any area — the table's total row
    frs_without_br: int
    effort_days: float                # every live FR
    traced_effort_days: float         # distinct traced FRs — the table's total row
    untraced_effort_days: float
    # slice 12 (docs/slice12_kpis.md)
    dfd_on: bool                      # the to-be DFD rule applies; when off the S7 figures are None
    not_ready_red: int | None
    not_ready_amber: int | None
    entities_without_fields: int      # S8, whole project
    entities_keys_only: int           # S8 (FULL depth only; always 0 under KEYS_ONLY)
    freeze_errors: int                # S10: what the next freeze would refuse on (must-be-empty lines) …
    freeze_blocking: int              # … the freeze-blocking warnings (e.g. a process missing its output) …
    freeze_warnings: int              # … and the warnings that never refuse


class ScopeSummaryOut(BaseModel):
    """The project dashboard's scope figures per level-1 area (services/scope_summary.py)."""
    areas: list[ScopeAreaOut]
    totals: ScopeTotalsOut
