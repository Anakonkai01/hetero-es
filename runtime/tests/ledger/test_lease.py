import re
import sqlite3
import time
from dataclasses import FrozenInstanceError

import pytest

from heteroes.ledger import (
    AlreadyLeasedError,
    CandidateState,
    Lease,
    Ledger,
    LedgerError,
    RetriesExhaustedError,
)
from ledger_helpers import FakeClock, batch, make

@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def ledger(clock):
    with Ledger(":memory:", clock=clock) as opened:
        opened.open_generation(batch(3))
        yield opened


def state_of(ledger, candidate_id):
    return ledger.get_candidate(candidate_id).state


def attempts_of(ledger, candidate_id):
    return ledger.get_candidate(candidate_id).attempts


def expire(clock, lease):
    clock.now = lease.deadline                     # a lease is over AT its deadline


# ---------------------------------------------------------------------------
# granting a lease
# ---------------------------------------------------------------------------

def test_a_candidate_that_was_never_leased_has_no_attempt(ledger):
    assert [record.attempts for record in ledger.list_candidates("exp", 0)] == [0, 0, 0]


def test_leasing_a_pending_candidate_gives_attempt_one_with_a_deadline(ledger, clock):
    lease = ledger.lease("exp/g0/c1", "worker-a", 30.0)

    assert isinstance(lease, Lease)
    assert lease.candidate_id == "exp/g0/c1"
    assert lease.attempt_number == 1
    assert lease.attempt_id == "exp/g0/c1/a1"
    assert lease.worker_id == "worker-a"
    assert lease.deadline == 1030.0                 # now (1000.0) + duration
    assert re.fullmatch(r"[0-9a-f]{32}", lease.token)
    record = ledger.get_candidate("exp/g0/c1")
    assert record.state is CandidateState.LEASED
    assert record.attempts == 1


def test_the_deadline_is_the_time_of_the_call_plus_the_duration(ledger, clock):
    clock.now = 2000.5

    lease = ledger.lease("exp/g0/c0", "worker-a", 0.25)

    assert lease.deadline == 2000.75


def test_leasing_one_candidate_leaves_the_others_alone(ledger):
    ledger.lease("exp/g0/c1", "worker-a", 30.0)

    assert [record.state for record in ledger.list_candidates("exp", 0)] == [
        CandidateState.PENDING, CandidateState.LEASED, CandidateState.PENDING]
    assert [record.attempts for record in ledger.list_candidates("exp", 0)] == [0, 1, 0]


def test_a_lease_cannot_be_changed(ledger):
    lease = ledger.lease("exp/g0/c0", "worker-a", 30.0)

    with pytest.raises(FrozenInstanceError):
        lease.worker_id = "worker-b"


def test_the_descriptor_of_a_candidate_does_not_change_when_it_is_leased(ledger):
    before = ledger.get_candidate("exp/g0/c2").descriptor

    ledger.lease("exp/g0/c2", "worker-a", 30.0)

    assert ledger.get_candidate("exp/g0/c2").descriptor == before == make(2, 1014)


def test_every_lease_gets_its_own_token():
    clock = FakeClock()
    with Ledger(":memory:", clock=clock, max_attempts=2) as ledger:
        ledger.open_generation(batch(40))
        leases = [ledger.lease(f"exp/g0/c{i}", "worker-a", 10.0) for i in range(40)]
        clock.advance(10.0)
        leases.append(ledger.lease("exp/g0/c0", "worker-a", 10.0))                # a retry of the first one

    tokens = [lease.token for lease in leases]
    assert len(set(tokens)) == 41
    assert all(re.fullmatch(r"[0-9a-f]{32}", token) for token in tokens)


# ---------------------------------------------------------------------------
# a lease that is still valid is respected
# ---------------------------------------------------------------------------

def test_a_candidate_with_a_valid_lease_cannot_be_leased_again(ledger, clock):
    first = ledger.lease("exp/g0/c0", "worker-a", 30.0)
    clock.advance(1.0)

    with pytest.raises(AlreadyLeasedError):
        ledger.lease("exp/g0/c0", "worker-b", 30.0)               # another worker
    with pytest.raises(AlreadyLeasedError):
        ledger.lease("exp/g0/c0", "worker-a", 30.0)               # and the same worker, too

    assert state_of(ledger, "exp/g0/c0") is CandidateState.LEASED
    assert attempts_of(ledger, "exp/g0/c0") == 1
    assert isinstance(first, Lease)


def test_refused_requests_do_not_extend_the_lease_that_exists(ledger, clock):
    ledger.lease("exp/g0/c0", "worker-a", 30.0)                    # deadline 1030.0
    clock.now = 1029.0
    with pytest.raises(AlreadyLeasedError):
        ledger.lease("exp/g0/c0", "worker-b", 100.0)

    clock.now = 1030.0                                             # had the refusal extended it, it would still be held

    assert state_of(ledger, "exp/g0/c0") is CandidateState.PENDING


def test_the_lease_is_valid_until_its_deadline_and_over_at_the_deadline(ledger, clock):
    ledger.lease("exp/g0/c0", "worker-a", 30.0)                    # deadline 1030.0

    clock.now = 1029.5
    assert state_of(ledger, "exp/g0/c0") is CandidateState.LEASED
    with pytest.raises(AlreadyLeasedError):
        ledger.lease("exp/g0/c0", "worker-b", 30.0)

    clock.now = 1030.0
    assert state_of(ledger, "exp/g0/c0") is CandidateState.PENDING
    assert ledger.lease("exp/g0/c0", "worker-b", 30.0).attempt_number == 2


# ---------------------------------------------------------------------------
# an expired lease: lazy recovery and retry as a new attempt
# ---------------------------------------------------------------------------

def test_an_expired_lease_is_seen_as_pending_by_every_read_and_reading_changes_nothing(ledger, clock):
    lease = ledger.lease("exp/g0/c0", "worker-a", 30.0)
    expire(clock, lease)

    assert state_of(ledger, "exp/g0/c0") is CandidateState.PENDING
    assert ledger.list_candidates("exp", 0)[0].state is CandidateState.PENDING
    assert ledger.list_candidates("exp", 0)[0].attempts == 1       # the attempt is history, it is not erased
    clock.now = lease.deadline - 1.0                               # back in time: had the reads written PENDING, it would stay
    assert state_of(ledger, "exp/g0/c0") is CandidateState.LEASED


def test_a_retry_is_a_new_attempt_of_the_same_candidate_with_a_new_token(ledger, clock):
    first = ledger.lease("exp/g0/c0", "worker-a", 30.0)
    expire(clock, first)

    second = ledger.lease("exp/g0/c0", "worker-b", 60.0)

    assert second.candidate_id == first.candidate_id
    assert (second.attempt_number, second.attempt_id) == (2, "exp/g0/c0/a2")
    assert second.worker_id == "worker-b"
    assert second.token != first.token
    assert second.deadline == 1030.0 + 60.0                        # counted from the time of the retry
    record = ledger.get_candidate("exp/g0/c0")
    assert record.state is CandidateState.LEASED and record.attempts == 2
    assert record.descriptor == make(0, 1000)                      # same seed, same job


def test_the_same_worker_may_take_a_candidate_again_after_its_lease_expired(ledger, clock):
    first = ledger.lease("exp/g0/c0", "worker-a", 30.0)
    expire(clock, first)

    assert ledger.lease("exp/g0/c0", "worker-a", 30.0).attempt_number == 2


def test_the_history_of_attempts_is_kept(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(1))
        first = ledger.lease("exp/g0/c0", "worker-a", 30.0)
        expire(clock, first)
        second = ledger.lease("exp/g0/c0", "worker-b", 30.0)

    raw = sqlite3.connect(path)
    try:
        rows = raw.execute("SELECT attempt_number, worker_id, lease_token, leased_at, deadline FROM attempt "
                           "WHERE candidate_id = 'exp/g0/c0' ORDER BY attempt_number").fetchall()
    finally:
        raw.close()
    assert rows == [(1, "worker-a", first.token, 1000.0, 1030.0), (2, "worker-b", second.token, 1030.0, 1060.0)]


# ---------------------------------------------------------------------------
# the retry budget
# ---------------------------------------------------------------------------

def test_by_default_a_candidate_gets_three_attempts(ledger, clock):
    for expected in (1, 2, 3):
        lease = ledger.lease("exp/g0/c0", "worker-a", 10.0)
        assert lease.attempt_number == expected
        expire(clock, lease)

    with pytest.raises(RetriesExhaustedError):
        ledger.lease("exp/g0/c0", "worker-a", 10.0)
    assert attempts_of(ledger, "exp/g0/c0") == 3


def test_the_budget_is_a_parameter():
    clock = FakeClock()
    with Ledger(":memory:", clock=clock, max_attempts=1) as ledger:
        ledger.open_generation(batch(2))
        lease = ledger.lease("exp/g0/c0", "worker-a", 10.0)
        expire(clock, lease)

        with pytest.raises(RetriesExhaustedError):
            ledger.lease("exp/g0/c0", "worker-b", 10.0)
        assert attempts_of(ledger, "exp/g0/c1") == 0                                # each candidate has its own budget

    clock = FakeClock()
    with Ledger(":memory:", clock=clock, max_attempts=5) as ledger:
        ledger.open_generation(batch(1))
        for expected in range(1, 6):
            lease = ledger.lease("exp/g0/c0", "worker-a", 10.0)
            assert lease.attempt_number == expected
            expire(clock, lease)
        with pytest.raises(RetriesExhaustedError):
            ledger.lease("exp/g0/c0", "worker-a", 10.0)


def test_a_valid_lease_is_reported_as_held_not_as_an_exhausted_budget():
    clock = FakeClock()
    with Ledger(":memory:", clock=clock, max_attempts=1) as ledger:
        ledger.open_generation(batch(1))
        ledger.lease("exp/g0/c0", "worker-a", 10.0)

        with pytest.raises(AlreadyLeasedError):                    # the last attempt is still running
            ledger.lease("exp/g0/c0", "worker-b", 10.0)


def test_the_two_refusals_are_ledger_errors_but_different_ones():
    assert issubclass(AlreadyLeasedError, LedgerError) and issubclass(RetriesExhaustedError, LedgerError)
    assert not issubclass(AlreadyLeasedError, RetriesExhaustedError)
    assert not issubclass(RetriesExhaustedError, AlreadyLeasedError)


@pytest.mark.parametrize("bad", [0, -1])
def test_a_budget_below_one_is_refused(bad):
    with pytest.raises(LedgerError):
        Ledger(":memory:", max_attempts=bad)


@pytest.mark.parametrize("bad", [True, 2.0, "3", None])
def test_a_budget_that_is_not_an_integer_is_a_type_error(bad):
    with pytest.raises(TypeError):
        Ledger(":memory:", max_attempts=bad)


# ---------------------------------------------------------------------------
# what cannot be leased, and bad arguments
# ---------------------------------------------------------------------------

def test_an_unknown_candidate_cannot_be_leased(ledger):
    with pytest.raises(LedgerError, match="unknown candidate"):
        ledger.lease("exp/g0/c9", "worker-a", 30.0)


@pytest.mark.parametrize("state", ["COMMITTED", "RUNNING"])
def test_a_candidate_that_is_neither_pending_nor_leased_cannot_be_leased(tmp_path, clock, state):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(2))
    raw = sqlite3.connect(path)
    raw.execute("UPDATE candidate SET state = ? WHERE candidate_id = 'exp/g0/c0'", (state,))
    raw.commit()
    raw.close()

    with Ledger(path, clock=clock) as ledger:
        with pytest.raises(LedgerError) as caught:
            ledger.lease("exp/g0/c0", "worker-a", 30.0)
        assert not isinstance(caught.value, (AlreadyLeasedError, RetriesExhaustedError))
        assert attempts_of(ledger, "exp/g0/c0") == 0
        assert ledger.lease("exp/g0/c1", "worker-a", 30.0).attempt_number == 1


def test_a_candidate_put_back_to_pending_can_be_leased_even_if_its_last_attempt_has_time_left(tmp_path, clock):
    # what a later step will do when a worker reports a failure: the state says PENDING, the old attempt row stays
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(1))
        ledger.lease("exp/g0/c0", "worker-a", 30.0)
    raw = sqlite3.connect(path)
    raw.execute("UPDATE candidate SET state = 'PENDING' WHERE candidate_id = 'exp/g0/c0'")
    raw.commit()
    raw.close()

    with Ledger(path, clock=clock) as ledger:
        assert state_of(ledger, "exp/g0/c0") is CandidateState.PENDING
        assert ledger.lease("exp/g0/c0", "worker-b", 30.0).attempt_number == 2


@pytest.mark.parametrize("worker_id, error", [("", LedgerError), (None, TypeError), (7, TypeError), (b"w", TypeError)])
def test_a_bad_worker_id_is_refused_and_changes_nothing(ledger, worker_id, error):
    with pytest.raises(error):
        ledger.lease("exp/g0/c0", worker_id, 30.0)

    assert state_of(ledger, "exp/g0/c0") is CandidateState.PENDING
    assert attempts_of(ledger, "exp/g0/c0") == 0


@pytest.mark.parametrize("duration, error", [
    (0, LedgerError), (0.0, LedgerError), (-1.0, LedgerError), (float("nan"), LedgerError),
    (float("inf"), LedgerError), (True, TypeError), ("30", TypeError), (None, TypeError),
])
def test_a_bad_duration_is_refused_and_changes_nothing(ledger, duration, error):
    with pytest.raises(error):
        ledger.lease("exp/g0/c0", "worker-a", duration)

    assert state_of(ledger, "exp/g0/c0") is CandidateState.PENDING
    assert attempts_of(ledger, "exp/g0/c0") == 0


def test_an_integer_duration_is_fine(ledger):
    assert ledger.lease("exp/g0/c0", "worker-a", 30).deadline == 1030.0


# ---------------------------------------------------------------------------
# the file, two readers, the real clock, failures
# ---------------------------------------------------------------------------

def test_a_lease_survives_closing_and_reopening_the_file(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(2))
        lease = ledger.lease("exp/g0/c0", "worker-a", 30.0)

    clock.advance(10.0)
    with Ledger(path, clock=clock) as again:
        record = again.get_candidate("exp/g0/c0")
        assert (record.state, record.attempts) == (CandidateState.LEASED, 1)
        with pytest.raises(AlreadyLeasedError):
            again.lease("exp/g0/c0", "worker-b", 30.0)

        expire(clock, lease)                                       # time passes while nobody runs the ledger
        assert again.get_candidate("exp/g0/c0").state is CandidateState.PENDING
        assert again.lease("exp/g0/c0", "worker-b", 30.0).attempt_number == 2


def test_two_connections_to_the_same_file_see_each_others_leases(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as first, Ledger(path, clock=clock) as second:
        first.open_generation(batch(2))
        first.lease("exp/g0/c0", "worker-a", 30.0)

        with pytest.raises(AlreadyLeasedError):
            second.lease("exp/g0/c0", "worker-b", 30.0)
        assert second.get_candidate("exp/g0/c0").attempts == 1
        assert second.lease("exp/g0/c1", "worker-b", 30.0).attempt_number == 1
        assert first.get_candidate("exp/g0/c1").state is CandidateState.LEASED


def test_without_a_clock_the_ledger_uses_real_time():
    with Ledger(":memory:") as ledger:
        ledger.open_generation(batch(1))
        before = time.time()
        lease = ledger.lease("exp/g0/c0", "worker-a", 10.0)
        after = time.time()

    assert before + 10.0 <= lease.deadline <= after + 10.0


def test_a_failure_while_leasing_writes_nothing(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(2))
    raw = sqlite3.connect(path)                              # the attempt row is written first, then the candidate row
    raw.execute("CREATE TRIGGER boom BEFORE UPDATE ON candidate BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    raw.commit()

    with Ledger(path, clock=clock) as ledger:
        with pytest.raises(LedgerError, match="injected failure") as raised:     # the ledger's own error, the SQLite error is its cause
            ledger.lease("exp/g0/c0", "worker-a", 30.0)
        assert isinstance(raised.value.__cause__, sqlite3.Error)
        assert attempts_of(ledger, "exp/g0/c0") == 0         # the attempt row that had been written is gone
        assert state_of(ledger, "exp/g0/c0") is CandidateState.PENDING

        raw.execute("DROP TRIGGER boom")
        raw.commit()
        assert ledger.lease("exp/g0/c0", "worker-a", 30.0).attempt_number == 1
    raw.close()


# ---------------------------------------------------------------------------
# the rules are in the database itself, not only in Python
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_after_lease(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(2))
        ledger.lease("exp/g0/c0", "worker-a", 30.0)
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA foreign_keys = ON")
    yield raw
    raw.close()


def insert_attempt(raw, candidate_id="exp/g0/c1", number=1, worker="worker-b", token="f" * 32, leased_at=1000.0,
                   deadline=1030.0):
    raw.execute("INSERT INTO attempt (candidate_id, attempt_number, worker_id, lease_token, leased_at, deadline) "
                "VALUES (?, ?, ?, ?, ?, ?)", (candidate_id, number, worker, token, leased_at, deadline))


def test_the_database_accepts_a_well_formed_attempt(raw_after_lease):
    insert_attempt(raw_after_lease)                          # the helper itself is sound: the refusals below are about one field


def test_the_database_refuses_a_second_attempt_with_the_same_number(raw_after_lease):
    with pytest.raises(sqlite3.IntegrityError):
        insert_attempt(raw_after_lease, candidate_id="exp/g0/c0", number=1, token="e" * 32)


def test_the_database_refuses_a_token_used_twice(raw_after_lease):
    token = raw_after_lease.execute("SELECT lease_token FROM attempt").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        insert_attempt(raw_after_lease, token=token)


def test_the_database_refuses_an_attempt_of_a_candidate_that_does_not_exist(raw_after_lease):
    with pytest.raises(sqlite3.IntegrityError):
        insert_attempt(raw_after_lease, candidate_id="exp/g0/c9")


def test_the_database_refuses_attempt_number_zero(raw_after_lease):
    with pytest.raises(sqlite3.IntegrityError):
        insert_attempt(raw_after_lease, number=0)


@pytest.mark.parametrize("deadline", [1000.0, 999.0])
def test_the_database_refuses_a_deadline_that_is_not_after_the_start(raw_after_lease, deadline):
    with pytest.raises(sqlite3.IntegrityError):
        insert_attempt(raw_after_lease, leased_at=1000.0, deadline=deadline)
