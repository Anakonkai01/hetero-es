"""Delivery remains leased and restartable; a dirty worker stops even when reporting loses the network."""

import threading

import pytest

from heteroes.ledger import FailureKind, Ledger
from heteroes.worker import CandidateFailed, StepKind, Worker, local_transport
from heteroes.worker_api import WorkerAPI
from ledger_helpers import batch


@pytest.fixture
def api():
    with Ledger(":memory:") as ledger:
        ledger.open_generation(batch(3))
        yield WorkerAPI(ledger, "exp", 0, 30)


def test_heartbeat_continues_while_result_delivery_waits(api):
    sending, beat, release = threading.Event(), threading.Event(), threading.Event()
    inner = local_transport(api)

    def transport(op, payload):
        if op == "submit_result":
            sending.set()
            assert release.wait(3)
        if op == "heartbeat" and sending.is_set():
            beat.set()
        return inner(op, payload)

    worker = Worker("worker-a", transport, lambda d: 0.5, heartbeat_seconds=0.01)
    results = []
    thread = threading.Thread(target=lambda: results.append(worker.step()), daemon=True)
    thread.start()
    assert sending.wait(3)
    try:
        assert beat.wait(1), "delivery must not end the heartbeat before its terminal ACK"
    finally:
        release.set()
        thread.join(3)
    assert results[0].kind is StepKind.COMMITTED


def test_heartbeat_continues_between_pending_retries(api):
    failed, beat = threading.Event(), threading.Event()
    inner = local_transport(api)

    def transport(op, payload):
        if op == "submit_result" and not failed.is_set():
            failed.set()
            raise ConnectionError("lost response")
        if op == "heartbeat" and failed.is_set():
            beat.set()
        return inner(op, payload)

    worker = Worker("worker-a", transport, lambda d: 0.5, transient_errors=(ConnectionError,), heartbeat_seconds=0.01)
    try:
        with pytest.raises(ConnectionError):
            worker.step()
        assert beat.wait(1), "pending delivery must keep renewing its lease"
        assert worker.step().kind is StepKind.COMMITTED
    finally:
        worker.close()


def test_restart_replays_exact_result_before_leasing_or_evaluating(api, tmp_path):
    calls = []
    inner = local_transport(api)

    def lost_ack(op, payload):
        reply = inner(op, payload)
        if op == "submit_result":
            raise ConnectionError("committed, but ACK lost")
        return reply

    args = dict(outbox_path=tmp_path / "outbox.json", outbox_scope="run-and-endpoint")
    first = Worker("worker-a", lost_ack, lambda d: 0.75, transient_errors=(ConnectionError,), **args)
    with pytest.raises(ConnectionError):
        first.step()
    first.close()

    def transport(op, payload):
        calls.append(op)
        return inner(op, payload)

    second = Worker("worker-a", transport, lambda d: pytest.fail("must not evaluate again"), **args)
    assert second.step().kind is StepKind.ALREADY_COMMITTED
    assert calls == ["submit_result"]
    assert (tmp_path / "outbox.json").stat().st_mode & 0o777 == 0o600


def test_restore_fault_poison_survives_lost_report_and_restart(api, tmp_path):
    inner, calls = local_transport(api), []

    def transport(op, payload):
        calls.append(op)
        if op == "report_failure":
            raise ConnectionError("offline")
        return inner(op, payload)

    def dirty(descriptor):
        raise CandidateFailed(FailureKind.RESTORE_MISMATCH)

    args = dict(outbox_path=tmp_path / "outbox.json", outbox_scope="run", transient_errors=(ConnectionError,))
    first = Worker("worker-a", transport, dirty, **args)
    with pytest.raises(ConnectionError):
        first.step()
    with pytest.raises(ConnectionError):
        first.step()
    first.close()
    assert calls.count("lease") == 1 and calls.count("report_failure") == 2

    second = Worker("worker-a", inner, lambda d: pytest.fail("dirty worker must stop"), **args)
    assert second.step().kind is StepKind.FAILURE_REPORTED
    assert second.step().kind is StepKind.QUARANTINED
    second.close()
    third = Worker("worker-a", lambda *a: pytest.fail("no new request after durable poison"), dirty, **args)
    assert third.step().kind is StepKind.QUARANTINED


@pytest.mark.parametrize("worker,scope", [("another-worker", "run"), ("worker-a", "other-run")])
def test_outbox_cannot_cross_worker_or_endpoint_recipe_scope(api, tmp_path, worker, scope):
    inner = local_transport(api)

    def offline(op, payload):
        if op == "submit_result":
            raise ConnectionError("offline")
        return inner(op, payload)

    path = tmp_path / "outbox.json"
    first = Worker(
        "worker-a", offline, lambda d: 0.5, transient_errors=(ConnectionError,), outbox_path=path, outbox_scope="run"
    )
    with pytest.raises(ConnectionError):
        first.step()
    first.close()
    with pytest.raises(ValueError, match="lineage"):
        Worker(worker, inner, lambda d: 0.5, outbox_path=path, outbox_scope=scope)


def test_restart_keeps_heartbeat_interval_during_pending_delivery(api, tmp_path):
    inner, beat, sending, release = local_transport(api), threading.Event(), threading.Event(), threading.Event()
    path = tmp_path / "outbox.json"

    def offline(op, payload):
        if op == "submit_result":
            raise ConnectionError("offline")
        return inner(op, payload)

    first = Worker(
        "worker-a",
        offline,
        lambda d: 0.5,
        transient_errors=(ConnectionError,),
        heartbeat_seconds=0.01,
        outbox_path=path,
        outbox_scope="run",
    )
    with pytest.raises(ConnectionError):
        first.step()
    first.close()

    def transport(op, payload):
        if op == "submit_result":
            sending.set()
            assert release.wait(3)
        if op == "heartbeat" and sending.is_set():
            beat.set()
        return inner(op, payload)

    second = Worker("worker-a", transport, lambda d: pytest.fail("delivery only"), outbox_path=path, outbox_scope="run")
    thread = threading.Thread(target=second.step, daemon=True)
    thread.start()
    assert sending.wait(3)
    try:
        assert beat.wait(1), "restart must retain the lease renewal interval"
    finally:
        release.set()
        thread.join(3)
        second.close()


def test_bounded_outbox_preserves_previous_record_on_oversized_write(tmp_path):
    from heteroes.worker_outbox import DeliveryOutbox

    store = DeliveryOutbox(tmp_path / "outbox.json", "worker", "scope", max_bytes=512)
    store.save(None, True)
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="byte limit"):
        store.save({"huge": "x" * 1000}, False)
    assert store.path.read_bytes() == before and store.load()["poisoned"] is True


def test_corrupt_outbox_cannot_be_replayed(tmp_path):
    from heteroes.worker_outbox import DeliveryOutbox

    store = DeliveryOutbox(tmp_path / "outbox.json", "worker", "scope")
    store.save(None, True)
    store.path.write_bytes(store.path.read_bytes().replace(b'"poisoned":true', b'"poisoned":false'))
    with pytest.raises(ValueError, match="checksum"):
        store.load()


def test_outbox_refuses_symlink_and_preserves_its_target(tmp_path):
    from heteroes.worker_outbox import DeliveryOutbox

    target = tmp_path / "keep"
    target.write_text("keep me")
    link = tmp_path / "outbox.json"
    link.symlink_to(target)
    store = DeliveryOutbox(link, "worker", "scope")
    with pytest.raises(ValueError, match="symlink"):
        store.save(None, True)
    assert target.read_text() == "keep me"


def test_runtime_drains_restart_outbox_before_fetching_job_or_syncing_parent(api, tmp_path):
    from types import SimpleNamespace

    from heteroes.http_transport import TransportError
    from heteroes.worker_runtime import WorkerRuntime

    inner, stop, calls = local_transport(api), threading.Event(), []

    class Client:
        _base = "same-coordinator"
        down = True

        def __call__(self, op, payload):
            calls.append(op)
            if op == "submit_result" and self.down:
                raise TransportError("offline")
            reply = inner(op, payload)
            if op == "submit_result":
                stop.set()
            return reply

        def get_json(self, path):
            pytest.fail("pending delivery precedes job discovery and parent changes")

    client = Client()
    executor = SimpleNamespace(recipe=SimpleNamespace(hash="a" * 64))
    first = WorkerRuntime("worker-a", client, executor, tmp_path / "cache")
    first._worker._evaluate = lambda d: 0.5
    with pytest.raises(TransportError):
        first._worker.step()
    first._worker.close()
    client.down = False
    second = WorkerRuntime("worker-a", client, executor, tmp_path / "cache")
    assert second.run(stop) == "stopped"
    assert calls == ["lease", "submit_result", "submit_result"]
    assert not second._worker.pending_delivery


def test_failed_outbox_write_blocks_delivery_and_new_work_until_persisted(api, tmp_path, monkeypatch):
    calls, inner = [], local_transport(api)

    def transport(op, payload):
        calls.append(op)
        return inner(op, payload)

    worker = Worker("worker-a", transport, lambda d: 0.5, outbox_path=tmp_path / "outbox.json", outbox_scope="run")
    save = worker._outbox.save
    monkeypatch.setattr(worker._outbox, "save", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        worker.step()
    assert calls == ["lease"]
    monkeypatch.setattr(worker._outbox, "save", save)
    assert worker.step().kind is StepKind.COMMITTED
    assert calls == ["lease", "submit_result"]


def test_restart_preserves_text_digest_usage_and_chunk_even_with_new_client_defaults(api, tmp_path):
    from heteroes.v3.usage import CompletionBatch

    usage = {"formatVersion": 1, "generatedTokens": [2, 3], "device": "cpu", "wallSeconds": 0.5}
    completions = CompletionBatch(("answer one", "answer two"), usage)
    completions.chunk = 2
    api._scorer, api.allowed_chunks = lambda d, texts: 0.5, (2,)
    inner, requests = local_transport(api), []

    def lost(op, payload):
        if op == "submit_result":
            requests.append(payload)
            raise ConnectionError("offline")
        return inner(op, payload)

    args = dict(outbox_path=tmp_path / "outbox.json", outbox_scope="run")
    first = Worker("worker-a", lost, lambda d: completions, transient_errors=(ConnectionError,), **args)
    first.client.usage_reporting = True
    with pytest.raises(ConnectionError):
        first.step()
    first.close()

    def deliver(op, payload):
        requests.append(payload)
        return inner(op, payload)

    second = Worker("worker-a", deliver, lambda d: pytest.fail("no recompute"), **args)
    assert second.step().kind is StepKind.COMMITTED
    assert requests[0] == requests[1]
    assert requests[1]["usage"] == usage and requests[1]["chunk"] == 2


def test_runtime_delivery_state_is_private_and_survives_a_changed_weights_cache(api, tmp_path):
    from types import SimpleNamespace

    from heteroes.http_transport import TransportError
    from heteroes.worker_runtime import WorkerRuntime

    inner = local_transport(api)

    class Client:
        _base = "same-coordinator"
        down = True

        def __call__(self, op, payload):
            if op == "submit_result" and self.down:
                raise TransportError("offline")
            return inner(op, payload)

    client = Client()
    executor = SimpleNamespace(recipe=SimpleNamespace(hash="a" * 64))
    state = tmp_path / "private-state"
    first = WorkerRuntime("worker-a", client, executor, tmp_path / "large-disk" / "cache-1", delivery_state_dir=state)
    first._worker._evaluate = lambda d: 0.5
    with pytest.raises(TransportError):
        first._worker.step()
    first._worker.close()
    assert len(list(state.glob("*.json"))) == 1
    assert not (tmp_path / "large-disk").exists()
    second = WorkerRuntime("worker-a", client, executor, tmp_path / "large-disk" / "cache-2", delivery_state_dir=state)
    client.down = False
    assert second._worker.step().kind is StepKind.COMMITTED
