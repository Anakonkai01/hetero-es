"""
Recipe v3 submissions: scoring runs outside the request lock, an identical retry is answered from the ledger
without scoring again, concurrent duplicates are scored once, and the stale-attempt rule still holds when a
lease is replaced while texts are being scored. Threads use events with timeouts; no sleeps decide outcomes.
"""

import json
import threading

import pytest

from heteroes.ledger import Ledger
from heteroes.v3.audit import AuditAPI
from heteroes.worker_api import WorkerAPI, completions_sha256
from ledger_helpers import FakeClock, batch

LEASE_SECONDS = 30.0
WAIT = 10.0


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def ledger(clock):
    with Ledger(":memory:", clock=clock) as ledger:
        ledger.open_generation(batch(3))
        yield ledger


def call(api, operation, request):
    return api.handle(operation, json.loads(json.dumps(request)))


def take(api, worker="worker-a"):
    reply = call(api, "lease", {"worker_id": worker})
    assert reply["ok"] and reply["work"] is not None, reply
    return reply["work"]


def texts(work, values=("a", "b")):
    return {
        "descriptor": work["descriptor"],
        "attempt_number": work["attempt_number"],
        "token": work["token"],
        "completions": list(values),
        "completions_sha256": completions_sha256(values),
    }


def attempt(work):
    return {key: work[key] for key in ("descriptor", "attempt_number", "token")}


class BlockingScorer:
    """Counts calls; each call waits until the test releases it (so a test can act while scoring runs)."""

    def __init__(self, reward=0.5):
        self.calls, self.reward = 0, reward
        self.entered, self.release = threading.Event(), threading.Event()
        self._count = threading.Lock()

    def __call__(self, descriptor, completions):
        with self._count:
            self.calls += 1
        self.entered.set()
        assert self.release.wait(WAIT), "the test never released the scorer"
        return self.reward


def submit_in_thread(api, request):
    replies = []
    thread = threading.Thread(target=lambda: replies.append(call(api, "submit_result", request)))
    thread.start()
    return thread, replies


def test_an_identical_retry_after_commit_is_answered_without_scoring_again(ledger):
    rewards = iter([0.25, 0.75])  # a nondeterministic scorer: a second scoring would conflict
    calls = []
    api = WorkerAPI(ledger, "exp", 0, LEASE_SECONDS, scorer=lambda d, t: calls.append(1) or next(rewards))
    work = take(api)
    assert call(api, "submit_result", texts(work))["outcome"] == "COMMITTED"
    assert call(api, "submit_result", texts(work)) == {"ok": True, "outcome": "ALREADY_COMMITTED"}
    assert calls == [1]
    assert ledger.get_candidate("exp/g0/c0").result.reward == 0.25


def test_other_texts_after_commit_conflict_without_scoring(ledger):
    calls = []
    api = WorkerAPI(ledger, "exp", 0, LEASE_SECONDS, scorer=lambda d, t: calls.append(1) or 0.5)
    work = take(api)
    call(api, "submit_result", texts(work))
    reply = call(api, "submit_result", texts(work, ("a", "c")))
    assert reply["ok"] is False and reply["error"]["code"] == "conflicting_result"
    assert calls == [1] and ledger.get_completions("exp/g0/c0")[1] == ["a", "b"]


def test_heartbeats_and_other_leases_are_served_while_texts_are_scored(ledger):
    scorer = BlockingScorer()
    api = WorkerAPI(ledger, "exp", 0, LEASE_SECONDS, scorer=scorer)
    work = take(api)
    thread, replies = submit_in_thread(api, texts(work))
    assert scorer.entered.wait(WAIT)
    try:
        assert call(api, "heartbeat", attempt(work))["ok"] is True
        assert take(api, "worker-b")["descriptor"]["index"] == 1
    finally:
        scorer.release.set()
        thread.join(WAIT)
    assert replies == [{"ok": True, "outcome": "COMMITTED"}]


def test_concurrent_duplicates_are_scored_once_and_both_acknowledged(ledger):
    scorer = BlockingScorer()
    api = WorkerAPI(ledger, "exp", 0, LEASE_SECONDS, scorer=scorer)
    work = take(api)
    first, first_reply = submit_in_thread(api, texts(work))
    assert scorer.entered.wait(WAIT)
    second, second_reply = submit_in_thread(api, texts(work))
    try:
        assert api.wait_for_waiters(1, WAIT)  # the duplicate waits on the first scoring, it does not score
    finally:
        scorer.release.set()
        first.join(WAIT)
        second.join(WAIT)
    outcomes = sorted(r["outcome"] for r in first_reply + second_reply)
    assert outcomes == ["ALREADY_COMMITTED", "COMMITTED"] and scorer.calls == 1


def test_a_failed_scoring_fails_the_waiting_duplicate_too_and_commits_nothing(ledger):
    from heteroes.v3.scoring import ScorerError

    entered, release = threading.Event(), threading.Event()

    def broken(descriptor, completions):
        entered.set()
        assert release.wait(WAIT)
        raise ScorerError("bad answer field")

    api = WorkerAPI(ledger, "exp", 0, LEASE_SECONDS, scorer=broken)
    work = take(api)
    first, first_reply = submit_in_thread(api, texts(work))
    assert entered.wait(WAIT)
    second, second_reply = submit_in_thread(api, texts(work))
    assert api.wait_for_waiters(1, WAIT)
    release.set()
    first.join(WAIT)
    second.join(WAIT)
    assert [r["error"]["code"] for r in first_reply + second_reply] == ["scorer_failed", "scorer_failed"]
    assert ledger.get_candidate("exp/g0/c0").result is None


def test_a_lease_replaced_during_scoring_makes_the_late_result_stale(ledger, clock):
    scorer = BlockingScorer()
    api = WorkerAPI(ledger, "exp", 0, LEASE_SECONDS, scorer=scorer)
    work = take(api)
    thread, replies = submit_in_thread(api, texts(work))
    assert scorer.entered.wait(WAIT)
    clock.advance(LEASE_SECONDS + 1)
    replacement = take(api, "worker-b")
    assert replacement["descriptor"] == work["descriptor"] and replacement["attempt_number"] == 2
    scorer.release.set()
    thread.join(WAIT)
    assert replies[0]["ok"] is False and replies[0]["error"]["code"] == "stale_attempt"
    assert ledger.get_candidate("exp/g0/c0").result is None
    assert call(api, "submit_result", texts(replacement))["outcome"] == "COMMITTED"


def test_a_stale_or_foreign_submission_is_refused_before_scoring(ledger, clock):
    calls = []
    api = WorkerAPI(ledger, "exp", 0, LEASE_SECONDS, scorer=lambda d, t: calls.append(1) or 0.5)
    work = take(api)
    forbidden = api.handle("submit_result", texts(work), authenticated_worker_id="worker-z")
    assert forbidden["error"]["code"] == "forbidden"
    bad_chunk = {**texts(work), "chunk": 7}
    assert call(api, "submit_result", bad_chunk)["ok"] is False
    assert calls == []


def test_the_audit_layer_does_not_hold_its_lock_while_the_base_scores(ledger):
    scorer = BlockingScorer()
    base = WorkerAPI(ledger, "exp", 0, LEASE_SECONDS, scorer=scorer)
    api = AuditAPI(base, ledger, "exp", 0, rate=0.0, clock=lambda: 1000.0)
    work = take(api)
    thread, replies = submit_in_thread(api, texts(work))
    assert scorer.entered.wait(WAIT)
    done = []
    heartbeat = threading.Thread(target=lambda: done.append(call(api, "heartbeat", attempt(work))))
    heartbeat.start()
    heartbeat.join(WAIT)
    try:
        assert done and done[0]["ok"] is True, "a heartbeat must not wait behind scoring"
    finally:
        scorer.release.set()
        thread.join(WAIT)
    assert replies[0]["outcome"] == "COMMITTED"
