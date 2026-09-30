"""Slice 3b response shape: the logical ERD graph (§7.4 generate_erd, D-29; spec §7 3b).
Read-only; nothing here is ever accepted from a request body."""
from typing import Literal

from pydantic import BaseModel

from schemas.process_flow import LayoutItem


class ErdField(BaseModel):
    data_field_id: int
    field_name: str
    data_type_code: str | None
    is_mandatory: bool | None            # NULL = unknown (A-53)
    is_primary_key: bool
    pk_ordinal: int | None
    is_foreign_key: bool
    ref_data_entity_id: int | None
    ref_data_field_id: int | None
    fk_group_no: int | None
    ref_de_name: str | None              # the parent's name, for the FK row
    description: str | None


class ErdEntity(BaseModel):
    data_entity_id: int
    de_number: str
    de_name: str
    description: str | None
    field_count: int
    fields: list[ErdField]               # PK by pk_ordinal, then FK, then attributes (by seq_no)
    warnings: list[Literal["NO_KEY"]]


class ErdViaField(BaseModel):
    data_field_id: int
    field_name: str
    ref_data_field_id: int | None
    ref_is_key: bool                     # the parent field is a live PK row → it has a row handle


class ErdRelationship(BaseModel):
    child_data_entity_id: int
    parent_data_entity_id: int
    parent_de_number: str
    parent_de_name: str
    fk_group_no: int
    label: str                           # the FK field names, comma-joined (A-S3-3)
    via_fields: list[ErdViaField]
    parent_cardinality: Literal["1", "0..1"]
    child_cardinality: Literal["1", "many"]
    identifying: bool
    retired: bool                        # defensive only (A-S3-4)


class ErdGraphOut(BaseModel):
    scope_key: str                       # 'project' or the subject-area node id, as the layout routes take it
    entities: list[ErdEntity]
    relationships: list[ErdRelationship]
    outside_refs: list[ErdRelationship]  # stubs: the parent is outside the area (or retired)
    layout: list[LayoutItem]
