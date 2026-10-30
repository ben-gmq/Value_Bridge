"""Control rules and the control panel (docs/slice_control_a_spec.md §3–§4). The PATCH body replaces every editable
field: each is required, and null clears a nullable one. comparison, agreed_at and the authors are server-set (law 6)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OwnerRef(BaseModel):
    org_role_code: str
    org_role_name: str


class ControlRuleOut(BaseModel):
    analysis_code: str
    unit: str                                  # PCT | COUNT
    comparison: str
    threshold_value: Decimal
    escalate_value: Decimal | None
    owner_org_role_id: int | None
    owner: OwnerRef | None                     # None: "Owner not named" (CT-1)
    prescribed_action: str | None
    escalation_path: str | None
    is_enabled: bool
    change_rationale: str | None
    agreed_at: datetime
    last_changed_at: datetime | None           # None: never edited — the FTC house default as copied (round 2 N2)
    last_changed_by: str | None
    row_version: int


class ControlRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold_value: Decimal = Field(max_digits=12, decimal_places=2)
    escalate_value: Decimal | None = Field(max_digits=12, decimal_places=2)
    owner_org_role_id: int | None
    prescribed_action: str | None = Field(max_length=2000)
    escalation_path: str | None = Field(max_length=2000)
    is_enabled: bool
    change_rationale: str = Field(max_length=2000)
    row_version: int


class PanelRow(ControlRuleOut):
    measured: Decimal | None
    reason: str | None                         # why NOT_MEASURED (a code the screen translates)
    figures: dict                              # the analysis' supporting numbers (e.g. added / removed days)
    verdict: str | None                        # GREEN | FLAG | ESCALATE | NOT_MEASURED; None when switched off
    off_state: str | None                      # NOT_YET_AGREED | SWITCHED_OFF; None when on (CB-5)


class Coming(BaseModel):
    analysis_code: str
    brought_by: str                            # CONTROL_B | BENEFITS | RISKS | SEED


class ControlPanelOut(BaseModel):
    generated_at: str
    rows: list[PanelRow]
    coming: list[Coming]


# ---- Control-B report tabs (docs/slice_control_b_spec.md §4) -------------------------------------------------------
class Headline(BaseModel):
    model_config = ConfigDict(extra="allow")   # the analysis' supporting figures ride beside measured / reason
    measured: Decimal | None
    reason: str | None


class VolatilityGeneration(BaseModel):
    from_label: str
    to_label: str
    churning: int


class VolatilityArea(BaseModel):
    bfc_node_id: int
    hier_code: str
    area_name: str
    in_latest: bool
    churned: list[bool]                        # one per generation, oldest first
    current_run: int


class VolatilityOut(BaseModel):
    generated_at: str
    generations: list[VolatilityGeneration]
    areas: list[VolatilityArea]
    headline: Headline


class AppRef(BaseModel):
    application_id: int
    application_code: str
    application_name: str


class EntityRef(BaseModel):
    data_entity_id: int
    de_number: str
    de_name: str


class MigrationEntity(EntityRef):
    state: str                                 # OK | NO_SOURCE | CONFLICTING
    as_is_steps: int
    sources: list[AppRef]
    targets: list[AppRef] | None               # None: SOLUTION off


class DataMigrationOut(BaseModel):
    generated_at: str
    entities: list[MigrationEntity] | None     # None: AS_IS or APPLICATION off
    new_data: list[EntityRef] | None
    retiring: list[EntityRef] | None
    headline: Headline
