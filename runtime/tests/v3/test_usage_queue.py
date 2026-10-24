"""Slow/failed metrics never hold a canonical result ACK; pending work remains bounded and keyed."""

import threading

import pytest

from heteroes.ledger import Ledger
from heteroes.manifest import CandidateDescriptor
from heteroes.v3.usage import CompletionBatch
from heteroes.worker import WorkerClient, local_transport
from heteroes.worker_api import WorkerAPI


def descriptor(index=0):
    return CandidateDescriptor("a" * 64, "b" * 64, "usage", 0, index, 5 + index)


def usage(count=2):
    return {"formatVersion": 1, "generatedTokens": [count], "device": "cpu", "wallSeconds": 0.5}


def test_slow_sink_does_not_delay_canonical_ack_or_identical_retry(tmp_path):
    entered, release, acknowledged = threading.Event(), threading.Event(), threading.Event()
    calls, outcomes = [], []

    def sink(*args):
        calls.append(args)
        entered.set()
        assert release.wait(3)

    with Ledger(tmp_path / "ledger.sqlite") as ledger:
        ledger.open_generation([descriptor()])
        api = WorkerAPI(ledger, "usage", 0, 30, scorer=lambda d, t: 0.75, usage_sink=sink)
        client = WorkerClient("worker", local_transport(api), usage_reporting=True)
        work = client.lease().assignment

        def submit():
            outcomes.append(client.submit_completions(work, CompletionBatch(["answer"], usage())))
            acknowledged.set()

        thread = threading.Thread(target=submit, daemon=True)
        thread.start()
        assert entered.wait(3)
        try:
            assert acknowledged.wait(1), "usage I/O must not keep the canonical result ACK waiting"
            assert client.submit_completions(work, CompletionBatch(["answer"], usage())).value == "ALREADY_COMMITTED"
            assert ledger.get_candidate(descriptor().candidate_id).result.reward == 0.75
        finally:
            release.set()
            thread.join(3)
            api.flush_usage(3)
            api.close_usage(3)
    assert len(calls) == 1 and outcomes[0].value == "COMMITTED"


def test_capacity_includes_inflight_and_duplicate_keys_do_not_consume_it():
    from heteroes.v3.usage_queue import BoundedUsageSink

    entered, release, calls = threading.Event(), threading.Event(), []

    def sink(*args):
        entered.set()
        assert release.wait(3)
        calls.append(args)

    queue = BoundedUsageSink(sink, capacity=2)
    try:
        assert queue(descriptor(), 1, "worker", usage(), "candidate")
        assert entered.wait(3)
        assert queue(descriptor(), 1, "worker", usage(), "candidate")
        assert queue(descriptor(1), 1, "worker", usage(), "candidate")
        assert not queue(descriptor(2), 1, "worker", usage(), "candidate")
        status = queue.status()
        assert status["pending"] == 2 and status["dropped"] == 1 and status["partial"]
    finally:
        release.set()
        assert queue.close(3)
    assert [args[0].index for args in calls] == [0, 1]


def test_failed_sink_does_not_kill_consumer_and_errors_remain_visible():
    from heteroes.v3.usage_queue import BoundedUsageSink

    delivered = []

    def sink(d, *args):
        if d.index == 0:
            raise OSError("usage unavailable")
        delivered.append(d.index)

    queue = BoundedUsageSink(sink)
    queue(descriptor(), 1, "worker", usage(), "candidate")
    queue(descriptor(1), 1, "worker", usage(), "candidate")
    assert queue.close(3)
    assert delivered == [1]
    assert queue.status()["errors"] == 1 and queue.status()["partial"]


def test_close_is_bounded_when_sink_is_blocked_and_rejects_new_usage():
    from heteroes.v3.usage_queue import BoundedUsageSink

    entered, release = threading.Event(), threading.Event()

    def sink(*args):
        entered.set()
        assert release.wait(3)

    queue = BoundedUsageSink(sink)
    queue(descriptor(), 1, "worker", usage(), "candidate")
    assert entered.wait(3)
    try:
        assert queue.close(0) is False
        assert not queue(descriptor(1), 1, "worker", usage(), "candidate")
    finally:
        release.set()
        assert queue.close(3)


def test_pending_usage_cannot_change_under_the_same_execution_key():
    from heteroes.v3.usage_queue import BoundedUsageSink

    entered, release, saved = threading.Event(), threading.Event(), []

    def sink(d, attempt, worker, body, kind):
        entered.set()
        assert release.wait(3)
        saved.append(body)

    queue = BoundedUsageSink(sink)
    queue(descriptor(), 1, "worker", usage(2), "candidate")
    assert entered.wait(3)
    try:
        assert not queue(descriptor(), 1, "worker", usage(99), "candidate")
        assert queue.status()["errors"] == 1
    finally:
        release.set()
        assert queue.close(3)
    assert saved == [usage(2)]


@pytest.mark.parametrize("counts", [[2] * 1000, [9999999] * 64])
def test_oversized_usage_is_dropped_before_entering_the_queue(counts):
    from heteroes.v3.usage_queue import BoundedUsageSink

    queue = BoundedUsageSink(lambda *a: pytest.fail("oversized usage must not reach the sink"), max_record_bytes=256)
    body = {**usage(), "generatedTokens": counts}
    assert not queue(descriptor(), 1, "worker", body, "candidate")
    assert queue.status()["pending"] == 0 and queue.status()["dropped"] == 1
    assert queue.close(0)


def test_obviously_oversized_counts_are_rejected_before_copying_or_serializing():
    from heteroes.v3.usage_queue import BoundedUsageSink

    class OversizedCounts(list):
        def __iter__(self):
            pytest.fail("oversized input must not be copied or serialized")

    queue = BoundedUsageSink(lambda *a: None, max_record_bytes=256)
    assert not queue(
        descriptor(), 1, "worker", {**usage(), "generatedTokens": OversizedCounts([2] * 1000)}, "candidate"
    )
    assert queue.close(0)
