"""Slice 6b-2 request / response shapes (§9). The interface list is generated, never typed (D-27)."""
from pydantic import BaseModel, Field

Note = Field(default=None, max_length=4000)


class CarriedIn(BaseModel):
    """`note` omitted keeps the stored note; sent (even null) replaces it (S6b2-4)."""
    data_entity_id: int
    note: str | None = Note


class InterfaceIn(BaseModel):
    """`row_version` is the detail's (absent only when none exists yet). `carried` is required:
    `[]` means the interface carries nothing (DR6b2-D1)."""
    row_version: int | None = None
    source_application_id: int
    target_application_id: int
    pattern_code: str | None = Field(default=None, max_length=40)
    method_code: str | None = Field(default=None, max_length=40)
    frequency_code: str | None = Field(default=None, max_length=40)
    volume_note: str | None = Note
    carried: list[CarriedIn] = Field(max_length=200)


class CarriedOut(BaseModel):
    data_entity_id: int
    de_number: str
    de_name: str
    note: str | None


class InterfaceOut(BaseModel):
    described: bool
    is_active: bool
    row_version: int | None
    source_application_id: int | None = None
    target_application_id: int | None = None
    source_application_code: str | None = None
    target_application_code: str | None = None
    pattern_code: str | None = None
    method_code: str | None = None
    frequency_code: str | None = None
    volume_note: str | None = None
    carried: list[CarriedOut] = []


class ListCarried(BaseModel):
    de_number: str
    de_name: str
    note: str | None


class InterfaceRowOut(BaseModel):
    fr_id: int
    interface_number: str
    interface_name: str
    fr_type_code: str
    fr_type_label: str
    is_described: bool
    is_complete: bool
    missing: list[str]
    source_application_id: int | None
    source_application_code: str | None
    source_application_name: str | None
    target_application_id: int | None
    target_application_code: str | None
    target_application_name: str | None
    pattern_code: str | None
    pattern_label: str | None
    method_code: str | None
    method_label: str | None
    frequency_code: str | None
    frequency_label: str | None
    volume_note: str | None
    carried: list[ListCarried]
    solution_id: int | None
    solution_number: str | None
    br_numbers: list[str]
    fulfilment_status_code: str | None
    fulfilment_status_label: str | None


class InterfaceListOut(BaseModel):
    rows: list[InterfaceRowOut]
    unfilterable_incomplete: int
    generated_at: str
