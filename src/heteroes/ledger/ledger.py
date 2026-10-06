import dataclasses
import math
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum

from heteroes.generation_record import GenerationRecord
from heteroes.manifest import CandidateDescriptor

SCHEMA_VERSION = 5
DEFAULT_MAX_ATTEMPTS = 3


class CandidateState(Enum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    COMMITTED = "COMMITTED"


class FailureKind(Enum):
    """Why an attempt failed. An infrastructure failure is never a reward of 0."""
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    VERIFIER_ERROR = "VERIFIER_ERROR"
    RESTORE_MISMATCH = "RESTORE_MISMATCH"
    OTHER = "OTHER"


class SubmitOutcome(Enum):
    COMMITTED = "COMMITTED"
    ALREADY_COMMITTED = "ALREADY_COMMITTED"      # the same result was committed before: nothing was written


class GenerationState(Enum):
    OPEN = "OPEN"              # there is still work, or a lease that may still deliver
    COMPLETE = "COMPLETE"      # every candidate is committed: the update can be computed
    FAILED = "FAILED"          # a candidate has no attempts left and its last lease is over; its last attempt may still deliver late


class UpdateOutcome(Enum):
    RECORDED = "RECORDED"
    ALREADY_RECORDED = "ALREADY_RECORDED"      # the same record was stored before: nothing was written
    APPLIED = "APPLIED"
    ALREADY_APPLIED = "ALREADY_APPLIED"        # the same child was marked before: nothing was written


_HEX64 = re.compile(r"[0-9a-f]{64}")


def _sql_list(enum) -> str:
    return ", ".join(f"'{member.value}'" for member in enum)


_SCHEMA = f"""
BEGIN;
CREATE TABLE generation (
    experiment_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    recipe_hash TEXT NOT NULL,
    parent_weights_sha256 TEXT NOT NULL,
    PRIMARY KEY (experiment_id, generation)
);
CREATE TABLE candidate (
    candidate_id TEXT NOT NULL PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    candidate_index INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    state TEXT NOT NULL CHECK (state IN ({_sql_list(CandidateState)})),
    FOREIGN KEY (experiment_id, generation) REFERENCES generation (experiment_id, generation),
    UNIQUE (experiment_id, generation, candidate_index),
    UNIQUE (experiment_id, generation, seed)
);
CREATE TABLE attempt (
    candidate_id TEXT NOT NULL REFERENCES candidate (candidate_id),
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    worker_id TEXT NOT NULL,
    lease_token TEXT NOT NULL UNIQUE,
    leased_at REAL NOT NULL,
    deadline REAL NOT NULL,
    ended_at REAL,
    failure_kind TEXT CHECK (failure_kind IN ({_sql_list(FailureKind)})),
    PRIMARY KEY (candidate_id, attempt_number),
    CHECK (deadline > leased_at),
    CHECK (failure_kind IS NULL OR ended_at IS NOT NULL)
);
CREATE TABLE result (
    candidate_id TEXT NOT NULL PRIMARY KEY REFERENCES candidate (candidate_id),
    attempt_number INTEGER NOT NULL,
    reward REAL NOT NULL,
    committed_at REAL NOT NULL,
    FOREIGN KEY (candidate_id, attempt_number) REFERENCES attempt (candidate_id, attempt_number)
);
CREATE TABLE quarantine (
    worker_id TEXT NOT NULL PRIMARY KEY,
    quarantined_at REAL NOT NULL,
    candidate_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    FOREIGN KEY (candidate_id, attempt_number) REFERENCES attempt (candidate_id, attempt_number)
);
CREATE TABLE generation_update (
    experiment_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    record_json TEXT NOT NULL,
    record_hash TEXT NOT NULL UNIQUE,
    recorded_at REAL NOT NULL,
    child_weights_sha256 TEXT,
    applied_at REAL,
    PRIMARY KEY (experiment_id, generation),
    FOREIGN KEY (experiment_id, generation) REFERENCES generation (experiment_id, generation),
    CHECK ((child_weights_sha256 IS NULL) = (applied_at IS NULL))
);
PRAGMA user_version = {SCHEMA_VERSION};
COMMIT;
"""

# one row per candidate, with its attempts so far, the deadline of the latest one and its result, if committed
_SELECT_CANDIDATES = """
SELECT c.experiment_id, c.generation, g.recipe_hash, g.parent_weights_sha256, c.candidate_index, c.seed, c.state,
       (SELECT COUNT(*) FROM attempt AS a WHERE a.candidate_id = c.candidate_id),
       (SELECT a.deadline FROM attempt AS a WHERE a.candidate_id = c.candidate_id
        ORDER BY a.attempt_number DESC LIMIT 1),
       r.attempt_number, r.reward, r.committed_at
FROM candidate AS c JOIN generation AS g USING (experiment_id, generation)
LEFT JOIN result AS r ON r.candidate_id = c.candidate_id
"""

_SELECT_DESCRIPTOR = """
SELECT c.experiment_id, c.generation, g.recipe_hash, g.parent_weights_sha256, c.candidate_index, c.seed
FROM candidate AS c JOIN generation AS g USING (experiment_id, generation)
WHERE c.candidate_id = ?
"""


class LedgerError(Exception):
    """The ledger refuses something: a broken rule, an unknown name, a file it does not understand."""


class AlreadyLeasedError(LedgerError):
    """The candidate has a lease that is still valid."""


class RetriesExhaustedError(LedgerError):
    """The candidate has used all its attempts and its last lease is over."""


class StaleAttemptError(LedgerError):
    """The attempt is not the one that may deliver: an older attempt, a wrong token, or an attempt already closed."""


class ResultMismatchError(LedgerError):
    """The worker says it ran another job than the one the ledger gave (another seed, recipe or parent weights)."""


class ConflictingResultError(LedgerError):
    """The same attempt already delivered something else (another reward, or another kind of failure)."""


class GenerationFailedError(LedgerError):
    """A candidate of the generation has no attempts left: no more leases are given (its last attempt may still deliver late)."""


class GenerationNotCompleteError(LedgerError):
    """The generation is still open: some candidates have no committed result yet."""


class WorkerQuarantinedError(LedgerError):
    """The worker failed to restore its weights: it gets no work and its new results are not accepted."""


class RecordMismatchError(LedgerError):
    """The update record does not say what the ledger has committed for the generation."""


class ConflictingUpdateError(LedgerError):
    """The generation already has another update recorded, or the update already has another child."""


@dataclass(frozen=True)
class CandidateResult:
    attempt_number: int      # the attempt that delivered it
    reward: float
    committed_at: float


@dataclass(frozen=True)
class GenerationStatus:
    state: GenerationState
    committed: int
    total: int
    exhausted: tuple[str, ...]     # ids of the candidates with no attempts left and no valid lease, in index order


@dataclass(frozen=True)
class GenerationResults:
    """What the update needs from a complete generation: position i of `seeds` and `rewards` is candidate i."""
    recipe_hash: str
    parent_weights_sha256: str
    seeds: tuple[int, ...]
    rewards: tuple[float, ...]


@dataclass(frozen=True)
class StoredUpdate:
    """The update of a generation as the ledger holds it: the record (the inputs) and, once applied, the outcome."""
    record: GenerationRecord
    record_hash: str
    recorded_at: float
    child_weights_sha256: str | None
    applied_at: float | None


@dataclass(frozen=True)
class QuarantineRecord:
    worker_id: str
    quarantined_at: float
    candidate_id: str       # the candidate whose failed restore put the worker aside
    attempt_number: int


@dataclass(frozen=True)
class CandidateRecord:
    """
    A candidate as the ledger knows it: the immutable job (descriptor), where it is in its life (state), how many
    attempts it has had and its result, if committed. A LEASED candidate whose lease is over is reported as PENDING.
    """
    descriptor: CandidateDescriptor
    state: CandidateState
    attempts: int
    result: CandidateResult | None


@dataclass(frozen=True)
class Lease:
    """The temporary right of one worker to run one candidate, until `deadline` (seconds of the ledger's clock)."""
    candidate_id: str
    attempt_number: int
    worker_id: str
    token: str          # a random proof that this attempt holds the lease; a result must bring it back
    deadline: float

    @property
    def attempt_id(self) -> str:
        return f"{self.candidate_id}/a{self.attempt_number}"


def _check_descriptors(descriptors) -> list[CandidateDescriptor]:
    if not isinstance(descriptors, (list, tuple)):
        raise TypeError(f"descriptors must be a list or a tuple, got {type(descriptors).__name__}")
    for descriptor in descriptors:
        if not isinstance(descriptor, CandidateDescriptor):
            raise TypeError(f"every element must be a CandidateDescriptor, got {type(descriptor).__name__}")
    if not descriptors:
        raise LedgerError("a generation needs at least one candidate")

    for field in ("experiment_id", "generation", "recipe_hash", "parent_weights_sha256"):
        if len({getattr(descriptor, field) for descriptor in descriptors}) != 1:
            raise LedgerError(f"all candidates of a generation must have the same {field}")

    ordered = sorted(descriptors, key=lambda descriptor: descriptor.index)
    if [descriptor.index for descriptor in ordered] != list(range(len(ordered))):
        raise LedgerError(f"the indexes must be exactly 0..{len(ordered) - 1}, each once")
    if len({descriptor.seed for descriptor in ordered}) != len(ordered):
        raise LedgerError("the seeds of a generation must all be different")
    return ordered


def _check_max_attempts(max_attempts) -> None:
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
        raise TypeError(f"max_attempts must be an integer, got {type(max_attempts).__name__}")
    if max_attempts < 1:
        raise LedgerError(f"max_attempts must be at least 1, got {max_attempts}")


def _check_lease_arguments(worker_id, duration) -> None:
    if not isinstance(worker_id, str):
        raise TypeError(f"worker_id must be a string, got {type(worker_id).__name__}")
    if not worker_id:
        raise LedgerError("worker_id must not be empty")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise TypeError(f"duration must be a number, got {type(duration).__name__}")
    if not (math.isfinite(duration) and duration > 0):
        raise LedgerError(f"duration must be finite and positive, got {duration}")


def _check_attempt_identity(descriptor, attempt_number, token) -> None:
    if not isinstance(descriptor, CandidateDescriptor):
        raise TypeError(f"descriptor must be a CandidateDescriptor, got {type(descriptor).__name__}")
    if isinstance(attempt_number, bool) or not isinstance(attempt_number, int):
        raise TypeError(f"attempt_number must be an integer, got {type(attempt_number).__name__}")
    if not isinstance(token, str):
        raise TypeError(f"token must be a string, got {type(token).__name__}")


def _check_reward(reward) -> None:
    if isinstance(reward, bool) or not isinstance(reward, (int, float)):
        raise TypeError(f"reward must be a number, got {type(reward).__name__}")
    if not math.isfinite(reward):
        raise LedgerError(f"reward must be finite, got {reward} (an infrastructure failure is not a reward: report it)")


def _check_hash(name: str, value) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, got {type(value).__name__}")
    if not _HEX64.fullmatch(value):
        raise ValueError(f"{name} must be 64 lowercase hex digits, got {value!r}")


def _descriptor(row) -> CandidateDescriptor:
    experiment_id, generation, recipe_hash, parent_weights_sha256, index, seed = row
    return CandidateDescriptor(
        recipe_hash=recipe_hash, parent_weights_sha256=parent_weights_sha256,
        experiment_id=experiment_id, generation=generation, index=index, seed=seed,
    )


def _record(row, now: float) -> CandidateRecord:
    state, attempts, deadline, result_attempt, reward, committed_at = row[6:]
    state = CandidateState(state)
    if state is CandidateState.LEASED and now >= deadline:    # lazy recovery: nobody wrote it, but it is over
        state = CandidateState.PENDING
    result = None if result_attempt is None else CandidateResult(result_attempt, reward, committed_at)
    return CandidateRecord(descriptor=_descriptor(row[:6]), state=state, attempts=attempts, result=result)


class Ledger:
    """
    The coordinator's durable book: which candidates a generation consists of, and what became of each.

    `path` is a file (kept across restarts) or ":memory:" (gone when closed, for tests).
    `clock` returns the current time in seconds. Deadlines are stored in the file and compared after a restart,
    so the default is the wall clock (`time.time`), not a monotonic clock (that one starts again at every boot).
    `max_attempts` is how many attempts (leases) one candidate may have; it is a policy of this process, not stored.
    """

    def __init__(self, path, clock=time.time, max_attempts: int = DEFAULT_MAX_ATTEMPTS):
        _check_max_attempts(max_attempts)
        self._clock = clock
        self._max_attempts = max_attempts
        self._db = sqlite3.connect(path)
        try:
            self._db.execute("PRAGMA foreign_keys = ON")      # off by default in SQLite, and per connection
            self._db.execute("PRAGMA journal_mode = WAL")     # a file ledger; ":memory:" ignores it
            version = self._db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                self._db.executescript(_SCHEMA)
            elif version != SCHEMA_VERSION:
                raise LedgerError(f"unknown ledger schema version {version} (this code knows {SCHEMA_VERSION})")
        except BaseException:
            self._db.close()
            raise

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def open_generation(self, descriptors) -> None:
        """
        Record, before anything runs, the exact set of candidates of one generation, all PENDING.
        All or nothing; a generation (experiment, number) can be opened only once.
        """
        ordered = _check_descriptors(descriptors)
        first = ordered[0]
        with self._db:    # one transaction: it commits when the block ends and rolls back if anything raises inside
            try:
                self._db.execute(
                    "INSERT INTO generation (experiment_id, generation, recipe_hash, parent_weights_sha256) "
                    "VALUES (?, ?, ?, ?)",
                    (first.experiment_id, first.generation, first.recipe_hash, first.parent_weights_sha256),
                )
            except sqlite3.IntegrityError as error:
                raise LedgerError(
                    f"generation {first.experiment_id}/g{first.generation} is already open") from error
            self._db.executemany(
                "INSERT INTO candidate (candidate_id, experiment_id, generation, candidate_index, seed, state) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(d.candidate_id, d.experiment_id, d.generation, d.index, d.seed, CandidateState.PENDING.value)
                 for d in ordered],
            )

    def _load_generation(self, experiment_id: str, generation: int, now: float) -> list[CandidateRecord]:
        rows = self._db.execute(
            _SELECT_CANDIDATES + "WHERE c.experiment_id = ? AND c.generation = ? ORDER BY c.candidate_index",
            (experiment_id, generation),
        ).fetchall()
        if not rows:    # a generation is opened with at least one candidate, so no rows means it does not exist
            raise LedgerError(f"unknown generation {experiment_id}/g{generation}")
        return [_record(row, now) for row in rows]

    def _status_of(self, records: list[CandidateRecord]) -> GenerationStatus:
        committed = sum(record.state is CandidateState.COMMITTED for record in records)
        exhausted = tuple(record.descriptor.candidate_id for record in records
                          if record.state is CandidateState.PENDING and record.attempts >= self._max_attempts)
        if committed == len(records):
            state = GenerationState.COMPLETE
        elif exhausted:
            state = GenerationState.FAILED
        else:
            state = GenerationState.OPEN
        return GenerationStatus(state=state, committed=committed, total=len(records), exhausted=exhausted)

    def list_candidates(self, experiment_id: str, generation: int) -> list[CandidateRecord]:
        """The candidates of a generation in canonical order (by index)."""
        return self._load_generation(experiment_id, generation, self._clock())

    def get_generation_status(self, experiment_id: str, generation: int) -> GenerationStatus:
        """
        COMPLETE when every candidate is committed; FAILED when a candidate has used all its attempts and the last one
        is over (no new lease is given; that last attempt may still deliver late, which makes the generation COMPLETE);
        OPEN otherwise. Computed from the candidates at every call, never stored: raising `max_attempts` and restarting
        turns a FAILED generation into an OPEN one.
        """
        return self._status_of(self._load_generation(experiment_id, generation, self._clock()))

    def _complete_records(self, experiment_id: str, generation: int, now: float) -> list[CandidateRecord]:
        records = self._load_generation(experiment_id, generation, now)
        status = self._status_of(records)
        name = f"{experiment_id}/g{generation}"
        if status.state is GenerationState.FAILED:
            raise GenerationFailedError(f"generation {name} failed: {', '.join(status.exhausted)} used all "
                                        f"{self._max_attempts} attempts")
        if status.state is GenerationState.OPEN:
            raise GenerationNotCompleteError(f"generation {name} is open: {status.committed} of {status.total} committed")
        return records

    def get_generation_results(self, experiment_id: str, generation: int) -> GenerationResults:
        """
        The seeds and rewards of a COMPLETE generation, in canonical (index) order: the input of the ES update.
        Never a part of them: an open or failed generation raises GenerationNotCompleteError / GenerationFailedError.
        """
        records = self._complete_records(experiment_id, generation, self._clock())
        first = records[0].descriptor
        return GenerationResults(
            recipe_hash=first.recipe_hash, parent_weights_sha256=first.parent_weights_sha256,
            seeds=tuple(record.descriptor.seed for record in records),
            rewards=tuple(record.result.reward for record in records),
        )

    def get_candidate(self, candidate_id: str) -> CandidateRecord:
        now = self._clock()
        row = self._db.execute(_SELECT_CANDIDATES + "WHERE c.candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            raise LedgerError(f"unknown candidate {candidate_id}")
        return _record(row, now)

    def lease(self, candidate_id: str, worker_id: str, duration: float) -> Lease:
        """
        Give `worker_id` the right to run the candidate for `duration` seconds: a new attempt, with its own token.

        A lease that is over (its deadline has been reached) is recovered here, lazily: nothing runs in the
        background, whoever asks next finds the candidate free. A retry is simply the next attempt of the same
        candidate (same seed, same job). Raises AlreadyLeasedError while a lease is valid, and
        RetriesExhaustedError when the candidate has had `max_attempts` attempts and the last one is over.
        """
        _check_lease_arguments(worker_id, duration)
        now = self._clock()
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")     # take the write lock before reading, so two writers cannot both pass
            self._refuse_if_quarantined(worker_id)
            row = self._db.execute(
                "SELECT state, experiment_id, generation FROM candidate WHERE candidate_id = ?", (candidate_id,)).fetchone()
            if row is None:
                raise LedgerError(f"unknown candidate {candidate_id}")
            state = CandidateState(row[0])
            if state not in (CandidateState.PENDING, CandidateState.LEASED):
                raise LedgerError(f"candidate {candidate_id} is {state.value} and cannot be leased")

            last = self._db.execute(
                "SELECT attempt_number, deadline FROM attempt WHERE candidate_id = ? "
                "ORDER BY attempt_number DESC LIMIT 1", (candidate_id,)).fetchone()
            attempts = 0 if last is None else last[0]
            if state is CandidateState.LEASED and now < last[1]:
                raise AlreadyLeasedError(f"candidate {candidate_id} is leased until {last[1]}")
            if attempts >= self._max_attempts:
                raise RetriesExhaustedError(f"candidate {candidate_id} has used its {self._max_attempts} attempts")
            generation_status = self._status_of(self._load_generation(row[1], row[2], now))
            if generation_status.state is GenerationState.FAILED:      # no point in spending GPU time on it
                raise GenerationFailedError(f"generation {row[1]}/g{row[2]} failed: "
                                            f"{', '.join(generation_status.exhausted)} used all {self._max_attempts} attempts")

            lease = Lease(candidate_id=candidate_id, attempt_number=attempts + 1, worker_id=worker_id,
                          token=secrets.token_hex(16), deadline=now + duration)
            self._db.execute(
                "INSERT INTO attempt (candidate_id, attempt_number, worker_id, lease_token, leased_at, deadline) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (candidate_id, lease.attempt_number, worker_id, lease.token, now, lease.deadline),
            )
            self._db.execute("UPDATE candidate SET state = ? WHERE candidate_id = ?",
                             (CandidateState.LEASED.value, candidate_id))
        return lease

    def _latest_attempt(self, descriptor: CandidateDescriptor, attempt_number: int, token: str):
        """
        Inside a transaction: check that the worker's report is about the job the ledger gave and about the latest
        attempt of it, with that attempt's token. Returns the stored state of the candidate, the failure kind already
        reported for the attempt (or None) and the worker that held it.
        """
        candidate_id = descriptor.candidate_id
        row = self._db.execute("SELECT state FROM candidate WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            raise LedgerError(f"unknown candidate {candidate_id}")

        stored = _descriptor(self._db.execute(_SELECT_DESCRIPTOR, (candidate_id,)).fetchone())
        if stored != descriptor:
            differing = [f.name for f in dataclasses.fields(stored) if getattr(stored, f.name) != getattr(descriptor, f.name)]
            raise ResultMismatchError(f"the report for {candidate_id} is about another job: {', '.join(differing)} differ")

        last = self._db.execute(
            "SELECT attempt_number, lease_token, failure_kind, worker_id FROM attempt WHERE candidate_id = ? "
            "ORDER BY attempt_number DESC LIMIT 1", (candidate_id,)).fetchone()
        if last is None or (last[0], last[1]) != (attempt_number, token):
            raise StaleAttemptError(f"attempt {attempt_number} of {candidate_id} is not the latest attempt with that token")
        return CandidateState(row[0]), last[2], last[3]

    def submit_result(self, descriptor: CandidateDescriptor, attempt_number: int, token: str, reward: float) -> SubmitOutcome:
        """
        Commit the reward of a candidate: the worker returns the job it ran (descriptor), its attempt number, its
        token and the reward. At most one result is ever committed for a candidate.

        The latest attempt may deliver even after its deadline, as long as nobody was given the candidate in the
        meantime (the lease is the right to be the only one, until it is replaced). The same result sent again is
        acknowledged (ALREADY_COMMITTED) and nothing is written; another reward for an attempt that already
        delivered raises ConflictingResultError. Raises StaleAttemptError for an old attempt, a wrong token or an
        attempt that was closed, ResultMismatchError for another job.
        """
        _check_attempt_identity(descriptor, attempt_number, token)
        _check_reward(reward)
        now = self._clock()
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            state, _, worker_id = self._latest_attempt(descriptor, attempt_number, token)
            candidate_id = descriptor.candidate_id
            if state is CandidateState.COMMITTED:
                committed = self._db.execute("SELECT reward FROM result WHERE candidate_id = ?", (candidate_id,)).fetchone()[0]
                if committed == reward:
                    return SubmitOutcome.ALREADY_COMMITTED
                raise ConflictingResultError(f"{candidate_id} was committed with reward {committed}, not {reward}")
            if state is not CandidateState.LEASED:
                raise StaleAttemptError(f"candidate {candidate_id} is {state.value}: attempt {attempt_number} is closed")
            self._refuse_if_quarantined(worker_id)     # its weights are in doubt: the lease runs out and another worker retries

            self._db.execute("INSERT INTO result (candidate_id, attempt_number, reward, committed_at) VALUES (?, ?, ?, ?)",
                             (candidate_id, attempt_number, reward, now))
            self._db.execute("UPDATE attempt SET ended_at = ? WHERE candidate_id = ? AND attempt_number = ?",
                             (now, candidate_id, attempt_number))
            self._db.execute("UPDATE candidate SET state = ? WHERE candidate_id = ?",
                             (CandidateState.COMMITTED.value, candidate_id))
        return SubmitOutcome.COMMITTED

    def report_failure(self, descriptor: CandidateDescriptor, attempt_number: int, token: str, kind: FailureKind) -> None:
        """
        The worker could not deliver (out of memory, verifier error, restore mismatch...). The attempt is closed with
        the kind of failure, the candidate is PENDING again at once (no waiting for the deadline) and the attempt
        stays counted in the retry budget. Never a reward. Reporting the same failure again changes nothing.
        """
        _check_attempt_identity(descriptor, attempt_number, token)
        if not isinstance(kind, FailureKind):
            raise TypeError(f"kind must be a FailureKind, got {type(kind).__name__}")
        now = self._clock()
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            state, reported, worker_id = self._latest_attempt(descriptor, attempt_number, token)
            candidate_id = descriptor.candidate_id
            if reported is not None:
                if reported == kind.value:
                    return
                raise ConflictingResultError(f"attempt {attempt_number} of {candidate_id} already failed with {reported}, not {kind.value}")
            if state is not CandidateState.LEASED:
                raise StaleAttemptError(f"candidate {candidate_id} is {state.value}: attempt {attempt_number} is closed")

            self._db.execute("UPDATE attempt SET ended_at = ?, failure_kind = ? WHERE candidate_id = ? AND attempt_number = ?",
                             (now, kind.value, candidate_id, attempt_number))
            self._db.execute("UPDATE candidate SET state = ? WHERE candidate_id = ?",
                             (CandidateState.PENDING.value, candidate_id))
            if kind is FailureKind.RESTORE_MISMATCH:   # its weights are not the canonical ones any more: put it aside
                self._db.execute(
                    "INSERT OR IGNORE INTO quarantine (worker_id, quarantined_at, candidate_id, attempt_number) "
                    "VALUES (?, ?, ?, ?)", (worker_id, now, candidate_id, attempt_number))

    def _refuse_if_quarantined(self, worker_id: str) -> None:
        if self._db.execute("SELECT 1 FROM quarantine WHERE worker_id = ?", (worker_id,)).fetchone() is not None:
            raise WorkerQuarantinedError(f"worker {worker_id} is quarantined (a restore failed)")

    def list_quarantined(self) -> list[QuarantineRecord]:
        rows = self._db.execute("SELECT worker_id, quarantined_at, candidate_id, attempt_number FROM quarantine "
                                "ORDER BY quarantined_at, worker_id").fetchall()
        return [QuarantineRecord(*row) for row in rows]

    def release_worker(self, worker_id: str) -> None:
        """Take a worker out of quarantine. A human does this, after dealing with the worker; nothing calls it by itself."""
        if not isinstance(worker_id, str):
            raise TypeError(f"worker_id must be a string, got {type(worker_id).__name__}")
        with self._db:
            released = self._db.execute("DELETE FROM quarantine WHERE worker_id = ?", (worker_id,)).rowcount
            if released == 0:
                raise LedgerError(f"worker {worker_id} is not quarantined")

    def _require_generation(self, experiment_id: str, generation: int) -> None:
        found = self._db.execute("SELECT 1 FROM generation WHERE experiment_id = ? AND generation = ?",
                                 (experiment_id, generation)).fetchone()
        if found is None:
            raise LedgerError(f"unknown generation {experiment_id}/g{generation}")

    def record_update(self, record: GenerationRecord) -> UpdateOutcome:
        """
        Write down, BEFORE the weights are touched, the update of a COMPLETE generation. The record must say exactly what
        was committed (seeds in index order, rewards, recipe, parent weights); the alpha and the coefficients are the
        coordinator's to decide. At most one record per generation: the same one again is acknowledged (a restart finds
        its own record), another one raises ConflictingUpdateError (after a restart, apply the one that is stored).
        """
        if not isinstance(record, GenerationRecord):
            raise TypeError(f"record must be a GenerationRecord, got {type(record).__name__}")
        now = self._clock()
        name = f"{record.experiment_id}/g{record.generation}"
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            records = self._complete_records(record.experiment_id, record.generation, now)
            first = records[0].descriptor
            says = {
                "recipe_hash": (record.recipe_hash, first.recipe_hash),
                "parent_weights_sha256": (record.parent_weights_sha256, first.parent_weights_sha256),
                "seeds": (record.seeds, tuple(r.descriptor.seed for r in records)),
                "rewards": (record.rewards, tuple(r.result.reward for r in records)),
            }
            differing = [field for field, (given, committed) in says.items() if given != committed]
            if differing:
                raise RecordMismatchError(f"the record of {name} does not say what was committed: {', '.join(differing)} differ")

            row = self._db.execute("SELECT record_hash FROM generation_update WHERE experiment_id = ? AND generation = ?",
                                   (record.experiment_id, record.generation)).fetchone()
            if row is not None:
                if row[0] == record.hash:
                    return UpdateOutcome.ALREADY_RECORDED
                raise ConflictingUpdateError(f"{name} already has another update recorded ({row[0][:12]}...), "
                                             f"not {record.hash[:12]}...: apply the one that is stored")
            self._db.execute(
                "INSERT INTO generation_update (experiment_id, generation, record_json, record_hash, recorded_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (record.experiment_id, record.generation, record.to_json(), record.hash, now))
        return UpdateOutcome.RECORDED

    def get_update(self, experiment_id: str, generation: int) -> StoredUpdate | None:
        """The update written down for a generation (None if there is none yet); a record that no longer matches its hash is an error."""
        self._require_generation(experiment_id, generation)
        row = self._db.execute(
            "SELECT record_json, record_hash, recorded_at, child_weights_sha256, applied_at FROM generation_update "
            "WHERE experiment_id = ? AND generation = ?", (experiment_id, generation)).fetchone()
        if row is None:
            return None
        name = f"{experiment_id}/g{generation}"
        try:
            record = GenerationRecord.from_json(row[0])
        except (ValueError, TypeError, KeyError) as error:
            raise LedgerError(f"the stored update of {name} is corrupt: {error}") from error
        if record.hash != row[1] or (record.experiment_id, record.generation) != (experiment_id, generation):
            raise LedgerError(f"the stored update of {name} is corrupt: it does not match its hash")
        return StoredUpdate(record=record, record_hash=row[1], recorded_at=row[2], child_weights_sha256=row[3], applied_at=row[4])

    def mark_applied(self, experiment_id: str, generation: int, record_hash: str, child_weights_sha256: str) -> UpdateOutcome:
        """
        Say that the recorded update was applied and gave these weights. The update is deterministic, so a second call with
        another child is not a new fact but an alarm: ConflictingUpdateError. The same child again is acknowledged.
        """
        _check_hash("record_hash", record_hash)
        _check_hash("child_weights_sha256", child_weights_sha256)
        now = self._clock()
        name = f"{experiment_id}/g{generation}"
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            self._require_generation(experiment_id, generation)
            row = self._db.execute(
                "SELECT record_hash, child_weights_sha256 FROM generation_update WHERE experiment_id = ? AND generation = ?",
                (experiment_id, generation)).fetchone()
            if row is None:
                raise LedgerError(f"no update recorded for {name}")
            if row[0] != record_hash:
                raise ConflictingUpdateError(f"the update recorded for {name} is another record ({row[0][:12]}...), "
                                             f"not {record_hash[:12]}...")
            if row[1] is not None:
                if row[1] == child_weights_sha256:
                    return UpdateOutcome.ALREADY_APPLIED
                raise ConflictingUpdateError(f"the update of {name} already gave child {row[1][:12]}..., not "
                                             f"{child_weights_sha256[:12]}...: the update is deterministic")
            self._db.execute(
                "UPDATE generation_update SET child_weights_sha256 = ?, applied_at = ? WHERE experiment_id = ? AND generation = ?",
                (child_weights_sha256, now, experiment_id, generation))
        return UpdateOutcome.APPLIED
