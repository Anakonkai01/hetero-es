#!/usr/bin/env python3
"""Root-only fixed sysfs reader; publishes low-rate RAPL counters, changes no limits."""

import json
import os
from pathlib import Path
import signal
import time

ROOT = Path("/sys/class/powercap")
OUTPUT = Path("/run/heteroes-power")
running = True


def snapshot():
    domains = []
    # Do not follow arbitrary user-supplied paths or execute shell commands.
    for path in sorted(ROOT.glob("intel-rapl:*"))[:64]:
        try:
            domains.append(
                {
                    "id": path.name,
                    "name": (path / "name").read_text().strip(),
                    "energyUj": int((path / "energy_uj").read_text()),
                    "maxEnergyUj": int((path / "max_energy_range_uj").read_text()),
                }
            )
        except (OSError, ValueError):
            continue
    return {
        "sampledAt": time.time(),
        "tick": time.monotonic(),
        "bootId": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "domains": domains,
    }


def main():
    global running
    if os.geteuid() != 0:
        raise SystemExit("This fixed sensor publisher requires root; workers must remain unprivileged.")

    def stop(*_):
        global running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    OUTPUT.mkdir(mode=0o755, exist_ok=True)
    while running:
        pending = OUTPUT / "rapl.pending"
        pending.write_text(json.dumps(snapshot(), allow_nan=False))
        os.chmod(pending, 0o644)
        pending.replace(OUTPUT / "rapl.json")
        time.sleep(2)


if __name__ == "__main__":
    main()
