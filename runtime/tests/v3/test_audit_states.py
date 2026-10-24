"""Operational audit outcomes are separate from immutable canonical completions."""

import json

import pytest

from heteroes.v3.audit import AuditAPI
from heteroes.worker_api import WorkerAPI, completions_sha256
from test_v3_audit import setup, lease, result


def restarted(ledger, tmp_path, rate=1.0, generation=0):
    return AuditAPI(
        WorkerAPI(ledger, "audit", generation, 60),
        ledger,
        "audit",
        generation,
        rate=rate,
        workers=["original", "auditor", "another"],
        state_path=tmp_path / "audit-state.json",
    )


def expected(**changes):
    return {
        "enabled": True,
        "selected": 6,
        "completed": 0,
        "matched": 0,
        "mismatched": 0,
        "pending": 6,
        "timed_out": 0,
        "skipped": 0,
        "incomplete": 6,
        "drain_reason": None,
        **changes,
    }


def test_unexecuted_audits_are_pending_and_mismatch_is_a_completed_audit(setup, tmp_path):
    ledger, _, _ = setup
    api = restarted(ledger, tmp_path)
    assert api.audit_summary() == expected()
    assert result(api, lease(api)["work"])["matched"]
    assert not result(api, lease(api, request_id="second")["work"], ["different"])["matched"]
    assert api.audit_summary() == expected(completed=2, matched=1, mismatched=1, pending=4, incomplete=4)
    assert api.audit_counts() == (6, 2)
    assert restarted(ledger, tmp_path).audit_summary() == api.audit_summary()


def test_multiple_ledger_receipts_count_a_candidate_once_and_any_mismatch_wins(setup, tmp_path):
    ledger, _, descriptors = setup
    cid = descriptors[0].candidate_id
    ledger.record_audit(cid, "auditor", completions_sha256(["canonical"]))
    ledger.record_audit(cid, "another", completions_sha256(["different"]))
    api = restarted(ledger, tmp_path)
    assert api.audit_summary() == expected(completed=1, mismatched=1, pending=5, incomplete=5)
    assert api.audit_counts() == (6, 1)


@pytest.mark.parametrize("reason,field", [("timeout", "timed_out"), ("insufficient_workers", "skipped")])
def test_drain_closure_survives_restart_without_inventing_completed_audits(setup, tmp_path, reason, field):
    ledger, _, _ = setup
    api = restarted(ledger, tmp_path)
    work = lease(api)["work"]
    api.close_drain(reason)
    assert api.audit_summary() == expected(pending=0, drain_reason=reason, **{field: 6})
    assert lease(api, "another")["work"] is None
    # An already leased execution may finish after the drain. Canonical evidence supersedes the operational reason.
    assert result(api, work)["ok"]
    want = expected(completed=1, matched=1, pending=0, incomplete=5, drain_reason=reason, **{field: 5})
    assert api.audit_summary() == want
    again = restarted(ledger, tmp_path)
    assert again.audit_summary() == want
    assert lease(again)["work"] is None
    again.close_drain("complete")
    assert again.audit_summary() == want
    assert "token" not in (tmp_path / "audit-state.json").read_text()


def test_disabled_and_fully_matched_audits_have_distinct_states(setup, tmp_path):
    ledger, _, descriptors = setup
    off = restarted(ledger, tmp_path, rate=0)
    assert off.audit_summary() == expected(enabled=False, selected=0, pending=0, incomplete=0)
    for descriptor in descriptors:
        ledger.record_audit(descriptor.candidate_id, "auditor", completions_sha256(["canonical"]))
    on = restarted(ledger, tmp_path)
    on.close_drain("complete")
    assert on.audit_summary() == expected(completed=6, matched=6, pending=0, incomplete=0, drain_reason="complete")


def test_a_closed_drain_cannot_be_reused_for_another_identity_or_coverage(setup, tmp_path):
    ledger, _, _ = setup
    restarted(ledger, tmp_path).close_drain("timeout")
    with pytest.raises(ValueError, match="audit drain"):
        restarted(ledger, tmp_path, generation=1)
    with pytest.raises(ValueError, match="audit drain"):
        restarted(ledger, tmp_path, rate=0.5)
    path = tmp_path / "audit-state.json"
    saved = json.loads(path.read_text())
    path.write_text(json.dumps({**saved, "reason": "everything_matched"}))
    with pytest.raises(ValueError, match="audit drain"):
        restarted(ledger, tmp_path)


def test_unclosed_drain_cannot_claim_all_work_completed(setup, tmp_path):
    ledger, _, _ = setup
    api = restarted(ledger, tmp_path)
    with pytest.raises(ValueError, match="pending"):
        api.close_drain("complete")
    assert not (tmp_path / "audit-state.json").exists()


@pytest.mark.parametrize("body", [None, [], {"reason": "timeout"}])
def test_corrupt_existing_drain_is_not_treated_as_unclosed(setup, tmp_path, body):
    ledger, _, _ = setup
    (tmp_path / "audit-state.json").write_text(json.dumps(body))
    with pytest.raises(ValueError, match="audit drain"):
        restarted(ledger, tmp_path)
