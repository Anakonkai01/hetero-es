"""
Every order of a small alphabet of actions, up to a length: for these small worlds nothing is left to chance. The same
harness as the random schedules. A test at the end checks that between them the sequences really reach every kind of
outcome the model predicts, so that "all of them passed" says something.
"""
import functools
import itertools
import os
from collections import Counter

import pytest

from harness import LedgerHarness
from heteroes.ledger import FailureKind

OTHER, RESTORE = FailureKind.OTHER, FailureKind.RESTORE_MISMATCH

# 4 actions in a row take a few seconds; 5 take a minute:  HETEROES_EXHAUSTIVE=deep pytest tests/ledger/test_exhaustive.py
LENGTH = 5 if os.environ.get("HETEROES_EXHAUSTIVE") == "deep" else 4

# one candidate, two workers, two attempts: the contention for one candidate in all its forms
ONE_CANDIDATE = dict(
    candidates=1, max_attempts=2, length=LENGTH,
    alphabet=[("lease", "A", 0), ("lease", "B", 0), ("advance", 31.0), ("submit", "A", 0, "good"),
              ("submit", "B", 0, "good"), ("submit", "A", 0, "other"), ("fail", "A", 0, OTHER), ("fail", "B", 0, RESTORE)],
)
# two candidates, one attempt each: completion, failure of the generation, and the quarantine as well
TWO_CANDIDATES = dict(
    candidates=2, max_attempts=1, length=LENGTH,
    alphabet=[("lease", "A", 0), ("lease", "B", 1), ("lease", "A", 1), ("advance", 31.0), ("submit", "A", 0, "good"),
              ("submit", "B", 1, "good"), ("submit", "A", 1, "good"), ("fail", "A", 0, RESTORE), ("release", "A")],
)
# one worker that holds two candidates when its restore fails: the second failed restore of a worker already put aside
ONE_WORKER_TWO_ATTEMPTS = dict(
    candidates=2, max_attempts=2, length=4,
    alphabet=[("lease", "A", 0), ("lease", "A", 1), ("fail", "A", 0, RESTORE), ("fail", "A", 1, RESTORE),
              ("submit", "A", 1, "good"), ("release", "A"), ("advance", 31.0)],
)
# two workers put aside one after the other (in the order of the time, which is not that of the names), then released
TWO_WORKERS = dict(
    candidates=3, max_attempts=2, length=5,
    alphabet=[("lease", "A", 0), ("lease", "B", 2), ("fail", "A", 0, RESTORE), ("fail", "B", 2, RESTORE),
              ("advance", 31.0), ("release", "A")],
)
CONFIGS = {"one candidate": ONE_CANDIDATE, "two candidates": TWO_CANDIDATES,
           "one worker, two attempts": ONE_WORKER_TWO_ATTEMPTS, "two workers": TWO_WORKERS}


@functools.cache
def explored(name):
    """Run every sequence of a world once (the tests below share the result): how many, and which outcomes were reached."""
    config, seen, count = CONFIGS[name], Counter(), 0
    for sequence in itertools.product(config["alphabet"], repeat=config["length"]):
        harness = LedgerHarness(candidates=config["candidates"], max_attempts=config["max_attempts"], seen=seen)
        try:
            for action in sequence:
                harness.apply(action)
        finally:
            harness.close()
        count += 1
    return count, seen


@pytest.mark.parametrize("name", list(CONFIGS))
def test_every_order_of_actions_keeps_the_model_and_the_ledger_in_step(name):
    config = CONFIGS[name]

    assert explored(name)[0] == len(config["alphabet"]) ** config["length"]


def test_between_them_the_sequences_reach_every_kind_of_outcome():
    reached = set(explored("one candidate")[1]) | set(explored("two candidates")[1])
    expected = {"granted", "AlreadyLeasedError", "RetriesExhaustedError", "GenerationFailedError", "WorkerQuarantinedError",
                "SubmitOutcome.COMMITTED", "SubmitOutcome.ALREADY_COMMITTED", "ConflictingResultError", "StaleAttemptError",
                "failure accepted", "released"}
    assert expected <= reached, expected - reached
