"""
Hardening of the worker protocol found by the audit of 07/10/2026 (G6):
  - heartbeat: a worker that is still working keeps its lease, so leases can be short and a dead worker is noticed in seconds;
  - a lease request can be repeated safely (same `request_id` -> same lease), so a lost reply no longer costs a whole lease;
  - an exception that is not a typed failure releases the candidate at once (reported as OTHER) before it reaches the caller;
  - a reward that could not be delivered stays in an outbox and is delivered first at the next turn.
"""
import json
import threading
import time

import pytest

from heteroes.dispatch import Greedy
from heteroes.ledger import CandidateState, FailureKind, Ledger
from heteroes.worker import CandidateFailed, StepKind, Worker, WorkerAPIError, local_transport
from heteroes.worker_api import WorkerAPI
from ledger_helpers import FakeClock, batch, descriptor_of

LEASE_SECONDS = 30.0


def reward_of(descriptor):
    return (descriptor.seed % 97) / 96


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


def call(api, operation, request):
    reply = api.handle(operation, json.loads(json.dumps(request)))
    assert json.loads(json.dumps(reply)) == reply
    return reply


def code_of(reply):
    assert reply["ok"] is False, reply
    return reply["error"]["code"]


def take(api, worker="worker-a", **extra):
    reply = call(api, "lease", {"worker_id": worker, **extra})
    assert reply["ok"] is True, reply
    return reply["work"]


def attempt_request(work, **changes):
    request = {"descriptor": work["descriptor"], "attempt_number": work["attempt_number"], "token": work["token"]}
    request.update(changes)
    return request


# ---------------------------------------------------------------------------
# heartbeat
# ---------------------------------------------------------------------------

def test_a_heartbeat_moves_the_deadline_by_the_lease_length_of_the_coordinator(api, ledger, clock):
    work = take(api)
    clock.advance(20.0)

    reply = call(api, "heartbeat", attempt_request(work))

    assert reply == {"ok": True, "deadline": clock.now + LEASE_SECONDS}
    clock.advance(25.0)                                           # past the original deadline
    assert ledger.get_candidate("exp/g0/c0").state is CandidateState.LEASED


def test_a_worker_cannot_choose_the_length_of_its_heartbeat(api):
    work = take(api)
    assert code_of(call(api, "heartbeat", attempt_request(work, duration=1e9))) == "bad_request"


def test_a_heartbeat_of_a_replaced_attempt_is_refused(api, clock):
    old = take(api, "worker-a")
    clock.advance(LEASE_SECONDS)
    take(api, "worker-b")                                         # c0 again, to another worker
    assert code_of(call(api, "heartbeat", attempt_request(old))) == "stale_attempt"


def test_a_heartbeat_with_the_wrong_token_is_refused(api):
    work = take(api)
    assert code_of(call(api, "heartbeat", attempt_request(work, token="0" * 32))) == "stale_attempt"


def test_a_malformed_heartbeat_is_a_bad_request(api):
    work = take(api)
    request = attempt_request(work)
    del request["token"]
    assert code_of(call(api, "heartbeat", request)) == "bad_request"
    assert code_of(call(api, "heartbeat", [])) == "bad_request"


def test_worker_client_heartbeat_returns_the_new_deadline(api, clock):
    from heteroes.worker import WorkerClient
    client = WorkerClient("worker-a", local_transport(api))
    assignment = client.lease().assignment
    clock.advance(5.0)
    assert client.heartbeat(assignment) == clock.now + LEASE_SECONDS


# ---------------------------------------------------------------------------
# a repeated lease request gets the same lease
# ---------------------------------------------------------------------------

def test_the_same_request_id_gets_the_same_lease_and_no_second_candidate(api, ledger):
    first = take(api, request_id="r1")
    again = take(api, request_id="r1")

    assert again == first
    assert ledger.get_candidate("exp/g0/c0").attempts == 1
    assert ledger.get_candidate("exp/g0/c1").attempts == 0        # nothing else was given out


def test_another_request_id_is_another_request(api):
    assert take(api, request_id="r1")["descriptor"]["index"] == 0
    assert take(api, request_id="r2")["descriptor"]["index"] == 1


def test_the_same_request_id_of_another_worker_is_another_request(api):
    assert take(api, "worker-a", request_id="r1")["descriptor"]["index"] == 0
    assert take(api, "worker-b", request_id="r1")["descriptor"]["index"] == 1


def test_a_repeated_request_after_the_lease_ended_gets_a_new_attempt(api, clock):
    first = take(api, request_id="r1")
    clock.advance(LEASE_SECONDS)                                  # the lease is over: it must not be handed out again
    again = take(api, request_id="r1")
    assert again["descriptor"]["index"] == 0 and again["attempt_number"] == 2 and again["token"] != first["token"]


def test_a_repeated_request_after_the_result_was_delivered_gets_the_next_candidate(api):
    first = take(api, request_id="r1")
    assert call(api, "submit_result", attempt_request(first, reward=0.5))["ok"] is True
    again = take(api, request_id="r1")
    assert again is None or again["descriptor"]["index"] != 0


def test_a_request_without_an_id_keeps_working_as_before(api):
    assert take(api)["descriptor"]["index"] == 0
    assert take(api)["descriptor"]["index"] == 1


@pytest.mark.parametrize("bad", [1, None, "", ["r"], True])
def test_a_bad_request_id_is_a_bad_request(api, bad):
    assert code_of(call(api, "lease", {"worker_id": "worker-a", "request_id": bad})) == "bad_request"


def test_the_memory_of_request_ids_is_bounded(api, ledger):
    from heteroes.worker_api import MAX_REMEMBERED_REQUESTS
    for i in range(MAX_REMEMBERED_REQUESTS + 5):
        api.handle("lease", {"worker_id": "worker-a", "request_id": f"r{i}"})
    assert len(api._remembered) <= MAX_REMEMBERED_REQUESTS


# ---------------------------------------------------------------------------
# an exception that is not a typed failure
# ---------------------------------------------------------------------------

def test_an_unexpected_exception_releases_the_candidate_at_once_and_is_then_raised(api, ledger):
    def broken(descriptor):
        raise RuntimeError("a bug in the evaluation")

    worker = Worker("worker-a", local_transport(api), broken)
    with pytest.raises(RuntimeError, match="a bug in the evaluation"):
        worker.step()

    c0 = ledger.get_candidate("exp/g0/c0")
    assert c0.state is CandidateState.PENDING and c0.attempts == 1       # free again now, not at the end of the lease
    failure = ledger._db.execute("SELECT failure_kind FROM attempt WHERE candidate_id = 'exp/g0/c0'").fetchone()[0]
    assert failure == FailureKind.OTHER.value


def test_a_failure_to_report_the_unexpected_exception_does_not_hide_it(api):
    calls = []

    def transport(operation, payload):
        calls.append(operation)
        if operation == "report_failure":
            raise ConnectionError("the network is gone")
        return local_transport(api)(operation, payload)

    def broken(descriptor):
        raise RuntimeError("the real problem")

    with pytest.raises(RuntimeError, match="the real problem"):
        Worker("worker-a", transport, broken).step()
    assert "report_failure" in calls                                       # it tried


def test_a_typed_failure_is_still_a_report_and_not_an_exception(api):
    def fails(descriptor):
        raise CandidateFailed(FailureKind.OUT_OF_MEMORY)

    step = Worker("worker-a", local_transport(api), fails).step()
    assert step.kind is StepKind.FAILURE_REPORTED


# ---------------------------------------------------------------------------
# the outbox
# ---------------------------------------------------------------------------

class Flaky:
    """A transport that loses the answers to `submit_result` until told to stop."""

    def __init__(self, api):
        self.inner = local_transport(api)
        self.down = False
        self.submits = 0

    def __call__(self, operation, payload):
        if operation == "submit_result":
            self.submits += 1
            if self.down:
                raise ConnectionError("no route to the coordinator")
        return self.inner(operation, payload)


def test_a_reward_that_could_not_be_delivered_is_delivered_first_at_the_next_turn(api, ledger):
    transport = Flaky(api)
    transport.down = True
    worker = Worker("worker-a", transport, reward_of, transient_errors=(ConnectionError,))
    with pytest.raises(ConnectionError):
        worker.step()                                                      # the candidate was run, its reward could not be sent
    assert ledger.get_candidate("exp/g0/c0").result is None

    transport.down = False
    step = worker.step()

    assert step.kind is StepKind.COMMITTED and step.candidate_id == "exp/g0/c0"
    assert ledger.get_candidate("exp/g0/c0").result.reward == reward_of(descriptor_of(0))
    assert ledger.get_candidate("exp/g0/c1").attempts == 0                 # no new candidate was taken in that turn: delivery came first
    nxt = worker.step()
    assert nxt.kind is StepKind.COMMITTED and nxt.candidate_id == "exp/g0/c1"


def test_the_outbox_keeps_the_reward_across_several_failed_deliveries(api, ledger):
    transport = Flaky(api)
    transport.down = True
    worker = Worker("worker-a", transport, reward_of, transient_errors=(ConnectionError,))
    with pytest.raises(ConnectionError):
        worker.step()
    for _ in range(3):
        with pytest.raises(ConnectionError):
            worker.step()                                                  # still down: still the same reward waiting, no new lease
    assert ledger.get_candidate("exp/g0/c1").attempts == 0
    transport.down = False
    assert worker.step().kind is StepKind.COMMITTED


def test_a_reward_that_is_refused_as_late_is_dropped_not_sent_for_ever(api, ledger, clock):
    transport = Flaky(api)
    transport.down = True
    worker = Worker("worker-a", transport, reward_of, transient_errors=(ConnectionError,))
    with pytest.raises(ConnectionError):
        worker.step()
    clock.advance(LEASE_SECONDS)
    take(api, "worker-b")                                                  # another worker took c0 over meanwhile

    transport.down = False
    step = worker.step()

    assert step.kind is StepKind.REFUSED and step.code == "stale_attempt"
    submits = transport.submits
    worker.step()                                                          # a normal turn: nothing is sent again
    assert transport.submits == submits + 1                                # only the new candidate's own result


def test_without_transient_errors_configured_nothing_is_kept(api):
    transport = Flaky(api)
    transport.down = True
    worker = Worker("worker-a", transport, reward_of)                      # the old behaviour: the exception passes through
    with pytest.raises(ConnectionError):
        worker.step()
    assert worker._pending is None


# ---------------------------------------------------------------------------
# the heartbeat thread of a worker
# ---------------------------------------------------------------------------

def make_realtime_api(lease_seconds, n=1):
    ledger = Ledger(":memory:")                                           # the wall clock
    ledger.open_generation(batch(n))
    return ledger, WorkerAPI(ledger, "exp", 0, lease_seconds=lease_seconds, policy=Greedy())


def run_slow_candidate(api, heartbeat_seconds, seconds):
    started, release = threading.Event(), threading.Event()

    def evaluate(descriptor):
        started.set()
        release.wait(timeout=seconds)
        return 0.5

    worker = Worker("worker-a", local_transport(api), evaluate, heartbeat_seconds=heartbeat_seconds)
    thread = threading.Thread(target=worker.step, daemon=True)
    thread.start()
    assert started.wait(5)
    return worker, thread, release


def test_with_a_heartbeat_the_lease_outlives_its_own_length():
    ledger, api = make_realtime_api(lease_seconds=0.4)
    worker, thread, release = run_slow_candidate(api, heartbeat_seconds=0.1, seconds=5)
    time.sleep(1.0)                                                       # 2.5 lease lengths later
    other = api.handle("lease", {"worker_id": "worker-b"})
    release.set()
    thread.join(5)
    assert other["work"] is None                                          # nobody could take it: the lease was kept alive
    assert ledger.get_candidate("exp/g0/c0").result is not None


def test_without_a_heartbeat_the_same_lease_is_given_to_another_worker():
    ledger, api = make_realtime_api(lease_seconds=0.4)
    worker, thread, release = run_slow_candidate(api, heartbeat_seconds=None, seconds=5)
    time.sleep(1.0)
    other = api.handle("lease", {"worker_id": "worker-b"})
    release.set()
    thread.join(5)
    assert other["work"] is not None and other["work"]["attempt_number"] == 2     # premise of the test above: it does expire


def test_the_heartbeat_stops_when_the_candidate_is_done():
    ledger, api = make_realtime_api(lease_seconds=0.4)
    calls = []
    transport = local_transport(api)

    def counting(operation, payload):
        calls.append(operation)
        return transport(operation, payload)

    worker = Worker("worker-a", counting, lambda d: 0.5, heartbeat_seconds=0.05)
    worker.step()
    count = calls.count("heartbeat")
    time.sleep(0.4)
    assert calls.count("heartbeat") == count                              # no thread is left beating
    assert threading.active_count() < 20


def test_a_heartbeat_that_fails_does_not_stop_the_candidate():
    ledger, api = make_realtime_api(lease_seconds=5.0)
    transport = local_transport(api)

    def no_heartbeats(operation, payload):
        if operation == "heartbeat":
            raise ConnectionError("down")
        return transport(operation, payload)

    def slow(descriptor):
        time.sleep(0.3)
        return 0.5

    worker = Worker("worker-a", no_heartbeats, slow, heartbeat_seconds=0.05)
    assert worker.step().kind is StepKind.COMMITTED


def test_the_heartbeat_interval_can_be_changed_between_turns():
    worker = Worker("worker-a", lambda *a: {}, lambda d: 0.0)
    assert worker.heartbeat_seconds is None
    worker.heartbeat_seconds = 10.0
    assert worker.heartbeat_seconds == 10.0
    with pytest.raises(ValueError):
        worker.heartbeat_seconds = 0


# ---------------------------------------------------------------------------
# a worker that read the job of the previous generation must not be handed a candidate of the next one
# ---------------------------------------------------------------------------

def test_a_lease_for_another_generation_than_the_api_serves_gets_no_work_and_takes_nothing(api, ledger):
    reply = call(api, "lease", {"worker_id": "worker-a", "generation": 7})
    assert reply == {"ok": True, "generation_state": "OPEN", "work": None}
    assert all(r.attempts == 0 for r in ledger.list_candidates("exp", 0))


def test_a_lease_for_the_generation_the_api_serves_gets_work(api):
    assert take(api, generation=0)["descriptor"]["index"] == 0


@pytest.mark.parametrize("bad", ["0", None, 1.5, True])
def test_a_bad_generation_in_a_lease_is_a_bad_request(api, bad):
    assert code_of(call(api, "lease", {"worker_id": "worker-a", "generation": bad})) == "bad_request"


def test_the_worker_passes_the_generation_of_its_job_to_the_lease(api):
    sent = []
    inner = local_transport(api)

    def spy(operation, payload):
        sent.append((operation, payload))
        return inner(operation, payload)

    Worker("worker-a", spy, reward_of).step(generation=0)
    assert sent[0][0] == "lease" and sent[0][1]["generation"] == 0
    Worker("worker-b", spy, reward_of).step()
    lease_payloads = [payload for operation, payload in sent if operation == "lease"]
    assert "generation" not in lease_payloads[-1]
