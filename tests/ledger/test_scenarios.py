"""The six scenarios of MASTER section 22.4 (and the quarantine), with fake workers on simulated time."""
import itertools

import pytest

pytest.importorskip("simpy")

from harness import check_tables, oracle_reward  # noqa: E402
from heteroes.ledger import (  # noqa: E402
    CandidateState,
    GenerationFailedError,
    GenerationState,
    QuarantineRecord,
)
from ledger_helpers import descriptor_of  # noqa: E402
from sim import Behavior, Cluster, Greedy  # noqa: E402


def expected_rewards(candidates):
    return tuple(oracle_reward(descriptor_of(i).seed) for i in range(candidates))


def run(candidates, workers, max_attempts=3, dispatcher=Greedy):
    cluster = Cluster(candidates=candidates, max_attempts=max_attempts)
    shared = dispatcher()                             # one for the whole cluster
    for name, behavior in workers.items():
        cluster.start(name, behavior, shared)
    cluster.run()
    check_tables(cluster.ledger, max_attempts)
    return cluster


def assert_complete_and_right(cluster):
    assert cluster.status().state is GenerationState.COMPLETE
    results = cluster.ledger.get_generation_results("exp", 0)
    assert results.rewards == expected_rewards(cluster.candidates)
    assert results.seeds == tuple(descriptor_of(i).seed for i in range(cluster.candidates))


# ---- 1. the order in which the candidates finish changes, the update does not -------------------------------------------

def test_the_results_do_not_depend_on_who_finishes_first():
    outcomes, orders = [], []
    for speeds in itertools.permutations([1.0, 3.0, 10.0]):
        cluster = run(6, {name: Behavior(compute=speed) for name, speed in zip(("w1", "w2", "w3"), speeds)})
        assert_complete_and_right(cluster)
        outcomes.append(cluster.ledger.get_generation_results("exp", 0))
        orders.append(tuple(entry[3] for entry in cluster.events("commit")))

    assert len(set(orders)) > 1                       # the premise: the candidates really did finish in different orders
    assert all(outcome == outcomes[0] for outcome in outcomes)


# ---- 2. two attempts compete for one candidate: the one that was replaced loses ------------------------------------------

def test_a_slow_worker_whose_lease_ran_out_loses_to_the_worker_that_took_over_while_it_is_still_running():
    # A takes c0 and needs 40 s but has 30; B finishes c1, finds c0 free at t=30, needs 20 s: it commits at t=50, A speaks at t=40
    cluster = run(2, {"A": Behavior(compute=40.0), "B": Behavior(compute=20.0)})

    assert_complete_and_right(cluster)
    assert [(e[0], e[1], e[4]) for e in cluster.events("rejected")] == [(40.0, "A", "StaleAttemptError")]
    assert [(e[0], e[1], e[3]) for e in cluster.events("commit")] == [(20.0, "B", 1), (50.0, "B", 0)]
    c0 = cluster.ledger.get_candidate("exp/g0/c0")
    assert c0.attempts == 2 and c0.result.attempt_number == 2


# ---- 3. the acknowledgement is lost: the same result again changes nothing ------------------------------------------------

def test_a_result_sent_again_is_acknowledged_and_counted_once():
    cluster = run(3, {"L": Behavior(kind="lossy_ack", compute=5.0)})

    assert_complete_and_right(cluster)
    assert len(cluster.events("commit")) == 3 and len(cluster.events("acknowledged_again")) == 3
    assert cluster.events("rejected") == []
    assert [r.result.attempt_number for r in cluster.ledger.list_candidates("exp", 0)] == [1, 1, 1]


def test_another_reward_for_an_attempt_that_delivered_is_refused_and_the_first_stays():
    cluster = run(3, {"L": Behavior(kind="lossy_ack", compute=5.0, conflict=True)})

    assert_complete_and_right(cluster)                # the honest reward stayed
    assert [e[4] for e in cluster.events("rejected")] == ["ConflictingResultError"] * 3


# ---- 4. an old attempt arrives after the candidate was taken over and committed -----------------------------------------

def test_an_attempt_that_arrives_after_the_commit_of_its_replacement_is_refused():
    # A needs 100 s for c0 and has 30; B commits c0 at t=35; A speaks at t=100, when everything is over
    cluster = run(2, {"A": Behavior(compute=100.0), "B": Behavior(compute=5.0)})

    assert_complete_and_right(cluster)
    assert [(e[0], e[1], e[3], e[4]) for e in cluster.events("rejected")] == [(100.0, "A", 0, "StaleAttemptError")]
    assert cluster.ledger.get_candidate("exp/g0/c0").result.attempt_number == 2
    assert cluster.makespan() == 35.0                 # A's late word did not move anything


# ---- 5. a result for another job (wrong seed, recipe or parent weights) is never committed --------------------------------

@pytest.mark.parametrize("wrong", ["seed", "recipe", "parent"])
def test_a_result_for_another_job_is_refused_and_the_honest_one_after_it_is_committed(wrong):
    cluster = run(2, {"W": Behavior(kind="wrong_job_once", compute=5.0, wrong=wrong)})

    assert_complete_and_right(cluster)                # the wrong job came with a wrong reward: had it been taken, this would fail
    assert [(e[3], e[4]) for e in cluster.events("rejected")] == [(0, "ResultMismatchError")]
    assert len(cluster.events("commit")) == 2 and cluster.events("acknowledged_again") == []
    assert [r.attempts for r in cluster.ledger.list_candidates("exp", 0)] == [1, 1]     # the same attempt delivered after all


# ---- 6. the budget runs out: the generation fails and no reward is invented -------------------------------------------------

def test_when_every_attempt_fails_the_generation_fails_and_there_is_no_reward():
    cluster = run(3, {name: Behavior(kind="oom", compute=4.0) for name in ("w1", "w2", "w3")}, max_attempts=2)

    status = cluster.status()
    assert status.state is GenerationState.FAILED and status.committed == 0 and status.exhausted
    assert cluster.events("commit") == []
    assert all(r.result is None and r.state is not CandidateState.COMMITTED for r in cluster.ledger.list_candidates("exp", 0))
    assert cluster.ledger._db.execute("SELECT COUNT(*) FROM result").fetchone()[0] == 0
    with pytest.raises(GenerationFailedError):
        cluster.ledger.get_generation_results("exp", 0)
    assert all(r.attempts <= 2 for r in cluster.ledger.list_candidates("exp", 0))


def test_workers_that_vanish_use_up_the_budget_just_the_same_without_inventing_a_reward():
    cluster = Cluster(candidates=1, max_attempts=2)
    for name in ("a", "b", "c"):
        cluster.start(name, Behavior(kind="vanish_after", after=0), Greedy())
    cluster.run()

    assert cluster.events("vanished") and cluster.events("commit") == []
    assert cluster.ledger.get_candidate("exp/g0/c0").result is None
    assert cluster.ledger._db.execute("SELECT COUNT(*) FROM result").fetchone()[0] == 0


# ---- 7. a worker that cannot restore its weights is put aside ------------------------------------------------------------

def test_a_worker_whose_restore_failed_gets_no_more_work_and_the_others_finish_the_generation():
    cluster = run(6, {"bad": Behavior(kind="restore_broken", compute=2.0), "good1": Behavior(compute=5.0),
                      "good2": Behavior(compute=5.0)})

    assert_complete_and_right(cluster)
    assert cluster.ledger.list_quarantined() == [QuarantineRecord("bad", 2.0, "exp/g0/c0", 1)]
    assert [(e[1], e[4]) for e in cluster.events("failure")] == [("bad", "RESTORE_MISMATCH")]
    assert [e[1] for e in cluster.events("quarantined")] == ["bad"]
    started_by_bad = cluster.ledger._db.execute("SELECT COUNT(*) FROM attempt WHERE worker_id = 'bad'").fetchone()[0]
    assert started_by_bad == 1                        # it was given exactly one candidate, and none after the failed restore
    c0 = cluster.ledger.get_candidate("exp/g0/c0")
    assert c0.attempts == 2 and c0.result.attempt_number == 2     # the candidate of the failed restore was done by another
