"""
The coordinator's side of the worker protocol (ADR-002, decision 10).

`WorkerAPI.handle(operation, request)` takes a request and returns a reply, both plain JSON values: a network layer only
has to carry them (the HTTP code of the next step will do `reply = api.handle(route, json.loads(body))`). The ledger stays
the coordinator's private memory; workers never see it, only these messages.

    lease           {"worker_id"[, "request_id"][, "generation"]}          -> {"generation_state", "work": {...} | null}
    submit_result   {"descriptor", "attempt_number", "token", "reward"}    -> {"outcome": "COMMITTED" | "ALREADY_COMMITTED"}
                    Recipe v3 (ADR-008): {"descriptor", "attempt_number", "token", "completions", "completions_sha256"}
                    instead; the coordinator scores the texts (a WorkerAPI built with a scorer accepts only this form).
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
    SubmitOutcome,
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


class ScoringFailedError(LedgerError):
    """The coordinator could not score submitted texts (Recipe v3): the experiment's fault, not the worker's."""


ERROR_CODES[ScoringFailedError] = "scorer_failed"


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


def _decode_attempt(request, *last: str):
    _fields(request, {"descriptor", "attempt_number", "token", *last})
    return (
        CandidateDescriptor.from_dict(request["descriptor"]),
        _integer("attempt_number", request["attempt_number"]),
        _text("token", request["token"]),
    )


def _decode_result(request):
    if isinstance(request, dict) and "completions" in request:
        extra = ("usage",) if "usage" in request else ()
        descriptor, attempt_number, token = _decode_attempt(request, "completions", "completions_sha256", *extra)
        completions = request["completions"]
        if not isinstance(completions, list) or not completions or not all(isinstance(t, str) for t in completions):
            raise TypeError("completions must be a nonempty list of texts")
        if completions_sha256(completions) != request["completions_sha256"]:
            raise ValueError("completions_sha256 is not the hash of the completions")
        if extra:
            from heteroes.v3.usage import UsageTexts

            completions = UsageTexts(completions, request["usage"])
        return descriptor, attempt_number, token, completions
    descriptor, attempt_number, token = _decode_attempt(request, "reward")
    return descriptor, attempt_number, token, _finite_number("reward", request["reward"])


def completions_sha256(completions) -> str:
    """The identity of a list of texts: SHA-256 of their canonical JSON (the same hash the ledger stores)."""
    import hashlib

    from heteroes.canonical import canonical_json_bytes

    return hashlib.sha256(canonical_json_bytes(list(completions))).hexdigest()


def _decode_heartbeat(request):
    _fields(request, {"descriptor", "attempt_number", "token"})
    return (
        CandidateDescriptor.from_dict(request["descriptor"]),
        _integer("attempt_number", request["attempt_number"]),
        _text("token", request["token"]),
    )


def _decode_failure(request):
    descriptor, attempt_number, token = _decode_attempt(request, "kind")
    return descriptor, attempt_number, token, FailureKind(_text("kind", request["kind"]))


class WorkerAPI:
    """
    Serves the workers of ONE generation. `lease_seconds` is the coordinator's choice, not the worker's, and so is the
    candidate: `policy` (default: greedy, B3; see `heteroes.dispatch`) picks it. Requests are served one at a time (a lock),
    so that "pick a candidate, then lease it" cannot be interleaved with another worker's request.
    """

    def __init__(
        self,
        ledger,
        experiment_id: str,
        generation: int,
        lease_seconds: float,
        policy=None,
        cancel_requested=lambda: False,
        scorer=None,
        usage_sink=None,
    ):
        # Recipe v3: `scorer(descriptor, completions) -> reward` runs here, on the coordinator; it raises ScorerError when the
        # experiment's scoring fails, which is never a reward and never the worker's fault (`scoring_error` keeps it)
        self._scorer = scorer
        self._usage_sink, self.usage_errors = usage_sink, 0
        self.scoring_error: str | None = None
        self._ledger = ledger
        self._experiment_id = experiment_id
        self._generation = generation
        self._lease_seconds = lease_seconds
        self._policy = Greedy() if policy is None else policy
        self._cancel_requested = cancel_requested
        self._lock = threading.Lock()
        self._remembered: OrderedDict = (
            OrderedDict()
        )  # (worker_id, request_id) -> the work that was given, for repeated requests
        self._operations = {
            "lease": (_decode_lease, self._lease),
            "submit_result": (_decode_result, self._submit_result),
            "report_failure": (_decode_failure, self._report_failure),
            "heartbeat": (_decode_heartbeat, self._heartbeat),
        }

    def handle(self, operation, request, authenticated_worker_id=None) -> dict:
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
                if authenticated_worker_id is not None:
                    owner = decoded[0] if operation == "lease" else self._ledger.attempt_worker(*decoded[:3])
                    if owner != authenticated_worker_id:
                        return _error("forbidden", "Credential does not own this worker or attempt")
                return {"ok": True, **act(decoded)}
            except LedgerError as error:
                return _error(_code_of(error), str(error))

    def _lease(self, decoded) -> dict:
        if self._cancel_requested():
            return {"generation_state": GenerationState.OPEN.value, "work": None}
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
                work = {
                    "descriptor": chosen.descriptor.to_dict(),
                    "attempt_number": lease.attempt_number,
                    "token": lease.token,
                    "deadline": lease.deadline,
                }
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
        if hasattr(self._policy, "heartbeat"):  # a busy worker is alive for the policy too (GreedyTail, ADR-009)
            self._policy.heartbeat(self._ledger.attempt_worker(descriptor, attempt_number, token))
        return {"deadline": lease.deadline}

    def _submit_result(self, decoded) -> dict:
        descriptor, attempt_number, token, payload = decoded
        texts = isinstance(payload, list)
        if texts != (self._scorer is not None):
            raise LedgerError(
                "this coordinator scores texts: submit completions" if self._scorer else "submit a reward, not texts"
            )
        if texts:
            from heteroes.v3.scoring import ScorerError

            # a stale or foreign report is refused before the experiment's scorer spends any time on it
            worker = self._ledger.attempt_worker(descriptor, attempt_number, token)
            try:
                reward = self._scorer(descriptor, payload)
            except ScorerError as error:
                self.scoring_error = str(error)
                raise ScoringFailedError(str(error)) from error
            outcome = self._ledger.submit_result(descriptor, attempt_number, token, reward, completions=payload)
            self.record_usage(descriptor, attempt_number, worker, getattr(payload, "usage", None), "candidate")
        else:
            outcome = self._ledger.submit_result(descriptor, attempt_number, token, payload)
        if outcome is SubmitOutcome.COMMITTED and hasattr(self._policy, "committed"):
            self._policy.committed(descriptor.candidate_id)  # a policy may learn from the duration (GreedyTail)
        return {"outcome": outcome.value}

    def record_usage(self, descriptor, attempt_number, worker, usage, kind):
        if usage is not None and self._usage_sink is not None:
            try:
                self._usage_sink(descriptor, attempt_number, worker, usage, kind)
            except Exception:
                # Usage is a best-effort sidecar: a failed metrics write cannot undo or misreport a canonical commit.
                self.usage_errors += 1

    def _report_failure(self, decoded) -> dict:
        descriptor, attempt_number, token, kind = decoded
        self._ledger.report_failure(descriptor, attempt_number, token, kind)
        return {}
