"""
Random schedules: Hypothesis chooses lists of actions (any worker, any candidate, any moment), the harness predicts what
each must do and checks the ledger after every one. When something goes wrong Hypothesis shrinks the list to a short one
that still goes wrong. `HETEROES_HYPOTHESIS=fuzz pytest tests/ledger/test_random_schedules.py` hunts with 3000 random lists.
"""
import pytest

pytest.importorskip("hypothesis")

from hypothesis import given  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from harness import LedgerHarness  # noqa: E402
from heteroes.ledger import FailureKind  # noqa: E402

WORKERS = st.sampled_from(["w1", "w2", "w3"])
CANDIDATE = st.integers(0, 3)                                             # wraps around when there are fewer candidates
WHICH = st.sampled_from(["first", "last"])

lease = st.tuples(st.just("lease"), WORKERS, CANDIDATE)
advance = st.tuples(st.just("advance"), st.sampled_from([1.0, 10.0, 29.0, 30.0, 31.0, 100.0]))
submit = st.tuples(st.just("submit"), WORKERS, CANDIDATE,
                   st.sampled_from(["good", "good", "good", "other", "wrong_job", "wrong_token"]), WHICH)
fail = st.tuples(st.just("fail"), WORKERS, CANDIDATE, st.sampled_from(list(FailureKind)), WHICH)
release = st.tuples(st.just("release"), WORKERS)

record = st.tuples(st.just("record"), st.sampled_from([1e-3, 2e-3]), st.sampled_from([None, None, None, "seeds", "rewards", "recipe", "parent"]))
apply = st.tuples(st.just("apply"), st.sampled_from(["c", "d"]), st.sampled_from(["right", "right", "wrong"]))

ACTIONS = st.one_of(lease, lease, lease, advance, advance, submit, submit, fail, release, record, apply)


@given(config=st.tuples(st.integers(1, 4), st.integers(1, 3)), actions=st.lists(ACTIONS, max_size=40))
def test_the_ledger_does_what_the_model_says_under_any_schedule(config, actions):
    candidates, max_attempts = config
    harness = LedgerHarness(candidates=candidates, max_attempts=max_attempts)
    try:
        for action in actions:
            harness.apply(action)
    finally:
        harness.close()


# the quarantine is where several rules meet (leases, results, failures, release), so a second search lives in it:
# two workers, three candidates, restore failures all over the place
Q_WORKER = st.sampled_from(["w1", "w2"])
Q_CANDIDATE = st.integers(0, 2)
QUARANTINE_ACTIONS = st.one_of(
    st.tuples(st.just("lease"), Q_WORKER, Q_CANDIDATE),
    st.tuples(st.just("lease"), Q_WORKER, Q_CANDIDATE),
    st.tuples(st.just("fail"), Q_WORKER, Q_CANDIDATE, st.just(FailureKind.RESTORE_MISMATCH), WHICH),
    st.tuples(st.just("fail"), Q_WORKER, Q_CANDIDATE, st.sampled_from(list(FailureKind)), WHICH),
    st.tuples(st.just("submit"), Q_WORKER, Q_CANDIDATE, st.sampled_from(["good", "good", "other"]), WHICH),
    st.tuples(st.just("release"), Q_WORKER),
    st.tuples(st.just("advance"), st.sampled_from([1.0, 31.0])),
)


@given(actions=st.lists(QUARANTINE_ACTIONS, max_size=30))
def test_the_ledger_does_what_the_model_says_when_workers_keep_failing_their_restores(actions):
    harness = LedgerHarness(candidates=3, max_attempts=3)
    try:
        for action in actions:
            harness.apply(action)
    finally:
        harness.close()
