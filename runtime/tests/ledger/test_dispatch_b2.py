"""
B2 `StaticProportional` and the `AdmittedOnly` wrapper, on the real `WorkerAPI` (who gets what and when), and `proportional_quotas`,
the rounding rule that makes the quotas add up to N. The oracle for the quotas is an exact-fraction computation (no floats).
"""
import itertools
from fractions import Fraction

import pytest

from heteroes.dispatch import AdmittedOnly, Greedy, StaticProportional, proportional_quotas
from heteroes.ledger import Ledger
from heteroes.worker_api import WorkerAPI
from ledger_helpers import FakeClock, batch
from test_dispatch import ask, deliver, index_of

LEASE_SECONDS = 30.0


def make(policy, n=8):
    ledger = Ledger(":memory:", clock=FakeClock())
    ledger.open_generation(batch(n))
    return ledger, WorkerAPI(ledger, "exp", 0, lease_seconds=LEASE_SECONDS, policy=policy)


# ---------------------------------------------------------------------------
# proportional_quotas
# ---------------------------------------------------------------------------

def oracle(n, speeds):
    """Largest remainder with exact fractions; ties to the smaller id."""
    total = sum(Fraction(s) for s in speeds.values())
    share = {w: n * Fraction(s) / total for w, s in speeds.items()}
    quota = {w: share[w].numerator // share[w].denominator for w in speeds}
    for w in sorted(speeds, key=lambda w: (-(share[w] - quota[w]), w))[:n - sum(quota.values())]:
        quota[w] += 1
    return quota


def test_the_worked_example_of_the_docstring():
    assert proportional_quotas(8, {"fast": 4, "slow": 1}) == {"fast": 6, "slow": 2}


def test_equal_speeds_split_evenly_and_a_remainder_goes_to_the_smaller_id():
    assert proportional_quotas(8, {"b": 1, "a": 1}) == {"a": 4, "b": 4}
    assert proportional_quotas(7, {"b": 1, "a": 1}) == {"a": 4, "b": 3}
    assert proportional_quotas(1, {"b": 2.5, "a": 2.5, "c": 2.5}) == {"a": 1, "b": 0, "c": 0}


def test_the_quotas_always_add_up_to_n_and_match_the_exact_oracle():
    speed_sets = [{"a": 1, "b": 1}, {"a": 4, "b": 1}, {"a": 0.2, "b": 0.05}, {"a": 3, "b": 1, "c": 1}, {"a": 1}, {"a": 7, "b": 1, "c": 2, "d": 2}]
    for n, speeds in itertools.product(range(1, 40), speed_sets):
        quotas = proportional_quotas(n, speeds)
        assert sum(quotas.values()) == n, (n, speeds)
        assert quotas == oracle(n, speeds), (n, speeds)
        assert all(quotas[w] >= int(n * Fraction(s) / sum(Fraction(x) for x in speeds.values())) for w, s in speeds.items())      # no one below the floor


def test_a_faster_worker_never_gets_fewer_candidates_than_a_slower_one():
    for n in range(1, 40):
        quotas = proportional_quotas(n, {"fast": 4.4, "slow": 1.0})
        assert quotas["fast"] >= quotas["slow"]


@pytest.mark.parametrize("n", [0, -1, 1.0, True, "8"])
def test_a_bad_candidate_count_is_refused(n):
    with pytest.raises(ValueError):
        proportional_quotas(n, {"a": 1})


@pytest.mark.parametrize("speeds", [{}, {"a": 0}, {"a": -1}, {"a": float("nan")}, {"a": float("inf")}, {"a": True}, {"a": "1"}])
def test_bad_speeds_are_refused(speeds):
    with pytest.raises(ValueError):
        proportional_quotas(8, speeds)


# ---------------------------------------------------------------------------
# B2
# ---------------------------------------------------------------------------

def test_each_worker_runs_only_its_own_block_one_after_the_other_without_waiting():
    ledger, api = make(StaticProportional({"fast": 6, "slow": 2}))
    seen = {"fast": [], "slow": []}

    for _ in range(6):                                      # fast does its six, one by one, while slow has not even started
        work = ask(api, "fast")
        seen["fast"].append(index_of(work))
        deliver(api, work)
    assert ask(api, "fast") is None                         # its quota is done: it does NOT take the slow worker's candidates
    for _ in range(2):
        work = ask(api, "slow")
        seen["slow"].append(index_of(work))
        deliver(api, work)

    assert seen == {"fast": [0, 1, 2, 3, 4, 5], "slow": [6, 7]}         # blocks in the order of the worker ids ("fast" < "slow")


def test_the_blocks_follow_the_sorted_worker_ids():
    ledger, api = make(StaticProportional({"b": 3, "a": 5}))

    assert [index_of(ask(api, "a")) for _ in range(5)] == [0, 1, 2, 3, 4]
    assert [index_of(ask(api, "b")) for _ in range(3)] == [5, 6, 7]


def test_a_worker_with_no_quota_or_unknown_gets_nothing():
    ledger, api = make(StaticProportional({"a": 8, "b": 0}))

    assert ask(api, "b") is None
    assert ask(api, "stranger") is None
    assert index_of(ask(api, "a")) == 0


def test_a_failed_candidate_goes_back_to_its_own_worker_not_to_another():
    ledger, api = make(StaticProportional({"a": 4, "b": 4}))
    work = ask(api, "a")
    reply = api.handle("report_failure", {"descriptor": work["descriptor"], "attempt_number": work["attempt_number"],
                                          "token": work["token"], "kind": "OTHER"})
    assert reply["ok"] is True

    again = ask(api, "a")

    assert index_of(again) == 0 and again["attempt_number"] == 2
    assert index_of(ask(api, "b")) == 4                     # b has its own block; it never gets c0


def test_the_quotas_must_add_up_to_the_candidates_of_the_generation():
    ledger, api = make(StaticProportional({"a": 3, "b": 3}))            # 6 quotas, 8 candidates

    with pytest.raises(ValueError, match="add up to 6 but the generation has 8"):
        api.handle("lease", {"worker_id": "a"})


@pytest.mark.parametrize("quotas", [{}, {"a": 0}, {"a": -1}, {"a": 1.0}, {"a": True}])
def test_bad_quotas_are_refused(quotas):
    with pytest.raises(ValueError):
        StaticProportional(quotas)


def test_b2_differs_from_b3_the_premise_of_the_baseline():
    """A fast worker finishing early takes a waiting candidate under B3; under B2 the same candidate waits for its owner."""
    _, greedy_api = make(Greedy())
    _, static_api = make(StaticProportional({"fast": 4, "slow": 4}))
    for api in (greedy_api, static_api):
        for _ in range(4):
            deliver(api, ask(api, "fast"))

    assert index_of(ask(greedy_api, "fast")) == 4
    assert ask(static_api, "fast") is None


# ---------------------------------------------------------------------------
# AdmittedOnly
# ---------------------------------------------------------------------------

def test_only_the_admitted_workers_are_given_work():
    ledger, api = make(AdmittedOnly(Greedy(), ["fast"]))

    assert ask(api, "slow") is None
    assert [index_of(ask(api, "fast")) for _ in range(3)] == [0, 1, 2]       # the slow worker's refused request took nothing


def test_admitted_only_passes_the_choice_and_the_lease_notice_to_the_inner_policy():
    seen = []

    class Spy:
        def pick(self, records, worker_id):
            return records[0]

        def leased(self, candidate_id, worker_id):
            seen.append((candidate_id, worker_id))

    ledger, api = make(AdmittedOnly(Spy(), ["a"]))
    ask(api, "a")
    ask(api, "b")

    assert seen == [("exp/g0/c0", "a")]
