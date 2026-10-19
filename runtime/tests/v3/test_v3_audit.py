"""Audit leases use the same generation parent and never alter committed rewards."""

import hashlib
import time

import pytest

from heteroes.canonical import canonical_json_hash
from heteroes.ledger import Ledger
from heteroes.manifest import CandidateDescriptor
from heteroes.v3.audit import AuditAPI, selected_for_audit
from heteroes.worker_api import WorkerAPI, completions_sha256


def committed(ledger, index=0, worker="original"):
    descriptor = CandidateDescriptor("1" * 64, "2" * 64, "audit", 0, index, index)
    return descriptor


@pytest.fixture
def setup(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    descriptors = [committed(ledger, i) for i in range(6)]
    ledger.open_generation(descriptors)
    for descriptor in descriptors:
        lease = ledger.lease(descriptor.candidate_id, "original", 60)
        ledger.submit_result(descriptor, lease.attempt_number, lease.token, 0.75, completions=["canonical"])
    api = AuditAPI(
        WorkerAPI(ledger, "audit", 0, 60),
        ledger,
        "audit",
        0,
        rate=1.0,
        workers=["original", "auditor"],
        fault_path=tmp_path / "audit-faults.json",
    )
    yield ledger, api, descriptors
    ledger.close()


def lease(api, worker="auditor", request_id="request"):
    return api.handle(
        "lease", {"worker_id": worker, "generation": 0, "request_id": request_id}, authenticated_worker_id=worker
    )


def result(api, work, texts=None, worker="auditor"):
    texts = ["canonical"] if texts is None else texts
    return api.handle(
        "submit_result",
        {
            **{k: work[k] for k in ("descriptor", "attempt_number", "token", "audit_id")},
            "completions": texts,
            "completions_sha256": completions_sha256(texts),
        },
        authenticated_worker_id=worker,
    )


def test_sampling_is_the_versioned_candidate_hash_rule():
    expected = []
    actual = []
    for i in range(1000):
        cid = f"experiment/g3/c{i}"
        expected.append(int(hashlib.sha256(cid.encode()).hexdigest(), 16) < (2**256 // 20))
        actual.append(selected_for_audit(cid))
    assert actual == expected and 20 < sum(actual) < 80
    assert all(selected_for_audit(str(i), 1.0) for i in range(20))
    assert not any(selected_for_audit(str(i), 0.0) for i in range(20))


def test_other_worker_authentication_hash_and_retry_are_enforced(setup):
    ledger, api, _ = setup
    assert lease(api, "original")["work"] is None
    assert lease(api, "outsider")["ok"] is False
    work = lease(api)["work"]
    assert work["audit_id"] and work == lease(api)["work"]
    assert result(api, work, worker="original")["error"]["code"] == "forbidden"
    assert result(api, {**work, "token": "not-the-lease"})["error"]["code"] == "stale_attempt"
    wrong = {
        **{k: work[k] for k in ("descriptor", "attempt_number", "token", "audit_id")},
        "completions": ["canonical"],
        "completions_sha256": "0" * 64,
    }
    assert api.handle("submit_result", wrong, authenticated_worker_id="auditor")["error"]["code"] == "bad_request"
    assert result(api, work)["outcome"] == "COMMITTED"
    assert result(api, work)["outcome"] == "ALREADY_COMMITTED"
    assert result(api, work, ["changed"])["error"]["code"] == "conflicting_result"
    assert ledger.get_generation_results("audit", 0).rewards == (0.75,) * 6


def test_three_mismatches_quarantine_both_workers_without_changing_rewards(setup):
    ledger, api, _ = setup
    for i in range(3):
        work = lease(api, request_id=f"request-{i}")["work"]
        reply = result(api, work, ["different"])
        assert reply["ok"] and reply["matched"] is False
        assert len(ledger.list_quarantined()) == (2 if i == 2 else 0)
    assert {q.worker_id for q in ledger.list_quarantined()} == {"original", "auditor"}
    assert all(q.reason == "AUDIT_MISMATCH" for q in ledger.list_quarantined())
    assert lease(api)["error"]["code"] == "worker_quarantined"
    assert ledger.get_generation_results("audit", 0).rewards == (0.75,) * 6


def test_restart_does_not_repeat_completed_audits(setup, tmp_path):
    ledger, api, _ = setup
    first = lease(api)["work"]
    result(api, first)
    restarted = AuditAPI(
        WorkerAPI(ledger, "audit", 0, 60),
        ledger,
        "audit",
        0,
        rate=1.0,
        workers=["original", "auditor"],
        fault_path=tmp_path / "audit-faults.json",
    )
    next_work = lease(restarted)["work"]
    assert next_work["descriptor"]["index"] == 1
    assert restarted.pending == 5


def test_infrastructure_failure_is_not_recorded_as_a_mismatch(setup):
    ledger, api, _ = setup
    work = lease(api)["work"]
    payload = {k: work[k] for k in ("descriptor", "attempt_number", "token", "audit_id")}
    reply = api.handle("report_failure", {**payload, "kind": "OUT_OF_MEMORY"}, authenticated_worker_id="auditor")
    assert reply["ok"] and not ledger.list_quarantined()
    assert api.pending == 6
    assert ledger.get_generation_results("audit", 0).rewards == (0.75,) * 6


def test_worker_protocol_keeps_audits_separate_and_stops_on_quarantine(setup):
    from heteroes.worker import Worker, StepKind, local_transport

    ledger, api, _ = setup
    worker = Worker("auditor", local_transport(api), lambda descriptor: ("different",))
    assert worker.step(0).kind is StepKind.AUDITED
    assert worker.step(0).kind is StepKind.AUDITED
    assert worker.step(0).kind is StepKind.QUARANTINED
    assert ledger.get_generation_results("audit", 0).rewards == (0.75,) * 6


def test_restore_failure_quarantine_is_durable_without_fabricating_a_hash(setup, tmp_path):
    from heteroes.worker import Worker, StepKind, local_transport, CandidateFailed
    from heteroes.ledger import FailureKind

    ledger, api, _ = setup

    def fail(descriptor):
        raise CandidateFailed(FailureKind.RESTORE_MISMATCH)

    worker = Worker("auditor", local_transport(api), fail)
    assert worker.step(0).kind is StepKind.QUARANTINED
    assert api.fatal_error and api.pending == 6
    restarted = AuditAPI(
        WorkerAPI(ledger, "audit", 0, 60),
        ledger,
        "audit",
        0,
        rate=1.0,
        workers=["original", "auditor"],
        fault_path=tmp_path / "audit-faults.json",
    )
    assert lease(restarted)["error"]["code"] == "worker_quarantined"
    assert not ledger.list_quarantined()  # restore fault is persisted separately; no invented ledger audit text hash


def test_cancelled_generation_issues_no_new_audits(setup):
    ledger, api, _ = setup
    api.cancel_requested = lambda: True
    assert lease(api)["work"] is None


def test_expired_lease_can_move_to_another_worker_and_old_result_is_refused(setup):
    ledger, api, _ = setup
    api.workers = frozenset(["original", "auditor", "replacement"])
    now = [10.0]
    api.clock = lambda: now[0]
    work = lease(api)["work"]
    now[0] = 100.0
    replacement = lease(api, "replacement", "other-request")["work"]
    assert replacement["attempt_number"] == 2
    assert result(api, work)["error"]["code"] in {"forbidden", "stale_attempt"}
    assert result(api, replacement, worker="replacement")["ok"]
