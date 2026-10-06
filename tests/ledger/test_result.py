import sqlite3

import pytest

from heteroes.ledger import (
    AlreadyLeasedError,
    CandidateResult,
    CandidateState,
    ConflictingResultError,
    FailureKind,
    Ledger,
    LedgerError,
    ResultMismatchError,
    RetriesExhaustedError,
    StaleAttemptError,
    SubmitOutcome,
)
from ledger_helpers import FakeClock, batch, descriptor_of, fail, lease, make, record, submit


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def ledger(clock):
    with Ledger(":memory:", clock=clock) as opened:
        opened.open_generation(batch(3))
        yield opened


# ---------------------------------------------------------------------------
# submitting a result
# ---------------------------------------------------------------------------

def test_a_candidate_without_a_result_says_so(ledger):
    assert [r.result for r in ledger.list_candidates("exp", 0)] == [None, None, None]


def test_a_valid_result_commits_the_candidate(ledger, clock):
    held = lease(ledger)
    clock.advance(5.0)

    outcome = submit(ledger, held, 0.5)

    assert outcome is SubmitOutcome.COMMITTED
    committed = record(ledger)
    assert committed.state is CandidateState.COMMITTED
    assert committed.result == CandidateResult(attempt_number=1, reward=0.5, committed_at=1005.0)
    assert committed.attempts == 1
    assert committed.descriptor == descriptor_of(0)


def test_committing_one_candidate_leaves_the_others_alone(ledger):
    lease(ledger, 1)
    held = lease(ledger, 0)

    submit(ledger, held)

    assert [r.state for r in ledger.list_candidates("exp", 0)] == [
        CandidateState.COMMITTED, CandidateState.LEASED, CandidateState.PENDING]
    assert [r.result is None for r in ledger.list_candidates("exp", 0)] == [False, True, True]


@pytest.mark.parametrize("reward", [0, 1, 0.25, -2.5, 1e300, 5e-324])
def test_any_finite_number_is_a_reward(ledger, reward):
    submit(ledger, lease(ledger), reward)

    assert record(ledger).result.reward == reward                  # (0 and 0.0 are equal: the ledger does not police a range)


def test_a_result_may_arrive_after_the_deadline_when_nobody_else_took_the_candidate(ledger, clock):
    held = lease(ledger)                                           # deadline 1030.0
    clock.now = 5000.0                                             # long over
    assert record(ledger).state is CandidateState.PENDING          # (the read says: free to be given again)

    assert submit(ledger, held, 0.75) is SubmitOutcome.COMMITTED

    assert record(ledger).state is CandidateState.COMMITTED
    assert record(ledger).result.committed_at == 5000.0


def test_a_commit_stays_a_commit_when_time_passes(ledger, clock):
    held = lease(ledger)
    submit(ledger, held)

    clock.now = 10_000.0

    assert record(ledger).state is CandidateState.COMMITTED


def test_a_committed_candidate_cannot_be_leased_again(ledger, clock):
    submit(ledger, lease(ledger))
    clock.now = 10_000.0

    with pytest.raises(LedgerError) as caught:
        lease(ledger)
    assert not isinstance(caught.value, (AlreadyLeasedError, RetriesExhaustedError))


# ---------------------------------------------------------------------------
# the reward must be a real number
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reward, error", [
    (float("nan"), LedgerError), (float("inf"), LedgerError), (float("-inf"), LedgerError),
    (True, TypeError), (False, TypeError), ("0.5", TypeError), (None, TypeError), ([0.5], TypeError),
])
def test_a_bad_reward_is_refused_and_the_attempt_stays_open(ledger, reward, error):
    held = lease(ledger)

    with pytest.raises(error):
        submit(ledger, held, reward)

    assert record(ledger).state is CandidateState.LEASED and record(ledger).result is None
    assert submit(ledger, held, 0.5) is SubmitOutcome.COMMITTED    # the same attempt can still deliver a good one


# ---------------------------------------------------------------------------
# the result must be of the job that was given
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("what, wrong", [
    ("seed", make(0, 4242)),
    ("recipe", make(0, 1000, recipe_hash="c" * 64)),
    ("parent weights", make(0, 1000, parent_weights_sha256="d" * 64)),
    ("another candidate's seed", make(0, 1007)),
])
def test_a_result_for_another_job_is_refused_and_changes_nothing(ledger, what, wrong):
    held = lease(ledger)

    with pytest.raises(ResultMismatchError):
        submit(ledger, held, 0.5, descriptor=wrong)

    assert record(ledger).state is CandidateState.LEASED and record(ledger).result is None
    assert submit(ledger, held, 0.5) is SubmitOutcome.COMMITTED


def test_the_mismatch_says_which_fields_differ(ledger):
    held = lease(ledger)

    with pytest.raises(ResultMismatchError, match="seed"):
        submit(ledger, held, 0.5, descriptor=make(0, 4242))


@pytest.mark.parametrize("wrong", [make(0, 1000, generation=5), make(0, 1000, experiment_id="other"), make(9, 1000)])
def test_a_result_for_a_candidate_that_does_not_exist_is_refused(ledger, wrong):
    held = lease(ledger)

    with pytest.raises(LedgerError, match="unknown candidate") as caught:
        submit(ledger, held, 0.5, descriptor=wrong)
    assert not isinstance(caught.value, (ResultMismatchError, StaleAttemptError))


# ---------------------------------------------------------------------------
# only the latest attempt, with its own token
# ---------------------------------------------------------------------------

def test_a_wrong_token_is_refused(ledger):
    held = lease(ledger)

    with pytest.raises(StaleAttemptError):
        ledger.submit_result(descriptor_of(0), held.attempt_number, "0" * 32, 0.5)

    assert record(ledger).result is None and record(ledger).state is CandidateState.LEASED


def test_the_token_of_another_candidate_is_refused(ledger):
    mine = lease(ledger, 0)
    other = lease(ledger, 1)

    with pytest.raises(StaleAttemptError):
        ledger.submit_result(descriptor_of(0), mine.attempt_number, other.token, 0.5)


@pytest.mark.parametrize("attempt_number", [0, 2, 99])
def test_a_wrong_attempt_number_is_refused_even_with_the_right_token(ledger, attempt_number):
    held = lease(ledger)

    with pytest.raises(StaleAttemptError):
        ledger.submit_result(descriptor_of(0), attempt_number, held.token, 0.5)


def test_a_candidate_that_was_never_leased_has_no_attempt_to_submit_for(ledger):
    with pytest.raises(StaleAttemptError):
        ledger.submit_result(descriptor_of(0), 1, "0" * 32, 0.5)


def test_an_old_attempt_cannot_commit_once_the_candidate_was_given_again(ledger, clock):
    first = lease(ledger, worker="worker-a")                       # deadline 1030.0
    clock.now = 1030.0
    second = lease(ledger, worker="worker-b")                      # attempt 2

    with pytest.raises(StaleAttemptError):
        submit(ledger, first, 0.9)
    assert record(ledger).result is None and record(ledger).state is CandidateState.LEASED

    assert submit(ledger, second, 0.5) is SubmitOutcome.COMMITTED
    assert record(ledger).result == CandidateResult(attempt_number=2, reward=0.5, committed_at=1030.0)


def test_an_old_attempt_arriving_after_the_new_one_committed_is_refused(ledger, clock):
    first = lease(ledger, worker="worker-a")
    clock.now = 1030.0
    second = lease(ledger, worker="worker-b")
    submit(ledger, second, 0.5)

    with pytest.raises(StaleAttemptError):
        submit(ledger, first, 0.5)                                 # even with the same reward

    assert record(ledger).result.attempt_number == 2


@pytest.mark.parametrize("bad", [True, "1", 1.0, None])
def test_an_attempt_number_that_is_not_an_integer_is_a_type_error(ledger, bad):
    held = lease(ledger)

    with pytest.raises(TypeError):
        ledger.submit_result(descriptor_of(0), bad, held.token, 0.5)


@pytest.mark.parametrize("bad", [None, 7, b"abc"])
def test_a_token_that_is_not_a_string_is_a_type_error(ledger, bad):
    held = lease(ledger)

    with pytest.raises(TypeError):
        ledger.submit_result(descriptor_of(0), held.attempt_number, bad, 0.5)


@pytest.mark.parametrize("bad", [None, {"seed": 1000}, "exp/g0/c0"])
def test_something_that_is_not_a_descriptor_is_a_type_error(ledger, bad):
    held = lease(ledger)

    with pytest.raises(TypeError):
        ledger.submit_result(bad, held.attempt_number, held.token, 0.5)


# ---------------------------------------------------------------------------
# sending the same result again (the ACK was lost)
# ---------------------------------------------------------------------------

def test_the_same_result_again_is_acknowledged_and_changes_nothing(ledger, clock):
    held = lease(ledger)
    clock.advance(5.0)
    submit(ledger, held, 0.5)
    before = record(ledger)
    clock.advance(100.0)

    assert submit(ledger, held, 0.5) is SubmitOutcome.ALREADY_COMMITTED
    assert submit(ledger, held, 0.5) is SubmitOutcome.ALREADY_COMMITTED

    assert record(ledger) == before                                # same reward, same attempt, same commit time


def test_the_same_number_written_as_int_or_float_is_the_same_result(ledger):
    held = lease(ledger)
    submit(ledger, held, 1)

    assert submit(ledger, held, 1.0) is SubmitOutcome.ALREADY_COMMITTED


@pytest.mark.parametrize("other", [0.7, 0.5000000000000001, -0.5])
def test_another_reward_for_the_same_attempt_is_a_conflict_and_the_first_stays(ledger, other):
    held = lease(ledger)
    submit(ledger, held, 0.5)
    before = record(ledger)

    with pytest.raises(ConflictingResultError):
        submit(ledger, held, other)

    assert record(ledger) == before and before.result.reward == 0.5


# ---------------------------------------------------------------------------
# reporting a failure: never a reward
# ---------------------------------------------------------------------------

def test_a_reported_failure_frees_the_candidate_at_once_and_gives_no_reward(ledger, clock):
    held = lease(ledger)                                           # deadline 1030.0: lots of time left
    clock.advance(1.0)

    fail(ledger, held, FailureKind.OUT_OF_MEMORY)

    after = record(ledger)
    assert after.state is CandidateState.PENDING
    assert after.result is None
    assert after.attempts == 1
    assert after.descriptor == descriptor_of(0)


def test_a_failed_candidate_is_given_again_as_the_next_attempt(ledger, clock):
    first = lease(ledger, worker="worker-a")
    fail(ledger, first)                                            # no waiting for the lease to expire

    second = lease(ledger, worker="worker-b")

    assert (second.attempt_number, second.worker_id) == (2, "worker-b")
    assert second.token != first.token
    assert submit(ledger, second, 0.5) is SubmitOutcome.COMMITTED


def test_a_failure_uses_up_an_attempt_of_the_budget(ledger):
    for expected in (1, 2, 3):
        held = lease(ledger)
        assert held.attempt_number == expected
        fail(ledger, held)

    with pytest.raises(RetriesExhaustedError):
        lease(ledger)
    assert record(ledger).result is None and record(ledger).attempts == 3


@pytest.mark.parametrize("kind", list(FailureKind))
def test_every_kind_of_failure_is_recorded_under_its_name(tmp_path, clock, kind):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(1))
        clock.advance(2.0)
        fail(ledger, lease(ledger), kind)

    assert attempt_row(path, "exp/g0/c0", 1)["failure_kind"] == kind.name
    assert attempt_row(path, "exp/g0/c0", 1)["ended_at"] == 1002.0


def test_the_four_kinds_of_failure():
    assert {kind.name: kind.value for kind in FailureKind} == {
        "OUT_OF_MEMORY": "OUT_OF_MEMORY", "VERIFIER_ERROR": "VERIFIER_ERROR",
        "RESTORE_MISMATCH": "RESTORE_MISMATCH", "OTHER": "OTHER"}


@pytest.mark.parametrize("bad", ["OTHER", "OOM", None, 3])
def test_a_failure_kind_must_be_one_of_the_enum(ledger, bad):
    held = lease(ledger)

    with pytest.raises(TypeError):
        ledger.report_failure(descriptor_of(0), held.attempt_number, held.token, bad)

    assert record(ledger).state is CandidateState.LEASED


def test_a_failure_of_an_old_attempt_is_refused(ledger, clock):
    first = lease(ledger, worker="worker-a")
    clock.now = 1030.0
    second = lease(ledger, worker="worker-b")

    with pytest.raises(StaleAttemptError):
        fail(ledger, first)

    assert record(ledger).state is CandidateState.LEASED          # the attempt that is really running is untouched
    assert submit(ledger, second) is SubmitOutcome.COMMITTED


def test_a_failure_with_a_wrong_token_or_for_another_job_is_refused(ledger):
    held = lease(ledger)

    with pytest.raises(StaleAttemptError):
        ledger.report_failure(descriptor_of(0), held.attempt_number, "0" * 32, FailureKind.OTHER)
    with pytest.raises(ResultMismatchError):
        fail(ledger, held, descriptor=make(0, 4242))

    assert record(ledger).state is CandidateState.LEASED


def test_a_candidate_that_was_never_leased_cannot_fail(ledger):
    with pytest.raises(StaleAttemptError):
        ledger.report_failure(descriptor_of(0), 1, "0" * 32, FailureKind.OTHER)


def test_a_committed_attempt_cannot_be_reported_as_failed(ledger):
    held = lease(ledger)
    submit(ledger, held, 0.5)

    with pytest.raises(StaleAttemptError):
        fail(ledger, held)

    assert record(ledger).state is CandidateState.COMMITTED and record(ledger).result.reward == 0.5


def test_a_failed_attempt_cannot_deliver_a_result_afterwards(ledger):
    held = lease(ledger)
    fail(ledger, held)

    with pytest.raises(StaleAttemptError):
        submit(ledger, held, 0.5)

    assert record(ledger).result is None and record(ledger).state is CandidateState.PENDING


def test_the_same_failure_reported_twice_is_acknowledged_and_changes_nothing(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(1))
        held = lease(ledger)
        clock.advance(2.0)
        fail(ledger, held, FailureKind.VERIFIER_ERROR)
        clock.advance(50.0)

        fail(ledger, held, FailureKind.VERIFIER_ERROR)

        assert record(ledger).attempts == 1 and record(ledger).state is CandidateState.PENDING
    assert attempt_row(path, "exp/g0/c0", 1)["ended_at"] == 1002.0       # not rewritten


def test_another_kind_of_failure_for_the_same_attempt_is_a_conflict(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(1))
        held = lease(ledger)
        fail(ledger, held, FailureKind.VERIFIER_ERROR)

        with pytest.raises(ConflictingResultError):
            fail(ledger, held, FailureKind.OUT_OF_MEMORY)
    assert attempt_row(path, "exp/g0/c0", 1)["failure_kind"] == "VERIFIER_ERROR"


def test_a_failure_report_after_a_new_attempt_started_is_refused_even_if_it_repeats_the_old_one(ledger):
    first = lease(ledger)
    fail(ledger, first)
    lease(ledger)                                                  # attempt 2 is running

    with pytest.raises(StaleAttemptError):
        fail(ledger, first)

    assert record(ledger).state is CandidateState.LEASED


# ---------------------------------------------------------------------------
# the file, two connections, failures in the middle
# ---------------------------------------------------------------------------

def attempt_row(path, candidate_id, number):
    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row
    try:
        return dict(raw.execute("SELECT * FROM attempt WHERE candidate_id = ? AND attempt_number = ?",
                                (candidate_id, number)).fetchone())
    finally:
        raw.close()


def test_committing_closes_the_attempt_without_a_failure(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(1))
        held = lease(ledger)
        clock.advance(7.0)
        submit(ledger, held, 0.5)

    row = attempt_row(path, "exp/g0/c0", 1)
    assert row["ended_at"] == 1007.0 and row["failure_kind"] is None


def test_a_commit_survives_closing_and_reopening_the_file(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(2))
        held = lease(ledger)
        clock.advance(3.0)
        submit(ledger, held, 0.625)

    clock.advance(1000.0)
    with Ledger(path, clock=clock) as again:
        committed = record(again)
        assert committed.state is CandidateState.COMMITTED
        assert committed.result == CandidateResult(attempt_number=1, reward=0.625, committed_at=1003.0)
        assert submit(again, held, 0.625) is SubmitOutcome.ALREADY_COMMITTED
        with pytest.raises(ConflictingResultError):
            submit(again, held, 0.5)
        assert record(again, 1).state is CandidateState.PENDING


def test_a_failure_survives_closing_and_reopening_the_file(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(1))
        fail(ledger, lease(ledger), FailureKind.VERIFIER_ERROR)

    with Ledger(path, clock=clock) as again:
        assert record(again).state is CandidateState.PENDING and record(again).attempts == 1
        assert lease(again).attempt_number == 2


def test_two_connections_to_the_same_file_agree_on_who_committed(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as first, Ledger(path, clock=clock) as second:
        first.open_generation(batch(1))
        held = lease(first)
        assert submit(first, held, 0.5) is SubmitOutcome.COMMITTED

        assert submit(second, held, 0.5) is SubmitOutcome.ALREADY_COMMITTED
        with pytest.raises(ConflictingResultError):
            submit(second, held, 0.9)
        assert record(second).result.reward == 0.5


def test_a_failure_while_committing_writes_nothing(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(1))
        held = lease(ledger)
    raw = sqlite3.connect(path)                                    # the result row is written first, the candidate row last
    raw.execute("CREATE TRIGGER boom BEFORE UPDATE ON candidate WHEN NEW.state = 'COMMITTED' "
                "BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    raw.commit()

    with Ledger(path, clock=clock) as ledger:
        with pytest.raises(sqlite3.Error, match="injected failure"):
            submit(ledger, held, 0.5)
        assert record(ledger).result is None and record(ledger).state is CandidateState.LEASED
        assert attempt_row(path, "exp/g0/c0", 1)["ended_at"] is None

        raw.execute("DROP TRIGGER boom")
        raw.commit()
        assert submit(ledger, held, 0.5) is SubmitOutcome.COMMITTED
    raw.close()


def test_a_failure_while_reporting_a_failure_writes_nothing(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(1))
        held = lease(ledger)
    raw = sqlite3.connect(path)                                    # the attempt row is written first, the candidate row last
    raw.execute("CREATE TRIGGER boom BEFORE UPDATE ON candidate WHEN NEW.state = 'PENDING' "
                "BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    raw.commit()

    with Ledger(path, clock=clock) as ledger:
        with pytest.raises(sqlite3.Error, match="injected failure"):
            fail(ledger, held)
        row = attempt_row(path, "exp/g0/c0", 1)
        assert row["failure_kind"] is None and row["ended_at"] is None
        assert record(ledger).state is CandidateState.LEASED
    raw.close()


# ---------------------------------------------------------------------------
# the rules are in the database itself, not only in Python
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_after_commit(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(2))
        submit(ledger, lease(ledger, 0), 0.5)
        lease(ledger, 1)
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA foreign_keys = ON")
    yield raw
    raw.close()


def insert_result(raw, candidate_id="exp/g0/c1", attempt_number=1, reward=0.25, committed_at=1001.0):
    raw.execute("INSERT INTO result (candidate_id, attempt_number, reward, committed_at) VALUES (?, ?, ?, ?)",
                (candidate_id, attempt_number, reward, committed_at))


def test_the_database_accepts_a_well_formed_result(raw_after_commit):
    insert_result(raw_after_commit)                                # the helper is sound: the refusals below are about one field


def test_the_database_refuses_a_second_result_for_a_candidate(raw_after_commit):
    with pytest.raises(sqlite3.IntegrityError):
        insert_result(raw_after_commit, candidate_id="exp/g0/c0", reward=0.9)


def test_the_database_refuses_a_result_of_an_attempt_that_does_not_exist(raw_after_commit):
    with pytest.raises(sqlite3.IntegrityError):
        insert_result(raw_after_commit, attempt_number=2)


def test_the_database_refuses_a_result_of_a_candidate_that_does_not_exist(raw_after_commit):
    with pytest.raises(sqlite3.IntegrityError):
        insert_result(raw_after_commit, candidate_id="exp/g0/c9")


def test_the_database_refuses_a_failure_kind_that_is_not_one_of_the_four(raw_after_commit):
    with pytest.raises(sqlite3.IntegrityError):
        raw_after_commit.execute("UPDATE attempt SET ended_at = 1002.0, failure_kind = 'BORED' "
                                 "WHERE candidate_id = 'exp/g0/c1'")


def test_the_database_refuses_a_failure_that_has_no_end_time(raw_after_commit):
    with pytest.raises(sqlite3.IntegrityError):
        raw_after_commit.execute("UPDATE attempt SET failure_kind = 'OTHER' WHERE candidate_id = 'exp/g0/c1'")
