"""Bounded Linux host details. Never inspect command arguments or environments."""

import os
import math
from pathlib import Path
import re
import time


def sensors(root=Path("/sys/class/hwmon")):
    rows = []
    for chip in sorted(root.glob("hwmon*")):
        try:
            name = (chip / "name").read_text().strip()
        except OSError:
            continue
        for prefix, kind, scale, unit in [
            ("temp", "temperature", 1000, "°C"),
            ("fan", "fan", 1, "RPM"),
            ("in", "voltage", 1000, "V"),
            ("power", "power", 1_000_000, "W"),
        ]:
            for file in sorted(chip.glob(prefix + "*_input")):
                try:
                    label = file.with_name(file.name.replace("_input", "_label"))
                    value = float(file.read_text()) / scale
                    if not math.isfinite(value):
                        continue
                    rows.append(
                        {
                            "id": chip.name + "/" + file.name,
                            "group": name[:100],
                            "label": (label.read_text().strip() if label.exists() else file.stem)[:100],
                            "kind": kind,
                            "value": value,
                            "unit": unit,
                        }
                    )
                except (OSError, ValueError):
                    continue
                if len(rows) >= 128:
                    return rows
    return rows


class HostDetail:
    def __init__(self, proc=Path("/proc"), sys=Path("/sys")):
        self.proc, self.sys = proc, sys
        self.cores, self.network, self.disks, self.processes = {}, {}, {}, {}
        self.tick = None

    def sample(self):
        tick = time.monotonic()
        dt = tick - self.tick if self.tick is not None else None
        result = {
            "uptimeSeconds": float((self.proc / "uptime").read_text().split()[0]),
            "cpuModel": next(
                (
                    s.split(":", 1)[1].strip()
                    for s in (self.proc / "cpuinfo").read_text().splitlines()
                    if s.startswith("model name")
                ),
                "Unknown",
            ),
            "cores": [],
            "networkInterfaces": [],
            "blockDevices": [],
            "processes": [],
            "sensors": sensors(self.sys / "class/hwmon"),
        }
        cores = {}
        for line in (self.proc / "stat").read_text().splitlines():
            data = line.split()
            if not data or not re.fullmatch(r"cpu\d+", data[0]):
                continue
            values = list(map(int, data[1:9]))
            total, idle = sum(values), values[3] + values[4]
            previous = self.cores.get(data[0])
            percent = None
            if previous and total > previous[0]:
                percent = max(0, min(100, 100 * (1 - (idle - previous[1]) / (total - previous[0]))))
            row = {"id": data[0], "utilizationPercent": percent}
            try:
                row["clockMhz"] = (
                    int((self.sys / "devices/system/cpu" / data[0] / "cpufreq/scaling_cur_freq").read_text()) / 1000
                )
            except (OSError, ValueError):
                pass
            result["cores"].append(row)
            cores[data[0]] = total, idle
        self.cores = cores
        result["cores"] = result["cores"][:512]
        memory = {
            line.split(":")[0]: int(line.split()[1]) * 1024
            for line in (self.proc / "meminfo").read_text().splitlines()
            if len(line.split()) >= 2
        }
        result.update(
            ramAvailableBytes=memory.get("MemAvailable"),
            ramCachedBytes=memory.get("Cached"),
            ramBuffersBytes=memory.get("Buffers"),
            ramDirtyBytes=memory.get("Dirty"),
        )
        network = {}
        for line in (self.proc / "net/dev").read_text().splitlines()[2:]:
            name, fields = line.split(":", 1)
            name = name.strip()
            if name == "lo":
                continue
            values = fields.split()
            rx, tx = int(values[0]), int(values[8])
            row = {"name": name, "rxBytes": rx, "txBytes": tx}
            old = self.network.get(name)
            if old and dt and dt > 0 and rx >= old[0] and tx >= old[1]:
                row.update(rxBytesPerSecond=(rx - old[0]) / dt, txBytesPerSecond=(tx - old[1]) / dt)
            try:
                row["state"] = (self.sys / "class/net" / name / "operstate").read_text().strip()
            except OSError:
                pass
            try:
                speed = int((self.sys / "class/net" / name / "speed").read_text())
                if speed > 0:
                    row["speedMbps"] = speed
            except (OSError, ValueError):
                pass
            result["networkInterfaces"].append(row)
            network[name] = rx, tx
        self.network = network
        result["networkInterfaces"] = result["networkInterfaces"][:32]
        disks = {}
        for line in (self.proc / "diskstats").read_text().splitlines():
            fields = line.split()
            if len(fields) < 14 or not re.fullmatch(r"(?:sd[a-z]+|nvme\d+n\d+|vd[a-z]+)", fields[2]):
                continue
            name, read, written, busy = fields[2], int(fields[5]) * 512, int(fields[9]) * 512, int(fields[12])
            row = {"name": name, "readBytes": read, "writtenBytes": written, "inFlight": int(fields[11])}
            old = self.disks.get(name)
            if old and dt and dt > 0 and all(a >= b for a, b in zip((read, written, busy), old)):
                row.update(
                    readBytesPerSecond=(read - old[0]) / dt,
                    writeBytesPerSecond=(written - old[1]) / dt,
                    busyPercent=min(100, (busy - old[2]) / (dt * 10)),
                )
            result["blockDevices"].append(row)
            disks[name] = read, written, busy
        self.disks = disks
        result["blockDevices"] = result["blockDevices"][:32]
        processes = {}
        rows = []
        hz = os.sysconf("SC_CLK_TCK")
        page = os.sysconf("SC_PAGE_SIZE")
        for path in self.proc.iterdir():
            if not path.name.isdigit():
                continue
            try:
                raw = (path / "stat").read_text()
                fields = raw.rsplit(")", 1)[1].split()
                name = raw[raw.index("(") + 1 : raw.rindex(")")]
                start = int(fields[19])
                cpu = int(fields[11]) + int(fields[12])
                old = self.processes.get((path.name, start))
                percent = None
                if old is not None and dt and dt > 0 and cpu >= old:
                    percent = (cpu - old) / hz / dt * 100
                rows.append(
                    {
                        "pid": int(path.name),
                        "name": name[:100],
                        "state": fields[0],
                        "cpuPercent": percent,
                        "ramBytes": max(0, int(fields[21]) * page),
                        "threads": int(fields[17]),
                    }
                )
                processes[path.name, start] = cpu
            except (OSError, ValueError, IndexError):
                continue
        self.processes = processes
        result["processCount"] = len(rows)
        result["processes"] = sorted(rows, key=lambda row: (row["cpuPercent"] or 0, row["ramBytes"]), reverse=True)[:20]
        self.tick = tick
        return result
