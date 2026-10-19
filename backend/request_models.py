"""HTTP request contracts shared by route modules."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .policies import Strict


class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class BackupPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interval: int = Field(ge=1, le=1000, strict=True)
    retain: int = Field(ge=1, le=1000, strict=True)


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(min_length=3, max_length=160)
    modelName: str
    modelArtifactId: str = "qwen-pinned"
    schedulerPolicy: str = "greedy"
    syncMode: str = "synchronous"
    workerIds: list[str] = Field(min_length=1, max_length=10)
    task: str = "arith16"
    maxGenerations: int = Field(default=3, ge=1, le=1000, strict=True)
    candidatesPerGeneration: int = Field(default=8, ge=2, le=256, strict=True)
    alpha: float = Field(default=0.001, gt=0, le=1)
    sigma: float = Field(default=0.001, gt=0, le=1)
    decodeEngine: str = "hf_generate"
    datasetIds: list[str] = Field(default_factory=list)
    coordinatorDeviceId: str | None = None
    backupPolicy: dict | None = None
    recipeVersion: int = Field(default=1, ge=1, le=3, strict=True)
    batchSize: int = Field(default=32, ge=1, le=1024, strict=True)
    batchSeed: int = Field(default=11, ge=0, lt=2**53, strict=True)
    sigmaSchedule: str = "constant"
    sigmaMinimum: float = Field(default=0.00025, gt=0, le=1)
    maxNewTokens: int = Field(default=512, ge=1, le=2048, strict=True)
    weightSpace: dict = Field(default_factory=lambda: {"kind": "full"})
    antithetic: bool = Field(default=False, strict=True)
    scorer: dict | None = None
    coefficientRule: str = "zscore@1"
    # the update formula of Recipe v3 (heteroes.v3.coefficients): alpha schedule, momentum, prompts per generate() call
    alphaSchedule: str = "constant"
    alphaMinimum: float | None = Field(default=None, gt=0, le=1)
    momentumBeta: float | None = Field(default=None, gt=0, lt=1)
    momentumWindow: int = Field(default=4, ge=2, le=8, strict=True)
    evalChunk: int | None = Field(default=None, strict=True)
    systemPrompt: str | None = Field(default=None, max_length=4000)
    validationInterval: int = Field(default=1, ge=1, le=1000, strict=True)


class Registration(Strict):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    password: str = Field(max_length=200)
    displayName: str = Field(min_length=1, max_length=100)


class ProfileEdit(Strict):
    displayName: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    bio: str | None = Field(default=None, max_length=1000)


class AccountEdit(Strict):
    accountStatus: Literal["PENDING", "ACTIVE", "REJECTED", "SUSPENDED"] | None = None
    canCreateWorkspace: bool | None = None
    platformAdmin: bool | None = None


class PasswordEdit(Strict):
    currentPassword: str = Field(max_length=200)
    newPassword: str = Field(max_length=200)


class WorkspaceCreate(Strict):
    name: str = Field(min_length=3, max_length=100)
    description: str = Field(default="", max_length=1000)


class Invite(Strict):
    username: str = Field(min_length=3, max_length=64)


class MemberEdit(Strict):
    role: Literal["ADMIN", "PARTICIPANT"]


class Resume(Strict):
    workerConfigurationConfirmed: Literal[True]
