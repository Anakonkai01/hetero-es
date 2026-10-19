"""
The two dispatch policies that the real `WorkerAPI` can use (MASTER baselines):

  B3 `Greedy`      a worker that asks gets the first candidate that is waiting: work goes to whoever is free;
  B1 `StaticWave`  candidates are cut into waves of `wave_size` (the number of workers); a worker takes at most one candidate
                   of a wave, and the next wave starts only when the whole current wave is committed.

What is checked here is who gets what and when. What the ledger owes whichever policy is used (one result per candidate,
nothing invented) is checked elsewhere; the SimPy tests of `test_dispatch_policies.py` compare how the two treat workers of
different speeds on simulated time, this file checks the real objects.
"""
import threading

import pytest

from heteroes.dispatch import Greedy, StaticWave
from heteroes.ledger import FailureKind, GenerationState, Ledger
from heteroes.worker_api import WorkerAPI
from ledger_helpers import FakeClock, batch, descriptor_of

LEASE_SECONDS = 30.0


@pytest.fixture
def clock():
    return FakeClock()


def make(clock, policy, n=6):
    ledger = Ledger(":memory:", clock=clock)
    ledger.open_generation(batch(n))
    return ledger, WorkerAPI(ledger, "exp", 0, lease_seconds=LEASE_SECONDS, policy=policy)


def ask(api, worker):
    reply = api.handle("lease", {"worker_id": worker})
    assert reply["ok"] is True, reply
    return reply["work"]


def index_of(work):
    return None if work is None else work["descriptor"]["index"]


def deliver(api, work, reward=0.5):
    reply = api.handle("submit_result", {"descriptor": work["descriptor"], "attempt_number": work["attempt_number"],
                                         "token": work["token"], "reward": reward})
    assert reply["ok"] is True, reply


def fail(api, work, kind="OTHER"):
    reply = api.handle("report_failure", {"descriptor": work["descriptor"], "attempt_number": work["attempt_number"],
                                          "token": work["token"], "kind": kind})
    assert reply["ok"] is True, reply


# ---------------------------------------------------------------------------
# B3: greedy
# ---------------------------------------------------------------------------

def test_the_default_policy_is_greedy(clock):
    ledger = Ledger(":memory:", clock=clock)
    ledger.open_generation(batch(3))
    api = WorkerAPI(ledger, "exp", 0, lease_seconds=LEASE_SECONDS)

    assert [index_of(ask(api, w)) for w in ("a", "b", "c")] == [0, 1, 2]


def test_greedy_gives_a_free_worker_the_next_candidate_at_once(clock):
    ledger, api = make(clock, Greedy())
    first = ask(api, "fast")
    deliver(api, first)

    assert index_of(ask(api, "fast")) == 1                 # no waiting for anybody
    assert index_of(ask(api, "fast")) == 2                 # a worker may hold several candidates at once, it is the caller's business


def test_greedy_gives_a_retried_candidate_before_a_fresh_one(clock):
    ledger, api = make(clock, Greedy())
    fail(api, ask(api, "a"))

    again = ask(api, "b")

    assert index_of(again) == 0 and again["attempt_number"] == 2


# ---------------------------------------------------------------------------
# B1: static waves
# ---------------------------------------------------------------------------

def test_a_wave_gives_each_worker_one_candidate_and_the_others_wait(clock):
    ledger, api = make(clock, StaticWave(2))

    assert index_of(ask(api, "a")) == 0
    assert index_of(ask(api, "b")) == 1
    third = api.handle("lease", {"worker_id": "c"})
    assert third == {"ok": True, "generation_state": "OPEN", "work": None}          # the wave is full: nothing for c


def test_a_worker_that_is_done_waits_for_the_slow_one_before_the_next_wave(clock):
    ledger, api = make(clock, StaticWave(2))
    fast, slow = ask(api, "fast"), ask(api, "slow")
    deliver(api, fast)

    assert ask(api, "fast") is None                         # c2 is waiting, but the wave of c0 and c1 is not over
    assert ledger.get_candidate("exp/g0/c2").attempts == 0
    deliver(api, slow)

    assert index_of(ask(api, "fast")) == 2                 # the wave is over: the next one starts
    assert index_of(ask(api, "slow")) == 3


def test_a_worker_takes_at_most_one_candidate_per_wave_even_if_it_asks_again(clock):
    ledger, api = make(clock, StaticWave(2))
    only = ask(api, "a")
    assert index_of(only) == 0

    assert ask(api, "a") is None                            # it holds c0: c1 is for the other worker
    deliver(api, only)
    assert ask(api, "a") is None                            # it delivered c0: still no second one in this wave
    assert index_of(ask(api, "b")) == 1


def test_a_failed_candidate_is_retried_inside_its_wave_by_a_worker_that_is_free(clock):
    ledger, api = make(clock, StaticWave(2))
    a, b = ask(api, "a"), ask(api, "b")
    deliver(api, a)
    fail(api, b)                                            # c1 is waiting again, and "a" has already done its part

    assert ask(api, "a") is None
    retry = ask(api, "c")

    assert index_of(retry) == 1 and retry["attempt_number"] == 2


def test_the_worker_whose_attempt_failed_may_take_the_retry(clock):
    ledger, api = make(clock, StaticWave(2))
    ask(api, "a")
    fail(api, ask(api, "b"))

    retry = ask(api, "b")

    assert index_of(retry) == 1 and retry["attempt_number"] == 2


def test_a_lease_that_ran_out_blocks_its_wave_only_until_somebody_retakes_it(clock):
    ledger, api = make(clock, StaticWave(2))
    deliver(api, ask(api, "a"))
    ask(api, "b")                                           # c1 is taken and never delivered
    clock.advance(LEASE_SECONDS)

    retry = ask(api, "a")                                   # "a" has done its part; the retry is not for it

    assert retry is None
    assert index_of(ask(api, "c")) == 1


def test_the_waves_are_cut_by_index_and_the_last_one_may_be_smaller(clock):
    ledger, api = make(clock, StaticWave(2), n=5)
    order = []
    for _ in range(3):
        wave = [ask(api, "a"), ask(api, "b")]
        order.append([index_of(w) for w in wave])
        for work in wave:
            if work is not None:
                deliver(api, work)

    assert order == [[0, 1], [2, 3], [4, None]]
    assert api.handle("lease", {"worker_id": "a"})["generation_state"] == "COMPLETE"


def test_a_wave_of_one_is_a_sequence_a_wave_as_wide_as_the_generation_is_everything_at_once(clock):
    ledger, api = make(clock, StaticWave(1), n=3)
    first = ask(api, "a")
    assert ask(api, "b") is None                            # one at a time in the whole cluster
    deliver(api, first)
    assert index_of(ask(api, "b")) == 1

    ledger, api = make(clock, StaticWave(3), n=3)
    assert [index_of(ask(api, w)) for w in ("a", "b", "c")] == [0, 1, 2]


@pytest.mark.parametrize("size", [0, -1, 1.5, "2", None, True])
def test_the_size_of_a_wave_must_be_a_positive_integer(size):
    with pytest.raises((TypeError, ValueError)):
        StaticWave(size)


def test_a_policy_is_told_about_the_leases_it_gave(clock):
    seen = []

    class Spy(Greedy):
        def leased(self, candidate_id, worker_id):
            seen.append((candidate_id, worker_id))

    ledger, api = make(clock, Spy())
    ask(api, "a")
    ask(api, "b")

    assert seen == [("exp/g0/c0", "a"), ("exp/g0/c1", "b")]


# ---------------------------------------------------------------------------
# the API serves one request at a time, so "pick, then lease" is not a race
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("policy", [Greedy, lambda: StaticWave(8)])
def test_many_threads_asking_at_once_each_get_a_different_candidate_and_no_error(policy):
    ledger = Ledger(":memory:", clock=FakeClock())
    ledger.open_generation(batch(8))
    api = WorkerAPI(ledger, "exp", 0, lease_seconds=LEASE_SECONDS, policy=policy())
    start = threading.Barrier(8)
    replies = []
    guard = threading.Lock()

    def worker(name):
        start.wait(timeout=30)
        reply = api.handle("lease", {"worker_id": name})
        with guard:
            replies.append(reply)

    threads = [threading.Thread(target=worker, args=(f"w{i}",), daemon=True) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(replies) == 8 and all(reply["ok"] is True for reply in replies), replies
    assert sorted(index_of(reply["work"]) for reply in replies) == list(range(8))
