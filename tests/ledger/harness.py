"""
A ledger together with a MODEL of what it must do, written from the contract (MASTER section 10 and the decisions of
G2a to G2d), not from the code of the ledger. Every action is predicted by the model before the ledger runs it; the
ledger must raise exactly the predicted error (the exact class, not a parent) or give the predicted outcome, and after
every action what the ledger says about every candidate, about the generation and about the quarantine must be what the
model says. A second check reads the tables directly and does not use the model at all.

Used by the random schedules and by the exhaustive ones: the same checks, two ways of choosing the actions.
"""
from collections import Counter
from dataclasses import dataclass

from heteroes.ledger import (
    AlreadyLeasedError,
    CandidateResult,
    CandidateState,
    ConflictingResultError,
    FailureKind,
    GenerationFailedError,
    GenerationNotCompleteError,
    GenerationState,
    GenerationStatus,
    Ledger,
    LedgerError,
    QuarantineRecord,
    ResultMismatchError,
    RetriesExhaustedError,
    StaleAttemptError,
    SubmitOutcome,
    WorkerQuarantinedError,
)
from ledger_helpers import PARENT, RECIPE, FakeClock, batch, descriptor_of, make

LEASE_SECONDS = 30.0


def oracle_reward(seed: int) -> float:
    """What an honest worker computes for a candidate: a fixed function of the seed, so the right answer is known."""
    return (seed % 11) / 10


@dataclass
class _Attempt:
    number: int
    worker: str
    token: str
    deadline: float
    status: str = "open"                 # open | failed | committed
    failure: FailureKind | None = None
    reward: float | None = None
    committed_at: float | None = None


class LedgerHarness:
    def __init__(self, candidates=3, max_attempts=2, seen=None):
        self.n = candidates
        self.max_attempts = max_attempts
        self.clock = FakeClock()
        self.ledger = Ledger(":memory:", clock=self.clock, max_attempts=max_attempts)
        self.ledger.open_generation(batch(candidates))
        self.attempts = {i: [] for i in range(candidates)}              # the model: what was granted, and what became of it
        self.quarantine = {}                                            # worker -> (time, candidate_id, attempt_number)
        self.leases = []                                                # (candidate index, Lease), in the order granted
        self.seen = Counter() if seen is None else seen                 # which predicted outcomes were reached

    def close(self):
        self.ledger.close()

    # ---- what the model knows -------------------------------------------------------------------------------------

    def _state(self, i):
        a = self.attempts[i]
        if a and a[-1].status == "committed":
            return CandidateState.COMMITTED
        if a and a[-1].status == "open" and self.clock.now < a[-1].deadline:
            return CandidateState.LEASED
        return CandidateState.PENDING                                   # never leased, failed, or the lease is over

    def _exhausted(self):
        return tuple(f"exp/g0/c{i}" for i in range(self.n)
                     if self._state(i) is CandidateState.PENDING and len(self.attempts[i]) >= self.max_attempts)

    def _generation_state(self):
        committed = sum(self._state(i) is CandidateState.COMMITTED for i in range(self.n))
        if committed == self.n:
            return GenerationState.COMPLETE
        return GenerationState.FAILED if self._exhausted() else GenerationState.OPEN

    # ---- the actions ----------------------------------------------------------------------------------------------

    def apply(self, action):
        """One action: ("lease", worker, i) | ("advance", seconds) | ("submit", worker, i, mode[, which]) |
        ("fail", worker, i, kind[, which]) | ("release", worker). Candidate numbers wrap around."""
        name, *arguments = action
        getattr(self, f"_do_{name}")(*arguments)
        self.check()

    def _expect(self, expected, function, *arguments):
        """Run a ledger call whose outcome the model predicted: an exception class (the exact one), or a value."""
        label = expected.__name__ if isinstance(expected, type) else str(expected)
        self.seen[label] += 1
        try:
            value = function(*arguments)
        except LedgerError as error:
            assert isinstance(expected, type) and type(error) is expected, (
                f"{function.__name__}{arguments}: the model predicted {label}, the ledger raised "
                f"{type(error).__name__}: {error}")
            return None
        assert not isinstance(expected, type), f"{function.__name__}{arguments}: the model predicted {label}, nothing was raised"
        assert value == expected, f"{function.__name__}{arguments}: the model predicted {expected}, got {value}"
        return value

    def _pick(self, worker, i, which="last"):
        mine = [lease for j, lease in self.leases if j == i and lease.worker_id == worker]
        if not mine:
            return None
        return mine[0] if which == "first" else mine[-1]

    def _do_advance(self, seconds):
        self.clock.advance(seconds)

    def _do_lease(self, worker, i):
        i %= self.n
        attempts = self.attempts[i]
        if worker in self.quarantine:
            expected = WorkerQuarantinedError
        elif attempts and attempts[-1].status == "committed":
            expected = LedgerError                                       # not leasable: neither of the two special cases
        elif self._state(i) is CandidateState.LEASED:
            expected = AlreadyLeasedError
        elif len(attempts) >= self.max_attempts:
            expected = RetriesExhaustedError
        elif self._exhausted():
            expected = GenerationFailedError                             # another candidate can no longer commit
        else:
            expected = "granted"

        if expected == "granted":
            lease = self.ledger.lease(f"exp/g0/c{i}", worker, LEASE_SECONDS)
            self.seen["granted"] += 1
            assert lease.attempt_number == len(attempts) + 1 and lease.worker_id == worker
            assert lease.deadline == self.clock.now + LEASE_SECONDS
            attempts.append(_Attempt(lease.attempt_number, worker, lease.token, lease.deadline))
            self.leases.append((i, lease))
        else:
            self._expect(expected, self.ledger.lease, f"exp/g0/c{i}", worker, LEASE_SECONDS)

    def _do_submit(self, worker, i, mode, which="last"):
        i %= self.n
        lease = self._pick(worker, i, which)
        if lease is None:
            return
        latest = self.attempts[i][-1]
        seed = descriptor_of(i).seed
        descriptor, token, reward = descriptor_of(i), lease.token, oracle_reward(seed)
        if mode == "other":
            reward += 0.5                                                # a reward that differs from the honest one
        elif mode == "wrong_job":
            descriptor = make(i, seed + 1)
        elif mode == "wrong_token":
            token = "0" * 32

        if mode == "wrong_job":
            expected = ResultMismatchError
        elif mode == "wrong_token" or lease.attempt_number != latest.number:
            expected = StaleAttemptError
        elif latest.status == "committed":
            expected = SubmitOutcome.ALREADY_COMMITTED if reward == latest.reward else ConflictingResultError
        elif latest.status == "failed":
            expected = StaleAttemptError
        elif lease.worker_id in self.quarantine:
            expected = WorkerQuarantinedError
        else:
            expected = SubmitOutcome.COMMITTED

        outcome = self._expect(expected, self.ledger.submit_result, descriptor, lease.attempt_number, token, reward)
        if outcome is SubmitOutcome.COMMITTED:
            latest.status, latest.reward, latest.committed_at = "committed", reward, self.clock.now

    def _do_fail(self, worker, i, kind, which="last"):
        i %= self.n
        lease = self._pick(worker, i, which)
        if lease is None:
            return
        latest = self.attempts[i][-1]
        if lease.attempt_number != latest.number or latest.status == "committed":
            expected = StaleAttemptError
        elif latest.status == "failed":
            expected = None if latest.failure is kind else ConflictingResultError
        else:
            expected = None
        if expected is None:
            self.seen["failure accepted"] += 1
            self.ledger.report_failure(descriptor_of(i), lease.attempt_number, lease.token, kind)
            if latest.status == "open":
                latest.status, latest.failure = "failed", kind
                if kind is FailureKind.RESTORE_MISMATCH:                 # the first record of a worker is kept
                    self.quarantine.setdefault(lease.worker_id, (self.clock.now, f"exp/g0/c{i}", lease.attempt_number))
        else:
            self._expect(expected, self.ledger.report_failure, descriptor_of(i), lease.attempt_number, lease.token, kind)

    def _do_release(self, worker):
        if worker in self.quarantine:
            self.seen["released"] += 1
            self.ledger.release_worker(worker)
            del self.quarantine[worker]
        else:
            self._expect(LedgerError, self.ledger.release_worker, worker)

    # ---- the checks -----------------------------------------------------------------------------------------------

    def check(self):
        """What the ledger says must be what the model says, and the tables must obey the rules on their own."""
        ledger = self.ledger
        for i in range(self.n):
            record = ledger.get_candidate(f"exp/g0/c{i}")
            attempts = self.attempts[i]
            assert record.descriptor == descriptor_of(i)
            assert record.state is self._state(i), (i, record.state, self._state(i))
            assert record.attempts == len(attempts)
            committed = bool(attempts) and attempts[-1].status == "committed"
            expected = CandidateResult(attempts[-1].number, attempts[-1].reward, attempts[-1].committed_at) if committed else None
            assert record.result == expected, (i, record.result, expected)

        state = self._generation_state()
        committed_count = sum(self._state(i) is CandidateState.COMMITTED for i in range(self.n))
        assert ledger.get_generation_status("exp", 0) == GenerationStatus(state, committed_count, self.n, self._exhausted())
        if state is GenerationState.COMPLETE:
            results = ledger.get_generation_results("exp", 0)
            assert results.seeds == tuple(descriptor_of(i).seed for i in range(self.n))
            assert (results.recipe_hash, results.parent_weights_sha256) == (RECIPE, PARENT)
            assert results.rewards == tuple(self.attempts[i][-1].reward for i in range(self.n))
        else:
            error = GenerationFailedError if state is GenerationState.FAILED else GenerationNotCompleteError
            try:
                ledger.get_generation_results("exp", 0)
            except LedgerError as raised:
                assert type(raised) is error
            else:
                raise AssertionError("the results of a generation that is not complete were handed out")

        expected_quarantine = sorted(
            (QuarantineRecord(worker, *cause) for worker, cause in self.quarantine.items()),
            key=lambda q: (q.quarantined_at, q.worker_id))
        assert ledger.list_quarantined() == expected_quarantine
        check_tables(ledger, self.max_attempts)


def check_tables(ledger, max_attempts):
    """The rules of the contract, asked of the tables directly: no model, no help from the ledger's own code."""
    db = ledger._db           # test support: the point is to look at what was really written

    def count(sql, *arguments):
        return db.execute(sql, arguments).fetchone()[0]

    # at most one committed effect per candidate
    assert count("SELECT COUNT(*) FROM (SELECT candidate_id FROM result GROUP BY candidate_id HAVING COUNT(*) > 1)") == 0
    # a result belongs to an attempt that ended, did not fail, and is the latest attempt of its candidate
    assert count("SELECT COUNT(*) FROM result r JOIN attempt a USING (candidate_id, attempt_number) "
                 "WHERE a.ended_at IS NULL OR a.failure_kind IS NOT NULL") == 0
    assert count("SELECT COUNT(*) FROM result r WHERE r.attempt_number != "
                 "(SELECT MAX(a.attempt_number) FROM attempt a WHERE a.candidate_id = r.candidate_id)") == 0
    # COMMITTED if and only if there is a result
    assert count("SELECT COUNT(*) FROM candidate c LEFT JOIN result r USING (candidate_id) "
                 "WHERE (c.state = 'COMMITTED') != (r.candidate_id IS NOT NULL)") == 0
    # attempts are numbered 1..k, and k stays within the budget
    assert count("SELECT COUNT(*) FROM (SELECT 1 FROM attempt GROUP BY candidate_id HAVING MAX(attempt_number) != COUNT(*))") == 0
    assert count("SELECT COUNT(*) FROM (SELECT 1 FROM attempt GROUP BY candidate_id HAVING COUNT(*) > ?)", max_attempts) == 0
    # a failed attempt has an end time; an attempt cannot both fail and carry a result
    assert count("SELECT COUNT(*) FROM attempt WHERE failure_kind IS NOT NULL AND ended_at IS NULL") == 0
    # no attempt started by a worker while it was in quarantine (the quarantine table holds only the current ones)
    assert count("SELECT COUNT(*) FROM quarantine q JOIN attempt a ON a.worker_id = q.worker_id "
                 "WHERE a.leased_at > q.quarantined_at") == 0
