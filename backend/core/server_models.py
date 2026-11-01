"""Bootstrap input contract; secrets are never rendered as validation diagnostics."""

from pydantic import BaseModel, ConfigDict, Field


class Bootstrap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=200)
    host: str
    port: int = Field(ge=1024, le=65535, strict=True)
    storageDirectory: str
    storageVolumeUUID: str | None = None
