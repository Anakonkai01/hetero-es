import sqlite3
from dataclasses import dataclass
from enum import Enum

from heteroes.manifest import CandidateDescriptor

SCHEMA_VERSION = 1

_SCHEMA = """
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
PRAGMA user_version = 1;
COMMIT;
"""

_SELECT_CANDIDATES = """
SELECT c.experiment_id, c.generation, g.recipe_hash, g.parent_weights_sha256, c.candidate_index, c.seed, c.state
FROM candidate AS c JOIN generation AS g USING (experiment_id, generation)
"""


class LedgerError(Exception):
    """The ledger refuses something: a broken rule, an unknown name, a file it does not understand."""


class CandidateState(Enum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    COMMITTED = "COMMITTED"


@dataclass(frozen=True)
class CandidateRecord:
    """A candidate as the ledger knows it: the immutable job (descriptor) and where it is in its life (state)."""
    descriptor: CandidateDescriptor
    state: CandidateState


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


def _record(row) -> CandidateRecord:
    experiment_id, generation, recipe_hash, parent_weights_sha256, index, seed, state = row
    descriptor = CandidateDescriptor(
        recipe_hash=recipe_hash, parent_weights_sha256=parent_weights_sha256,
        experiment_id=experiment_id, generation=generation, index=index, seed=seed,
    )
    return CandidateRecord(descriptor=descriptor, state=CandidateState(state))


class Ledger:
    """
    The coordinator's durable book: which candidates a generation consists of, and what became of each.

    `path` is a file (kept across restarts) or ":memory:" (gone when closed, for tests).
    """

    def __init__(self, path):
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
        rows = self._db.execute(
            _SELECT_CANDIDATES + "WHERE c.experiment_id = ? AND c.generation = ? ORDER BY c.candidate_index",
            (experiment_id, generation),
        ).fetchall()
        if not rows:    # a generation is opened with at least one candidate, so no rows means it does not exist
            raise LedgerError(f"unknown generation {experiment_id}/g{generation}")
        return [_record(row) for row in rows]

    def get_candidate(self, candidate_id: str) -> CandidateRecord:
        row = self._db.execute(_SELECT_CANDIDATES + "WHERE c.candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            raise LedgerError(f"unknown candidate {candidate_id}")
        return _record(row)
