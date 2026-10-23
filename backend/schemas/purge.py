"""Removal requests (slice16 spec §9). The kind is a CHECK list on the table, not a code (schema §12.5); the service
refuses an unknown one with a 422 of its own."""
from pydantic import BaseModel, Field


class PurgeRequestIn(BaseModel):
    kind: str = Field(max_length=15)             # ARCHIVE or DELETE; an archive is deleted from its ARCHIVE request
    reason: str = Field(max_length=2000)
    confirm_text: str = Field(max_length=70)


class ArchiveDeletionIn(BaseModel):
    reason: str = Field(max_length=2000)
    confirm_text: str = Field(max_length=70)


class PurgeApproveIn(BaseModel):
    confirm_text: str = Field(max_length=70)
    row_version: int


class PurgeCancelIn(BaseModel):
    row_version: int
