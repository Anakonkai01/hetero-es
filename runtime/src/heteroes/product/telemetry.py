"""Best-effort host/GPU observations; never import torch or start a CUDA context."""

import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError):
        return None


def gpu_observation(uuid=None):
    fields = "uuid,name,utilization.gpu,temperature.gpu,memory.total,memory.used,power.draw,power.limit,fan.speed,clocks.current.graphics"
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=" + fields, "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=3,
        check=True,
    )
    for line in result.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 10 or (uuid and parts[0] != uuid):
            continue
        keys = [
            "utilizationPercent",
            "temperatureC",
            "vramTotalMb",
            "vramUsedMb",
            "powerDrawW",
            "powerLimitW",
            "fanPercent",
            "clockMhz",
        ]
        row = {"uuid": parts[0], "name": parts[1], **dict(zip(keys, map(number, parts[2:])))}
        # Optional queries must not discard the primary metrics on older drivers.
        try:
            extra = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=uuid,utilization.memory,clocks.current.memory,pstate,pcie.link.gen.gpucurrent,pcie.link.width.current",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )
            for extra_line in extra.stdout.splitlines():
                values = [p.strip() for p in extra_line.split(",")]
                if len(values) == 6 and values[0] == row["uuid"]:
                    row.update(
                        memoryUtilizationPercent=number(values[1]),
                        memoryClockMhz=number(values[2]),
                        performanceState=values[3][:30],
                        pcieGeneration=number(values[4]),
                        pcieWidth=number(values[5]),
                    )
            apps = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )
            processes = []
            for line in apps.stdout.splitlines():
                values = [p.strip() for p in line.split(",")]
                if len(values) == 4 and values[0] == row["uuid"] and values[1].isdigit():
                    processes.append(
                        {
                            "pid": int(values[1]),
                            "name": values[2].replace("\\", "/").rsplit("/", 1)[-1][:100],
                            "vramMb": number(values[3]),
                        }
                    )
            row["processes"] = processes[:64]
        except (OSError, subprocess.SubprocessError):
            pass
        return row
    return None


def legacy_observation(row):
    """Keep rolling updates compatible with strict pre-detail Servers."""
    host_keys = {
        "cpuCount",
        "platform",
        "cpuPercent",
        "ramTotalBytes",
        "ramUsedBytes",
        "swapTotalBytes",
        "swapUsedBytes",
        "loadAverage",
        "networkRxBytesPerSecond",
        "networkTxBytesPerSecond",
        "diskReadBytesPerSecond",
        "diskWriteBytesPerSecond",
    }
    gpu_keys = {
        "uuid",
        "name",
        "utilizationPercent",
        "temperatureC",
        "vramTotalMb",
        "vramUsedMb",
        "powerDrawW",
        "powerLimitW",
        "fanPercent",
        "clockMhz",
        "energyWh",
        "energySampledSeconds",
    }
    result = {key: value for key, value in row.items() if key not in ("power", "availability")}
    for key, allowed in [("host", host_keys), ("gpu", gpu_keys)]:
        if key in result:
            result[key] = {name: value for name, value in result[key].items() if name in allowed}
    return result


class TelemetrySampler:
    def __init__(self, state_directory, storage_directory=None, gpu_uuid=None, energy_directory=None):
        self.state_directory = Path(state_directory)
        self.storage_directory = Path(storage_directory) if storage_directory else None
        self.gpu_uuid = gpu_uuid
        self.cpu_previous = None
        self.io_previous = None
        self.energy_previous = None
        self.energy_wh = 0.0
        self.sampled_seconds = 0.0
        self.started_at = time.time()
        from .host_detail import HostDetail
        from .power import PowerSampler

        self.detail = HostDetail()
        self.power = PowerSampler(energy_directory or self.state_directory / "energy", gpu_uuid)
        from collections import deque

        self.history = deque(maxlen=60)
        self.last = None
        self.last_tick = None

    def host(self):
        result = {"cpuCount": os.cpu_count(), "platform": platform.system().lower()}
        if platform.system() == "Linux":
            values = list(map(int, Path("/proc/stat").read_text().splitlines()[0].split()[1:9]))
            total, idle = sum(values), values[3] + values[4]
            if self.cpu_previous:
                dt, di = total - self.cpu_previous[0], idle - self.cpu_previous[1]
                if dt > 0:
                    result["cpuPercent"] = max(0, min(100, 100 * (dt - di) / dt))
            self.cpu_previous = total, idle
            memory = {
                line.split(":")[0]: int(line.split()[1]) * 1024
                for line in Path("/proc/meminfo").read_text().splitlines()
                if len(line.split()) >= 2
            }
            result.update(
                ramTotalBytes=memory["MemTotal"],
                ramUsedBytes=memory["MemTotal"] - memory.get("MemAvailable", memory.get("MemFree", 0)),
                swapTotalBytes=memory.get("SwapTotal"),
                swapUsedBytes=memory.get("SwapTotal", 0) - memory.get("SwapFree", 0),
            )
            result["loadAverage"] = list(os.getloadavg())
            result.update(self.detail.sample())
            rx = tx = read = written = 0
            for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
                name, data = line.split(":", 1)
                if name.strip() == "lo":
                    continue
                parts = data.split()
                rx += int(parts[0])
                tx += int(parts[8])
            import re

            for line in Path("/proc/diskstats").read_text().splitlines():
                parts = line.split()
                if len(parts) >= 10 and re.fullmatch(r"(?:sd[a-z]+|nvme\d+n\d+|vd[a-z]+)", parts[2]):
                    read += int(parts[5]) * 512
                    written += int(parts[9]) * 512
            tick = time.monotonic()
            counters = [rx, tx, read, written]
            if self.io_previous:
                before, old = self.io_previous
                if tick > before:
                    for key, current, previous in zip(
                        [
                            "networkRxBytesPerSecond",
                            "networkTxBytesPerSecond",
                            "diskReadBytesPerSecond",
                            "diskWriteBytesPerSecond",
                        ],
                        counters,
                        old,
                    ):
                        if current >= previous:
                            result[key] = (current - previous) / (tick - before)
            self.io_previous = tick, counters
        elif platform.system() == "Windows":
            if not hasattr(self, "windows_detail"):
                from .windows_detail import WindowsDetail

                self.windows_detail = WindowsDetail()
            result.update(self.windows_detail.sample())
        return result

    def sample(self):
        now, tick = time.time(), time.monotonic()
        if self.last_tick is not None and tick - self.last_tick < 3:
            return self.last
        row = {"sampledAt": now, "sessionStartedAt": self.started_at, "source": "host-observation", "disks": []}
        errors = []
        host_permission_denied = False
        try:
            row["host"] = self.host()
        except PermissionError:
            host_permission_denied = True
            errors.append("HOST_METRICS_UNAVAILABLE")
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            errors.append("HOST_METRICS_UNAVAILABLE")
        try:
            gpu = gpu_observation(self.gpu_uuid)
            if gpu:
                watts = gpu["powerDrawW"]
                if self.energy_previous and watts is not None:
                    before, previous_watts = self.energy_previous
                    dt = tick - before
                    if 0 < dt <= 30:
                        self.energy_wh += (previous_watts + watts) * 0.5 * dt / 3600
                        self.sampled_seconds += dt
                self.energy_previous = (tick, watts) if watts is not None else None
                gpu.update(
                    energyWh=self.energy_wh if self.sampled_seconds else None, energySampledSeconds=self.sampled_seconds
                )
                row["gpu"] = gpu
            else:
                self.energy_previous = None
                errors.append("GPU_METRICS_UNAVAILABLE")
        except (OSError, subprocess.SubprocessError):
            self.energy_previous = None
            errors.append("GPU_METRICS_UNAVAILABLE")
        for label, directory in [("state", self.state_directory), ("artifacts", self.storage_directory)]:
            if directory is None:
                continue
            # Never create a missing external mount as a side effect of monitoring.
            try:
                usage = shutil.disk_usage(directory)
                row["disks"].append(
                    {"label": label, "totalBytes": usage.total, "usedBytes": usage.used, "freeBytes": usage.free}
                )
            except OSError:
                errors.append("DISK_METRICS_UNAVAILABLE")
        row["errors"] = errors
        try:
            row["power"] = self.power.sample(row.get("gpu"), now, tick)
        except (OSError, ValueError, KeyError):
            row["errors"].append("POWER_ACCOUNTING_UNAVAILABLE")
        row["errors"] = list(dict.fromkeys(row["errors"]))[:5]
        host = row.get("host") or {}
        gpu = row.get("gpu") or {}
        missing_host = (
            "permission_denied"
            if host_permission_denied
            else ("error" if "HOST_METRICS_UNAVAILABLE" in errors else "unavailable")
        )
        availability = {}
        for key in (
            "cpuPercent",
            "ramUsedBytes",
            "networkRxBytesPerSecond",
            "networkTxBytesPerSecond",
            "diskReadBytesPerSecond",
            "diskWriteBytesPerSecond",
        ):
            if host.get(key) is None:
                status = missing_host
                if key == "cpuPercent" and self.last_tick is None and host.get("platform") == "linux":
                    status = "warming_up"
                if key.startswith("network") and host.get("networkInterfaces"):
                    status = "warming_up"
                if key.startswith("disk") and host.get("blockDevices"):
                    status = "warming_up"
                availability[key] = {"status": status}
        for key, field in (
            ("gpuUtilizationPercent", "utilizationPercent"),
            ("gpuTemperatureC", "temperatureC"),
            ("gpuPowerW", "powerDrawW"),
        ):
            if gpu.get(field) is None:
                availability[key] = {"status": "error" if "GPU_METRICS_UNAVAILABLE" in errors else "unavailable"}
        if host.get("platform") == "windows":
            # Our built-in Windows collector has ACPI zones, not a CPU package
            # temperature/power provider. Never relabel motherboard zones as CPU.
            availability["cpuPowerW"] = {"status": "unsupported"}
            availability["cpuTemperatureC"] = {"status": "unsupported"}
        row["availability"] = availability
        gpu, host = row.get("gpu", {}), row.get("host", {})
        power = row.get("power", {})
        self.history.append(
            {
                "at": now,
                "gpuPowerW": gpu.get("powerDrawW"),
                "cpuPowerW": sum(
                    c["powerW"]
                    for c in power.get("components", [])
                    if c["kind"] == "cpu-package" and c["powerW"] is not None
                )
                if any(c["kind"] == "cpu-package" and c["powerW"] is not None for c in power.get("components", []))
                else None,
                "componentPowerW": power.get("componentSubtotalW"),
                "wholeMachineW": power.get("wholeMachineW"),
                "temperatureC": gpu.get("temperatureC"),
                "gpuPercent": gpu.get("utilizationPercent"),
                "cpuPercent": host.get("cpuPercent"),
                "vramUsedMb": gpu.get("vramUsedMb"),
                "ramUsedBytes": host.get("ramUsedBytes"),
            }
        )
        self.last, self.last_tick = row, tick
        return row
