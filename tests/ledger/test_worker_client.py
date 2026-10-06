"""
The worker's side of the protocol: `WorkerClient` turns method calls into JSON requests for a `transport` (any function
`(operation, payload) -> reply`), and replies back into Python values. `local_transport(api)` is the transport that
stays in this process but goes through JSON text both ways, as a network would.
"""
import json

import pytest

from heteroes.ledger import FailureKind, GenerationState, Ledger, SubmitOutcome
from heteroes.manifest import CandidateDescriptor
from heteroes.worker import Assignment, LeaseReply, WorkerAPIError, WorkerClient, local_transport
from heteroes.worker_api import WorkerAPI
from ledger_helpers import FakeClock, batch, descriptor_of

LEASE_SECONDS = 30.0


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def ledger(clock):
    with Ledger(":memory:", clock=clock) as ledger:
        ledger.open_generation(batch(3))
        yield ledger


@pytest.fixture
def api(ledger):
    return WorkerAPI(ledger, "exp", 0, lease_seconds=LEASE_SECONDS)


@pytest.fixture
def client(api):
    return WorkerClient("worker-a", local_transport(api))


# ---------------------------------------------------------------------------
# the happy path, in Python values
# ---------------------------------------------------------------------------

def test_a_lease_comes_back_as_typed_values(client, clock):
    reply = client.lease()

    assert isinstance(reply, LeaseReply) and reply.generation_state is GenerationState.OPEN
    work = reply.assignment
    assert isinstance(work, Assignment) and isinstance(work.descriptor, CandidateDescriptor)
    assert work.descriptor == descriptor_of(0) and work.candidate_id == "exp/g0/c0"
    assert work.attempt_number == 1 and isinstance(work.token, str) and len(work.token) == 32
    assert work.deadline == clock.now + LEASE_SECONDS


def test_no_work_comes_back_as_none_with_the_state_of_the_generation(client, api):
    for _ in range(3):
        assert client.lease().assignment is not None

    reply = client.lease()

    assert reply.assignment is None and reply.generation_state is GenerationState.OPEN


def test_a_result_is_committed_and_acknowledged_again(client, ledger):
    work = client.lease().assignment

    assert client.submit_result(work, 0.5) is SubmitOutcome.COMMITTED
    assert client.submit_result(work, 0.5) is SubmitOutcome.ALREADY_COMMITTED
    assert ledger.get_candidate("exp/g0/c0").result.reward == 0.5


def test_an_integer_reward_is_a_reward(client, ledger):
    work = client.lease().assignment

    assert client.submit_result(work, 1) is SubmitOutcome.COMMITTED
    assert ledger.get_candidate("exp/g0/c0").result.reward == 1.0


def test_a_failure_is_reported(client, ledger):
    work = client.lease().assignment

    assert client.report_failure(work, FailureKind.OUT_OF_MEMORY) is None
    record = ledger.get_candidate("exp/g0/c0")
    assert record.state.name == "PENDING" and record.result is None


def test_a_refusal_is_an_error_with_its_code_and_message(client, api, clock):
    old = client.lease().assignment
    clock.advance(LEASE_SECONDS)
    WorkerClient("worker-b", local_transport(api)).lease()

    with pytest.raises(WorkerAPIError) as caught:
        client.submit_result(old, 0.5)

    assert caught.value.code == "stale_attempt" and "exp/g0/c0" in caught.value.message
    assert "stale_attempt" in str(caught.value)


def test_a_quarantined_worker_gets_its_code_from_the_lease(client):
    work = client.lease().assignment
    client.report_failure(work, FailureKind.RESTORE_MISMATCH)

    with pytest.raises(WorkerAPIError) as caught:
        client.lease()

    assert caught.value.code == "worker_quarantined"


# ---------------------------------------------------------------------------
# what crosses the boundary
# ---------------------------------------------------------------------------

class Recorder:
    """A transport that remembers what it was asked and answers like the real API."""

    def __init__(self, api):
        self.inner = local_transport(api)
        self.sent = []

    def __call__(self, operation, payload):
        self.sent.append((operation, payload))
        return self.inner(operation, payload)


def test_the_client_sends_exactly_the_protocol_fields_and_only_json(api):
    recorder = Recorder(api)
    client = WorkerClient("worker-a", recorder)

    work = client.lease().assignment
    client.submit_result(work, 0.5)
    work = client.lease().assignment
    client.report_failure(work, FailureKind.VERIFIER_ERROR)

    assert [operation for operation, _ in recorder.sent] == ["lease", "submit_result", "lease", "report_failure"]
    lease_payload, submit_payload, _, failure_payload = (payload for _, payload in recorder.sent)
    assert lease_payload == {"worker_id": "worker-a"}
    assert set(submit_payload) == {"descriptor", "attempt_number", "token", "reward"}
    assert submit_payload["descriptor"] == descriptor_of(0).to_dict() and submit_payload["reward"] == 0.5
    assert set(failure_payload) == {"descriptor", "attempt_number", "token", "kind"}
    assert failure_payload["kind"] == "VERIFIER_ERROR"
    for _, payload in recorder.sent:
        assert json.loads(json.dumps(payload)) == payload


class RecordingAPI:
    def __init__(self, reply):
        self.reply, self.seen = reply, []

    def handle(self, operation, request):
        self.seen.append((operation, request))
        return self.reply


def test_the_local_transport_really_goes_through_json_text_in_both_directions():
    reply = {"ok": True, "pair": (1, 2)}
    api = RecordingAPI(reply)
    payload = {"worker_id": "w", "pair": (1, 2)}

    answer = local_transport(api)("lease", payload)

    operation, request = api.seen[0]
    assert operation == "lease" and request == {"worker_id": "w", "pair": [1, 2]}       # a tuple became a list
    assert request is not payload
    assert answer == {"ok": True, "pair": [1, 2]} and answer is not reply


def test_the_local_transport_refuses_what_json_cannot_carry(api, ledger):
    transport = local_transport(api)

    with pytest.raises(TypeError):
        transport("lease", {"worker_id": object()})
    with pytest.raises(ValueError):
        transport("lease", {"worker_id": float("nan")})          # no NaN on the wire (the JSON text would not be standard)
    assert ledger.get_candidate("exp/g0/c0").attempts == 0


def test_a_reward_that_json_cannot_carry_never_reaches_the_coordinator(client, ledger):
    work = client.lease().assignment

    with pytest.raises(ValueError):
        client.submit_result(work, float("nan"))
    with pytest.raises(ValueError):
        client.submit_result(work, float("inf"))

    assert ledger.get_candidate("exp/g0/c0").result is None


def test_a_network_error_is_the_transports_business_and_is_not_wrapped():
    def broken(operation, payload):
        raise ConnectionError("no route to the coordinator")

    with pytest.raises(ConnectionError):
        WorkerClient("worker-a", broken).lease()


# ---------------------------------------------------------------------------
# a reply that does not follow the protocol
# ---------------------------------------------------------------------------

GOOD_WORK = {"descriptor": descriptor_of(0).to_dict(), "attempt_number": 1, "token": "0" * 32, "deadline": 1030.0}


@pytest.mark.parametrize("reply", [
    None, [], "ok", {}, {"ok": "yes"}, {"ok": 1},
    {"ok": False}, {"ok": False, "error": "stale"}, {"ok": False, "error": {"code": "x"}},
    {"ok": False, "error": {"code": 5, "message": "m"}},
    {"ok": True},
    {"ok": True, "work": None},
    {"ok": True, "generation_state": "BOGUS", "work": None},
    {"ok": True, "generation_state": "OPEN", "work": {}},
    {"ok": True, "generation_state": "OPEN", "work": {k: v for k, v in GOOD_WORK.items() if k != "token"}},
    {"ok": True, "generation_state": "OPEN", "work": dict(GOOD_WORK, descriptor={"seed": 1})},
    {"ok": True, "generation_state": "OPEN", "work": dict(GOOD_WORK, attempt_number="1")},
    {"ok": True, "generation_state": "OPEN", "work": dict(GOOD_WORK, deadline="soon")},
    {"ok": True, "generation_state": "OPEN", "work": dict(GOOD_WORK, deadline="1030.0")},
    {"ok": True, "generation_state": "OPEN", "work": dict(GOOD_WORK, deadline=True)},
    {"ok": True, "generation_state": "OPEN", "work": dict(GOOD_WORK, deadline=None)},
    {"ok": True, "generation_state": "OPEN", "work": dict(GOOD_WORK, token=5)},
    {"ok": True, "generation_state": "OPEN", "work": dict(GOOD_WORK, token=None)},
    {"ok": True, "generation_state": "OPEN", "work": dict(GOOD_WORK, attempt_number=True)},
    {"ok": True, "generation_state": "OPEN", "work": dict(GOOD_WORK, attempt_number=1.0)},
], ids=lambda reply: json.dumps(reply, default=str)[:60])
def test_a_reply_that_breaks_the_protocol_is_a_bad_response(reply):
    client = WorkerClient("worker-a", lambda operation, payload: reply)

    with pytest.raises(WorkerAPIError) as caught:
        client.lease()

    assert caught.value.code == "bad_response"


@pytest.mark.parametrize("reply", [None, {}, {"ok": True}, {"ok": True, "outcome": "NOPE"}, {"ok": True, "outcome": 1}])
def test_a_result_reply_that_breaks_the_protocol_is_a_bad_response(reply):
    work = Assignment(descriptor_of(0), 1, "0" * 32, 1030.0)

    with pytest.raises(WorkerAPIError) as caught:
        WorkerClient("worker-a", lambda operation, payload: reply).submit_result(work, 0.5)

    assert caught.value.code == "bad_response"


@pytest.mark.parametrize("reply", [None, {}, {"ok": 1}, {"ok": False}])
def test_a_failure_reply_that_breaks_the_protocol_is_a_bad_response(reply):
    work = Assignment(descriptor_of(0), 1, "0" * 32, 1030.0)

    with pytest.raises(WorkerAPIError) as caught:
        WorkerClient("worker-a", lambda operation, payload: reply).report_failure(work, FailureKind.OTHER)

    assert caught.value.code == "bad_response"


def test_a_deadline_that_arrives_as_an_integer_is_a_float():
    reply = {"ok": True, "generation_state": "OPEN", "work": dict(GOOD_WORK, deadline=1030)}

    work = WorkerClient("worker-a", lambda operation, payload: reply).lease().assignment

    assert work.deadline == 1030.0 and isinstance(work.deadline, float)


def test_the_good_reply_that_the_bad_ones_are_made_from_is_accepted():
    reply = {"ok": True, "generation_state": "OPEN", "work": GOOD_WORK}      # premise for the cases above

    work = WorkerClient("worker-a", lambda operation, payload: reply).lease().assignment

    assert work == Assignment(descriptor_of(0), 1, "0" * 32, 1030.0)
