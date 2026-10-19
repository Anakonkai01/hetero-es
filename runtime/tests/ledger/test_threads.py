"""
The ledger with real threads.

A coordinator that serves HTTP has several threads, and a worker's request can arrive while another is being handled.
Two things must hold, and these tests use real threads (not simulated time) to check them:
  * ONE Ledger object shared by many threads: every method takes one lock, so a transaction is never interleaved with another
    one on the same connection;
  * SEVERAL Ledger objects (connections) on the same file, as when two processes meet: the write lock is taken BEFORE reading
    (BEGIN IMMEDIATE), so two writers cannot both pass the same check; the loser sees the winner's row and is refused with
    the proper ledger error, never with a database error.
"""
import threading
import time

import pytest

from heteroes.generation_record import GenerationRecord
from heteroes.ledger import (
    AlreadyLeasedError,
    ConflictingResultError,
    ConflictingUpdateError,
    FailureKind,
    GenerationState,
    Ledger,
    LedgerError,
    StaleAttemptError,
    SubmitOutcome,
    UpdateOutcome,
)
from ledger_helpers import FakeClock, batch, descriptor_of

N = 40
ROUNDS = 60


def reward_of(index):
    return index / 64


def run_threads(targets):
    """Start every target in its own thread, wait for all, and return the exceptions they died of."""
    errors = []

    def guarded(target):
        try:
            target()
        except BaseException as error:      # noqa: BLE001 - a test must see every kind of failure
            errors.append(error)

    threads = [threading.Thread(target=guarded, args=(target,), daemon=True) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "a thread is stuck (a deadlock?)"
    return errors


# ---------------------------------------------------------------------------
# one ledger, many threads
# ---------------------------------------------------------------------------

def test_one_ledger_shared_by_many_threads_commits_every_candidate_exactly_once():
    ledger = Ledger(":memory:", clock=FakeClock())                  # made here, used in other threads
    ledger.open_generation(batch(N))
    committed_by = {}
    guard = threading.Lock()
    start = threading.Barrier(8)

    def worker(name):
        start.wait(timeout=30)
        while ledger.get_generation_status("exp", 0).state is not GenerationState.COMPLETE:
            for index in range(N):
                try:
                    lease = ledger.lease(f"exp/g0/c{index}", name, 600.0)
                except LedgerError:                                  # somebody else has it, or it is committed already
                    continue
                if index % 5 == 0 and lease.attempt_number == 1:     # these candidates fail once, then are retried
                    ledger.report_failure(descriptor_of(index), lease.attempt_number, lease.token, FailureKind.OTHER)
                    continue
                outcome = ledger.submit_result(descriptor_of(index), lease.attempt_number, lease.token, reward_of(index))
                assert outcome is SubmitOutcome.COMMITTED
                with guard:
                    assert index not in committed_by, f"candidate {index} was committed twice"
                    committed_by[index] = name
                time.sleep(0.0005)                                   # let the other threads in
                ledger.list_candidates("exp", 0)

    errors = run_threads([lambda n=f"worker-{i}": worker(n) for i in range(8)])

    assert errors == []
    assert sorted(committed_by) == list(range(N))
    records = ledger.list_candidates("exp", 0)
    assert [r.attempts for r in records] == [2 if i % 5 == 0 else 1 for i in range(N)]
    assert ledger.get_generation_results("exp", 0).rewards == tuple(reward_of(i) for i in range(N))
    assert len(set(committed_by.values())) > 1, "premise: more than one thread really took part"


def test_the_same_generation_opened_by_many_threads_is_opened_once():
    ledger = Ledger(":memory:", clock=FakeClock())
    wins = {g: [] for g in range(ROUNDS)}
    start = threading.Barrier(6)

    def opener(name):
        start.wait(timeout=30)
        for generation in range(ROUNDS):
            try:
                ledger.open_generation(batch(5, generation=generation))
            except LedgerError:
                continue
            wins[generation].append(name)

    errors = run_threads([lambda n=f"opener-{i}": opener(n) for i in range(6)])

    assert errors == []
    assert all(len(winners) == 1 for winners in wins.values())
    assert all(len(ledger.list_candidates("exp", g)) == 5 for g in range(ROUNDS))


def test_readers_and_writers_on_one_ledger_do_not_disturb_each_other():
    ledger = Ledger(":memory:", clock=FakeClock())
    ledger.open_generation(batch(N))
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            status = ledger.get_generation_status("exp", 0)
            assert 0 <= status.committed <= N
            ledger.list_candidates("exp", 0)
            ledger.list_quarantined()

    def writer():
        for index in range(N):
            lease = ledger.lease(f"exp/g0/c{index}", "writer", 600.0)
            ledger.submit_result(descriptor_of(index), lease.attempt_number, lease.token, reward_of(index))
        stop.set()

    errors = run_threads([reader, reader, reader, writer])

    assert errors == []
    assert ledger.get_generation_status("exp", 0).committed == N


# ---------------------------------------------------------------------------
# several connections to one file: the write lock is taken before reading
# ---------------------------------------------------------------------------

@pytest.fixture
def two_ledgers(tmp_path):
    path = tmp_path / "ledger.sqlite"
    clock = FakeClock()
    first, second = Ledger(path, clock=clock), Ledger(path, clock=clock)
    first.open_generation(batch(ROUNDS))
    yield first, second
    first.close()
    second.close()


def race(first, second, action_first, action_second):
    """Run the two actions at the same moment, as often as there are rounds; return, per round, what each one gave."""
    outcomes = [[None, None] for _ in range(ROUNDS)]
    barrier = threading.Barrier(2)

    def runner(slot, action):
        def target():
            for round_ in range(ROUNDS):
                barrier.wait(timeout=30)
                try:
                    outcomes[round_][slot] = ("ok", action(round_))
                except LedgerError as error:
                    outcomes[round_][slot] = ("refused", type(error))
            return None
        return target

    errors = run_threads([runner(0, action_first), runner(1, action_second)])
    return outcomes, errors


def test_two_connections_cannot_both_lease_the_same_candidate(two_ledgers):
    first, second = two_ledgers

    outcomes, errors = race(first, second,
                            lambda r: first.lease(f"exp/g0/c{r}", "worker-a", 600.0),
                            lambda r: second.lease(f"exp/g0/c{r}", "worker-b", 600.0))

    assert errors == []                                         # never a database error
    for round_, (a, b) in enumerate(outcomes):
        kinds = sorted([a[0], b[0]])
        assert kinds == ["ok", "refused"], f"round {round_}: {a}, {b}"
        refused = a if a[0] == "refused" else b
        assert refused[1] is AlreadyLeasedError
    assert [r.attempts for r in first.list_candidates("exp", 0)] == [1] * ROUNDS


def test_two_connections_cannot_both_commit_a_result_for_the_same_attempt(two_ledgers):
    first, second = two_ledgers
    leases = [first.lease(f"exp/g0/c{r}", "worker-a", 600.0) for r in range(ROUNDS)]

    def submit(ledger, reward):
        return lambda r: ledger.submit_result(descriptor_of(r), leases[r].attempt_number, leases[r].token, reward)

    outcomes, errors = race(first, second, submit(first, 0.25), submit(second, 0.75))

    assert errors == []
    for round_, (a, b) in enumerate(outcomes):
        assert sorted([a[0], b[0]]) == ["ok", "refused"], f"round {round_}: {a}, {b}"
        refused = a if a[0] == "refused" else b
        assert refused[1] is ConflictingResultError
        winner = a if a[0] == "ok" else b
        assert winner[1] is SubmitOutcome.COMMITTED
        committed = first.get_candidate(f"exp/g0/c{round_}").result.reward
        assert committed == (0.25 if a[0] == "ok" else 0.75)     # the stored reward is the winner's


def test_a_failure_and_a_result_for_the_same_attempt_cannot_both_be_written(two_ledgers):
    first, second = two_ledgers
    leases = [first.lease(f"exp/g0/c{r}", "worker-a", 600.0) for r in range(ROUNDS)]

    outcomes, errors = race(
        first, second,
        lambda r: first.report_failure(descriptor_of(r), leases[r].attempt_number, leases[r].token, FailureKind.OTHER),
        lambda r: second.submit_result(descriptor_of(r), leases[r].attempt_number, leases[r].token, 0.5))

    assert errors == []
    for round_, (a, b) in enumerate(outcomes):
        assert sorted([a[0], b[0]]) == ["ok", "refused"], f"round {round_}: {a}, {b}"
        assert (a if a[0] == "refused" else b)[1] is StaleAttemptError
        row = first._db.execute("SELECT failure_kind FROM attempt WHERE candidate_id = ?", (f"exp/g0/c{round_}",)).fetchone()
        committed = first.get_candidate(f"exp/g0/c{round_}").result is not None
        assert committed == (row[0] is None)                        # an attempt either failed or carries a result, never both


def test_two_connections_cannot_both_record_an_update(tmp_path):
    path = tmp_path / "ledger.sqlite"
    clock = FakeClock()
    first, second = Ledger(path, clock=clock), Ledger(path, clock=clock)
    try:
        for generation in range(ROUNDS):
            first.open_generation(batch(2, generation=generation))
            for index in range(2):
                lease = first.lease(f"exp/g{generation}/c{index}", "worker-a", 600.0)
                first.submit_result(batch(2, generation=generation)[index], lease.attempt_number, lease.token,
                                    0.25 * (index + 1))

        def record(ledger, alpha):
            def action(generation):
                results = ledger.get_generation_results("exp", generation)
                return ledger.record_update(
                    GenerationRecord.from_results("exp", generation, results, alpha=alpha, eta=1e-9))
            return action

        outcomes, errors = race(first, second, record(first, 1e-3), record(second, 2e-3))

        assert errors == []
        for round_, (a, b) in enumerate(outcomes):
            assert sorted([a[0], b[0]]) == ["ok", "refused"], f"round {round_}: {a}, {b}"
            refused = a if a[0] == "refused" else b
            assert refused[1] is ConflictingUpdateError
            assert (a if a[0] == "ok" else b)[1] is UpdateOutcome.RECORDED
    finally:
        first.close()
        second.close()
