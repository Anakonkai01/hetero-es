"""
B4 `GreedyTail`: greedy dispatch that does not give a slow worker a candidate near the end of a generation, when the fast worker would
finish it sooner. The slow worker holding the LAST candidate is what makes a generation wait for it (the tail), and with a 10 times slower
GPU that cost is as large as what the GPU adds. The rule is checked here with exact numbers; `SpeedBook` keeps the durations it learns.
"""
import pytest

from heteroes.dispatch import Greedy, GreedyTail, SpeedBook
from heteroes.ledger import Ledger
from heteroes.worker_api import WorkerAPI
from ledger_helpers import FakeClock, batch
from test_dispatch import ask, deliver, fail, index_of

LEASE_SECONDS = 30.0


class Clock(FakeClock):
    pass


def make(n=12, fast=1.0, slow=10.0, margin=1.0, active_window=30.0, observed=True):
    clock = Clock()
    book = SpeedBook(alpha=1.0)                                   # alpha 1: the estimate is the last duration, easy to compute by hand
    if observed:
        book.observe("fast", fast)
        book.observe("slow", slow)
    ledger = Ledger(":memory:", clock=clock)
    ledger.open_generation(batch(n))
    policy = GreedyTail(book, clock=clock, margin=margin, active_window=active_window)
    api = WorkerAPI(ledger, "exp", 0, lease_seconds=LEASE_SECONDS, policy=policy)
    policy._seen["fast"] = clock()                                # the fast worker has been seen (it is alive)
    return clock, book, ledger, api, policy


# ---- SpeedBook

def test_speed_book_is_an_exponential_moving_average():
    book = SpeedBook(alpha=0.5)
    assert book.estimate("w") is None
    book.observe("w", 10.0)
    assert book.estimate("w") == 10.0
    book.observe("w", 20.0)                                       # 0.5 * 20 + 0.5 * 10
    assert book.estimate("w") == 15.0
    book.observe("w", 15.0)
    assert book.estimate("w") == 15.0


def test_speed_book_prior_and_workers():
    book = SpeedBook(prior={"a": 2.0, "b": 5.0})
    assert book.estimate("a") == 2.0 and sorted(book.workers()) == ["a", "b"]


@pytest.mark.parametrize("bad", [0, -1.0, float("nan"), float("inf"), True, "3"])
def test_speed_book_refuses_bad_durations(bad):
    with pytest.raises((ValueError, TypeError)):
        SpeedBook().observe("w", bad)
    with pytest.raises((ValueError, TypeError)):
        SpeedBook(prior={"w": bad})


@pytest.mark.parametrize("bad", [0, -0.1, 1.5, True])
def test_speed_book_alpha_is_in_0_1(bad):
    with pytest.raises((ValueError, TypeError)):
        SpeedBook(alpha=bad)


# ---- the rule, by hand: fast 1 s, slow 10 s, one fast worker. The slow worker takes a candidate iff (ceil(p / 1) + 1) * 1 >= 10,
#      p being the number of candidates waiting: p >= 9.

@pytest.mark.parametrize("waiting,takes", [(12, True), (10, True), (9, True), (8, False), (4, False), (1, False)])
def test_the_slow_worker_takes_a_candidate_only_while_many_are_waiting(waiting, takes):
    clock, book, ledger, api, policy = make(n=12)
    # lease (12 - waiting) candidates to the fast worker, so that `waiting` are left; they stay leased (in flight)
    for _ in range(12 - waiting):
        assert ask(api, "fast") is not None
        policy._seen["fast"] = clock()
    work = ask(api, "slow")
    assert (work is not None) is takes


def test_the_decision_uses_the_margin():
    # p = 5: (5 + 1) * 1 = 6 < 10: declined with margin 1; with margin 0.5 the slow worker's time counts as 5: 6 < 5 is false: it takes it
    clock, book, ledger, api, policy = make(n=12, margin=1.0)
    for _ in range(7):
        ask(api, "fast")
    assert ask(api, "slow") is None
    clock, book, ledger, api, policy = make(n=12, margin=0.5)
    for _ in range(7):
        ask(api, "fast")
    assert ask(api, "slow") is not None


def test_two_fast_workers_share_the_waiting_candidates_in_the_estimate():
    # fast ones: 1 s each (two of them). p = 6: ceil(6 / 2) + 1 = 4 -> 4 s < 10: the slow worker waits; p = 18 would be ceil(18/2)+1 = 10 -> takes
    clock, book, ledger, api, policy = make(n=24)
    book.observe("fast2", 1.0)
    policy._seen["fast2"] = clock()
    for _ in range(18):
        ask(api, "fast")
        policy._seen["fast"] = clock()
    assert ask(api, "slow") is None                               # 6 waiting
    clock, book, ledger, api, policy = make(n=24)
    book.observe("fast2", 1.0)
    policy._seen["fast2"] = clock()
    for _ in range(6):
        ask(api, "fast")
    assert ask(api, "slow") is not None                           # 18 waiting


# ---- when it must NOT decline

def test_a_worker_with_no_estimate_takes_work_to_learn_its_speed():
    clock, book, ledger, api, policy = make(n=12, observed=False)
    for _ in range(11):
        ask(api, "fast")
    assert ask(api, "newcomer") is not None                       # one candidate left, but nobody knows how fast it is


def test_the_slow_worker_takes_work_when_it_is_alone():
    clock, book, ledger, api, policy = make(n=3)
    policy._seen.clear()                                          # the fast worker has never asked: nobody else is known to be alive
    assert ask(api, "slow") is not None


def test_a_fast_worker_that_has_not_been_seen_for_a_while_is_not_waited_for():
    clock, book, ledger, api, policy = make(n=12, active_window=20.0)       # shorter than the lease (30 s): the 11 leases below stay valid
    for _ in range(11):
        ask(api, "fast")
    assert ask(api, "slow") is None                               # the fast worker is alive: wait for it
    clock.advance(21.0)                                           # but it went silent (a crash, a cut cable): the slow one takes the last candidate
    work = ask(api, "slow")
    assert work is not None and index_of(work) == 11              # candidate 11 (the only one waiting: the others are still leased)


def test_a_fast_worker_is_never_held_back_by_a_slower_one():
    clock, book, ledger, api, policy = make(n=12)
    policy._seen["slow"] = clock()
    for _ in range(11):
        assert ask(api, "fast") is not None                       # the slow worker is alive and has the larger estimate: the fast one just works


def test_the_same_rule_does_not_stop_the_failed_candidate_logic_of_greedy():
    # a candidate that just failed on a worker is still not handed straight back to it (Greedy's rule, which GreedyTail keeps)
    clock, book, ledger, api, policy = make(n=2)
    work = ask(api, "fast")
    fail(api, work, "OUT_OF_MEMORY")
    policy._seen["slow"] = clock()
    assert ask(api, "fast") is not None                           # c1 is for fast too: the other candidate (c1) is untouched
    assert index_of(ask(api, "slow")) in (0, None)


# ---- learning from the results

def test_a_committed_result_teaches_the_book_the_duration_of_the_worker():
    clock, book, ledger, api, policy = make(n=3, observed=False)
    work = ask(api, "w")
    clock.advance(4.0)
    deliver(api, work)
    assert book.estimate("w") == 4.0


def test_a_failure_and_an_already_committed_repeat_teach_nothing():
    clock, book, ledger, api, policy = make(n=3, observed=False)
    work = ask(api, "w")
    clock.advance(4.0)
    fail(api, work, "OUT_OF_MEMORY")
    assert book.estimate("w") is None
    work = ask(api, "w")
    clock.advance(2.0)
    deliver(api, work)
    assert book.estimate("w") == 2.0
    clock.advance(50.0)
    deliver(api, work)                                            # the same result again: acknowledged, not a new measurement
    assert book.estimate("w") == 2.0


def test_a_policy_without_committed_still_works_with_the_api():
    # Greedy has no `committed` method: the API must not require it
    ledger = Ledger(":memory:", clock=FakeClock())
    ledger.open_generation(batch(2))
    api = WorkerAPI(ledger, "exp", 0, lease_seconds=LEASE_SECONDS, policy=Greedy())
    deliver(api, ask(api, "a"))


def test_a_worker_seen_exactly_one_window_ago_is_still_waited_for():
    clock, book, ledger, api, policy = make(n=12, active_window=20.0)       # shorter than the lease (30 s), so the leases are still valid
    for _ in range(11):
        ask(api, "fast")
    clock.advance(20.0)                                           # exactly the window: the fast worker is still counted as alive
    assert ask(api, "slow") is None
