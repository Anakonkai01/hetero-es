from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from heteroes.es.update import standardize_rewards
from heteroes.ledger import (
    AlreadyLeasedError,
    FailureKind,
    GenerationFailedError,
    GenerationNotCompleteError,
    GenerationResults,
    GenerationState,
    GenerationStatus,
    Ledger,
    LedgerError,
    RetriesExhaustedError,
    SubmitOutcome,
)
from ledger_helpers import FakeClock, batch, fail, lease, make, record, submit

RECIPE = "a" * 64
PARENT = "b" * 64


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def ledger(clock):
    with Ledger(":memory:", clock=clock) as opened:
        opened.open_generation(batch(3))
        yield opened


def status(ledger, experiment_id="exp", generation=0):
    return ledger.get_generation_status(experiment_id, generation)


def exhaust(ledger, index, attempts=3):
    """Use up the attempts of one candidate with failures (the candidate is free again after each one)."""
    for _ in range(attempts):
        fail(ledger, lease(ledger, index))


def exhaust_by_expiry(ledger, clock, index, attempts=3):
    """The same, but the workers just disappear: every lease runs out."""
    for _ in range(attempts):
        clock.now = lease(ledger, index).deadline


# ---------------------------------------------------------------------------
# the state of a generation, computed from its candidates
# ---------------------------------------------------------------------------

def test_a_generation_nobody_worked_on_is_open(ledger):
    assert status(ledger) == GenerationStatus(state=GenerationState.OPEN, committed=0, total=3, exhausted=())


def test_a_generation_with_some_results_is_open(ledger):
    submit(ledger, lease(ledger, 0))
    lease(ledger, 1)

    assert status(ledger) == GenerationStatus(GenerationState.OPEN, committed=1, total=3, exhausted=())


def test_a_generation_is_complete_when_every_candidate_is_committed(ledger):
    for index in range(3):
        submit(ledger, lease(ledger, index))

    assert status(ledger) == GenerationStatus(GenerationState.COMPLETE, committed=3, total=3, exhausted=())


def test_the_order_of_the_commits_does_not_matter(ledger):
    leases = [lease(ledger, index) for index in range(3)]

    for index in (2, 0, 1):
        assert status(ledger).state is GenerationState.OPEN
        submit(ledger, leases[index])

    assert status(ledger).state is GenerationState.COMPLETE


def test_a_candidate_that_used_all_its_attempts_makes_the_generation_failed(ledger):
    exhaust(ledger, 1)

    assert status(ledger) == GenerationStatus(GenerationState.FAILED, committed=0, total=3, exhausted=("exp/g0/c1",))


def test_workers_that_vanish_exhaust_a_candidate_just_the_same(ledger, clock):
    exhaust_by_expiry(ledger, clock, 2)

    assert status(ledger) == GenerationStatus(GenerationState.FAILED, committed=0, total=3, exhausted=("exp/g0/c2",))


def test_the_last_attempt_may_still_deliver_so_the_generation_is_open_until_its_lease_is_over(ledger, clock):
    fail(ledger, lease(ledger, 1))
    fail(ledger, lease(ledger, 1))
    last = lease(ledger, 1)                                        # the third and last attempt, deadline 1030.0

    clock.now = 1029.5
    assert status(ledger).state is GenerationState.OPEN

    clock.now = 1030.0
    assert status(ledger).state is GenerationState.FAILED


def test_the_last_attempt_that_delivers_in_time_saves_the_generation(ledger):
    fail(ledger, lease(ledger, 1))
    fail(ledger, lease(ledger, 1))
    last = lease(ledger, 1)

    submit(ledger, last)

    assert status(ledger).state is GenerationState.OPEN and status(ledger).committed == 1
    assert status(ledger).exhausted == ()


def test_one_exhausted_candidate_fails_the_generation_even_if_all_the_others_committed(ledger):
    submit(ledger, lease(ledger, 0))
    submit(ledger, lease(ledger, 2))
    exhaust(ledger, 1)

    assert status(ledger) == GenerationStatus(GenerationState.FAILED, committed=2, total=3, exhausted=("exp/g0/c1",))


def test_all_the_exhausted_candidates_are_named_in_index_order(clock):
    with Ledger(":memory:", clock=clock, max_attempts=1) as ledger:
        ledger.open_generation(batch(4))
        for index in (3, 1):                                       # both leases are given while the generation is still open
            lease(ledger, index)
        assert status(ledger).state is GenerationState.OPEN

        clock.now = 1030.0

        assert status(ledger) == GenerationStatus(GenerationState.FAILED, 0, 4, ("exp/g0/c1", "exp/g0/c3"))


def test_the_budget_is_the_one_the_ledger_was_given(clock):
    with Ledger(":memory:", clock=clock, max_attempts=1) as ledger:
        ledger.open_generation(batch(2))

        fail(ledger, lease(ledger, 0))

        assert status(ledger).state is GenerationState.FAILED


def test_each_generation_has_its_own_state(ledger, clock):
    ledger.open_generation(batch(2, generation=1))
    ledger.open_generation(batch(2, experiment_id="other"))
    exhaust(ledger, 0)

    assert status(ledger).state is GenerationState.FAILED
    assert status(ledger, generation=1) == GenerationStatus(GenerationState.OPEN, 0, 2, ())
    assert status(ledger, "other", 0) == GenerationStatus(GenerationState.OPEN, 0, 2, ())


def test_the_state_of_an_unknown_generation_is_an_error(ledger):
    with pytest.raises(LedgerError, match="unknown generation"):
        status(ledger, generation=9)
    with pytest.raises(LedgerError, match="unknown generation"):
        status(ledger, "nope", 0)


def test_asking_for_the_state_changes_nothing(ledger, clock):
    held = lease(ledger, 0)
    clock.now = held.deadline

    first, second = status(ledger), status(ledger)

    assert first == second and record(ledger).attempts == 1


def test_the_status_cannot_be_changed(ledger):
    with pytest.raises(FrozenInstanceError):
        status(ledger).state = GenerationState.COMPLETE


def test_a_failed_generation_is_open_again_when_the_budget_is_raised(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock, max_attempts=1) as ledger:
        ledger.open_generation(batch(2))
        fail(ledger, lease(ledger, 0))
        assert status(ledger).state is GenerationState.FAILED

    with Ledger(path, clock=clock, max_attempts=2) as again:
        assert status(again).state is GenerationState.OPEN
        assert lease(again, 0).attempt_number == 2


# ---------------------------------------------------------------------------
# a failed generation hands out no more work
# ---------------------------------------------------------------------------

def test_no_candidate_of_a_failed_generation_can_be_leased(ledger):
    exhaust(ledger, 1)

    for index in (0, 2):
        with pytest.raises(GenerationFailedError, match="exp/g0/c1"):
            lease(ledger, index)

    assert [r.attempts for r in ledger.list_candidates("exp", 0)] == [0, 3, 0]


def test_the_exhausted_candidate_itself_is_still_reported_as_exhausted(ledger):
    exhaust(ledger, 1)

    with pytest.raises(RetriesExhaustedError):
        lease(ledger, 1)


def test_a_candidate_held_by_a_valid_lease_is_still_reported_as_held(ledger):
    lease(ledger, 0)
    exhaust(ledger, 1)

    with pytest.raises(AlreadyLeasedError):
        lease(ledger, 0)


def test_another_generation_keeps_getting_work(ledger):
    ledger.open_generation(batch(2, generation=1))
    exhaust(ledger, 1)

    assert ledger.lease("exp/g1/c0", "worker-a", 30.0).attempt_number == 1


def test_another_experiment_keeps_getting_work_and_a_failure_elsewhere_does_not_leak(ledger):
    ledger.open_generation(batch(3, experiment_id="other"))
    exhaust(ledger, 1)                                              # exp/g0 failed

    assert ledger.lease("other/g0/c0", "worker-a", 30.0).attempt_number == 1     # other/g0 is not affected

    for _ in range(3):                                              # now other/g0 fails too
        held = ledger.lease("other/g0/c1", "worker-a", 30.0)
        ledger.report_failure(make(1, 1007, experiment_id="other"), held.attempt_number, held.token, FailureKind.OTHER)
    with pytest.raises(GenerationFailedError, match="other/g0/c1"):
        ledger.lease("other/g0/c2", "worker-b", 30.0)


def test_an_attempt_that_was_already_running_can_still_deliver_in_a_failed_generation(ledger):
    running = lease(ledger, 0)
    exhaust(ledger, 1)
    assert status(ledger).state is GenerationState.FAILED

    assert submit(ledger, running, 0.5) is SubmitOutcome.COMMITTED

    assert status(ledger).state is GenerationState.FAILED and status(ledger).committed == 1


def test_the_error_of_a_failed_generation_is_a_ledger_error_of_its_own():
    assert issubclass(GenerationFailedError, LedgerError) and issubclass(GenerationNotCompleteError, LedgerError)
    assert not issubclass(GenerationFailedError, GenerationNotCompleteError)
    assert not issubclass(GenerationFailedError, (AlreadyLeasedError, RetriesExhaustedError))


# ---------------------------------------------------------------------------
# the data of a complete generation, ready for the update
# ---------------------------------------------------------------------------

def commit_all(ledger, rewards, order):
    leases = {index: lease(ledger, index) for index in order}
    for index in order:
        submit(ledger, leases[index], rewards[index])


def test_the_results_come_in_index_order_whatever_the_order_of_the_commits(ledger):
    rewards = {0: 0.5, 1: 0.25, 2: 0.75}
    commit_all(ledger, rewards, order=(2, 0, 1))                    # not the index order

    results = ledger.get_generation_results("exp", 0)

    assert results.seeds == (1000, 1007, 1014)
    assert results.rewards == (0.5, 0.25, 0.75)


def test_the_results_name_the_recipe_and_the_parent_weights(ledger):
    commit_all(ledger, {0: 0.1, 1: 0.2, 2: 0.3}, order=(0, 1, 2))

    results = ledger.get_generation_results("exp", 0)

    assert (results.recipe_hash, results.parent_weights_sha256) == (RECIPE, PARENT)


def test_the_reward_of_a_candidate_is_the_one_of_the_attempt_that_committed(ledger, clock):
    first = lease(ledger, 0)
    clock.now = first.deadline
    second = lease(ledger, 0, worker="worker-b")
    submit(ledger, lease(ledger, 1), 0.25)
    submit(ledger, lease(ledger, 2), 0.75)
    submit(ledger, second, 0.5)

    assert ledger.get_generation_results("exp", 0).rewards == (0.5, 0.25, 0.75)


def test_the_results_have_plain_types_and_cannot_be_changed(ledger):
    commit_all(ledger, {0: 0.5, 1: 0.25, 2: 1}, order=(0, 1, 2))

    results = ledger.get_generation_results("exp", 0)

    assert isinstance(results, GenerationResults)
    assert isinstance(results.seeds, tuple) and all(type(seed) is int for seed in results.seeds)
    assert isinstance(results.rewards, tuple) and all(type(reward) is float for reward in results.rewards)
    with pytest.raises(FrozenInstanceError):
        results.rewards = ()


def test_the_results_feed_the_update_in_the_right_pairing(ledger):
    commit_all(ledger, {0: 0.25, 1: 0.5, 2: 0.75}, order=(1, 2, 0))
    results = ledger.get_generation_results("exp", 0)

    z = standardize_rewards(results.rewards)

    # position i of the seeds and of z are the same candidate: the best reward belongs to the last seed
    assert len(z) == len(results.seeds) == 3
    assert z[0] < z[1] < z[2] and np.isclose(z.sum(), 0.0, atol=1e-6)


def test_the_results_of_an_open_generation_are_refused_not_given_in_part(ledger):
    submit(ledger, lease(ledger, 0))
    submit(ledger, lease(ledger, 1))

    with pytest.raises(GenerationNotCompleteError, match="2 of 3"):
        ledger.get_generation_results("exp", 0)


def test_the_results_of_a_failed_generation_are_refused_and_nothing_is_invented(ledger):
    submit(ledger, lease(ledger, 0))
    exhaust(ledger, 1)

    with pytest.raises(GenerationFailedError, match="exp/g0/c1"):
        ledger.get_generation_results("exp", 0)


def test_the_results_of_an_unknown_generation_are_an_error(ledger):
    with pytest.raises(LedgerError, match="unknown generation"):
        ledger.get_generation_results("exp", 4)


def test_the_results_are_the_same_every_time(ledger):
    commit_all(ledger, {0: 0.5, 1: 0.25, 2: 0.75}, order=(0, 1, 2))

    assert ledger.get_generation_results("exp", 0) == ledger.get_generation_results("exp", 0)


def test_a_generation_with_one_candidate(clock):
    with Ledger(":memory:", clock=clock) as ledger:
        ledger.open_generation([make(0, 77)])
        submit(ledger, lease(ledger, 0), 1, descriptor=make(0, 77))

        results = ledger.get_generation_results("exp", 0)

    assert (results.seeds, results.rewards) == ((77,), (1.0,))


def test_the_results_survive_closing_and_reopening_the_file(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(3))
        commit_all(ledger, {0: 0.5, 1: 0.25, 2: 0.75}, order=(1, 0, 2))

    with Ledger(path, clock=clock) as again:
        assert again.get_generation_results("exp", 0).rewards == (0.5, 0.25, 0.75)
        assert status(again).state is GenerationState.COMPLETE


def test_two_experiments_do_not_mix_their_results(ledger):
    ledger.open_generation([make(0, 5, experiment_id="other"), make(1, 6, experiment_id="other")])
    commit_all(ledger, {0: 0.5, 1: 0.25, 2: 0.75}, order=(0, 1, 2))
    for index, reward in ((0, 0.0), (1, 1.0)):
        other = ledger.lease(f"other/g0/c{index}", "worker-a", 30.0)
        ledger.submit_result(make(index, 5 + index, experiment_id="other"), other.attempt_number, other.token, reward)

    assert ledger.get_generation_results("other", 0).rewards == (0.0, 1.0)
    assert ledger.get_generation_results("other", 0).seeds == (5, 6)
    assert ledger.get_generation_results("exp", 0).rewards == (0.5, 0.25, 0.75)
