"""Recovery request contracts shared by HTTP adapters and services."""

from pydantic import BaseModel, ConfigDict, Field


class Begin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignmentId: str
    epoch: int
    manifest: dict


class Finish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignmentId: str
    epoch: int
    pointId: str
    sha256: str
    parts: list[dict] = Field(default_factory=list, max_length=10000)
