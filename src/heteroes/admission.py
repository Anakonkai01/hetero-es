"""
C1, admission (MASTER section 8): who MAY work (a hard gate on capability) and who SHOULD (a benefit prediction).

    capability_gate   a profile that does not describe this worker, this recipe, or a worker that gets the numerics right
                      is INELIGIBLE, with reason codes. Nothing can override this gate, forced admission included.
    predict_*         how long one generation takes with a set of workers, from their profiles alone (no run needed):
                      the candidates, the update on the coordinator, the synchronization of the remote workers
    decide            Admit(w) iff T(W + w) < T(W) - delta, with the mechanism in the answer; the prediction is written
                      BEFORE the benchmark and the benchmark may prove it wrong (a false decision is published, not hidden)

The model is deliberately small. A worker i takes `t_i` seconds per candidate (the median of its profile at the chunk it will
use) and, if it is remote, becomes free only after it has fetched the new weights (`sync_i`). Under B3 the next waiting candidate
goes to the first free worker; under B2 the quotas are fixed before. The generation ends when the last candidate is in, then the
coordinator updates (`update_per_candidate * N`) and publishes. What it leaves out: the polling delay of the workers, the
variation between candidates, contention for the CPU of the coordinator host. Those are what the forced-admit run measures.
"""
import heapq
from dataclasses import dataclass
from enum import Enum

from heteroes.dispatch import proportional_quotas


class AdmissionState(Enum):
    INELIGIBLE = "INELIGIBLE"
    ELIGIBLE_BUT_NOT_BENEFICIAL = "ELIGIBLE_BUT_NOT_BENEFICIAL"
    ADMITTED_LIMITED = "ADMITTED_LIMITED"       # admitted, but its safe chunk is below the reference worker's
    ADMITTED = "ADMITTED"


class Reason(Enum):
    OK = "OK"
    NOT_A_GPU = "NOT_A_GPU"
    PROFILE_KEY_MISMATCH = "PROFILE_KEY_MISMATCH"       # the profile was measured for other hardware, software, model or recipe
    DTYPE_MISMATCH = "DTYPE_MISMATCH"
    MEMORY_MARGIN = "MEMORY_MARGIN"                     # the measured peak leaves less than the required margin of the GPU
    NOISE_SELFTEST_FAILED = "NOISE_SELFTEST_FAILED"
    RESTORE_FAILED = "RESTORE_FAILED"
    NUMERICS_FAILED = "NUMERICS_FAILED"                 # not even chunk 1 reproduces the reference answers
    NOT_BENEFICIAL = "NOT_BENEFICIAL"                   # eligible, but the prediction says that it does not shorten a generation
    CHUNK_LIMITED = "CHUNK_LIMITED"                     # works with a smaller chunk than the reference worker


def capability_gate(profile: dict, expected_key: dict, min_free_fraction: float = 0.10) -> list[Reason]:
    """The reasons why this profile cannot admit its worker; an empty list means that the hard gate is passed."""
    reasons = []
    if profile["key"]["device"] != "cuda":
        reasons.append(Reason.NOT_A_GPU)
    if profile["key"] != expected_key:
        reasons.append(Reason.PROFILE_KEY_MISMATCH)
    checks = profile["checks"]
    if not checks["noise_selftest"]:
        reasons.append(Reason.NOISE_SELFTEST_FAILED)
    if not checks["restore_exact"]:
        reasons.append(Reason.RESTORE_FAILED)
    if not checks["chunk1_reproduces_reference"]:
        reasons.append(Reason.NUMERICS_FAILED)
    total, peak = profile["key"]["gpu_total_memory_bytes"], profile["peak_bytes_candidate"]
    if total is not None and peak is not None and total - peak < min_free_fraction * total:
        reasons.append(Reason.MEMORY_MARGIN)
    return reasons


@dataclass(frozen=True)
class WorkerModel:
    worker_id: str
    candidate_seconds: float        # median time of one candidate at the chunk this worker will use
    sync_seconds: float = 0.0       # 0 for the worker on the coordinator's own machine


def _check_workers(workers):
    if not workers:
        raise ValueError("no worker")
    for worker in workers:
        if not worker.candidate_seconds > 0 or worker.sync_seconds < 0:
            raise ValueError(f"bad times for {worker.worker_id}: {worker}")


def predict_candidates_seconds(policy: str, workers: list[WorkerModel], candidates: int) -> dict:
    """The seconds from the opening of the generation until its last candidate is committed, and who ran how many."""
    _check_workers(workers)
    if policy == "B3_GREEDY_DYNAMIC":
        free = [(worker.sync_seconds, worker.worker_id, worker) for worker in workers]
        heapq.heapify(free)
        jobs = {worker.worker_id: 0 for worker in workers}
        end = 0.0
        for _ in range(candidates):
            when, worker_id, worker = heapq.heappop(free)
            when += worker.candidate_seconds
            jobs[worker_id] += 1
            end = max(end, when)
            heapq.heappush(free, (when, worker_id, worker))
        return {"seconds": end, "jobs": jobs}
    if policy == "B2_STATIC_PROPORTIONAL":
        quotas = proportional_quotas(candidates, {worker.worker_id: 1.0 / worker.candidate_seconds for worker in workers})
        end = max(worker.sync_seconds + quotas[worker.worker_id] * worker.candidate_seconds
                  for worker in workers if quotas[worker.worker_id] > 0)
        return {"seconds": end, "jobs": quotas}
    raise ValueError(f"no prediction for the policy {policy!r}")


def predict_generation_seconds(policy: str, workers: list[WorkerModel], candidates: int, update_per_candidate: float,
                               publish_seconds: float, update_fixed_seconds: float = 0.0) -> dict:
    """`update_fixed_seconds`: the part of the update that does not grow with N (hashing the new weights and so on); 0 if unknown."""
    parts = predict_candidates_seconds(policy, workers, candidates)
    update = update_fixed_seconds + update_per_candidate * candidates
    return {"policy": policy, "workers": [worker.worker_id for worker in workers], "candidates_seconds": parts["seconds"],
            "jobs": parts["jobs"], "update_seconds": update, "publish_seconds": publish_seconds,
            "total_seconds": parts["seconds"] + update + publish_seconds}


@dataclass(frozen=True)
class Decision:
    worker_id: str
    state: AdmissionState
    reasons: tuple
    without: dict | None            # the prediction for the current members W
    with_worker: dict | None        # the prediction for W + w
    predicted_delta_seconds: float | None     # T(W) - T(W + w): positive means that the worker shortens a generation
    delta_threshold: float | None

    def to_dict(self) -> dict:
        return {"worker_id": self.worker_id, "state": self.state.value, "reasons": [reason.value for reason in self.reasons],
                "prediction_without": self.without, "prediction_with": self.with_worker,
                "predicted_delta_seconds": self.predicted_delta_seconds, "delta_threshold_seconds": self.delta_threshold}


def decide(candidate: WorkerModel, members: list[WorkerModel], gate_reasons: list[Reason], policy: str, candidates: int,
           update_per_candidate: float, publish_seconds: float, delta_fraction: float = 0.05, limited: bool = False,
           update_fixed_seconds: float = 0.0) -> Decision:
    """
    May `candidate` join `members`? Not if the hard gate failed. Otherwise yes iff the predicted time with it is shorter than
    without it by more than `delta_fraction` of the time without it (a margin against noise, so that a gain inside the
    run-to-run variation does not count as a benefit).
    """
    if gate_reasons:
        return Decision(candidate.worker_id, AdmissionState.INELIGIBLE, tuple(gate_reasons), None, None, None, None)
    without = predict_generation_seconds(policy, members, candidates, update_per_candidate, publish_seconds, update_fixed_seconds)
    joined = predict_generation_seconds(policy, members + [candidate], candidates, update_per_candidate, publish_seconds, update_fixed_seconds)
    delta = without["total_seconds"] - joined["total_seconds"]
    threshold = delta_fraction * without["total_seconds"]
    if delta > threshold:
        state, reasons = (AdmissionState.ADMITTED_LIMITED, (Reason.CHUNK_LIMITED,)) if limited else (AdmissionState.ADMITTED, (Reason.OK,))
    else:
        state, reasons = AdmissionState.ELIGIBLE_BUT_NOT_BENEFICIAL, (Reason.NOT_BENEFICIAL,)
    return Decision(candidate.worker_id, state, reasons, without, joined, delta, threshold)


def worker_model_from_profile(profile: dict, chunk: int, remote: bool) -> WorkerModel:
    """
    The numbers the prediction needs, taken from a profile: the median candidate time at `chunk` (which must have been timed:
    chunk 1 and the safe chunk are) and, for a remote worker, the whole synchronization (transfer + load + rehash).
    """
    times = profile["candidate_times"].get(str(chunk))
    if times is None or "total_median" not in times:
        raise ValueError(f"{profile['worker_id']}: candidates were not timed at chunk {chunk}")
    sync = 0.0
    if remote:
        if profile.get("sync") is None:
            raise ValueError(f"{profile['worker_id']}: a remote worker needs a measured synchronization")
        sync = profile["sync"]["total_seconds"]
    return WorkerModel(profile["worker_id"], times["total_median"], sync)
