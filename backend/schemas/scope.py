"""Slice 1 request / response shapes. Derived values — numbers, level_no, seq_no, hier_code,
direction, raci_behaviour, fk_group_no, created_by — appear only in *Out models (VB law 6)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

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
    pass


class ProcessOut(BaseModel):
    node: BfcNodeOut
    business_requirement: BrOut | None


class BrPatch(_Patch):
    br_statement: str | None = Field(default=None, max_length=8000)
    business_logic: str | None = Field(default=None, max_length=8000)
    output_expectation: str | None = Field(default=None, max_length=8000)
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


class ScopeSummaryOut(BaseModel):
    """The project dashboard's scope figures per level-1 area (services/scope_summary.py)."""
    areas: list[ScopeAreaOut]
    totals: ScopeTotalsOut
