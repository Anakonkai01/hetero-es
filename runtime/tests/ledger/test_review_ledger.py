"""Ledger review fixes: cross-connection idempotence, durable retry exemptions and public audit counts."""

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from heteroes.ledger import FailureKind, GenerationState, Ledger
from ledger_helpers import FakeClock, batch, fail, lease


def test_releasing_a_worker_keeps_previous_attempts_exempt_after_reopen(tmp_path):
    path = tmp_path / "ledger.sqlite"
    with Ledger(path, clock=FakeClock(), max_attempts=2) as ledger:
        ledger.open_generation(batch(1))
        fail(ledger, lease(ledger, worker="A"), FailureKind.OTHER)
        fail(ledger, lease(ledger, worker="A"), FailureKind.RESTORE_MISMATCH)
        fail(ledger, lease(ledger, worker="B"), FailureKind.OTHER)
        assert ledger.get_generation_status("exp", 0).state is GenerationState.OPEN
        assert ledger.list_candidates("exp", 0)[0].charged_attempts == 1
        ledger.release_worker("A")
        assert ledger.get_generation_status("exp", 0).state is GenerationState.OPEN
        assert ledger.list_candidates("exp", 0)[0].charged_attempts == 1
    with Ledger(path, clock=FakeClock(), max_attempts=2) as ledger:
        assert ledger.list_candidates("exp", 0)[0].charged_attempts == 1
        # A future attempt by the released worker counts normally.
        fail(ledger, lease(ledger, worker="A"), FailureKind.OTHER)
        assert ledger.get_generation_status("exp", 0).state is GenerationState.FAILED
        assert ledger.list_candidates("exp", 0)[0].charged_attempts == 2


def test_membership_change_is_idempotent_across_two_connections(tmp_path, monkeypatch):
    import heteroes.ledger.ledger as module

    barrier = threading.Barrier(2)
    original = sqlite3.connect

    class Connection(sqlite3.Connection):
        def execute(self, sql, *args):
            cursor = super().execute(sql, *args)
            if sql.startswith("SELECT worker_id, action, effective_generation, actor FROM membership"):
                row = cursor.fetchone()
                try:
                    barrier.wait(timeout=2)
                except threading.BrokenBarrierError:
                    pass  # BEGIN IMMEDIATE serializes writers, so the second reader cannot arrive until commit.
                return type("Row", (), {"fetchone": lambda self: row})()
            return cursor

    monkeypatch.setattr(module.sqlite3, "connect", lambda *a, **kw: original(*a, **kw, factory=Connection))
    path = tmp_path / "ledger.sqlite"
    with Ledger(path) as first, Ledger(path) as second:
        with ThreadPoolExecutor(2) as pool:
            futures = [
                pool.submit(ledger.record_membership, "exp", "change", "w", "JOIN", 0, "owner")
                for ledger in (first, second)
            ]
            assert sorted(f.result(timeout=10) for f in futures) == [False, True]


def test_audit_count_is_scoped_to_experiment_and_generation():
    from ledger_helpers import submit

    with Ledger(":memory:", clock=FakeClock()) as ledger:
        assert ledger.count_audits("exp", 0) == 0
        for experiment, generation in (("exp", 0), ("exp", 1), ("other", 0)):
            descriptor = batch(1, experiment_id=experiment, generation=generation)[0]
            ledger.open_generation([descriptor])
            held = ledger.lease(descriptor.candidate_id, "worker", 30)
            ledger.submit_result(descriptor, held.attempt_number, held.token, 0.5, completions=["answer"])
            sha, _ = ledger.get_completions(descriptor.candidate_id)
            ledger.record_audit(descriptor.candidate_id, "auditor", sha)
        assert ledger.count_audits("exp", 0) == 1
        assert ledger.count_audits("exp", 1) == 1
        assert ledger.count_audits("other", 0) == 1
        assert ledger.count_audits("absent", 0) == 0


def test_ledger_without_exemption_table_is_migrated_and_can_resume(tmp_path):
    path = tmp_path / "legacy-v3.sqlite"
    with Ledger(path, clock=FakeClock(), max_attempts=2) as ledger:
        ledger.open_generation(batch(1))
        fail(ledger, lease(ledger, worker="A"), FailureKind.OTHER)
        fail(ledger, lease(ledger, worker="A"), FailureKind.RESTORE_MISMATCH)
    with sqlite3.connect(path) as raw:
        raw.execute("DROP TABLE attempt_exemption")
    with Ledger(path, clock=FakeClock(), max_attempts=2) as ledger:
        assert ledger.list_candidates("exp", 0)[0].charged_attempts == 0
        ledger.release_worker("A")
        assert ledger.list_candidates("exp", 0)[0].charged_attempts == 0
        fail(ledger, lease(ledger, worker="B"), FailureKind.OTHER)
        assert ledger.get_generation_status("exp", 0).state is GenerationState.OPEN
