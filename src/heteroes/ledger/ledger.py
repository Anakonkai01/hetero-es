import math
import secrets
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum

from heteroes.manifest import CandidateDescriptor

SCHEMA_VERSION = 2
DEFAULT_MAX_ATTEMPTS = 3

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
    state TEXT NOT NULL CHECK (state IN ('PENDING', 'LEASED', 'RUNNING', 'COMMITTED')),
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
    PRIMARY KEY (candidate_id, attempt_number),
    CHECK (deadline > leased_at)
);
PRAGMA user_version = {SCHEMA_VERSION};
COMMIT;
"""

# one row per candidate, with how many attempts it has had and the deadline of the latest one
_SELECT_CANDIDATES = """
SELECT c.experiment_id, c.generation, g.recipe_hash, g.parent_weights_sha256, c.candidate_index, c.seed, c.state,
       (SELECT COUNT(*) FROM attempt AS a WHERE a.candidate_id = c.candidate_id),
       (SELECT a.deadline FROM attempt AS a WHERE a.candidate_id = c.candidate_id
        ORDER BY a.attempt_number DESC LIMIT 1)
FROM candidate AS c JOIN generation AS g USING (experiment_id, generation)
"""


class LedgerError(Exception):
    """The ledger refuses something: a broken rule, an unknown name, a file it does not understand."""


class AlreadyLeasedError(LedgerError):
    """The candidate has a lease that is still valid."""


class RetriesExhaustedError(LedgerError):
    """The candidate has used all its attempts and its last lease is over."""


class CandidateState(Enum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    COMMITTED = "COMMITTED"


@dataclass(frozen=True)
class CandidateRecord:
    """
    A candidate as the ledger knows it: the immutable job (descriptor), where it is in its life (state) and
    how many attempts it has had. A LEASED candidate whose lease is over is reported as PENDING.
    """
    descriptor: CandidateDescriptor
    state: CandidateState
    attempts: int


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


def _record(row, now: float) -> CandidateRecord:
    experiment_id, generation, recipe_hash, parent_weights_sha256, index, seed, state, attempts, deadline = row
    descriptor = CandidateDescriptor(
        recipe_hash=recipe_hash, parent_weights_sha256=parent_weights_sha256,
        experiment_id=experiment_id, generation=generation, index=index, seed=seed,
    )
    state = CandidateState(state)
    if state is CandidateState.LEASED and now >= deadline:    # lazy recovery: nobody wrote it, but it is over
        state = CandidateState.PENDING
    return CandidateRecord(descriptor=descriptor, state=state, attempts=attempts)


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

    def list_candidates(self, experiment_id: str, generation: int) -> list[CandidateRecord]:
        """The candidates of a generation in canonical order (by index)."""
        now = self._clock()
        rows = self._db.execute(
            _SELECT_CANDIDATES + "WHERE c.experiment_id = ? AND c.generation = ? ORDER BY c.candidate_index",
            (experiment_id, generation),
        ).fetchall()
        if not rows:    # a generation is opened with at least one candidate, so no rows means it does not exist
            raise LedgerError(f"unknown generation {experiment_id}/g{generation}")
        return [_record(row, now) for row in rows]

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
            row = self._db.execute("SELECT state FROM candidate WHERE candidate_id = ?", (candidate_id,)).fetchone()
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
