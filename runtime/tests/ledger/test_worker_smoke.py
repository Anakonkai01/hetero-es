"""
Smoke test of the remote-worker abstraction (MASTER Gate G2): fake workers finish one generation by talking to the
coordinator ONLY through JSON messages (`WorkerAPI` on one side, `Worker` + `local_transport` on the other), and the
coordinator then writes and marks the update. No network, no threads, no GPU: the point is that the same `Worker` code
will run unchanged over HTTP, because everything it sends is already JSON.

The expected rewards come from `reward_of`, a function of the seed that the test knows and the ledger does not.
"""
import itertools

import numpy as np
import pytest

from heteroes.generation_record import GenerationRecord
from heteroes.ledger import FailureKind, GenerationState, Ledger, UpdateOutcome
from heteroes.manifest import derive_seed
from heteroes.worker import CandidateFailed, Step, StepKind, Worker, WorkerAPIError, local_transport
from heteroes.worker_api import WorkerAPI
from ledger_helpers import FakeClock, make

LEASE_SECONDS = 30.0
N = 6
ETA = 1e-9
CHILD = "e" * 64


def descriptors():
    return [make(i, derive_seed("exp", 0, i)) for i in range(N)]


def reward_of(descriptor):
    return (descriptor.seed % 97) / 96


class World:
    def __init__(self):
        self.clock = FakeClock()
        self.ledger = Ledger(":memory:", clock=self.clock)
        self.ledger.open_generation(descriptors())
        self.api = WorkerAPI(self.ledger, "exp", 0, lease_seconds=LEASE_SECONDS)
        self.transport = local_transport(self.api)

    def worker(self, name, evaluate=reward_of):
        return Worker(name, self.transport, evaluate)

    def status(self):
        return self.ledger.get_generation_status("exp", 0)

    def close(self):
        self.ledger.close()


@pytest.fixture
def world():
    world = World()
    yield world
    world.close()


def drive(workers, limit=50):
    """Give every worker one turn, over and over, until each one is told the generation is complete (or is put aside)."""
    done = Step(StepKind.NO_WORK, generation_state=GenerationState.COMPLETE)
    log = []
    for _ in range(limit):
        turn = [(worker.worker_id, worker.step()) for worker in workers]
        log.extend(turn)
        if all(step == done or step.kind is StepKind.QUARANTINED for _, step in turn):
            return log
    raise AssertionError("the workers did not finish the generation")


def flaky_once(index):
    """Honest, except that the first time it is given candidate `index` it runs out of memory."""
    seen = set()

    def evaluate(descriptor):
        if descriptor.index == index and index not in seen:
            seen.add(index)
            raise CandidateFailed(FailureKind.OUT_OF_MEMORY, "CUDA out of memory")
        return reward_of(descriptor)

    return evaluate


def expected_rewards():
    return tuple(reward_of(d) for d in descriptors())


def expected_coefficients(rewards):
    r = np.asarray(rewards, dtype=np.float64)
    return (r - r.mean()) / (r.std() + ETA)


# ---------------------------------------------------------------------------

def test_three_workers_finish_a_generation_and_the_update_is_recorded_and_applied(world):
    workers = [world.worker("fast"), world.worker("slow"), world.worker("flaky", flaky_once(2))]

    log = drive(workers)

    assert world.status().state is GenerationState.COMPLETE
    results = world.ledger.get_generation_results("exp", 0)
    assert results.seeds == tuple(d.seed for d in descriptors()) and results.rewards == expected_rewards()

    kinds = [step.kind for _, step in log]
    assert kinds.count(StepKind.COMMITTED) == N                              # one commit per candidate, no more
    assert StepKind.REFUSED not in kinds and StepKind.ALREADY_COMMITTED not in kinds and StepKind.QUARANTINED not in kinds
    failures = [step for _, step in log if step.kind is StepKind.FAILURE_REPORTED]
    assert failures == [Step(StepKind.FAILURE_REPORTED, "exp/g0/c2", failure=FailureKind.OUT_OF_MEMORY)]
    attempts = sorted(r.attempts for r in world.ledger.list_candidates("exp", 0))
    assert attempts == [1] * (N - 1) + [2]                                   # only the failed candidate was tried twice

    record = GenerationRecord.from_results("exp", 0, results, alpha=1e-3, eta=ETA)
    record.verify_coefficients(ETA)
    assert np.allclose(record.coefficients, expected_coefficients(results.rewards), rtol=1e-6, atol=1e-7)
    assert world.ledger.record_update(record) is UpdateOutcome.RECORDED
    assert world.ledger.mark_applied("exp", 0, record.hash, CHILD) is UpdateOutcome.APPLIED
    stored = world.ledger.get_update("exp", 0)
    assert stored.record == record and stored.child_weights_sha256 == CHILD


@pytest.mark.parametrize("order", list(itertools.permutations(range(3))))
def test_the_order_in_which_the_workers_take_their_turns_does_not_change_the_update(order):
    reference = World()
    drive([reference.worker("fast"), reference.worker("slow"), reference.worker("flaky", flaky_once(2))])
    expected = GenerationRecord.from_results("exp", 0, reference.ledger.get_generation_results("exp", 0), 1e-3, ETA)
    reference.close()

    world = World()
    pool = [world.worker("fast"), world.worker("slow"), world.worker("flaky", flaky_once(2))]
    drive([pool[i] for i in order])

    record = GenerationRecord.from_results("exp", 0, world.ledger.get_generation_results("exp", 0), 1e-3, ETA)
    world.close()
    assert record.hash == expected.hash and record.rewards == expected_rewards()


def test_a_worker_that_vanishes_with_a_candidate_is_replaced_and_its_late_answer_is_refused(world):
    ghost = world.worker("ghost")
    leased = ghost.client.lease().assignment                                  # takes candidate 0 and is never heard of again
    assert leased.candidate_id == "exp/g0/c0"
    workers = [world.worker("fast"), world.worker("slow")]

    for _ in range(10):                                                        # candidate 0 is held: they do the others first
        for worker in workers:
            worker.step()
    assert world.status().state is GenerationState.OPEN and world.status().committed == N - 1

    world.clock.advance(LEASE_SECONDS)                                         # its lease runs out
    log = drive(workers)

    assert world.status().state is GenerationState.COMPLETE
    assert world.ledger.get_candidate("exp/g0/c0").result.attempt_number == 2
    assert [s for _, s in log if s.kind is StepKind.REFUSED] == []
    with pytest.raises(WorkerAPIError) as caught:                              # the ghost comes back with an answer
        ghost.client.submit_result(leased, 0.99)
    assert caught.value.code == "stale_attempt"
    assert world.ledger.get_generation_results("exp", 0).rewards == expected_rewards()


def test_a_worker_with_a_broken_restore_is_put_aside_and_the_others_finish(world):
    def restore_broken(descriptor):
        raise CandidateFailed(FailureKind.RESTORE_MISMATCH)

    broken = world.worker("broken", restore_broken)
    others = [world.worker("fast"), world.worker("slow")]

    log = drive([broken] + others)

    assert [q.worker_id for q in world.ledger.list_quarantined()] == ["broken"]
    broken_steps = [step.kind for name, step in log if name == "broken"]
    assert broken_steps[:2] == [StepKind.FAILURE_REPORTED, StepKind.QUARANTINED]
    assert world.ledger.get_generation_results("exp", 0).rewards == expected_rewards()
