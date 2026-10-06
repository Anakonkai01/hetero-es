"""
The coordinator's side of the worker protocol (ADR-002, decision 10).

`WorkerAPI.handle(operation, request)` takes a request and returns a reply, both plain JSON values: a network layer only
has to carry them (the HTTP code of the next step will do `reply = api.handle(route, json.loads(body))`). The ledger stays
the coordinator's private memory; workers never see it, only these messages.

    lease           {"worker_id"}                                          -> {"generation_state", "work": {...} | null}
    submit_result   {"descriptor", "attempt_number", "token", "reward"}    -> {"outcome": "COMMITTED" | "ALREADY_COMMITTED"}
    report_failure  {"descriptor", "attempt_number", "token", "kind"}      -> {}

A reply is {"ok": true, ...} or {"ok": false, "error": {"code", "message"}}. The codes are stable: `ERROR_CODES` for what the
ledger refuses, plus "bad_request" (a request that is not shaped as above; nothing was changed) and "unknown_operation".
The coordinator, not the worker, decides which candidate a worker gets and for how long.
"""
import math
import threading

from heteroes.dispatch import Greedy
from heteroes.ledger import (
    AlreadyLeasedError,
    ConflictingResultError,
    ConflictingUpdateError,
    FailureKind,
    GenerationFailedError,
    GenerationNotCompleteError,
    GenerationState,
    LedgerError,
    RecordMismatchError,
    ResultMismatchError,
    RetriesExhaustedError,
    StaleAttemptError,
    WorkerQuarantinedError,
)
from heteroes.manifest import CandidateDescriptor

ERROR_CODES = {
    LedgerError: "rejected",
    AlreadyLeasedError: "already_leased",
    RetriesExhaustedError: "retries_exhausted",
    StaleAttemptError: "stale_attempt",
    ResultMismatchError: "result_mismatch",
    ConflictingResultError: "conflicting_result",
    GenerationFailedError: "generation_failed",
    GenerationNotCompleteError: "generation_not_complete",
    WorkerQuarantinedError: "worker_quarantined",
    RecordMismatchError: "record_mismatch",
    ConflictingUpdateError: "conflicting_update",
}


def _code_of(error: LedgerError) -> str:
    return next(ERROR_CODES[cls] for cls in type(error).__mro__ if cls in ERROR_CODES)


def _error(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message}}


def _fields(request, names: set) -> None:
    if not isinstance(request, dict):
        raise TypeError(f"the request must be a JSON object, got {type(request).__name__}")
    if set(request) != names:
        raise ValueError(f"expected exactly the fields {sorted(names)}, got {sorted(request)}")


def _text(name: str, value) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, got {type(value).__name__}")
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _integer(name: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
    return value


def _finite_number(name: str, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value}")
    return value


def _decode_lease(request) -> str:
    _fields(request, {"worker_id"})
    return _text("worker_id", request["worker_id"])


def _decode_attempt(request, last: str):
    _fields(request, {"descriptor", "attempt_number", "token", last})
    return (CandidateDescriptor.from_dict(request["descriptor"]),
            _integer("attempt_number", request["attempt_number"]),
            _text("token", request["token"]))


def _decode_result(request):
    descriptor, attempt_number, token = _decode_attempt(request, "reward")
    return descriptor, attempt_number, token, _finite_number("reward", request["reward"])


def _decode_failure(request):
    descriptor, attempt_number, token = _decode_attempt(request, "kind")
    return descriptor, attempt_number, token, FailureKind(_text("kind", request["kind"]))


class WorkerAPI:
    """
    Serves the workers of ONE generation. `lease_seconds` is the coordinator's choice, not the worker's, and so is the
    candidate: `policy` (default: greedy, B3; see `heteroes.dispatch`) picks it. Requests are served one at a time (a lock),
    so that "pick a candidate, then lease it" cannot be interleaved with another worker's request.
    """

    def __init__(self, ledger, experiment_id: str, generation: int, lease_seconds: float, policy=None):
        self._ledger = ledger
        self._experiment_id = experiment_id
        self._generation = generation
        self._lease_seconds = lease_seconds
        self._policy = Greedy() if policy is None else policy
        self._lock = threading.Lock()
        self._operations = {
            "lease": (_decode_lease, self._lease),
            "submit_result": (_decode_result, self._submit_result),
            "report_failure": (_decode_failure, self._report_failure),
        }

    def handle(self, operation, request) -> dict:
        entry = self._operations.get(operation) if isinstance(operation, str) else None
        if entry is None:
            return _error("unknown_operation", f"unknown operation {operation!r}")
        decode, act = entry
        try:
            decoded = decode(request)
        except (TypeError, ValueError) as error:
            return _error("bad_request", f"{type(error).__name__}: {error}")
        with self._lock:
            try:
                return {"ok": True, **act(decoded)}
            except LedgerError as error:
                return _error(_code_of(error), str(error))

    def _lease(self, worker_id: str) -> dict:
        if any(entry.worker_id == worker_id for entry in self._ledger.list_quarantined()):
            raise WorkerQuarantinedError(f"worker {worker_id} is quarantined (a restore failed)")
        state = self._ledger.get_generation_status(self._experiment_id, self._generation).state
        if state is GenerationState.OPEN:
            chosen = self._policy.pick(self._ledger.list_candidates(self._experiment_id, self._generation), worker_id)
            if chosen is not None:
                candidate_id = chosen.descriptor.candidate_id
                lease = self._ledger.lease(candidate_id, worker_id, self._lease_seconds)
                self._policy.leased(candidate_id, worker_id)
                return {"generation_state": state.value, "work": {
                    "descriptor": chosen.descriptor.to_dict(), "attempt_number": lease.attempt_number,
                    "token": lease.token, "deadline": lease.deadline}}
        return {"generation_state": state.value, "work": None}

    def _submit_result(self, decoded) -> dict:
        descriptor, attempt_number, token, reward = decoded
        return {"outcome": self._ledger.submit_result(descriptor, attempt_number, token, reward).value}

    def _report_failure(self, decoded) -> dict:
        descriptor, attempt_number, token, kind = decoded
        self._ledger.report_failure(descriptor, attempt_number, token, kind)
        return {}
