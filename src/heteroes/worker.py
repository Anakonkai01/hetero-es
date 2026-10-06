"""
The worker's side of the worker protocol (ADR-002, decision 10; the coordinator's side is `heteroes.worker_api`).

`WorkerClient` turns method calls into JSON requests for a `transport` (any function `(operation, payload) -> reply`) and the
replies back into Python values. `local_transport(api)` stays in this process but sends everything through JSON text, as a
network would; an HTTP transport will be another such function. `Worker.step()` is one turn: ask for work, run it with
`evaluate(descriptor) -> reward` (the only part that needs a GPU), then deliver the reward or report why it could not.
A failure is reported with its kind and never turned into a reward.
"""
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from heteroes.ledger import FailureKind, GenerationState, SubmitOutcome
from heteroes.manifest import CandidateDescriptor

Transport = Callable[[str, dict], dict]

# the coordinator could not read the request, or the reply could not be read: a bug, never a normal refusal
_PROTOCOL_ERRORS = {"bad_request", "bad_response", "unknown_operation"}


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
    deadline: float          # in the coordinator's clock: for information, the worker's clock may differ

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
    return Assignment(descriptor, attempt_number, token, float(deadline))


class WorkerClient:
    def __init__(self, worker_id: str, transport: Transport):
        self.worker_id = worker_id
        self._transport = transport

    def _call(self, operation: str, payload: dict) -> dict:
        reply = self._transport(operation, payload)
        if not isinstance(reply, dict) or not isinstance(reply.get("ok"), bool):
            raise WorkerAPIError("bad_response", f"a reply without an ok flag: {reply!r}")
        if reply["ok"]:
            return reply
        error = reply.get("error")
        if not (isinstance(error, dict) and isinstance(error.get("code"), str) and isinstance(error.get("message"), str)):
            raise WorkerAPIError("bad_response", f"a refusal without a code and a message: {reply!r}")
        raise WorkerAPIError(error["code"], error["message"])

    def lease(self) -> LeaseReply:
        reply = self._call("lease", {"worker_id": self.worker_id})
        try:
            work = reply["work"]
            return LeaseReply(None if work is None else _assignment(work), GenerationState(reply["generation_state"]))
        except (KeyError, TypeError, ValueError) as error:
            raise WorkerAPIError("bad_response", f"a lease reply that cannot be read: {error!r}") from error

    def submit_result(self, assignment: Assignment, reward: float) -> SubmitOutcome:
        reply = self._call("submit_result", {
            "descriptor": assignment.descriptor.to_dict(), "attempt_number": assignment.attempt_number,
            "token": assignment.token, "reward": reward})
        try:
            return SubmitOutcome(reply["outcome"])
        except (KeyError, TypeError, ValueError) as error:
            raise WorkerAPIError("bad_response", f"a result reply that cannot be read: {error!r}") from error

    def report_failure(self, assignment: Assignment, kind: FailureKind) -> None:
        self._call("report_failure", {
            "descriptor": assignment.descriptor.to_dict(), "attempt_number": assignment.attempt_number,
            "token": assignment.token, "kind": kind.value})


class StepKind(Enum):
    NO_WORK = "NO_WORK"                    # nothing to run now; `generation_state` says whether to wait (OPEN) or stop
    COMMITTED = "COMMITTED"
    ALREADY_COMMITTED = "ALREADY_COMMITTED"
    FAILURE_REPORTED = "FAILURE_REPORTED"
    REFUSED = "REFUSED"                    # the coordinator did not accept the report (for example a stale attempt); `code` says why
    QUARANTINED = "QUARANTINED"            # this worker was put aside after a failed restore: it must stop


@dataclass(frozen=True)
class Step:
    kind: StepKind
    candidate_id: str | None = None
    code: str | None = None
    failure: FailureKind | None = None
    generation_state: GenerationState | None = None


class Worker:
    def __init__(self, worker_id: str, transport: Transport, evaluate: Callable[[CandidateDescriptor], float]):
        self.worker_id = worker_id
        self.client = WorkerClient(worker_id, transport)
        self._evaluate = evaluate

    def step(self) -> Step:
        try:
            reply = self.client.lease()
        except WorkerAPIError as error:
            if error.code == "worker_quarantined":
                return Step(StepKind.QUARANTINED, code=error.code)
            raise
        work = reply.assignment
        if work is None:
            return Step(StepKind.NO_WORK, generation_state=reply.generation_state)

        try:
            reward = self._evaluate(work.descriptor)
        except CandidateFailed as failed:
            return self._report(work, failed.kind)
        if isinstance(reward, bool) or not isinstance(reward, (int, float)) or not math.isfinite(reward):
            return self._report(work, FailureKind.VERIFIER_ERROR)    # never sent as a reward

        try:
            outcome = self.client.submit_result(work, reward)
        except WorkerAPIError as error:
            return self._refused(work, error)
        kind = StepKind.COMMITTED if outcome is SubmitOutcome.COMMITTED else StepKind.ALREADY_COMMITTED
        return Step(kind, work.candidate_id)

    def _report(self, work: Assignment, kind: FailureKind) -> Step:
        try:
            self.client.report_failure(work, kind)
        except WorkerAPIError as error:
            return self._refused(work, error, kind)
        return Step(StepKind.FAILURE_REPORTED, work.candidate_id, failure=kind)

    def _refused(self, work: Assignment, error: WorkerAPIError, failure: FailureKind | None = None) -> Step:
        if error.code in _PROTOCOL_ERRORS:
            raise error
        kind = StepKind.QUARANTINED if error.code == "worker_quarantined" else StepKind.REFUSED
        return Step(kind, work.candidate_id, code=error.code, failure=failure)
