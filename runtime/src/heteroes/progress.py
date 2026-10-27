"""
Stage progress of the work this worker process is computing (D11, ADR-012): counted units, read by the heartbeat thread.

A heartbeat proves that a worker can still talk to the coordinator; it does not prove that the GPU is getting anywhere.
The executor and the evaluation loop call `advance(stage)` after each finished step (perturb, one generate() chunk,
restore). The heartbeat sends the current (stage, units) when the coordinator asks for it; the coordinator counts a
heartbeat as progress only when the units grew. Units only ever increase within a process.
"""

import threading

STAGES = ("perturb", "rollout", "restore", "delivery")


class Progress:
    def __init__(self):
        self._lock = threading.Lock()
        self.stage, self.units = None, 0

    def advance(self, stage):
        if stage not in STAGES:
            raise ValueError(f"unknown progress stage {stage!r}")
        with self._lock:
            self.stage, self.units = stage, self.units + 1

    def snapshot(self):
        with self._lock:
            return self.stage, self.units


CURRENT = Progress()


def advance(stage):
    CURRENT.advance(stage)
