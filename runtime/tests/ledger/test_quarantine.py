import sqlite3

import pytest

from heteroes.ledger import (
    AlreadyLeasedError,
    CandidateState,
    FailureKind,
    Ledger,
    LedgerError,
    QuarantineRecord,
    RetriesExhaustedError,
    StaleAttemptError,
    SubmitOutcome,
    WorkerQuarantinedError,
)
from ledger_helpers import FakeClock, batch, fail, lease, record, submit

RESTORE = FailureKind.RESTORE_MISMATCH


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def ledger(clock):
    with Ledger(":memory:", clock=clock) as opened:
        opened.open_generation(batch(4))
        yield opened


def quarantine_worker_a(ledger, index=0):
    """worker-a restores wrongly after candidate `index`."""
    held = lease(ledger, index, "worker-a")
    fail(ledger, held, RESTORE)
    return held


# ---------------------------------------------------------------------------
# a failed restore puts the worker aside
# ---------------------------------------------------------------------------

def test_nobody_is_quarantined_at_the_start(ledger):
    assert ledger.list_quarantined() == []


def test_a_restore_mismatch_quarantines_the_worker_of_that_attempt(ledger, clock):
    clock.advance(4.0)

    quarantine_worker_a(ledger, 2)

    assert ledger.list_quarantined() == [
        QuarantineRecord(worker_id="worker-a", quarantined_at=1004.0, candidate_id="exp/g0/c2", attempt_number=1)]


@pytest.mark.parametrize("kind", [FailureKind.OUT_OF_MEMORY, FailureKind.VERIFIER_ERROR, FailureKind.OTHER])
def test_the_other_kinds_of_failure_do_not_quarantine(ledger, kind):
    fail(ledger, lease(ledger, 0, "worker-a"), kind)

    assert ledger.list_quarantined() == []
    assert lease(ledger, 1, "worker-a").attempt_number == 1


def test_the_worker_that_is_quarantined_is_the_one_who_held_the_attempt(ledger):
    lease(ledger, 0, "worker-b")
    quarantine_worker_a(ledger, 1)

    assert [q.worker_id for q in ledger.list_quarantined()] == ["worker-a"]
    assert lease(ledger, 2, "worker-b").attempt_number == 1


def test_the_candidate_of_the_failed_restore_is_free_for_another_worker(ledger):
    quarantine_worker_a(ledger, 0)

    assert record(ledger).state is CandidateState.PENDING
    assert lease(ledger, 0, "worker-b").attempt_number == 2          # the attempt of worker-a counts in the budget


def test_a_second_restore_mismatch_of_the_same_worker_keeps_the_first_record(ledger, clock):
    held_c0 = lease(ledger, 0, "worker-a")
    held_c1 = lease(ledger, 1, "worker-a")
    fail(ledger, held_c0, RESTORE)
    clock.advance(10.0)

    fail(ledger, held_c1, RESTORE)                                   # a quarantined worker may still report failures

    assert ledger.list_quarantined() == [QuarantineRecord("worker-a", 1000.0, "exp/g0/c0", 1)]
    assert record(ledger, 1).state is CandidateState.PENDING


def test_the_record_names_the_attempt_that_caused_it(ledger, clock):
    first = lease(ledger, 0, "worker-b")
    clock.now = first.deadline
    second = lease(ledger, 0, "worker-a")                           # attempt 2 of the candidate

    fail(ledger, second, RESTORE)

    assert ledger.list_quarantined() == [QuarantineRecord("worker-a", 1030.0, "exp/g0/c0", 2)]


# ---------------------------------------------------------------------------
# a quarantined worker is given nothing and delivers nothing new
# ---------------------------------------------------------------------------

def test_a_quarantined_worker_cannot_lease(ledger):
    quarantine_worker_a(ledger, 0)

    with pytest.raises(WorkerQuarantinedError) as caught:
        lease(ledger, 1, "worker-a")

    assert not isinstance(caught.value, (AlreadyLeasedError, RetriesExhaustedError))
    assert record(ledger, 1).attempts == 0 and record(ledger, 1).state is CandidateState.PENDING


def test_the_refusal_comes_before_the_questions_about_the_candidate(ledger):
    quarantine_worker_a(ledger, 0)

    with pytest.raises(WorkerQuarantinedError):
        ledger.lease("exp/g0/c9", "worker-a", 30.0)


def test_other_workers_are_not_affected(ledger):
    quarantine_worker_a(ledger, 0)

    assert lease(ledger, 1, "worker-b").attempt_number == 1
    assert lease(ledger, 2, "worker-c").attempt_number == 1


def test_the_other_leases_of_the_worker_stay_until_they_run_out_and_cannot_deliver(ledger, clock):
    held_c0 = lease(ledger, 0, "worker-a")
    held_c1 = lease(ledger, 1, "worker-a")
    fail(ledger, held_c0, RESTORE)

    assert record(ledger, 1).state is CandidateState.LEASED          # not freed at once: it simply waits for the deadline
    with pytest.raises(WorkerQuarantinedError):
        submit(ledger, held_c1, 0.5)                                 # the result of a worker whose weights are in doubt
    assert record(ledger, 1).state is CandidateState.LEASED and record(ledger, 1).result is None

    clock.now = held_c1.deadline
    assert record(ledger, 1).state is CandidateState.PENDING
    takeover = lease(ledger, 1, "worker-b")
    assert submit(ledger, takeover, 0.5) is SubmitOutcome.COMMITTED


def test_a_quarantined_worker_may_still_report_a_failure_for_an_attempt_it_holds(ledger):
    held_c0 = lease(ledger, 0, "worker-a")
    held_c1 = lease(ledger, 1, "worker-a")
    fail(ledger, held_c0, RESTORE)

    fail(ledger, held_c1, FailureKind.OTHER)                        # that frees the candidate at once, which is welcome

    assert record(ledger, 1).state is CandidateState.PENDING


def test_a_result_that_was_committed_before_the_quarantine_is_still_acknowledged(ledger):
    held_c0 = lease(ledger, 0, "worker-a")
    held_c1 = lease(ledger, 1, "worker-a")
    submit(ledger, held_c1, 0.5)
    fail(ledger, held_c0, RESTORE)

    assert submit(ledger, held_c1, 0.5) is SubmitOutcome.ALREADY_COMMITTED
    assert record(ledger, 1).state is CandidateState.COMMITTED


def test_a_stale_attempt_of_a_quarantined_worker_is_stale_first(ledger, clock):
    old = lease(ledger, 1, "worker-a")
    held_c0 = lease(ledger, 0, "worker-a")
    clock.now = old.deadline
    lease(ledger, 1, "worker-b")
    fail(ledger, held_c0, RESTORE)

    with pytest.raises(StaleAttemptError):
        submit(ledger, old, 0.5)


# ---------------------------------------------------------------------------
# letting a worker back in
# ---------------------------------------------------------------------------

def test_a_released_worker_can_lease_again(ledger):
    quarantine_worker_a(ledger, 0)

    ledger.release_worker("worker-a")

    assert ledger.list_quarantined() == []
    assert lease(ledger, 1, "worker-a").attempt_number == 1


def test_releasing_a_worker_that_is_not_quarantined_is_an_error(ledger):
    with pytest.raises(LedgerError, match="not quarantined"):
        ledger.release_worker("worker-a")

    quarantine_worker_a(ledger, 0)
    ledger.release_worker("worker-a")
    with pytest.raises(LedgerError, match="not quarantined"):
        ledger.release_worker("worker-a")


def test_only_the_named_worker_is_released(ledger):
    quarantine_worker_a(ledger, 0)
    fail(ledger, lease(ledger, 1, "worker-b"), RESTORE)

    ledger.release_worker("worker-a")

    assert [q.worker_id for q in ledger.list_quarantined()] == ["worker-b"]


@pytest.mark.parametrize("bad", [None, 7, b"worker-a"])
def test_a_worker_id_that_is_not_a_string_is_a_type_error(ledger, bad):
    with pytest.raises(TypeError):
        ledger.release_worker(bad)


def test_the_same_report_sent_again_after_the_release_does_not_quarantine_again(ledger):
    held = quarantine_worker_a(ledger, 0)
    ledger.release_worker("worker-a")

    fail(ledger, held, RESTORE)                                      # the ACK was lost, so the worker repeats the report

    assert ledger.list_quarantined() == []


def test_a_new_failed_restore_after_the_release_quarantines_again(ledger):
    quarantine_worker_a(ledger, 0)
    ledger.release_worker("worker-a")

    fail(ledger, lease(ledger, 1, "worker-a"), RESTORE)

    assert [(q.worker_id, q.candidate_id) for q in ledger.list_quarantined()] == [("worker-a", "exp/g0/c1")]


def test_the_list_is_ordered_by_time_then_by_name(ledger, clock):
    held_c = lease(ledger, 0, "worker-c")
    held_b = lease(ledger, 1, "worker-b")
    held_a = lease(ledger, 2, "worker-a")
    fail(ledger, held_c, RESTORE)
    clock.advance(1.0)
    fail(ledger, held_b, RESTORE)
    fail(ledger, held_a, RESTORE)                                    # same time as worker-b

    assert [q.worker_id for q in ledger.list_quarantined()] == ["worker-c", "worker-a", "worker-b"]


# ---------------------------------------------------------------------------
# the file, failures in the middle
# ---------------------------------------------------------------------------

def test_the_quarantine_survives_closing_and_reopening_the_file(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as first:
        first.open_generation(batch(2))
        quarantine_worker_a(first, 0)

    with Ledger(path, clock=clock) as again:
        assert [q.worker_id for q in again.list_quarantined()] == ["worker-a"]
        with pytest.raises(WorkerQuarantinedError):
            lease(again, 1, "worker-a")
        again.release_worker("worker-a")

    with Ledger(path, clock=clock) as last:
        assert last.list_quarantined() == []


def test_two_connections_agree_on_who_is_quarantined(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as first, Ledger(path, clock=clock) as second:
        first.open_generation(batch(2))
        quarantine_worker_a(first, 0)

        with pytest.raises(WorkerQuarantinedError):
            lease(second, 1, "worker-a")
        second.release_worker("worker-a")
        assert first.list_quarantined() == []


def test_a_failure_while_quarantining_leaves_the_attempt_open(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(2))
        held = lease(ledger, 0, "worker-a")
    raw = sqlite3.connect(path)                                      # the quarantine row is written last
    raw.execute("CREATE TRIGGER boom BEFORE INSERT ON quarantine BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    raw.commit()

    with Ledger(path, clock=clock) as ledger:
        with pytest.raises(LedgerError, match="injected failure"):   # the ledger's own error; the SQLite error is its cause
            fail(ledger, held, RESTORE)
        assert record(ledger).state is CandidateState.LEASED         # the failure itself was rolled back too
        row = raw.execute("SELECT failure_kind, ended_at FROM attempt").fetchone()
        assert row == (None, None)

        raw.execute("DROP TRIGGER boom")
        raw.commit()
        fail(ledger, held, RESTORE)
        assert [q.worker_id for q in ledger.list_quarantined()] == ["worker-a"]
    raw.close()


# ---------------------------------------------------------------------------
# the rules are in the database itself, not only in Python
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_after_quarantine(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(2))
        quarantine_worker_a(ledger, 0)
        lease(ledger, 1, "worker-b")
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA foreign_keys = ON")
    yield raw
    raw.close()


def insert_quarantine(raw, worker="worker-b", candidate_id="exp/g0/c1", attempt_number=1):
    raw.execute("INSERT INTO quarantine (worker_id, quarantined_at, candidate_id, attempt_number) VALUES (?, ?, ?, ?)",
                (worker, 1000.0, candidate_id, attempt_number))


def test_the_database_accepts_a_well_formed_quarantine_row(raw_after_quarantine):
    insert_quarantine(raw_after_quarantine)                          # the helper is sound: the refusals below are about one field


def test_the_database_refuses_a_worker_quarantined_twice(raw_after_quarantine):
    with pytest.raises(sqlite3.IntegrityError):
        insert_quarantine(raw_after_quarantine, worker="worker-a")


def test_the_database_refuses_a_quarantine_caused_by_an_attempt_that_does_not_exist(raw_after_quarantine):
    with pytest.raises(sqlite3.IntegrityError):
        insert_quarantine(raw_after_quarantine, attempt_number=2)
