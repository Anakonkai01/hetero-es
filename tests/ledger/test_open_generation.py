import sqlite3
from dataclasses import FrozenInstanceError

import pytest

from heteroes.ledger import CandidateRecord, CandidateState, Ledger, LedgerError
from heteroes.manifest import MAX_SEED
from ledger_helpers import PARENT, RECIPE, make

def batch(n=4, **changes):
    return [make(i, 1000 + 7 * i, **changes) for i in range(n)]


@pytest.fixture
def ledger():
    with Ledger(":memory:") as opened:
        yield opened


def descriptors_of(records):
    return [record.descriptor for record in records]


def assert_nothing_written(ledger):
    """A refused or failed open_generation leaves no trace: not in the generation it named, not in any other."""
    for experiment_id, generation in [("exp", 0), ("exp", 1), ("other", 0)]:
        with pytest.raises(LedgerError):
            ledger.list_candidates(experiment_id, generation)
    for candidate_id in ["exp/g0/c0", "exp/g0/c3", "exp/g1/c0", "other/g0/c3"]:
        with pytest.raises(LedgerError):
            ledger.get_candidate(candidate_id)


# ---------------------------------------------------------------------------
# what is stored, and what is read back
# ---------------------------------------------------------------------------

def test_a_generation_is_read_back_in_index_order_whatever_the_order_it_was_given(ledger):
    given = [make(2, 3003), make(0, 1001), make(3, 4004), make(1, 2002)]
    assert [d.index for d in given] != sorted(d.index for d in given)      # the data can tell sorted from unsorted

    ledger.open_generation(given)

    records = ledger.list_candidates("exp", 0)
    assert [record.descriptor.index for record in records] == [0, 1, 2, 3]
    assert [record.descriptor.seed for record in records] == [1001, 2002, 3003, 4004]


def test_the_descriptors_come_back_exactly_as_they_went_in(ledger):
    given = [make(0, 0, generation=7), make(1, MAX_SEED - 1, generation=7), make(2, 2**31, generation=7),
             make(3, 2**32 + 5, generation=7)]

    ledger.open_generation(given)

    assert descriptors_of(ledger.list_candidates("exp", 7)) == given          # dataclass equality: every field


def test_every_candidate_starts_pending(ledger):
    ledger.open_generation(batch(5))

    records = ledger.list_candidates("exp", 0)
    assert len(records) == 5
    assert all(record.state is CandidateState.PENDING for record in records)


def test_the_states_are_stored_under_these_names():
    assert {state.name: state.value for state in CandidateState} == {
        "PENDING": "PENDING", "LEASED": "LEASED", "RUNNING": "RUNNING", "COMMITTED": "COMMITTED"}


def test_one_candidate_can_be_read_by_its_id(ledger):
    ledger.open_generation(batch(4))

    record = ledger.get_candidate("exp/g0/c2")

    assert record == ledger.list_candidates("exp", 0)[2]
    assert record.descriptor == make(2, 1014)
    assert record.descriptor.candidate_id == "exp/g0/c2"
    assert record.state is CandidateState.PENDING


def test_a_generation_with_one_candidate_is_allowed(ledger):
    ledger.open_generation([make(0, 5)])

    assert descriptors_of(ledger.list_candidates("exp", 0)) == [make(0, 5)]


def test_a_tuple_of_descriptors_is_accepted(ledger):
    ledger.open_generation(tuple(batch(3)))

    assert len(ledger.list_candidates("exp", 0)) == 3


def test_records_cannot_be_changed(ledger):
    ledger.open_generation(batch(2))
    record = ledger.get_candidate("exp/g0/c0")

    with pytest.raises(FrozenInstanceError):
        record.state = CandidateState.COMMITTED
    assert isinstance(record, CandidateRecord)


# ---------------------------------------------------------------------------
# several generations and experiments live side by side
# ---------------------------------------------------------------------------

def test_generations_and_experiments_do_not_mix(ledger):
    ledger.open_generation(batch(3))
    ledger.open_generation(batch(2, generation=1))
    ledger.open_generation(batch(4, experiment_id="other"))

    assert [d.index for d in descriptors_of(ledger.list_candidates("exp", 0))] == [0, 1, 2]
    assert [d.index for d in descriptors_of(ledger.list_candidates("exp", 1))] == [0, 1]
    assert [d.index for d in descriptors_of(ledger.list_candidates("other", 0))] == [0, 1, 2, 3]
    assert {d.experiment_id for d in descriptors_of(ledger.list_candidates("other", 0))} == {"other"}


def test_every_generation_keeps_its_own_recipe_and_parent_weights(ledger):
    # the recipe and the parent are stored once per generation: a candidate must be read with ITS generation's values
    ledger.open_generation(batch(2))
    ledger.open_generation(batch(2, generation=1, recipe_hash="c" * 64, parent_weights_sha256="d" * 64))
    ledger.open_generation(batch(2, experiment_id="other", recipe_hash="e" * 64, parent_weights_sha256="f" * 64))

    assert {(d.recipe_hash, d.parent_weights_sha256) for d in descriptors_of(ledger.list_candidates("exp", 0))} == {(RECIPE, PARENT)}
    assert {(d.recipe_hash, d.parent_weights_sha256) for d in descriptors_of(ledger.list_candidates("exp", 1))} == {("c" * 64, "d" * 64)}
    assert ledger.get_candidate("other/g0/c1").descriptor.recipe_hash == "e" * 64
    assert ledger.get_candidate("exp/g1/c0").descriptor.parent_weights_sha256 == "d" * 64


def test_the_same_seeds_may_be_used_by_another_generation(ledger):
    # seeds must differ INSIDE a generation (the update refuses duplicates); across generations nothing forbids it
    ledger.open_generation(batch(3))
    ledger.open_generation(batch(3, generation=1))

    assert [d.seed for d in descriptors_of(ledger.list_candidates("exp", 1))] == [1000, 1007, 1014]


# ---------------------------------------------------------------------------
# what is refused, and the refusal leaves nothing behind
# ---------------------------------------------------------------------------

def bad_batches():
    good = batch(4)
    return {
        "another experiment inside": good[:3] + [make(3, 1021, experiment_id="other")],
        "another generation inside": good[:3] + [make(3, 1021, generation=1)],
        "another recipe inside": good[:3] + [make(3, 1021, recipe_hash="c" * 64)],
        "another parent inside": good[:3] + [make(3, 1021, parent_weights_sha256="d" * 64)],
        "a missing index": [good[0], good[1], good[3]],
        "indexes that do not start at 0": [make(1, 2002), make(2, 3003)],
        "a duplicate index": good[:3] + [make(2, 1021)],
        "a duplicate seed": good[:3] + [make(3, good[0].seed)],
        "the same descriptor twice": good + [good[3]],
    }


@pytest.mark.parametrize("name", list(bad_batches()))
def test_a_bad_batch_is_refused_and_leaves_nothing(ledger, name):
    with pytest.raises(LedgerError):
        ledger.open_generation(bad_batches()[name])

    assert_nothing_written(ledger)
    ledger.open_generation(batch(4))                         # the names are still free: nothing was half written
    assert descriptors_of(ledger.list_candidates("exp", 0)) == batch(4)


def test_an_empty_generation_is_refused_for_what_it_is(ledger):
    with pytest.raises(LedgerError, match="at least one"):
        ledger.open_generation([])

    assert_nothing_written(ledger)


@pytest.mark.parametrize("not_a_batch", [
    make(0, 1),                                              # one descriptor, not a list
    (d for d in batch(3)),                                   # a generator
    [make(0, 1), make(1, 2).to_dict()],                      # a dict in place of a descriptor
    "exp/g0/c0",
    None,
])
def test_something_that_is_not_a_list_of_descriptors_is_a_type_error(ledger, not_a_batch):
    with pytest.raises(TypeError):
        ledger.open_generation(not_a_batch)

    assert_nothing_written(ledger)


def test_a_generation_cannot_be_opened_twice_even_with_the_same_candidates(ledger):
    ledger.open_generation(batch(4))

    with pytest.raises(LedgerError, match="already"):
        ledger.open_generation(batch(4))

    other_seeds = [make(i, 9000 + i) for i in range(3)]                       # and not with other ones either
    with pytest.raises(LedgerError, match="already"):
        ledger.open_generation(other_seeds)
    assert descriptors_of(ledger.list_candidates("exp", 0)) == batch(4)        # the first one is untouched


def test_reading_something_that_does_not_exist_is_an_error_not_an_empty_answer(ledger):
    ledger.open_generation(batch(3))

    with pytest.raises(LedgerError):
        ledger.list_candidates("exp", 1)
    with pytest.raises(LedgerError):
        ledger.list_candidates("nope", 0)
    with pytest.raises(LedgerError):
        ledger.get_candidate("exp/g0/c3")
    with pytest.raises(LedgerError):
        ledger.get_candidate("exp/g1/c0")


# ---------------------------------------------------------------------------
# the file
# ---------------------------------------------------------------------------

def test_what_was_written_survives_closing_and_reopening_the_file(tmp_path):
    path = tmp_path / "ledger.db"
    with Ledger(path) as ledger:
        ledger.open_generation(batch(4))
        ledger.open_generation(batch(2, generation=1, experiment_id="other"))

    with Ledger(path) as again:
        assert descriptors_of(again.list_candidates("exp", 0)) == batch(4)
        assert descriptors_of(again.list_candidates("other", 1)) == batch(2, generation=1, experiment_id="other")
        assert again.get_candidate("exp/g0/c1").state is CandidateState.PENDING
        with pytest.raises(LedgerError, match="already"):                      # and the names stay taken
            again.open_generation(batch(4))


def test_two_in_memory_ledgers_are_independent():
    with Ledger(":memory:") as first, Ledger(":memory:") as second:
        first.open_generation(batch(2))

        with pytest.raises(LedgerError):
            second.list_candidates("exp", 0)


def test_a_file_ledger_uses_write_ahead_logging(tmp_path):
    path = tmp_path / "ledger.db"
    with Ledger(path):
        raw = sqlite3.connect(path)
        try:
            assert raw.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        finally:
            raw.close()


def test_a_new_file_records_its_schema_version(tmp_path):
    path = tmp_path / "ledger.db"
    Ledger(path).close()

    raw = sqlite3.connect(path)
    try:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == 5
    finally:
        raw.close()


def test_a_file_with_another_schema_version_is_refused(tmp_path):
    path = tmp_path / "ledger.db"
    Ledger(path).close()
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA user_version = 99")
    raw.commit()
    raw.close()

    with pytest.raises(LedgerError, match="99"):
        Ledger(path)


def test_the_same_file_can_be_reopened_when_its_schema_version_is_the_current_one(tmp_path):
    path = tmp_path / "ledger.db"
    Ledger(path).close()
    Ledger(path).close()                                     # does not try to create the tables a second time


def test_a_failure_in_the_middle_of_opening_a_generation_writes_nothing(tmp_path):
    path = tmp_path / "ledger.db"
    Ledger(path).close()
    raw = sqlite3.connect(path)                              # inject a failure at the third candidate row
    raw.execute("CREATE TRIGGER boom BEFORE INSERT ON candidate WHEN NEW.candidate_index = 2 "
                "BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    raw.commit()

    with Ledger(path) as ledger:
        with pytest.raises(LedgerError, match="injected failure"):   # the ledger's own error; the SQLite error is its cause
            ledger.open_generation(batch(4))                 # candidates 0 and 1 were already inserted by then
        assert_nothing_written(ledger)

        raw.execute("DROP TRIGGER boom")
        raw.commit()
        ledger.open_generation(batch(4))                     # the generation name is free again
        assert descriptors_of(ledger.list_candidates("exp", 0)) == batch(4)
    raw.close()


# ---------------------------------------------------------------------------
# the rules are in the database itself, not only in Python
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_after_open(tmp_path):
    path = tmp_path / "ledger.db"
    with Ledger(path) as ledger:
        ledger.open_generation(batch(3))
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA foreign_keys = ON")
    yield raw
    raw.close()


def insert_candidate(raw, candidate_id="exp/g0/c9", experiment_id="exp", generation=0, index=9, seed=5555, state="PENDING"):
    raw.execute(
        "INSERT INTO candidate (candidate_id, experiment_id, generation, candidate_index, seed, state) "
        "VALUES (?, ?, ?, ?, ?, ?)", (candidate_id, experiment_id, generation, index, seed, state))


def test_the_database_refuses_a_second_candidate_with_the_same_index(raw_after_open):
    with pytest.raises(sqlite3.IntegrityError):
        insert_candidate(raw_after_open, candidate_id="exp/g0/c1-again", index=1)


def test_the_database_refuses_a_second_candidate_with_the_same_seed_in_a_generation(raw_after_open):
    with pytest.raises(sqlite3.IntegrityError):
        insert_candidate(raw_after_open, seed=1007)


def test_the_database_refuses_the_same_candidate_id_twice(raw_after_open):
    with pytest.raises(sqlite3.IntegrityError):
        insert_candidate(raw_after_open, candidate_id="exp/g0/c1")


def test_the_database_refuses_a_candidate_of_a_generation_that_does_not_exist(raw_after_open):
    with pytest.raises(sqlite3.IntegrityError):
        insert_candidate(raw_after_open, candidate_id="exp/g5/c9", generation=5)


def test_the_database_refuses_a_state_that_is_not_one_of_the_four(raw_after_open):
    with pytest.raises(sqlite3.IntegrityError):
        insert_candidate(raw_after_open, state="DONE")


def test_a_closed_ledger_cannot_be_used(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    ledger.open_generation(batch(2))

    ledger.close()

    with pytest.raises(sqlite3.ProgrammingError):
        ledger.list_candidates("exp", 0)
