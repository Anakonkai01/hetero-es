"""
The coordinator's side of the worker protocol (ADR-002, decision 10).

`WorkerAPI.handle(operation, request)` takes a request and returns a reply, both plain JSON values: a network layer only
has to carry them (the HTTP code of the next step will do `reply = api.handle(route, json.loads(body))`). The ledger stays
the coordinator's private memory; workers never see it, only these messages.

    lease           {"worker_id"[, "request_id"][, "generation"]}          -> {"generation_state", "work": {...} | null}
    submit_result   {"descriptor", "attempt_number", "token", "reward"}    -> {"outcome": "COMMITTED" | "ALREADY_COMMITTED"}
    report_failure  {"descriptor", "attempt_number", "token", "kind"}      -> {}
    heartbeat       {"descriptor", "attempt_number", "token"}              -> {"deadline"}   the lease is extended by the coordinator's lease length

A lease request that carries the `generation` of the job the worker is working on gets no work if the coordinator has moved on to
another one meanwhile (the worker read the job and asked for work in two requests; a candidate of a newer parent would have been
refused by its executor and counted as a failure). A lease request that carries a `request_id` can be repeated: the same worker asking again with the same id gets the SAME lease
(as long as that attempt is still the live one), so a reply that was lost on the way does not cost the candidate a whole lease.

A reply is {"ok": true, ...} or {"ok": false, "error": {"code", "message"}}. The codes are stable: `ERROR_CODES` for what the
ledger refuses, plus "bad_request" (a request that is not shaped as above; nothing was changed) and "unknown_operation".
The coordinator, not the worker, decides which candidate a worker gets and for how long.
"""
import math
import threading
from collections import OrderedDict

from heteroes.dispatch import Greedy
from heteroes.ledger import (
    AlreadyLeasedError,
    CandidateState,
    ConflictingResultError,
    ConflictingUpdateError,
    FailureKind,
    GenerationFailedError,
    GenerationNotCompleteError,
    GenerationState,
    LedgerBusyError,
    LedgerError,
    RecordMismatchError,
    ResultMismatchError,
    RetriesExhaustedError,
    StaleAttemptError,
    WorkerQuarantinedError,
)
from heteroes.manifest import CandidateDescriptor

MAX_REMEMBERED_REQUESTS = 256

ERROR_CODES = {
    LedgerError: "rejected",
    LedgerBusyError: "busy",
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


def _fields(request, names: set, optional: frozenset = frozenset()) -> None:
    if not isinstance(request, dict):
        raise TypeError(f"the request must be a JSON object, got {type(request).__name__}")
    if not names <= set(request) <= names | optional:
        expected = sorted(names) if not optional else f"{sorted(names)} and optionally {sorted(optional)}"
        raise ValueError(f"expected exactly the fields {expected}, got {sorted(request)}")


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


def _decode_lease(request):
    _fields(request, {"worker_id"}, frozenset({"request_id", "generation"}))
    generation = request.get("generation")
    if "generation" in request:
        generation = _integer("generation", generation)
    request_id = _text("request_id", request["request_id"]) if "request_id" in request else None
    return _text("worker_id", request["worker_id"]), request_id, generation


def _decode_attempt(request, last: str):
    _fields(request, {"descriptor", "attempt_number", "token", last})
    return (CandidateDescriptor.from_dict(request["descriptor"]),
            _integer("attempt_number", request["attempt_number"]),
            _text("token", request["token"]))


def _decode_result(request):
    descriptor, attempt_number, token = _decode_attempt(request, "reward")
    return descriptor, attempt_number, token, _finite_number("reward", request["reward"])


def _decode_heartbeat(request):
    _fields(request, {"descriptor", "attempt_number", "token"})
    return (CandidateDescriptor.from_dict(request["descriptor"]),
            _integer("attempt_number", request["attempt_number"]),
            _text("token", request["token"]))


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
        self._remembered: OrderedDict = OrderedDict()      # (worker_id, request_id) -> the work that was given, for repeated requests
        self._operations = {
            "lease": (_decode_lease, self._lease),
            "submit_result": (_decode_result, self._submit_result),
            "report_failure": (_decode_failure, self._report_failure),
            "heartbeat": (_decode_heartbeat, self._heartbeat),
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

    def _lease(self, decoded) -> dict:
        worker_id, request_id, generation = decoded
        if any(entry.worker_id == worker_id for entry in self._ledger.list_quarantined()):
            raise WorkerQuarantinedError(f"worker {worker_id} is quarantined (a restore failed)")
        if generation is not None and generation != self._generation:
            # The worker looked at the job of another generation (the coordinator moved on between its two requests): it would be
            # given a candidate of a parent it does not have. No work now; its next turn reads the new job and synchronizes.
            return {"generation_state": GenerationState.OPEN.value, "work": None}
        if request_id is not None:
            work = self._repeat(worker_id, request_id)
            if work is not None:
                return {"generation_state": GenerationState.OPEN.value, "work": work}
        state = self._ledger.get_generation_status(self._experiment_id, self._generation).state
        if state is GenerationState.OPEN:
            chosen = self._policy.pick(self._ledger.list_candidates(self._experiment_id, self._generation), worker_id)
            if chosen is not None:
                candidate_id = chosen.descriptor.candidate_id
                lease = self._ledger.lease(candidate_id, worker_id, self._lease_seconds)
                self._policy.leased(candidate_id, worker_id)
                work = {"descriptor": chosen.descriptor.to_dict(), "attempt_number": lease.attempt_number,
                        "token": lease.token, "deadline": lease.deadline}
                if request_id is not None:
                    self._remembered[(worker_id, request_id)] = work
                    while len(self._remembered) > MAX_REMEMBERED_REQUESTS:
                        self._remembered.popitem(last=False)
                return {"generation_state": state.value, "work": work}
        return {"generation_state": state.value, "work": None}

    def _repeat(self, worker_id: str, request_id: str):
        """The work given for this request before, if that attempt is still the live lease of the candidate; else None (a new request)."""
        work = self._remembered.get((worker_id, request_id))
        if work is None:
            return None
        record = self._ledger.get_candidate(CandidateDescriptor.from_dict(work["descriptor"]).candidate_id)
        if record.state is CandidateState.LEASED and record.attempts == work["attempt_number"]:
            return work
        return None

    def _heartbeat(self, decoded) -> dict:
        descriptor, attempt_number, token = decoded
        lease = self._ledger.extend_lease(descriptor, attempt_number, token, self._lease_seconds)
        return {"deadline": lease.deadline}

    def _submit_result(self, decoded) -> dict:
        descriptor, attempt_number, token, reward = decoded
        return {"outcome": self._ledger.submit_result(descriptor, attempt_number, token, reward).value}

    def _report_failure(self, decoded) -> dict:
        descriptor, attempt_number, token, kind = decoded
        self._ledger.report_failure(descriptor, attempt_number, token, kind)
        return {}
