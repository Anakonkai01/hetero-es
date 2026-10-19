"""
G6 changes to the dispatch policies:
  - Greedy (B3) does not hand a candidate straight back to the worker whose attempt on it just failed, while another worker is around
    to take it (a worker with a broken GPU would otherwise burn the whole retry budget of a candidate); it does hand it back when
    that worker is the only one, or after `patience` refusals (the other worker may be gone);
  - AdmittedOnly refuses an empty or malformed set of workers (it would make every generation wait for ever).
"""
import pytest

from heteroes.dispatch import AdmittedOnly, Greedy
from heteroes.ledger import FailureKind, Ledger
from heteroes.worker_api import WorkerAPI
from ledger_helpers import FakeClock, batch
from test_dispatch import ask, deliver, fail, index_of

LEASE_SECONDS = 30.0


def make(policy, n=3):
    ledger = Ledger(":memory:", clock=FakeClock())
    ledger.open_generation(batch(n))
    return ledger, WorkerAPI(ledger, "exp", 0, lease_seconds=LEASE_SECONDS, policy=policy)


def records(ledger):
    return ledger.list_candidates("exp", 0)


# ---- the ledger tells the policy who failed

def test_the_record_names_the_worker_whose_latest_attempt_failed():
    ledger, api = make(Greedy())
    assert records(ledger)[0].last_failed_worker is None
    work = ask(api, "worker-a")
    assert records(ledger)[0].last_failed_worker is None              # leased, not failed
    fail(api, work, "OUT_OF_MEMORY")
    assert records(ledger)[0].last_failed_worker == "worker-a"
    retry = ask(api, "worker-b")
    assert index_of(retry) == 0 and records(ledger)[0].last_failed_worker is None   # the newer attempt did not fail (yet)


# ---- Greedy

def test_a_failed_candidate_goes_to_another_worker_when_one_is_around():
    ledger, api = make(Greedy(), n=2)
    ask(api, "worker-b")                                              # worker-b has been seen: it will ask again
    work = ask(api, "worker-a")
    fail(api, work, "OUT_OF_MEMORY")                                  # c1 failed on worker-a

    nxt = ask(api, "worker-a")

    assert nxt is None                                                # worker-a is told to wait: c1 is for somebody else
    assert index_of(ask(api, "worker-b")) == 1                       # the other worker takes it


def test_other_candidates_are_still_given_to_the_worker_that_failed():
    ledger, api = make(Greedy(), n=3)
    ask(api, "worker-b")
    fail(api, ask(api, "worker-a"), "OUT_OF_MEMORY")                  # c1 failed on worker-a, c2 is untouched

    assert index_of(ask(api, "worker-a")) == 2


def test_a_lone_worker_gets_its_failed_candidate_back():
    ledger, api = make(Greedy(), n=1)
    fail(api, ask(api, "worker-a"), "OUT_OF_MEMORY")
    retry = ask(api, "worker-a")
    assert index_of(retry) == 0 and retry["attempt_number"] == 2


def test_after_patience_refusals_the_same_worker_may_retry_in_case_the_other_is_gone():
    ledger, api = make(Greedy(patience=3), n=2)
    ask(api, "worker-b")                                              # worker-b asked once and then went away
    fail(api, ask(api, "worker-a"), "OUT_OF_MEMORY")
    assert [ask(api, "worker-a") for _ in range(3)] == [None, None, None]
    retry = ask(api, "worker-a")
    assert index_of(retry) == 1 and retry["attempt_number"] == 2


def test_the_patience_is_counted_again_for_each_new_failure():
    ledger, api = make(Greedy(patience=1), n=2)
    ask(api, "worker-b")
    fail(api, ask(api, "worker-a"), "OUT_OF_MEMORY")                  # first failure of c1 on worker-a
    assert ask(api, "worker-a") is None                               # one refusal ...
    again = ask(api, "worker-a")
    assert index_of(again) == 1                                       # ... then it may retry
    fail(api, again, "OUT_OF_MEMORY")                                 # and fails again: the count starts from zero
    assert ask(api, "worker-a") is None
    assert index_of(ask(api, "worker-a")) == 1


def test_greedy_still_gives_the_first_waiting_candidate_to_whoever_asks_when_nothing_failed():
    ledger, api = make(Greedy(), n=3)
    assert [index_of(ask(api, w)) for w in ("a", "b", "a")] == [0, 1, 2]


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, None])
def test_bad_patience_is_refused(bad):
    with pytest.raises((ValueError, TypeError)):
        Greedy(patience=bad)


# ---- AdmittedOnly

@pytest.mark.parametrize("bad", [[], (), set(), [""], [1], ["a", None], "worker-a"])
def test_admitted_only_refuses_an_empty_or_malformed_set(bad):
    with pytest.raises((ValueError, TypeError)):
        AdmittedOnly(Greedy(), bad)


def test_admitted_only_still_works_with_a_good_set():
    ledger, api = make(AdmittedOnly(Greedy(), ["worker-a"]), n=2)
    assert ask(api, "worker-b") is None
    assert index_of(ask(api, "worker-a")) == 0
