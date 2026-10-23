"""Platform-admin grant requests (slice17 spec §9). Who asks and who decides come from the token (law 6); the times
are the database's."""
from pydantic import BaseModel, Field


class GrantRequestIn(BaseModel):
    reason: str = Field(max_length=2000)


class GrantDecideIn(BaseModel):
    row_version: int


class GrantRejectIn(BaseModel):
    reason: str = Field(max_length=2000)
    row_version: int
