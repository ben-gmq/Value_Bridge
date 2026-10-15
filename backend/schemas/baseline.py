"""Baselines (slice8_schema §5). The freeze and approve bodies carry no derived value (law 6): the version,
status, digest of the stored row, who froze it and when all come from the server."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class FreezeIn(BaseModel):
    note: str | None = Field(default=None, max_length=4000)
    bump: Literal["MINOR", "MAJOR"] = "MINOR"
    confirm_text: str = Field(max_length=100)
    preview_digest: str = Field(min_length=64, max_length=64)    # DR8-P2: the preview this person confirmed


class ApproveIn(BaseModel):
    client_approver_name: str = Field(min_length=1, max_length=200)
    client_approved_on: date
    approval_note: str | None = Field(default=None, max_length=4000)
    approval_reference: str | None = Field(default=None, max_length=200)
    row_version: int


class BaselineOut(BaseModel):
    baseline_id: int
    project_id: int
    version_label: str
    major_no: int
    minor_no: int
    status_code: str | None
    status_label: str | None
    hash_spec_version: int
    data_model_depth: str
    dfd_rule_to_be: list[str] | None = None          # D-70 [Q-19]: both null = frozen before 13b (the D-38 rule)
    dfd_rule_as_is: list[str] | None = None
    note: str | None
    prior_baseline_id: int | None
    frozen_at: datetime
    frozen_by: str | None
    client_approver_name: str | None
    client_approved_on: date | None
    approval_note: str | None
    approval_reference: str | None
    approved_at: datetime | None
    approved_by: str | None
    row_version: int
    is_agreed: bool = False


class BaselineDetailOut(BaselineOut):
    intact: bool
    components: list[str]
    counts: dict[str, int | None]


class FreezeOut(BaseModel):
    baseline: BaselineOut
    counts: dict[str, int | None]
    warnings: dict[str, list]
