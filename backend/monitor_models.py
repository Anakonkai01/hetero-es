"""Bounded observations, not control commands or per-job billing."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Core(Observation):
    id: str = Field(max_length=30)
    utilizationPercent: float | None = Field(default=None, ge=0, le=100)
    clockMhz: float | None = Field(default=None, ge=0, le=100000)

class Interface(Observation):
    name: str = Field(max_length=100)
    state: str | None = Field(default=None, max_length=30)
    rxBytes: int = Field(ge=0)
    txBytes: int = Field(ge=0)
    rxBytesPerSecond: float | None = Field(default=None, ge=0)
    txBytesPerSecond: float | None = Field(default=None, ge=0)
    speedMbps: int | None = Field(default=None, ge=0)

class BlockDevice(Observation):
    name: str = Field(max_length=100)
    readBytes: int = Field(ge=0)
    writtenBytes: int = Field(ge=0)
    inFlight: int = Field(ge=0)
    readBytesPerSecond: float | None = Field(default=None, ge=0)
    writeBytesPerSecond: float | None = Field(default=None, ge=0)
    busyPercent: float | None = Field(default=None, ge=0, le=100)

class HostProcess(Observation):
    pid: int = Field(ge=1)
    name: str = Field(max_length=100)
    state: str = Field(max_length=10)
    cpuPercent: float | None = Field(default=None, ge=0)
    ramBytes: int = Field(ge=0)
    threads: int = Field(ge=0)

class GPUProcess(Observation):
    pid: int = Field(ge=1)
    name: str = Field(max_length=100)
    vramMb: float | None = Field(default=None, ge=0)

class Sensor(Observation):
    id: str = Field(max_length=150)
    group: str = Field(max_length=100)
    label: str = Field(max_length=100)
    kind: Literal['temperature','fan','voltage','power']
    value: float
    unit: Literal['°C','RPM','V','W']

class Energy(Observation):
    sessionWh: float = Field(ge=0)
    todayWh: float = Field(ge=0)
    monthWh: float = Field(ge=0)
    lifetimeWh: float = Field(ge=0)
    sessionSampledSeconds: float = Field(ge=0)
    sampledSeconds: float = Field(ge=0)
    todaySampledSeconds: float = Field(ge=0)
    monthSampledSeconds: float = Field(ge=0)
    since: float | None = Field(default=None, ge=0)
    day: str = Field(max_length=10)
    month: str = Field(max_length=7)
    timezone: str = Field(max_length=100)

class PowerComponent(Observation):
    id: str = Field(max_length=200)
    label: str = Field(max_length=100)
    kind: Literal['cpu-package','cpu-domain','dram','gpu','wall']
    powerW: float | None = Field(default=None, ge=0, le=100000)
    includedInSubtotal: bool
    method: Literal['rapl-counter','sampled-gpu','external-meter','unavailable']
    energy: Energy

class Power(Observation):
    hostId: str = Field(min_length=32, max_length=32, pattern='^[a-f0-9]{32}$')
    components: list[PowerComponent] = Field(max_length=66)
    componentSubtotalW: float | None = Field(default=None, ge=0)
    wholeMachineW: float | None = Field(default=None, ge=0)
    wholeMachineSource: str | None = Field(default=None, max_length=100)
    wholeMachineUnavailableReason: str | None = Field(default=None, max_length=100)
    cpuUnavailableReason: str | None = Field(default=None, max_length=100)
