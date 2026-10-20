"""CPU-only device control. Connectivity is never evidence of process death."""

from .constants import CORE_COMMAND_KINDS, COMMAND_KINDS, DESKTOP_V3_REFERENCE

from .policies import FiniteStrict
import hashlib
import re
import uuid
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, field_validator, model_validator
from .monitor_models import Core, Interface, BlockDevice, HostProcess, GPUProcess, Sensor, Power
from .addresses import endpoint, is_private


def command_capabilities(value):
    """Missing header means the conservative agent-v2 floor; empty means none."""
    if value is None:
        return CORE_COMMAND_KINDS
    parts = value.split(",") if value else []
    if len(value) > 2048 or len(parts) > 32 or any(not re.fullmatch("[A-Z][A-Z0-9_]{0,63}", p.strip()) for p in parts):
        raise HTTPException(422, "Invalid agent command capabilities")
    return frozenset(p.strip() for p in parts) & COMMAND_KINDS


def re_checkpoint(name):
    return re.fullmatch(r"[a-f0-9]{64}\.bin", name)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class SelfTest(FiniteStrict):
    passed: bool
    coordinator: bool = False
    gpuName: str = Field(max_length=200)
    vramTotalMb: int = Field(ge=1, le=1000000)
    noiseVersion: Literal["numpy_pcg64_normal_f32_to_f16_v1"]
    environment: dict = Field(default_factory=dict)
    platform: Literal["linux", "windows"] = "linux"
    runtimeProfile: str = Field(default="legacy", max_length=100)
    compatibility: dict = Field(default_factory=dict)
    gpuUUID: str | None = None
    recipeVersions: list[Literal[1, 2, 3]] = Field(default_factory=lambda: [1], max_length=3)
    qualifiedModelHashes: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("gpuUUID")
    @classmethod
    def physical_gpu(cls, value):
        if value is None:
            return value
        if not value.startswith("GPU-"):
            raise ValueError("Use the NVIDIA physical GPU UUID")
        try:
            return "GPU-" + str(uuid.UUID(value[4:]))
        except (ValueError, AttributeError):
            raise ValueError("Invalid physical GPU UUID") from None

    @model_validator(mode="after")
    def native_admission(self):
        if any(not re.fullmatch("[a-f0-9]{64}", h) for h in self.qualifiedModelHashes):
            raise ValueError("Invalid model qualification hash")
        if 3 in self.recipeVersions and self.recipeVersions != [3]:
            raise ValueError("Recipe v3 devices advertise only v3")
        for version in (2, 3):
            if version not in self.recipeVersions:
                continue
            evidence = self.compatibility.get(f"recipeV{version}", {})
            if not self.passed or evidence.get("passed") is not True or evidence.get("repeatIdentical") is not True:
                raise ValueError(f"Recipe v{version} requires repeated numerical compatibility evidence")
            if (
                any(
                    not re.fullmatch("[a-f0-9]{64}", str(evidence.get(k, "")))
                    for k in (
                        "modelManifestHash",
                        "recipeHash",
                        "parentSha256",
                        "restoredSha256",
                        "perturbedSha256",
                        "outputsHash",
                    )
                )
                or evidence["parentSha256"] != evidence["restoredSha256"]
            ):
                raise ValueError(f"Recipe v{version} compatibility identity or exact restore mismatch")
            if evidence["modelManifestHash"] not in self.qualifiedModelHashes:
                raise ValueError(f"Recipe v{version} model qualification missing")
        if self.platform == "windows" and self.runtimeProfile == "desktop-v3":
            self._native_windows_v3()
        elif self.platform == "windows":
            if self.recipeVersions != [1] or self.qualifiedModelHashes:
                raise ValueError("Windows remains the qualified v1 worker-only profile")
            if (
                not self.passed
                or self.coordinator
                or self.runtimeProfile != "desktop-v1"
                or self.compatibility.get("passed") is not True
                or self.compatibility.get("repeatIdentical") is not True
            ):
                raise ValueError("Native Windows requires the qualified worker-only desktop profile")
            for key in ("recipeHash", "parentSha256", "perturbedSha256", "restoredSha256"):
                if not re.fullmatch(r"[a-f0-9]{64}", str(self.compatibility.get(key, ""))):
                    raise ValueError("Missing native compatibility evidence")
            if self.compatibility["parentSha256"] != self.compatibility["restoredSha256"]:
                raise ValueError("Native candidate restore mismatch")
            if (
                self.compatibility.get("predictionProbePassed") is not True
                or self.compatibility.get("probeOutputsSha256")
                != "5601ce2d20cc290f9dd8d84ff3988b15a4191fb02411a2e72805af66bf5e31b4"
            ):
                raise ValueError("Native Windows requires the Linux prediction probe")
            reference = {
                "recipeHash": "efc1ff67c1bfa8c243ba93ce4a46dfcea74e5afc4b2daffa50498510d53dbc86",
                "parentSha256": "c9118c8a4903c0a84700deeaf7b1929c354dfcf6d6805c08d9afb22cfd5d22c7",
                "perturbedSha256": "d3e35e5984684a4f76c7ec2eeba10ff8afe0483721582c52013a06e5819a9c2c",
                "restoredSha256": "c9118c8a4903c0a84700deeaf7b1929c354dfcf6d6805c08d9afb22cfd5d22c7",
                "reward": 0.1875,
            }
            if any(self.compatibility.get(k) != value for k, value in reference.items()):
                raise ValueError("Native profile does not match the qualified Linux reference")
        return self

    def _native_windows_v3(self):
        """Worker-only Recipe v3 on native Windows: both reference cells, the pinned adapter, PEFT and model."""
        reference = DESKTOP_V3_REFERENCE
        compatibility = self.compatibility
        if (
            self.recipeVersions != [3]
            or self.coordinator
            or self.qualifiedModelHashes != [reference["modelManifestHash"]]
            or compatibility.get("passed") is not True
            or compatibility.get("repeatIdentical") is not True
            or compatibility.get("initialAdapterSha256") != reference["initialAdapterSha256"]
            or compatibility.get("peftVersion") != reference["peftVersion"]
        ):
            raise ValueError("Native Windows v3 requires the worker-only desktop-v3 reference profile")
        for cell in ("recipeV3", "recipeV3Lora"):
            evidence = compatibility.get(cell)
            if (
                not isinstance(evidence, dict)
                or evidence.get("passed") is not True
                or evidence.get("repeatIdentical") is not True
                or evidence.get("parentSha256") != evidence.get("restoredSha256")
                or evidence.get("modelManifestHash") != reference["modelManifestHash"]
                or any(evidence.get(key) != value for key, value in reference[cell].items())
            ):
                raise ValueError("Native Windows v3 evidence does not match the shipped reference")


class EndpointUpdate(FiniteStrict):
    computeUrl: str
    bulkUrl: str | None = None

    @field_validator("computeUrl")
    @classmethod
    def control(cls, value):
        return endpoint(value)

    @field_validator("bulkUrl")
    @classmethod
    def bulk(cls, value):
        return endpoint(value, private=True) if value is not None else None

    @model_validator(mode="after")
    def private_bulk_required(self):
        if self.bulkUrl is None and not is_private(self.computeUrl):
            raise ValueError("Public compute requires a private bulkUrl")
        return self


class DeviceConfigurationUpdate(EndpointUpdate):
    selfTest: SelfTest


class QualificationUpdate(FiniteStrict):
    bootId: str
    selfTest: SelfTest


class Enrollment(EndpointUpdate):
    code: str = Field(max_length=200)
    workerId: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    displayName: str = Field(min_length=1, max_length=100)
    selfTest: SelfTest

    @staticmethod
    def private_compute(value):
        # Kept strict for Server bootstrap and LocalBackend signed URLs.
        return endpoint(value, private=True)


class Approval(FiniteStrict):
    approved: bool
    workspaceId: str | None = None


class Contribution(FiniteStrict):
    enabled: bool
    bootId: str = Field(min_length=1, max_length=100)


class ProcessReport(FiniteStrict):
    assignmentId: str
    epoch: int = Field(ge=1)
    coordinatorAlive: bool | None = None
    workerAlive: bool | None = None
    ready: bool = False
    recoveryIndex: int = Field(default=0, ge=0, le=1)
    events: list[dict] = Field(default_factory=list, max_length=200)


class Report(FiniteStrict):
    sequence: int = Field(ge=1)
    assignmentId: str
    epoch: int = Field(ge=1)
    snapshot: dict


class MonitoringEvent(FiniteStrict):
    eventId: str
    assignmentId: str
    epoch: int = Field(ge=1)
    event: dict


class GPUObservation(FiniteStrict):
    uuid: str = Field(max_length=100)
    name: str = Field(max_length=200)
    utilizationPercent: float | None = Field(default=None, ge=0, le=100)
    temperatureC: float | None = Field(default=None, ge=0, le=200)
    vramTotalMb: float | None = Field(default=None, ge=0, le=1000000)
    vramUsedMb: float | None = Field(default=None, ge=0, le=1000000)
    powerDrawW: float | None = Field(default=None, ge=0, le=10000)
    powerLimitW: float | None = Field(default=None, ge=0, le=10000)
    fanPercent: float | None = Field(default=None, ge=0, le=100)
    clockMhz: float | None = Field(default=None, ge=0, le=100000)
    memoryUtilizationPercent: float | None = Field(default=None, ge=0, le=100)
    memoryClockMhz: float | None = Field(default=None, ge=0, le=100000)
    performanceState: str | None = Field(default=None, max_length=30)
    pcieGeneration: float | None = Field(default=None, ge=0, le=100)
    pcieWidth: float | None = Field(default=None, ge=0, le=100)
    processes: list[GPUProcess] = Field(default_factory=list, max_length=64)
    energyWh: float | None = Field(default=None, ge=0)
    energySampledSeconds: float = Field(default=0, ge=0)


class HostObservation(FiniteStrict):
    uptimeSeconds: float | None = Field(default=None, ge=0)
    cpuModel: str | None = Field(default=None, max_length=200)
    cores: list[Core] = Field(default_factory=list, max_length=512)
    networkInterfaces: list[Interface] = Field(default_factory=list, max_length=32)
    blockDevices: list[BlockDevice] = Field(default_factory=list, max_length=32)
    processes: list[HostProcess] = Field(default_factory=list, max_length=20)
    sensors: list[Sensor] = Field(default_factory=list, max_length=128)
    processCount: int | None = Field(default=None, ge=0)
    ramAvailableBytes: int | None = Field(default=None, ge=0)
    ramCachedBytes: int | None = Field(default=None, ge=0)
    ramBuffersBytes: int | None = Field(default=None, ge=0)
    ramDirtyBytes: int | None = Field(default=None, ge=0)
    cpuCount: int | None = Field(default=None, ge=1, le=100000)
    platform: str = Field(max_length=30)
    cpuPercent: float | None = Field(default=None, ge=0, le=100)
    ramTotalBytes: int | None = Field(default=None, ge=0)
    ramUsedBytes: int | None = Field(default=None, ge=0)
    swapTotalBytes: int | None = Field(default=None, ge=0)
    swapUsedBytes: int | None = Field(default=None, ge=0)
    networkRxBytesPerSecond: float | None = Field(default=None, ge=0)
    networkTxBytesPerSecond: float | None = Field(default=None, ge=0)
    diskReadBytesPerSecond: float | None = Field(default=None, ge=0)
    diskWriteBytesPerSecond: float | None = Field(default=None, ge=0)
    loadAverage: list[float] = Field(default_factory=list, max_length=3)


class DiskObservation(FiniteStrict):
    label: Literal["state", "artifacts"]
    totalBytes: int = Field(ge=0)
    usedBytes: int = Field(ge=0)
    freeBytes: int = Field(ge=0)


class TransportObservation(FiniteStrict):
    latencyMs: float | None = Field(default=None, ge=0)
    pendingReports: int = Field(default=0, ge=0)
    pendingEvents: int = Field(default=0, ge=0)


class Telemetry(FiniteStrict):
    power: Power | None = None
    transport: TransportObservation | None = None
    sampledAt: float = Field(ge=0)
    sessionStartedAt: float = Field(ge=0)
    source: Literal["host-observation"]
    host: HostObservation | None = None
    gpu: GPUObservation | None = None
    disks: list[DiskObservation] = Field(default_factory=list, max_length=2)
    errors: list[str] = Field(default_factory=list, max_length=5)


class ModelQualificationReport(FiniteStrict):
    jobId: str = Field(pattern="^[a-f0-9]{32}$")
    status: Literal["PREPARING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
    processAlive: bool | None = Field(default=None, strict=True)
    reference: dict | None = None
    observations: dict | None = None
    errorCode: str | None = Field(default=None, max_length=100, pattern="^[A-Z][A-Z0-9_]+$")


class Poll(FiniteStrict):
    telemetry: Telemetry | None = None
    bootId: str = Field(min_length=1, max_length=100)
    contribution: bool = False
    processes: list[ProcessReport] = Field(default_factory=list, max_length=10)
    reports: list[Report] = Field(default_factory=list, max_length=20)
    events: list[MonitoringEvent] = Field(default_factory=list, max_length=500)
    acknowledgements: list[str] = Field(default_factory=list, max_length=100)
    selfTest: SelfTest | None = None
    qualificationReports: list[ModelQualificationReport] = Field(default_factory=list, max_length=10)


class WorkerCommand(FiniteStrict):
    assignmentId: str
    epoch: int = Field(ge=1)
    workerId: str
    action: Literal["start", "poll", "stop", "probe"]
    recoveryIndex: int = Field(default=0, ge=0, le=1)
