"""
`Worker.step()`: one turn of a worker: ask for work, run it, then deliver the reward or report why it could not.
`evaluate(descriptor) -> reward` is the only thing that touches a GPU in real life; here it is a plain function.
The worker talks to the coordinator only through a transport, as it will over the network.
"""
import json

import pytest

from heteroes.ledger import FailureKind, GenerationState, Ledger
from heteroes.manifest import CandidateDescriptor
from heteroes.worker import CandidateFailed, Step, StepKind, Worker, WorkerAPIError, local_transport
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


class Calls:
    """An `evaluate` that remembers what it was given."""

    def __init__(self, behave=reward_of):
        self.seen, self.behave = [], behave

    def __call__(self, descriptor):
        self.seen.append(descriptor)
        return self.behave(descriptor)


def make_worker(api, name="worker-a", evaluate=None):
    evaluate = Calls() if evaluate is None else evaluate
    return Worker(name, local_transport(api), evaluate), evaluate


def failure_kind_of(ledger, index=0):
    return ledger._db.execute("SELECT failure_kind FROM attempt WHERE candidate_id = ? ORDER BY attempt_number DESC",
                              (f"exp/g0/c{index}",)).fetchone()[0]


# ---------------------------------------------------------------------------
# a normal turn
# ---------------------------------------------------------------------------

def test_a_step_runs_the_candidate_and_delivers_the_reward(api, ledger):
    worker, evaluate = make_worker(api)

    step = worker.step()

    assert step == Step(StepKind.COMMITTED, "exp/g0/c0")
    assert evaluate.seen == [descriptor_of(0)] and isinstance(evaluate.seen[0], CandidateDescriptor)
    record = ledger.get_candidate("exp/g0/c0")
    assert record.state.name == "COMMITTED" and record.result.reward == reward_of(descriptor_of(0))


def test_steps_go_through_the_generation_in_index_order_and_then_there_is_no_work(api, ledger):
    worker, evaluate = make_worker(api)

    steps = [worker.step() for _ in range(4)]

    assert steps[:3] == [Step(StepKind.COMMITTED, f"exp/g0/c{i}") for i in range(3)]
    assert steps[3] == Step(StepKind.NO_WORK, generation_state=GenerationState.COMPLETE)
    assert [d.index for d in evaluate.seen] == [0, 1, 2]
    results = ledger.get_generation_results("exp", 0)
    assert results.rewards == tuple(reward_of(descriptor_of(i)) for i in range(3))


@pytest.mark.parametrize("reward", [0, 1, 0.0, 0.25, -0.5])
def test_integers_and_floats_are_rewards(api, ledger, reward):
    worker, _ = make_worker(api, evaluate=Calls(lambda descriptor: reward))

    assert worker.step().kind is StepKind.COMMITTED
    assert ledger.get_candidate("exp/g0/c0").result.reward == reward


def test_with_every_candidate_held_by_others_there_is_no_work_but_the_generation_is_open(api):
    for _ in range(3):                                                      # another worker takes them straight from the API
        assert api.handle("lease", {"worker_id": "worker-b"})["work"] is not None
    worker, evaluate = make_worker(api)

    step = worker.step()

    assert step == Step(StepKind.NO_WORK, generation_state=GenerationState.OPEN) and evaluate.seen == []


def test_a_failed_generation_gives_no_work_and_says_why(api):
    held = api.handle("lease", {"worker_id": "worker-z"})["work"]
    for i in range(3):                                # a different worker each time: Greedy (G6) does not hand a failed candidate back at once
        work = api.handle("lease", {"worker_id": f"worker-b{i}"})["work"]
        api.handle("report_failure", {"descriptor": work["descriptor"], "attempt_number": work["attempt_number"],
                                      "token": work["token"], "kind": "OTHER"})
    worker, evaluate = make_worker(api)

    assert worker.step() == Step(StepKind.NO_WORK, generation_state=GenerationState.FAILED)
    assert evaluate.seen == [] and held is not None


# ---------------------------------------------------------------------------
# failures are reported, never turned into a reward
# ---------------------------------------------------------------------------

def test_a_failure_of_the_candidate_is_reported_with_its_kind_and_the_next_turn_retries(api, ledger):
    attempts = []

    def sometimes_fails(descriptor):
        attempts.append(descriptor.index)
        if len(attempts) == 1:
            raise CandidateFailed(FailureKind.OUT_OF_MEMORY, "CUDA out of memory")
        return reward_of(descriptor)

    worker, _ = make_worker(api, evaluate=sometimes_fails)

    first = worker.step()

    assert first == Step(StepKind.FAILURE_REPORTED, "exp/g0/c0", failure=FailureKind.OUT_OF_MEMORY)
    record = ledger.get_candidate("exp/g0/c0")
    assert record.state.name == "PENDING" and record.result is None and failure_kind_of(ledger) == "OUT_OF_MEMORY"

    second = worker.step()

    assert second == Step(StepKind.COMMITTED, "exp/g0/c0")
    assert ledger.get_candidate("exp/g0/c0").result.attempt_number == 2


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), None, True, False, "0.5", [0.5], {"r": 1}])
def test_a_reward_that_is_not_a_finite_number_is_reported_as_a_verifier_error_not_sent(api, ledger, bad):
    worker, _ = make_worker(api, evaluate=Calls(lambda descriptor: bad))

    step = worker.step()

    assert step == Step(StepKind.FAILURE_REPORTED, "exp/g0/c0", failure=FailureKind.VERIFIER_ERROR)
    record = ledger.get_candidate("exp/g0/c0")
    assert record.result is None and record.state.name == "PENDING" and failure_kind_of(ledger) == "VERIFIER_ERROR"


def test_an_unexpected_exception_is_not_swallowed_and_the_candidate_is_released_at_once(api, ledger, clock):
    def boom(descriptor):
        raise RuntimeError("bug in the evaluator")

    worker, _ = make_worker(api, evaluate=boom)

    with pytest.raises(RuntimeError, match="bug in the evaluator"):
        worker.step()

    record = ledger.get_candidate("exp/g0/c0")
    # G6: it used to stay LEASED until the lease ran out; now it is reported as OTHER and is free for another worker at once
    assert record.state.name == "PENDING" and record.result is None and failure_kind_of(ledger) == "OTHER"


def test_a_failed_restore_is_reported_and_the_next_turn_finds_the_worker_in_quarantine(api, ledger):
    def restore_broken(descriptor):
        raise CandidateFailed(FailureKind.RESTORE_MISMATCH)

    worker, evaluate = make_worker(api, evaluate=Calls(restore_broken))

    assert worker.step() == Step(StepKind.FAILURE_REPORTED, "exp/g0/c0", failure=FailureKind.RESTORE_MISMATCH)
    after = worker.step()

    assert after == Step(StepKind.QUARANTINED, code="worker_quarantined")
    assert len(evaluate.seen) == 1                                          # it was given nothing more to run
    assert [q.worker_id for q in ledger.list_quarantined()] == ["worker-a"]


# ---------------------------------------------------------------------------
# refusals: a result that is not accepted is not an exception
# ---------------------------------------------------------------------------

def test_a_slow_worker_whose_lease_was_taken_over_is_refused_and_the_other_result_stays(api, ledger, clock):
    quick, _ = make_worker(api, "worker-quick")

    def slow_evaluate(descriptor):
        clock.advance(LEASE_SECONDS)                                        # the lease runs out while it computes...
        assert quick.step() == Step(StepKind.COMMITTED, "exp/g0/c0")        # ...and another worker takes the candidate
        return 0.9

    slow, _ = make_worker(api, "worker-slow", Calls(slow_evaluate))

    step = slow.step()

    assert step == Step(StepKind.REFUSED, "exp/g0/c0", code="stale_attempt")
    record = ledger.get_candidate("exp/g0/c0")
    assert record.result.attempt_number == 2 and record.result.reward == reward_of(descriptor_of(0))


def test_a_slow_worker_that_nobody_replaced_still_delivers(api, ledger, clock):
    def slow_evaluate(descriptor):
        clock.advance(10 * LEASE_SECONDS)
        return reward_of(descriptor)

    worker, _ = make_worker(api, evaluate=Calls(slow_evaluate))

    assert worker.step() == Step(StepKind.COMMITTED, "exp/g0/c0")
    assert ledger.get_candidate("exp/g0/c0").result.attempt_number == 1


def test_a_worker_put_in_quarantine_while_it_computes_is_told_when_it_delivers(api, ledger):
    held = api.handle("lease", {"worker_id": "worker-a"})["work"]           # candidate 0, held by worker-a

    def restore_fails_elsewhere(descriptor):
        reply = api.handle("report_failure", {"descriptor": held["descriptor"], "attempt_number": 1,
                                              "token": held["token"], "kind": "RESTORE_MISMATCH"})
        assert reply == {"ok": True}
        return reward_of(descriptor)

    worker, _ = make_worker(api, "worker-a", Calls(restore_fails_elsewhere))

    step = worker.step()

    assert step == Step(StepKind.QUARANTINED, "exp/g0/c1", code="worker_quarantined")
    assert ledger.get_candidate("exp/g0/c1").state.name == "LEASED" and ledger.get_candidate("exp/g0/c1").result is None


def test_a_failure_report_that_is_refused_is_a_refusal_too(api, ledger, clock):
    quick, _ = make_worker(api, "worker-quick")

    def slow_fails(descriptor):
        clock.advance(LEASE_SECONDS)
        quick.step()
        raise CandidateFailed(FailureKind.OUT_OF_MEMORY)

    slow, _ = make_worker(api, "worker-slow", Calls(slow_fails))

    assert slow.step() == Step(StepKind.REFUSED, "exp/g0/c0", code="stale_attempt", failure=FailureKind.OUT_OF_MEMORY)
    assert ledger.get_candidate("exp/g0/c0").state.name == "COMMITTED"


def test_a_request_the_coordinator_calls_malformed_is_an_error_and_not_a_refusal(api):
    worker, _ = make_worker(api, name="")

    with pytest.raises(WorkerAPIError) as caught:
        worker.step()

    assert caught.value.code == "bad_request"


def test_a_transport_that_resends_after_a_lost_acknowledgement_gets_the_already_committed_answer(api, ledger):
    inner = local_transport(api)

    def resending(operation, payload):
        reply = inner(operation, payload)
        if operation == "submit_result":
            assert reply["outcome"] == "COMMITTED"                         # the first delivery committed; its answer is "lost"
            reply = inner(operation, payload)
        return reply

    worker = Worker("worker-a", resending, Calls())

    step = worker.step()

    assert step == Step(StepKind.ALREADY_COMMITTED, "exp/g0/c0")
    record = ledger.get_candidate("exp/g0/c0")
    assert record.result.reward == reward_of(descriptor_of(0)) and record.attempts == 1


@pytest.mark.parametrize("operation, field", [("submit_result", "token"), ("report_failure", "kind")])
def test_a_request_the_coordinator_cannot_read_is_a_bug_to_raise_not_a_refusal_to_step_over(api, ledger, operation, field):
    inner = local_transport(api)

    def corrupting(op, payload):
        if op == operation:
            payload = {key: value for key, value in payload.items() if key != field}
        return inner(op, payload)

    def evaluate(descriptor):
        if operation == "report_failure":
            raise CandidateFailed(FailureKind.OTHER)
        return reward_of(descriptor)

    worker = Worker("worker-a", corrupting, evaluate)

    with pytest.raises(WorkerAPIError) as caught:
        worker.step()

    assert caught.value.code == "bad_request"
    assert ledger.get_candidate("exp/g0/c0").result is None


def test_the_worker_sends_only_json_to_the_coordinator(api):
    sent = []
    inner = local_transport(api)

    def spy(operation, payload):
        sent.append(payload)
        return inner(operation, payload)

    worker = Worker("worker-a", spy, Calls())
    for _ in range(4):
        worker.step()

    assert len(sent) == 7                                                   # 3 x (lease, result) and the last lease
    assert all(json.loads(json.dumps(payload)) == payload for payload in sent)


@pytest.mark.parametrize("direction", ["request", "reply"])
def test_the_local_transport_refuses_a_number_json_cannot_carry_in_either_direction(direction):
    class Echo:
        def handle(self, operation, request):
            return {"ok": True, "value": float("nan")} if direction == "reply" else {"ok": True}

    transport = local_transport(Echo())
    payload = {"value": float("nan")} if direction == "request" else {"value": 1.0}

    with pytest.raises(ValueError):
        transport("lease", payload)
