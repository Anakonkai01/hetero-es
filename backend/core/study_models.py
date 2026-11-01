"""CPU-safe study and qualification request contracts."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from heteroes.noise.contracts import ENGINE_VERSION, ENGINE_V2
from heteroes.product.model_qualification import STRICT_DECODER
from .models import FiniteStrict


class ImportData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipeVersion: int = Field(default=2, ge=2, le=3, strict=True)
    name: str = Field(min_length=1, max_length=100)
    files: dict
    mapping: dict | None = None
    adapter: str = "exact-number-v1"
    splitSeed: int = Field(default=42, ge=0, lt=2**53, strict=True)


class DatasetUpload(BaseModel):
    """A large Recipe v3 dataset: one file or three named splits, uploaded with signed requests, then built."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    files: dict


class DatasetBuild(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mapping: dict | None = None
    splitSeed: int = Field(default=42, ge=0, lt=2**53, strict=True)


class DatasetLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maxBytes: int = Field(ge=1_000_000, le=50_000_000_000, strict=True)
    maxRows: int = Field(ge=1_000, le=1_000_000_000, strict=True)


class RegisterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipeVersion: int = Field(default=2, ge=2, le=3, strict=True)
    name: str = Field(min_length=1, max_length=100)
    manifest: dict
    source: str = "REFERENCE"


class ProbeRequest(FiniteStrict):
    deviceId: str = Field(pattern="^[a-f0-9]{32}$")
    noiseEngineVersion: Literal[ENGINE_VERSION, ENGINE_V2] | None = None
    decoder: Literal["hf_generate", STRICT_DECODER] | None = None
