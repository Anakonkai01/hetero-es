"""
The worker's side of the worker protocol (ADR-002, decision 10; the coordinator's side is `heteroes.worker_api`).

`WorkerClient` turns method calls into JSON requests for a `transport` (any function `(operation, payload) -> reply`) and the
replies back into Python values. `local_transport(api)` stays in this process but sends everything through JSON text, as a
network would; an HTTP transport will be another such function. `Worker.step()` is one turn: ask for work, run it with
`evaluate(descriptor) -> reward` (the only part that needs a GPU), then deliver the reward or report why it could not.
A failure is reported with its kind and never turned into a reward.

Three things make a turn survive what goes wrong around it. A lease request carries a fresh `request_id`, so the client may repeat it
after a lost reply and gets the same lease back. A heartbeat thread (if `heartbeat_seconds` is set) renews the lease
through evaluation, restore, delivery and pending retries until terminal ACK/refusal. Results and failures are
delivered before new work; an optional bounded private outbox preserves their exact payload across restart.
A restore fault poisons the worker locally before reporting, including while the coordinator is unreachable.
An exception that is not a typed failure is reported as OTHER before it propagates.
"""

import json
import math
import threading
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from heteroes.ledger import FailureKind, GenerationState, SubmitOutcome
from heteroes.manifest import CandidateDescriptor

Transport = Callable[[str, dict], dict]

# the coordinator could not read the request, or the reply could not be read: a bug, never a normal refusal
_PROTOCOL_ERRORS = {"bad_request", "bad_response", "unknown_operation", "unauthorized", "internal_error"}


class WorkerAPIError(Exception):
    """The coordinator refused (its error code and message), or its reply did not follow the protocol ("bad_response")."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class CandidateFailed(Exception):
    """Raised by `evaluate`: the candidate could not be evaluated, for a reason with a kind (never a reward of 0)."""

    def __init__(self, kind: FailureKind, message: str = ""):
        super().__init__(message or kind.value)
        self.kind = kind


@dataclass(frozen=True)
class Assignment:
    """What a lease gives a worker: the job, and the proof (attempt number and token) that it holds the lease."""

    descriptor: CandidateDescriptor
    attempt_number: int
    token: str
    deadline: float  # in the coordinator's clock: for information, the worker's clock may differ

    audit_id: str | None = None
    chunk: int | None = None  # an audit's: the chunk the first result used (ADR-010); None: this worker's own

    def payload(self):
        return {
            "descriptor": self.descriptor.to_dict(),
            "attempt_number": self.attempt_number,
            "token": self.token,
            **({"audit_id": self.audit_id} if self.audit_id is not None else {}),
        }

    @property
    def candidate_id(self) -> str:
        return self.descriptor.candidate_id


@dataclass(frozen=True)
class LeaseReply:
    assignment: Assignment | None
    generation_state: GenerationState


def local_transport(api) -> Transport:
    def transport(operation: str, payload: dict) -> dict:
        request = json.loads(json.dumps(payload, allow_nan=False))
        reply = api.handle(operation, request)
        return json.loads(json.dumps(reply, allow_nan=False))

    return transport


def _assignment(work) -> Assignment:
    descriptor = CandidateDescriptor.from_dict(work["descriptor"])
    attempt_number, token, deadline = work["attempt_number"], work["token"], work["deadline"]
    if isinstance(attempt_number, bool) or not isinstance(attempt_number, int):
        raise TypeError("attempt_number must be an integer")
    if not isinstance(token, str):
        raise TypeError("token must be a string")
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
        raise TypeError("deadline must be a number")
    audit_id = work.get("audit_id")
    if audit_id is not None and (
        not isinstance(audit_id, str) or len(audit_id) != 64 or any(c not in "0123456789abcdef" for c in audit_id)
    ):
        raise TypeError("audit_id must be a SHA-256 hex identity")
    chunk = work.get("chunk")
    if chunk is not None and (isinstance(chunk, bool) or not isinstance(chunk, int) or chunk < 1):
        raise TypeError("chunk must be a positive integer")
    return Assignment(descriptor, attempt_number, token, float(deadline), audit_id, chunk)


class WorkerClient:
    def __init__(self, worker_id: str, transport: Transport, *, usage_reporting=False, max_chunk=None):
        self.worker_id = worker_id
        self._transport = transport
        self.usage_reporting = usage_reporting
        self.max_chunk = (
            max_chunk  # ADR-010: the largest chunk this device may use, so it is given only audits it can run
        )

    def _call(self, operation: str, payload: dict) -> dict:
        reply = self._transport(operation, payload)
        if not isinstance(reply, dict) or not isinstance(reply.get("ok"), bool):
            raise WorkerAPIError("bad_response", f"a reply without an ok flag: {reply!r}")
        if reply["ok"]:
            return reply
        error = reply.get("error")
        if not (
            isinstance(error, dict) and isinstance(error.get("code"), str) and isinstance(error.get("message"), str)
        ):
            raise WorkerAPIError("bad_response", f"a refusal without a code and a message: {reply!r}")
        raise WorkerAPIError(error["code"], error["message"])

    def lease(self, generation: int | None = None) -> LeaseReply:
        payload = {"worker_id": self.worker_id, "request_id": uuid.uuid4().hex}
        if generation is not None:
            payload["generation"] = generation  # the generation of the job this worker is working on (see WorkerAPI)
        if self.max_chunk is not None:
            payload["max_chunk"] = self.max_chunk
        reply = self._call("lease", payload)
        try:
            work = reply["work"]
            return LeaseReply(None if work is None else _assignment(work), GenerationState(reply["generation_state"]))
        except (KeyError, TypeError, ValueError) as error:
            raise WorkerAPIError("bad_response", f"a lease reply that cannot be read: {error!r}") from error

    def submit_result(self, assignment: Assignment, reward: float) -> SubmitOutcome:
        reply = self._call(
            "submit_result",
            {
                **assignment.payload(),
                "reward": reward,
            },
        )
        try:
            return SubmitOutcome(reply["outcome"])
        except (KeyError, TypeError, ValueError) as error:
            raise WorkerAPIError("bad_response", f"a result reply that cannot be read: {error!r}") from error

    def submit_completions(self, assignment: Assignment, completions) -> SubmitOutcome:
        """Recipe v3: send the texts of the candidate; the coordinator scores them (ADR-008 section 7)."""
        reply = self._call("submit_result", self.completion_payload(assignment, completions))
        return self.result_outcome(assignment, reply)

    def completion_payload(self, assignment, completions):
        from heteroes.worker_api import completions_sha256

        texts = list(completions)
        return {
            **assignment.payload(),
            "completions": texts,
            "completions_sha256": completions_sha256(texts),
            **({"usage": completions.usage} if self.usage_reporting and hasattr(completions, "usage") else {}),
            **({"chunk": completions.chunk} if getattr(completions, "chunk", None) is not None else {}),
        }

    def result_outcome(self, assignment, reply):
        if assignment.audit_id is not None and self.worker_id in reply.get("quarantined_workers", []):
            raise WorkerAPIError("worker_quarantined", "Repeated audit mismatches")
        try:
            return SubmitOutcome(reply["outcome"])
        except (KeyError, TypeError, ValueError) as error:
            raise WorkerAPIError("bad_response", f"a result reply that cannot be read: {error!r}") from error

    def heartbeat(self, assignment: Assignment) -> float:
        """Tell the coordinator that the lease is still wanted; returns the new deadline (the coordinator's clock)."""
        reply = self._call(
            "heartbeat",
            assignment.payload(),
        )
        deadline = reply.get("deadline")
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
            raise WorkerAPIError("bad_response", f"a heartbeat reply without a deadline: {reply!r}")
        return float(deadline)

    def report_failure(self, assignment: Assignment, kind: FailureKind) -> None:
        self._call(
            "report_failure",
            {
                **assignment.payload(),
                "kind": kind.value,
            },
        )


class StepKind(Enum):
    NO_WORK = "NO_WORK"  # nothing to run now; `generation_state` says whether to wait (OPEN) or stop
    AUDITED = "AUDITED"
    COMMITTED = "COMMITTED"
    ALREADY_COMMITTED = "ALREADY_COMMITTED"
    FAILURE_REPORTED = "FAILURE_REPORTED"
    REFUSED = "REFUSED"  # the coordinator did not accept the report (for example a stale attempt); `code` says why
    QUARANTINED = "QUARANTINED"  # this worker was put aside after a failed restore: it must stop


@dataclass(frozen=True)
class Step:
    kind: StepKind
    candidate_id: str | None = None
    code: str | None = None
    failure: FailureKind | None = None
    generation_state: GenerationState | None = None


class Worker:
    def __init__(
        self,
        worker_id: str,
        transport: Transport,
        evaluate: Callable[[CandidateDescriptor], float | tuple[str, ...]],  # a reward, or the texts (Recipe v3)
        transient_errors: tuple = (),
        heartbeat_seconds: float | None = None,
        outbox_path=None,
        outbox_scope=None,
    ):
        self.worker_id = worker_id
        self.client = WorkerClient(worker_id, transport)
        self._evaluate = evaluate
        self._transient = tuple(
            transient_errors
        )  # what a lost network looks like: a reward that meets it waits in the outbox
        self._pending = None
        self._poisoned = False
        self._heartbeat = None
        self._outbox = None
        self._heartbeat_seconds = None
        self.heartbeat_seconds = heartbeat_seconds
        if outbox_path is not None:
            from heteroes.worker_outbox import DeliveryOutbox

            self._outbox = DeliveryOutbox(outbox_path, worker_id, outbox_scope)
            state = self._outbox.load()
            self._poisoned = state["poisoned"]
            if state["pending"] is not None:
                self._pending = self._read_pending(state["pending"])

    @property
    def heartbeat_seconds(self) -> float | None:
        return self._heartbeat_seconds

    @heartbeat_seconds.setter
    def heartbeat_seconds(self, seconds: float | None) -> None:
        if seconds is not None and not (
            isinstance(seconds, (int, float))
            and not isinstance(seconds, bool)
            and seconds > 0
            and math.isfinite(seconds)
        ):
            raise ValueError(f"heartbeat_seconds must be a positive finite number or None, got {seconds!r}")
        self._heartbeat_seconds = seconds

    def step(self, generation: int | None = None) -> Step:
        if self._pending is not None:
            return self._deliver_pending()
        if self._poisoned:
            return Step(StepKind.QUARANTINED, code="worker_quarantined")
        try:
            reply = self.client.lease(generation)
        except WorkerAPIError as error:
            if error.code == "worker_quarantined":
                return Step(StepKind.QUARANTINED, code=error.code)
            raise
        work = reply.assignment
        if work is None:
            return Step(StepKind.NO_WORK, generation_state=reply.generation_state)

        self._start_heartbeat(work)
        try:
            reward = (
                self._evaluate(work.descriptor)
                if work.chunk is None
                else self._evaluate(work.descriptor, chunk=work.chunk)  # an audit, at the original's chunk
            )
        except CandidateFailed as failed:
            return self._report(work, failed.kind)
        except Exception:
            # not a typed failure: a bug, or something the executor could not classify. Free the candidate NOW (the lease would
            # otherwise hold it for its whole length) and let the exception reach the caller; a failure to say so changes nothing.
            try:
                self._report(work, FailureKind.OTHER)
            except Exception:
                pass
            raise
        if isinstance(reward, (list, tuple)):  # Recipe v3: the texts, scored by the coordinator (ADR-008 section 7)
            if not reward or not all(isinstance(text, str) for text in reward):
                return self._report(work, FailureKind.VERIFIER_ERROR)
            return self._deliver(work, reward if isinstance(reward, tuple) else tuple(reward))
        if isinstance(reward, bool) or not isinstance(reward, (int, float)) or not math.isfinite(reward):
            return self._report(work, FailureKind.VERIFIER_ERROR)  # never sent as a reward
        return self._deliver(work, reward)

    @property
    def pending_delivery(self):
        return self._pending is not None

    @property
    def poisoned(self):
        return self._poisoned

    def _deliver(self, work: Assignment, reward) -> Step:
        payload = (
            self.client.completion_payload(work, reward)
            if isinstance(reward, tuple)
            else {**work.payload(), "reward": reward}
        )
        self._pending = (work, "submit_result", payload, None)
        return self._deliver_pending()

    def _deliver_pending(self) -> Step:
        work, operation, payload, failure = self._pending
        self._save_pending()  # an earlier persistence error must be retried before sending anything
        self._start_heartbeat(work)
        try:
            reply = self.client._call(operation, payload)
            outcome = self.client.result_outcome(work, reply) if operation == "submit_result" else None
        except self._transient:
            raise
        except WorkerAPIError as error:
            if error.code in _PROTOCOL_ERRORS:
                raise
            if error.code == "worker_quarantined":
                self._poisoned = True
            self._finish_pending()
            return self._refused(work, error, failure)
        except BaseException:
            if self._outbox is None:
                self._finish_pending()  # legacy callers without configured transport retries
            raise
        self._finish_pending()
        if operation == "report_failure":
            return Step(StepKind.FAILURE_REPORTED, work.candidate_id, failure=failure)
        kind = StepKind.COMMITTED if outcome is SubmitOutcome.COMMITTED else StepKind.ALREADY_COMMITTED
        return Step(StepKind.AUDITED if work.audit_id is not None else kind, work.candidate_id)

    def _report(self, work: Assignment, kind: FailureKind) -> Step:
        if kind is FailureKind.RESTORE_MISMATCH:
            self._poisoned = True  # local stop precedes persistence and any attempt to notify the coordinator
        self._pending = (work, "report_failure", {**work.payload(), "kind": kind.value}, kind)
        return self._deliver_pending()

    def _start_heartbeat(self, work):
        if self._heartbeat is None:
            self._heartbeat = _Heartbeat(self.client, work, self._heartbeat_seconds)
            self._heartbeat.__enter__()

    def close(self):
        """Stop this process's heartbeat. Durable delivery/poison state remains for the next process."""
        if self._heartbeat is not None:
            self._heartbeat.__exit__(None, None, None)
            self._heartbeat = None

    def _save_pending(self):
        if self._outbox is not None:
            pending = None
            if self._pending is not None:
                work, operation, payload, failure = self._pending
                pending = {
                    "assignment": {**work.payload(), "deadline": work.deadline, "chunk": work.chunk},
                    "operation": operation,
                    "payload": payload,
                    "failure": None if failure is None else failure.value,
                    "heartbeatSeconds": self.heartbeat_seconds,
                }
            self._outbox.save(pending, self._poisoned)

    def _finish_pending(self):
        pending, self._pending = self._pending, None
        try:
            self._save_pending()
        except BaseException:
            self._pending = pending
            raise
        self.close()

    def _read_pending(self, value):
        from heteroes.worker_api import _decode_failure, _decode_result

        work = _assignment(value["assignment"])
        self.heartbeat_seconds = value.get("heartbeatSeconds")
        operation, payload = value["operation"], value["payload"]
        if operation not in ("submit_result", "report_failure"):
            raise ValueError("Invalid outbox delivery operation")
        if any(payload.get(key) != expected for key, expected in work.payload().items()):
            raise ValueError("Outbox assignment lineage differs from the payload")
        failure = None if value["failure"] is None else FailureKind(value["failure"])
        decoded = {key: item for key, item in payload.items() if key != "audit_id"}
        if operation == "submit_result":
            _decode_result(decoded)
            if failure is not None:
                raise ValueError("A result outbox cannot contain a failure")
        else:
            _decode_failure(decoded)
            if failure is None or payload["kind"] != failure.value:
                raise ValueError("Outbox failure differs from the payload")
            if failure is FailureKind.RESTORE_MISMATCH and not self._poisoned:
                raise ValueError("Restore fault outbox must keep the worker poisoned")
        return work, operation, payload, failure

    def _refused(self, work: Assignment, error: WorkerAPIError, failure: FailureKind | None = None) -> Step:
        if error.code in _PROTOCOL_ERRORS:
            raise error
        kind = StepKind.QUARANTINED if error.code == "worker_quarantined" else StepKind.REFUSED
        return Step(kind, work.candidate_id, code=error.code, failure=failure)


class _Heartbeat:
    """A context manager: while the block runs, a thread sends a heartbeat every `seconds` (nothing if `seconds` is None)."""

    def __init__(self, client: WorkerClient, assignment: Assignment, seconds: float | None):
        self._client, self._assignment, self._seconds = client, assignment, seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _run(self) -> None:
        while not self._stop.wait(self._seconds):
            try:
                self._client.heartbeat(self._assignment)
            except Exception:
                pass  # a lost heartbeat is not a reason to stop the candidate: the next one may get through

    def __enter__(self):
        if self._seconds is not None:
            self._thread = threading.Thread(target=self._run, name="heteroes-heartbeat", daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        return False
