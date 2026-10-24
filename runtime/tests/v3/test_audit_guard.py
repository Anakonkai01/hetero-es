"""Run-level safety survives API rotation; strict policy remains an internal fixture until M4."""

from concurrent.futures import ThreadPoolExecutor
import json
import threading

import pytest

from heteroes.generation_record import GenerationRecord
from heteroes.ledger import FailureKind
from heteroes.manifest import CandidateDescriptor
from heteroes.v3.audit import AuditAPI
from heteroes.v3.audit_guard import AuditRunGuard, AuditStopped
from heteroes.worker_api import WorkerAPI
from test_v3_audit import setup, lease, result


def guard_for(ledger, tmp_path, strict=False, experiment="audit"):
    return AuditRunGuard(
        ledger,
        experiment,
        fault_path=tmp_path / "audit-faults.json",
        stop_path=tmp_path / "audit-stop.json",
        stop_on_mismatch=strict,
    )


def api_for(ledger, guard, generation=0):
    return AuditAPI(
        WorkerAPI(ledger, "audit", generation, 60),
        ledger,
        "audit",
        generation,
        rate=1,
        workers=["original", "auditor"],
        guard=guard,
    )


def update_for(ledger):
    return GenerationRecord.from_results("audit", 0, ledger.get_generation_results("audit", 0), alpha=0.05, eta=1e-9)


def test_first_strict_mismatch_keeps_both_receipts_and_latches_across_restart(setup, tmp_path):
    ledger, _, _ = setup
    guard = guard_for(ledger, tmp_path, strict=True)
    api = api_for(ledger, guard)
    work = lease(api)["work"]
    assert not result(api, work, ["different"])["matched"]
    assert result(api, work, ["different"])["outcome"] == "ALREADY_COMMITTED"
    assert not ledger.list_quarantined()  # frozen three-mismatch policy is not rewritten
    assert guard.fatal_error and api.fatal_error
    assert lease(api)["error"]["code"] == "audit_stopped"
    with pytest.raises(AuditStopped, match="mismatch"):
        guard.record_update(update_for(ledger))
    assert ledger.get_update("audit", 0) is None
    saved = json.loads((tmp_path / "audit-stop.json").read_text())
    assert saved["descriptor"] == work["descriptor"]
    assert saved["original"]["worker_id"] == "original"
    assert saved["original"]["completions"] == ["canonical"]
    assert saved["auditor"]["worker_id"] == "auditor"
    assert saved["auditor"]["completions"] == ["different"]
    assert saved["auditor"]["attempt_number"] == work["attempt_number"]
    assert work["token"] not in json.dumps(saved)
    # Even a caller requesting legacy policy cannot ignore an existing stop.
    again = guard_for(ledger, tmp_path)
    with pytest.raises(AuditStopped):
        again.record_update(update_for(ledger))
    assert api_for(ledger, again, generation=1).fatal_error
    assert ledger.get_generation_results("audit", 0).rewards == (0.75,) * 6


def test_historical_mismatch_still_allows_update_and_does_not_create_strict_stop(setup, tmp_path):
    ledger, _, _ = setup
    guard = guard_for(ledger, tmp_path)
    api = api_for(ledger, guard)
    assert not result(api, lease(api)["work"], ["different"])["matched"]
    assert guard.fatal_error is None
    guard.record_update(update_for(ledger))
    assert ledger.get_update("audit", 0) is not None
    assert not (tmp_path / "audit-stop.json").exists()


@pytest.mark.parametrize("kind", [FailureKind.RESTORE_MISMATCH, "mismatch"])
def test_fault_on_old_api_blocks_rotated_api_and_new_update(setup, tmp_path, kind):
    ledger, _, _ = setup
    guard = guard_for(ledger, tmp_path, strict=True)
    old = api_for(ledger, guard)
    work = lease(old)["work"]
    old.close_drain("timeout")
    current = api_for(ledger, guard, generation=1)
    if kind == "mismatch":
        assert result(old, work, ["different"])["ok"]
    else:
        request = {k: work[k] for k in ("descriptor", "attempt_number", "token", "audit_id")}
        reply = old.handle("report_failure", {**request, "kind": kind.value}, authenticated_worker_id="auditor")
        assert reply["error"]["code"] == "worker_quarantined"
    assert current.fatal_error
    assert not lease(current)["ok"]
    with pytest.raises(AuditStopped):
        guard.record_update(update_for(ledger))
    assert guard_for(ledger, tmp_path).fatal_error


def test_stop_is_persisted_before_canonical_audit_and_survives_a_failed_commit(setup, tmp_path, monkeypatch):
    ledger, _, _ = setup
    guard = guard_for(ledger, tmp_path, strict=True)
    api = api_for(ledger, guard)
    work = lease(api)["work"]

    def fail_commit(*args):
        assert (tmp_path / "audit-stop.json").is_file()
        raise OSError("simulated audit storage failure")

    monkeypatch.setattr(ledger, "record_audit", fail_commit)
    with pytest.raises(OSError, match="storage"):
        result(api, work, ["different"])
    assert api.audit_counts() == (6, 0)
    assert guard_for(ledger, tmp_path).fatal_error


def test_failed_stop_write_remains_blocked_in_memory_and_retry_persists(setup, tmp_path, monkeypatch):
    import heteroes.v3.audit_guard as module

    ledger, _, _ = setup
    guard = guard_for(ledger, tmp_path, strict=True)
    api = api_for(ledger, guard)
    work = lease(api)["work"]
    write = module.write_json
    monkeypatch.setattr(module, "write_json", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        result(api, work, ["different"])
    assert guard.fatal_error and api.audit_counts() == (6, 0)
    with pytest.raises(AuditStopped):
        guard.record_update(update_for(ledger))
    monkeypatch.setattr(module, "write_json", write)
    assert result(api, work, ["different"])["ok"]
    assert guard_for(ledger, tmp_path).fatal_error


def test_mismatch_observation_and_update_admission_share_one_lock(setup, tmp_path, monkeypatch):
    import heteroes.v3.audit_guard as module

    ledger, _, _ = setup
    guard = guard_for(ledger, tmp_path, strict=True)
    api = api_for(ledger, guard)
    work = lease(api)["work"]
    entered, release, tried_update = threading.Event(), threading.Event(), threading.Event()
    write = module.write_json
    record = update_for(ledger)

    def blocked_write(*args):
        entered.set()
        assert release.wait(5)
        return write(*args)

    def update():
        tried_update.set()
        return guard.record_update(record)

    monkeypatch.setattr(module, "write_json", blocked_write)
    with ThreadPoolExecutor(2) as pool:
        mismatch = pool.submit(result, api, work, ["different"])
        try:
            assert entered.wait(5)
            updating = pool.submit(update)
            assert tried_update.wait(5)
        finally:
            release.set()
        assert mismatch.result(timeout=5)["ok"]
        with pytest.raises(AuditStopped):
            updating.result(timeout=5)
    assert ledger.get_update("audit", 0) is None


def test_admitted_update_is_not_rolled_back_by_a_later_mismatch(setup, tmp_path):
    ledger, _, _ = setup
    guard = guard_for(ledger, tmp_path, strict=True)
    api = api_for(ledger, guard)
    work = lease(api)["work"]
    record = update_for(ledger)
    guard.record_update(record)
    assert result(api, work, ["different"])["ok"]
    assert ledger.get_update("audit", 0).record == record
    with pytest.raises(AuditStopped):
        guard.record_update(record)


def test_an_admitted_update_finishes_before_a_waiting_fault_is_observed(setup, tmp_path, monkeypatch):
    ledger, _, _ = setup
    guard = guard_for(ledger, tmp_path, strict=True)
    api = api_for(ledger, guard)
    work = lease(api)["work"]
    entered, release, trying, observed, committed = (threading.Event() for _ in range(5))
    update, audit = ledger.record_update, ledger.record_audit
    record = update_for(ledger)

    def blocked_update(record):
        entered.set()
        assert release.wait(5)
        outcome = update(record)
        committed.set()
        return outcome

    def observed_audit(*args):
        observed.set()
        assert committed.is_set()
        return audit(*args)

    def report():
        trying.set()
        return guard.record_audit(
            CandidateDescriptor.from_dict(work["descriptor"]), "auditor", work["attempt_number"], ["different"]
        )

    monkeypatch.setattr(ledger, "record_update", blocked_update)
    monkeypatch.setattr(ledger, "record_audit", observed_audit)
    with ThreadPoolExecutor(2) as pool:
        updating = pool.submit(guard.record_update, record)
        try:
            assert entered.wait(5)
            mismatch = pool.submit(report)
            assert trying.wait(5)
            assert not observed.wait(0.05)
        finally:
            release.set()
        updating.result(timeout=5)
        assert mismatch.result(timeout=5) is False
    assert ledger.get_update("audit", 0).record == record
    assert guard.fatal_error


def test_other_run_and_corrupted_receipt_cannot_clear_a_stop(setup, tmp_path):
    ledger, _, _ = setup
    api = api_for(ledger, guard_for(ledger, tmp_path, strict=True))
    result(api, lease(api)["work"], ["different"])
    with pytest.raises(ValueError, match="audit stop"):
        guard_for(ledger, tmp_path, experiment="another-run")
    path = tmp_path / "audit-stop.json"
    saved = json.loads(path.read_text())
    saved["auditor"]["completions"] = ["changed after receipt"]
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="audit stop"):
        guard_for(ledger, tmp_path)


def test_matching_audits_and_bad_credentials_cannot_trip_a_strict_stop(setup, tmp_path):
    ledger, _, _ = setup
    guard = guard_for(ledger, tmp_path, strict=True)
    api = api_for(ledger, guard)
    work = lease(api)["work"]
    assert not result(api, work, ["different"], worker="original")["ok"]
    assert result(api, work)["matched"]
    assert guard.fatal_error is None and not (tmp_path / "audit-stop.json").exists()


def test_invalid_direct_receipt_cannot_latch_a_strict_stop(setup, tmp_path):
    ledger, _, descriptors = setup
    guard = guard_for(ledger, tmp_path, strict=True)
    with pytest.raises(ValueError, match="audit stop"):
        guard.record_audit(descriptors[0], "original", 1, ["different"])
    assert guard.fatal_error is None


def test_restore_fault_retry_persists_after_failed_write(setup, tmp_path, monkeypatch):
    import heteroes.v3.audit_guard as module

    ledger, _, _ = setup
    guard = guard_for(ledger, tmp_path)
    api = api_for(ledger, guard)
    work = lease(api)["work"]
    request = {k: work[k] for k in ("descriptor", "attempt_number", "token", "audit_id")}
    request["kind"] = "RESTORE_MISMATCH"
    write = module.write_json
    monkeypatch.setattr(module, "write_json", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        api.handle("report_failure", request, authenticated_worker_id="auditor")
    monkeypatch.setattr(module, "write_json", write)
    reply = api.handle("report_failure", request, authenticated_worker_id="auditor")
    assert reply["error"]["code"] == "worker_quarantined"
    assert guard_for(ledger, tmp_path).fatal_error


@pytest.mark.parametrize("body", [None, [], {}, {"formatVersion": 1}])
def test_corrupt_stop_is_not_silently_ignored(setup, tmp_path, body):
    ledger, _, _ = setup
    (tmp_path / "audit-stop.json").write_text(json.dumps(body))
    with pytest.raises(ValueError, match="audit stop"):
        guard_for(ledger, tmp_path)


@pytest.mark.parametrize("fault", ["match", "text", "restore"])
def test_new_generation_endpoint_can_receive_a_prior_generations_audit(setup, tmp_path, fault):
    ledger, _, _ = setup
    guard = guard_for(ledger, tmp_path, strict=True)
    old = api_for(ledger, guard)
    work = lease(old)["work"]
    old.close_drain("timeout")
    current = api_for(ledger, guard, generation=1)
    if fault == "restore":
        request = {k: work[k] for k in ("descriptor", "attempt_number", "token", "audit_id")}
        reply = current.handle(
            "report_failure", {**request, "kind": "RESTORE_MISMATCH"}, authenticated_worker_id="auditor"
        )
        assert reply["error"]["code"] == "worker_quarantined"
    else:
        texts = ["canonical"] if fault == "match" else ["different"]
        assert result(current, work, texts)["matched"] is (fault == "match")
        assert result(current, work, texts)["outcome"] == "ALREADY_COMMITTED"
        assert old.audit_counts() == (6, 1)
    assert bool(current.fatal_error) is (fault != "match")
    if fault != "match":
        with pytest.raises(AuditStopped):
            guard.record_update(update_for(ledger))


def test_audit_lease_retention_is_bounded_without_evicting_unfinished_evidence(setup, tmp_path):
    ledger, _, _ = setup
    guard = AuditRunGuard(ledger, "audit", lease_capacity=2)
    api = api_for(ledger, guard)
    first, second = lease(api)["work"], lease(api, request_id="second")["work"]
    assert first and second
    assert lease(api, request_id="full")["work"] is None
    assert len(guard.audit_leases) == 2
    assert result(api, first)["ok"]
    assert lease(api, request_id="third")["work"]
    assert len(guard.audit_leases) == 2
    assert result(api, second)["ok"]  # the unfinished lease was retained


def test_http_delivery_after_server_rotation_still_trips_the_run_stop(setup, tmp_path):
    from heteroes.http_transport import CoordinatorServer, HttpClient
    from heteroes.worker_api import completions_sha256

    ledger, _, _ = setup
    guard = guard_for(ledger, tmp_path, strict=True)
    old = api_for(ledger, guard)
    server = CoordinatorServer(old, device_tokens={"auditor": "fixture-private-credential"})
    server.start()
    try:
        client = HttpClient(server.url, token="fixture-private-credential")
        work = client("lease", {"worker_id": "auditor", "generation": 0})["work"]
        old.close_drain("timeout")
        server.set_generation(api_for(ledger, guard, generation=1), {"generation": 1})
        payload = {k: work[k] for k in ("descriptor", "attempt_number", "token", "audit_id")}
        texts = ["late result after HTTP rotation"]
        reply = client(
            "submit_result", {**payload, "completions": texts, "completions_sha256": completions_sha256(texts)}
        )
        assert reply["ok"] and not reply["matched"]
        assert server.api.fatal_error and not server.internal_errors
        with pytest.raises(AuditStopped):
            guard.record_update(update_for(ledger))
    finally:
        server.stop()
