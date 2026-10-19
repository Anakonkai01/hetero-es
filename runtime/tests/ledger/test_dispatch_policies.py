"""
Two ways of giving candidates to workers of different speeds, on simulated time: a worker that is free takes the next
one (greedy), or each wave waits for the whole wave (wave). What is checked is what the ledger owes whichever way work is
given: the generation ends right, nothing is counted twice, nothing is invented. The times are those of the simulation: they
show how the two policies treat unequal workers in the model, they are NOT a measurement of anything on real GPUs.
"""
import pytest

pytest.importorskip("simpy")

from harness import check_tables, oracle_reward  # noqa: E402
from heteroes.ledger import GenerationFailedError, GenerationState  # noqa: E402
from ledger_helpers import descriptor_of  # noqa: E402
from sim import Behavior, Cluster, Greedy, Wave  # noqa: E402

POLICIES = {"greedy": Greedy, "wave": Wave}
HONEST = {"fast": Behavior(compute=1.0), "mid": Behavior(compute=3.0), "slow": Behavior(compute=10.0)}


def run(candidates, workers, policy, max_attempts=3):
    cluster = Cluster(candidates=candidates, max_attempts=max_attempts)
    dispatcher = POLICIES[policy]()                   # ONE for the whole cluster: a wave is shared by all the workers
    for name, behavior in workers.items():
        cluster.start(name, behavior, dispatcher)
    cluster.run()
    check_tables(cluster.ledger, max_attempts)
    return cluster


@pytest.mark.parametrize("policy", POLICIES)
def test_either_way_the_generation_ends_complete_with_the_right_results(policy):
    cluster = run(8, HONEST, policy)

    assert cluster.status().state is GenerationState.COMPLETE
    results = cluster.ledger.get_generation_results("exp", 0)
    assert results.rewards == tuple(oracle_reward(descriptor_of(i).seed) for i in range(8))
    assert [r.attempts for r in cluster.ledger.list_candidates("exp", 0)] == [1] * 8      # nobody had to be retried


def test_giving_work_as_soon_as_a_worker_is_free_ends_before_waiting_for_every_wave():
    greedy, wave = run(8, HONEST, "greedy"), run(8, HONEST, "wave")

    assert greedy.makespan() < wave.makespan()        # in this simulation, with these speeds


def test_the_policies_really_differ_in_when_they_give_work():
    greedy, wave = run(8, HONEST, "greedy"), run(8, HONEST, "wave")

    wave_times = {entry[0] for entry in wave.events("lease")}
    greedy_times = {entry[0] for entry in greedy.events("lease")}
    assert wave_times <= {0.0, 10.0, 20.0, 30.0}      # a wave lasts as long as its slowest worker (10 s)
    assert greedy_times - {0.0, 10.0, 20.0, 30.0}     # greedy hands out work at other moments too


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("workers", [
    {"f": Behavior(compute=1.0), "m": Behavior(kind="vanish_after", compute=3.0, after=1), "s": Behavior(kind="oom", compute=10.0)},
    {"f": Behavior(compute=1.0), "g": Behavior(compute=2.0), "m": Behavior(kind="vanish_after", compute=3.0, after=0)},
    {"f": Behavior(compute=2.0), "b": Behavior(kind="restore_broken", compute=1.0), "s": Behavior(compute=7.0)},
    {"o1": Behavior(kind="oom", compute=2.0), "o2": Behavior(kind="oom", compute=3.0), "f": Behavior(compute=1.0)},
])
def test_with_faulty_workers_the_generation_ends_either_complete_or_failed_and_never_wrong(policy, workers):
    cluster = run(6, workers, policy)

    state = cluster.status().state
    assert state in (GenerationState.COMPLETE, GenerationState.FAILED)       # never left open, never stuck
    if state is GenerationState.COMPLETE:
        results = cluster.ledger.get_generation_results("exp", 0)
        assert results.rewards == tuple(oracle_reward(descriptor_of(i).seed) for i in range(6))
    else:
        assert cluster.status().exhausted
        with pytest.raises(GenerationFailedError):
            cluster.ledger.get_generation_results("exp", 0)
    # whatever happened, a committed candidate was committed once and with the right reward
    for record in cluster.ledger.list_candidates("exp", 0):
        if record.result is not None:
            assert record.result.reward == oracle_reward(record.descriptor.seed)
