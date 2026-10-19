"""
Hardening of the ledger found by the audit of 07/10/2026 (G6):
  - SQLite settings are chosen on purpose (durable commits, a stated busy timeout) and a database error is the ledger's own error;
  - the clock is read INSIDE the write lock, so a deadline is never older than the state it was decided on;
  - a restore mismatch that arrives late (the attempt was already replaced) still puts the worker aside;
  - an attempt lost to a worker fault (restore mismatch, a quarantined worker) does not use up the retry budget of the candidate;
  - a lease can be extended (heartbeat) as long as the attempt is the latest one and nothing was committed;
  - generations can be forced to chain: generation g starts from the applied child of g - 1.
"""
import sqlite3

import pytest

from heteroes.generation_record import GenerationRecord
from heteroes.ledger import (
    CandidateState,
    FailureKind,
    GenerationState,
    Ledger,
    LedgerError,
    StaleAttemptError,
    WorkerQuarantinedError,
)
from heteroes.ledger import LedgerBusyError
from ledger_helpers import FakeClock, batch, descriptor_of, fail, lease, make, record, submit

RESTORE = FailureKind.RESTORE_MISMATCH


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def ledger(clock):
    with Ledger(":memory:", clock=clock) as opened:
        opened.open_generation(batch(3))
        yield opened


# ---------------------------------------------------------------------------
# SQLite settings and database errors
# ---------------------------------------------------------------------------

def test_a_file_ledger_commits_durably_and_states_its_busy_timeout(tmp_path):
    with Ledger(tmp_path / "ledger.sqlite") as opened:
        assert opened._db.execute("PRAGMA synchronous").fetchone()[0] == 2          # FULL: the write-ahead record survives a power cut
        assert opened._db.execute("PRAGMA busy_timeout").fetchone()[0] == 30_000
        assert opened._db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_the_busy_timeout_is_a_parameter(tmp_path):
    with Ledger(tmp_path / "ledger.sqlite", busy_timeout_seconds=0.25) as opened:
        assert opened._db.execute("PRAGMA busy_timeout").fetchone()[0] == 250


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), True, "3"])
def test_a_bad_busy_timeout_is_refused(tmp_path, bad):
    with pytest.raises((LedgerError, TypeError)):
        Ledger(tmp_path / "ledger.sqlite", busy_timeout_seconds=bad)


def test_a_locked_database_is_the_ledgers_own_error_not_a_raw_sqlite_error(tmp_path):
    path = tmp_path / "ledger.sqlite"
    with Ledger(path, clock=FakeClock(), busy_timeout_seconds=0.05) as opened:
        opened.open_generation(batch(2))
        other = sqlite3.connect(path, isolation_level=None)
        try:
            other.execute("BEGIN IMMEDIATE")                       # somebody else holds the write lock
            with pytest.raises(LedgerBusyError):
                opened.lease("exp/g0/c0", "worker-a", 30.0)
            assert issubclass(LedgerBusyError, LedgerError)        # callers that catch LedgerError (the API) see it
        finally:
            other.execute("ROLLBACK")
            other.close()
        # the ledger is intact and works again
        assert opened.lease("exp/g0/c0", "worker-a", 30.0).attempt_number == 1


def test_a_lease_too_short_to_register_is_refused_by_the_ledger_not_by_a_database_constraint(ledger, clock):
    clock.now = 1e9                                                # 1e9 + 1e-12 == 1e9: the deadline would equal the lease time
    with pytest.raises(LedgerError, match="too short"):
        ledger.lease("exp/g0/c0", "worker-a", 1e-12)
    assert record(ledger).attempts == 0 and record(ledger).state is CandidateState.PENDING


# ---------------------------------------------------------------------------
# the clock is read inside the write lock
# ---------------------------------------------------------------------------

class SpyClock(FakeClock):
    """Records whether a write transaction was open each time the ledger read the time."""

    def __init__(self):
        super().__init__()
        self.ledger = None
        self.in_transaction = []

    def __call__(self):
        if self.ledger is not None:
            self.in_transaction.append(self.ledger._db.in_transaction)
        return self.now


def test_lease_submit_and_failure_read_the_clock_after_taking_the_write_lock():
    clock = SpyClock()
    with Ledger(":memory:", clock=clock) as opened:
        opened.open_generation(batch(3))
        clock.ledger = opened
        first = lease(opened, 0)
        assert clock.in_transaction and all(clock.in_transaction), "lease read the clock before BEGIN IMMEDIATE"
        clock.in_transaction.clear()
        submit(opened, first)
        assert clock.in_transaction and all(clock.in_transaction), "submit_result read the clock before BEGIN IMMEDIATE"
        clock.in_transaction.clear()
        second = lease(opened, 1)
        clock.in_transaction.clear()
        fail(opened, second, FailureKind.OTHER)
        assert clock.in_transaction and all(clock.in_transaction), "report_failure read the clock before BEGIN IMMEDIATE"


# ---------------------------------------------------------------------------
# a late restore mismatch still quarantines
# ---------------------------------------------------------------------------

def test_a_restore_mismatch_reported_after_the_lease_was_replaced_still_quarantines_the_worker(ledger, clock):
    old = lease(ledger, 0, "worker-a", 30.0)
    clock.advance(31.0)
    new = lease(ledger, 0, "worker-b", 30.0)                       # worker-a's attempt is no longer the latest
    assert new.attempt_number == 2

    with pytest.raises(StaleAttemptError):
        fail(ledger, old, RESTORE)                                 # the report is refused (it is about an old attempt) ...

    assert [q.worker_id for q in ledger.list_quarantined()] == ["worker-a"]     # ... but its weights are in doubt all the same
    assert record(ledger).state is CandidateState.LEASED           # and the newer attempt is untouched
    with pytest.raises(WorkerQuarantinedError):
        lease(ledger, 1, "worker-a")


def test_a_late_restore_mismatch_after_the_candidate_was_committed_still_quarantines(ledger, clock):
    old = lease(ledger, 0, "worker-a", 30.0)
    clock.advance(31.0)
    new = lease(ledger, 0, "worker-b", 30.0)
    submit(ledger, new, 0.5)

    with pytest.raises(StaleAttemptError):
        fail(ledger, old, RESTORE)

    assert [q.worker_id for q in ledger.list_quarantined()] == ["worker-a"]
    assert record(ledger).state is CandidateState.COMMITTED


def test_a_late_failure_of_another_kind_does_not_quarantine(ledger, clock):
    old = lease(ledger, 0, "worker-a", 30.0)
    clock.advance(31.0)
    lease(ledger, 0, "worker-b", 30.0)
    with pytest.raises(StaleAttemptError):
        fail(ledger, old, FailureKind.OUT_OF_MEMORY)
    assert ledger.list_quarantined() == []


def test_a_forged_restore_mismatch_with_a_wrong_token_quarantines_nobody(ledger, clock):
    held = lease(ledger, 0, "worker-a", 30.0)
    with pytest.raises(StaleAttemptError):
        ledger.report_failure(descriptor_of(0), held.attempt_number, "0" * 32, RESTORE)
    assert ledger.list_quarantined() == []


def test_a_restore_mismatch_for_another_job_quarantines_nobody(ledger):
    held = lease(ledger, 0, "worker-a", 30.0)
    other_job = make(0, 1000, parent_weights_sha256="c" * 64)
    with pytest.raises(LedgerError):
        ledger.report_failure(other_job, held.attempt_number, held.token, RESTORE)
    assert ledger.list_quarantined() == []


# ---------------------------------------------------------------------------
# worker faults do not use up the retry budget of the candidate
# ---------------------------------------------------------------------------

def test_attempts_lost_to_a_restore_mismatch_are_not_charged(clock):
    with Ledger(":memory:", clock=clock, max_attempts=2) as ledger:
        ledger.open_generation(batch(2))
        for worker in ("worker-a", "worker-b", "worker-c"):         # three workers, each fails the restore on candidate 0
            fail(ledger, lease(ledger, 0, worker), RESTORE)
        c0 = record(ledger, 0)
        assert c0.attempts == 3                                     # three attempts happened ...
        assert c0.charged_attempts == 0                             # ... none of them was the candidate's fault
        assert ledger.get_generation_status("exp", 0).state is GenerationState.OPEN


def test_attempts_of_a_worker_that_was_quarantined_later_are_not_charged(clock):
    with Ledger(":memory:", clock=clock, max_attempts=2) as ledger:
        ledger.open_generation(batch(2))
        lease(ledger, 0, "worker-a", 30.0)                          # worker-a sits on candidate 0 ...
        clock.advance(31.0)
        fail(ledger, lease(ledger, 1, "worker-a", 30.0), RESTORE)   # ... and is quarantined for another candidate
        assert record(ledger, 0).attempts == 1
        assert record(ledger, 0).charged_attempts == 0


def test_a_candidate_failure_is_still_charged_and_still_exhausts_the_budget(clock):
    with Ledger(":memory:", clock=clock, max_attempts=2) as ledger:
        ledger.open_generation(batch(2))
        fail(ledger, lease(ledger, 0, "worker-a"), FailureKind.VERIFIER_ERROR)
        fail(ledger, lease(ledger, 0, "worker-b"), FailureKind.OUT_OF_MEMORY)
        assert record(ledger, 0).charged_attempts == 2
        assert ledger.get_generation_status("exp", 0).state is GenerationState.FAILED


def test_the_lease_itself_does_not_count_the_attempts_of_a_quarantined_worker(clock):
    with Ledger(":memory:", clock=clock, max_attempts=1) as ledger:
        ledger.open_generation(batch(2))
        lease(ledger, 0, "worker-a", 30.0)                          # worker-a holds candidate 0 ...
        fail(ledger, lease(ledger, 1, "worker-a", 30.0), RESTORE)   # ... and is quarantined for a restore mismatch on candidate 1
        clock.advance(31.0)                                         # worker-a's lease on candidate 0 is over
        again = lease(ledger, 0, "worker-b", 30.0)                  # it has had 1 attempt, but that one was not the candidate's fault
        assert again.attempt_number == 2


def test_an_expired_lease_of_a_healthy_worker_is_charged(clock):
    with Ledger(":memory:", clock=clock, max_attempts=2) as ledger:
        ledger.open_generation(batch(2))
        lease(ledger, 0, "worker-a", 30.0)
        clock.advance(31.0)
        lease(ledger, 0, "worker-b", 30.0)
        assert record(ledger, 0).charged_attempts == 2


# ---------------------------------------------------------------------------
# heartbeat: extend a lease
# ---------------------------------------------------------------------------

def test_extending_a_lease_moves_its_deadline(ledger, clock):
    held = lease(ledger, 0, "worker-a", 30.0)
    clock.advance(20.0)
    extended = ledger.extend_lease(descriptor_of(0), held.attempt_number, held.token, 30.0)
    assert extended.deadline == clock.now + 30.0
    assert (extended.token, extended.attempt_number, extended.worker_id) == (held.token, held.attempt_number, "worker-a")
    clock.advance(25.0)                                           # past the ORIGINAL deadline
    assert record(ledger).state is CandidateState.LEASED          # the lease still holds
    with pytest.raises(Exception):
        lease(ledger, 0, "worker-b")                              # nobody else can take it


def test_a_lease_is_never_shortened_by_extending_it(ledger, clock):
    held = lease(ledger, 0, "worker-a", 100.0)
    extended = ledger.extend_lease(descriptor_of(0), held.attempt_number, held.token, 5.0)
    assert extended.deadline == held.deadline


def test_an_expired_lease_that_nobody_took_can_still_be_extended(ledger, clock):
    held = lease(ledger, 0, "worker-a", 30.0)
    clock.advance(40.0)                                           # over, but nobody replaced it (same rule as a late delivery)
    extended = ledger.extend_lease(descriptor_of(0), held.attempt_number, held.token, 30.0)
    assert extended.deadline == clock.now + 30.0
    assert record(ledger).state is CandidateState.LEASED


def test_a_replaced_attempt_cannot_extend(ledger, clock):
    old = lease(ledger, 0, "worker-a", 30.0)
    clock.advance(31.0)
    lease(ledger, 0, "worker-b", 30.0)
    with pytest.raises(StaleAttemptError):
        ledger.extend_lease(descriptor_of(0), old.attempt_number, old.token, 30.0)


def test_a_wrong_token_cannot_extend(ledger):
    held = lease(ledger, 0, "worker-a", 30.0)
    with pytest.raises(StaleAttemptError):
        ledger.extend_lease(descriptor_of(0), held.attempt_number, "0" * 32, 30.0)


def test_a_committed_or_failed_attempt_cannot_extend(ledger):
    done = lease(ledger, 0, "worker-a")
    submit(ledger, done)
    with pytest.raises(StaleAttemptError):
        ledger.extend_lease(descriptor_of(0), done.attempt_number, done.token, 30.0)
    bad = lease(ledger, 1, "worker-a")
    fail(ledger, bad, FailureKind.OTHER)
    with pytest.raises(StaleAttemptError):
        ledger.extend_lease(descriptor_of(1), bad.attempt_number, bad.token, 30.0)


def test_a_quarantined_worker_cannot_extend(ledger):
    held = lease(ledger, 0, "worker-a", 30.0)
    fail(ledger, lease(ledger, 1, "worker-a", 30.0), RESTORE)
    with pytest.raises(WorkerQuarantinedError):
        ledger.extend_lease(descriptor_of(0), held.attempt_number, held.token, 30.0)


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf")])
def test_extend_lease_checks_the_duration(ledger, duration):
    held = lease(ledger, 0, "worker-a", 30.0)
    with pytest.raises(LedgerError):
        ledger.extend_lease(descriptor_of(0), held.attempt_number, held.token, duration)


# ---------------------------------------------------------------------------
# listing the generations (what a restarted coordinator reads)
# ---------------------------------------------------------------------------

def test_list_generations_is_empty_for_an_unknown_experiment(ledger):
    assert ledger.list_generations("nobody") == []


def test_list_generations_gives_them_by_number_with_recipe_and_parent(clock):
    from heteroes.ledger import GenerationInfo
    with Ledger(":memory:", clock=clock) as ledger:
        ledger.open_generation([make(i, 1000 + i, generation=2, parent_weights_sha256="e" * 64) for i in range(2)])
        ledger.open_generation([make(i, 1000 + i, generation=0) for i in range(2)])
        ledger.open_generation([make(i, 1000 + i, experiment_id="other", generation=1) for i in range(2)])
        assert ledger.list_generations("exp") == [
            GenerationInfo("exp", 0, "a" * 64, "b" * 64), GenerationInfo("exp", 2, "a" * 64, "e" * 64)]


# ---------------------------------------------------------------------------
# chain of generations
# ---------------------------------------------------------------------------

CHILD0 = "c" * 64


def _complete_and_apply(ledger, generation, child, parent="b" * 64):
    for index in range(2):
        held = ledger.lease(f"exp/g{generation}/c{index}", "worker-a", 30.0)
        ledger.submit_result(make(index, 1000 + 7 * index, generation=generation, parent_weights_sha256=parent),
                             held.attempt_number, held.token, 0.25 + 0.5 * index)
    results = ledger.get_generation_results("exp", generation)
    update = GenerationRecord.from_results("exp", generation, results, alpha=1e-3, eta=1e-9)
    ledger.record_update(update)
    ledger.mark_applied("exp", generation, update.hash, child)


def _open(ledger, generation, parent):
    ledger.open_generation([make(i, 1000 + 7 * i, generation=generation, parent_weights_sha256=parent) for i in range(2)])


def test_a_chained_ledger_accepts_the_child_of_the_previous_generation_as_the_parent(clock):
    with Ledger(":memory:", clock=clock, enforce_chain=True) as ledger:
        _open(ledger, 0, "b" * 64)
        _complete_and_apply(ledger, 0, CHILD0)
        _open(ledger, 1, CHILD0)
        assert ledger.get_generation_status("exp", 1).state is GenerationState.OPEN


def test_a_chained_ledger_refuses_another_parent(clock):
    with Ledger(":memory:", clock=clock, enforce_chain=True) as ledger:
        _open(ledger, 0, "b" * 64)
        _complete_and_apply(ledger, 0, CHILD0)
        with pytest.raises(LedgerError, match="parent"):
            _open(ledger, 1, "d" * 64)
        with pytest.raises(LedgerError):
            ledger.get_generation_status("exp", 1)                  # nothing was opened


def test_a_chained_ledger_refuses_a_generation_whose_predecessor_was_not_applied(clock):
    with Ledger(":memory:", clock=clock, enforce_chain=True) as ledger:
        _open(ledger, 0, "b" * 64)
        with pytest.raises(LedgerError, match="applied"):
            _open(ledger, 1, CHILD0)


def test_a_chained_ledger_refuses_a_generation_without_a_predecessor(clock):
    with Ledger(":memory:", clock=clock, enforce_chain=True) as ledger:
        with pytest.raises(LedgerError, match="previous generation"):
            _open(ledger, 3, "b" * 64)


def test_generation_zero_may_start_from_any_parent(clock):
    with Ledger(":memory:", clock=clock, enforce_chain=True) as ledger:
        _open(ledger, 0, "e" * 64)


def test_without_enforce_chain_generations_are_independent_as_before(clock):
    with Ledger(":memory:", clock=clock) as ledger:
        _open(ledger, 5, "e" * 64)
        _open(ledger, 2, "f" * 64)


def test_the_chain_is_checked_per_experiment(clock):
    with Ledger(":memory:", clock=clock, enforce_chain=True) as ledger:
        _open(ledger, 0, "b" * 64)
        _complete_and_apply(ledger, 0, CHILD0)
        with pytest.raises(LedgerError, match="previous generation"):
            ledger.open_generation([make(i, 1000 + 7 * i, experiment_id="other", generation=1, parent_weights_sha256=CHILD0)
                                    for i in range(2)])
