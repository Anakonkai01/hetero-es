"""Opt-in host phase telemetry and live tensor storage inventory (ADR-012).

Host wall timings do not claim CUDA kernel time: asynchronous work can complete in a later phase.
No tensors are copied, device work synchronized or credential/exception payloads included here.
Telemetry sink/clock failures never replace the measured operation's result or exception.
"""

from contextlib import contextmanager
from itertools import chain
import math
import threading
import time


class PhaseTrace:
    def __init__(self, sink, *, clock=time.perf_counter):
        self._sink = sink
        self._clock = clock
        self._dropped = 0
        self._lock = threading.Lock()

    @property
    def dropped_events(self):
        with self._lock:
            return self._dropped

    def _drop(self):
        with self._lock:
            self._dropped += 1

    @contextmanager
    def phase(self, name, *, candidate_id, generation, recipe_hash, device):
        try:
            start = self._clock()
        except Exception:
            self._drop()
            yield
            return
        status = "error"
        try:
            yield
            status = "ok"
        finally:
            try:
                elapsed = self._clock() - start
                if not math.isfinite(elapsed) or elapsed < 0:
                    self._drop()
                else:
                    self._sink(
                        {
                            "formatVersion": 1,
                            "event": "phase_timing",
                            "phase": name,
                            "wallSeconds": elapsed,
                            "status": status,
                            "timingKind": "host_wall",
                            "candidateId": candidate_id,
                            "generation": generation,
                            "recipeHash": recipe_hash,
                            "device": device,
                        }
                    )
            except Exception:
                self._drop()


def storage_inventory(models):
    """Unique backing storage for named live roles, including buffers and shared views.

    Counts the physical storage once across parameters, buffers and roles, without materializing data.
    This is not process peak memory: allocator reserve, temporaries, snapshots and other processes are absent.
    Meta tensors have unknown physical storage and are refused rather than counted as zero.
    """

    def summarize(storages):
        devices = {}
        for device, _pointer, size in storages:
            totals = devices.setdefault(device, {"storageBytes": 0, "storages": 0})
            totals["storageBytes"] += size
            totals["storages"] += 1
        return dict(sorted(devices.items()))

    roles, unique = {}, set()
    for name, model in models.items():
        storages = set()
        for tensor in chain(model.parameters(), model.buffers()):
            if tensor.device.type == "meta":
                raise ValueError("A meta tensor has no measured physical storage")
            storage = tensor.untyped_storage()
            size = storage.nbytes()
            if size:
                storages.add((str(tensor.device), storage.data_ptr(), size))
        roles[name] = summarize(storages)
        unique.update(storages)
    return {"formatVersion": 1, "roles": roles, "unique": summarize(unique)}
