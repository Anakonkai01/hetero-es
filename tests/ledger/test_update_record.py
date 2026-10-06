"""
Writing down the update of a complete generation BEFORE the weights are touched, and marking it applied afterwards:
what makes a crash between the two harmless (the update is deterministic, so it can be redone from the parent, and the
ledger knows whether it was done).
"""
import dataclasses
import sqlite3

import pytest

from heteroes.generation_record import GenerationRecord
from heteroes.ledger import (
    CandidateState,
    ConflictingUpdateError,
    GenerationFailedError,
    GenerationNotCompleteError,
    Ledger,
    LedgerError,
    RecordMismatchError,
    StoredUpdate,
    UpdateOutcome,
)
from ledger_helpers import PARENT, RECIPE, FakeClock, batch, fail, lease, make

REWARDS = {0: 0.5, 1: 0.25, 2: 0.75}
CHILD = "c" * 64
OTHER_CHILD = "d" * 64
ETA = 1e-9


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def ledger(clock):
    with Ledger(":memory:", clock=clock) as opened:
        opened.open_generation(batch(3))
        yield opened


def complete(ledger, rewards=REWARDS, experiment="exp", generation=0):
    for index, reward in rewards.items():
        held = ledger.lease(f"{experiment}/g{generation}/c{index}", "worker-a", 30.0)
        ledger.submit_result(make(index, 1000 + 7 * index, experiment_id=experiment, generation=generation),
                             held.attempt_number, held.token, reward)


def record_of(ledger, alpha=1e-3, experiment="exp", generation=0):
    results = ledger.get_generation_results(experiment, generation)
    return GenerationRecord.from_results(experiment, generation, results, alpha=alpha, eta=ETA)


def stored(ledger, experiment="exp", generation=0):
    return ledger.get_update(experiment, generation)


def test_the_update_of_a_generation_that_does_not_exist_cannot_be_read(ledger):
    complete(ledger)

    with pytest.raises(LedgerError, match="unknown generation"):
        stored(ledger, generation=9)
    with pytest.raises(LedgerError, match="unknown generation"):
        stored(ledger, experiment="nope")


# ---------------------------------------------------------------------------
# recording
# ---------------------------------------------------------------------------

def test_a_generation_that_was_never_recorded_has_no_update(ledger):
    complete(ledger)

    assert stored(ledger) is None


def test_the_update_of_a_complete_generation_is_recorded_and_can_be_read_back(ledger, clock):
    complete(ledger)
    record = record_of(ledger)
    clock.advance(7.0)

    outcome = ledger.record_update(record)

    assert outcome is UpdateOutcome.RECORDED
    assert stored(ledger) == StoredUpdate(record=record, record_hash=record.hash, recorded_at=1007.0,
                                          child_weights_sha256=None, applied_at=None)


def test_what_is_read_back_is_exactly_the_record(ledger):
    complete(ledger)
    record = record_of(ledger, alpha=0.25)
    ledger.record_update(record)

    again = stored(ledger).record

    assert again == record and again.hash == record.hash and again.to_json() == record.to_json()


def test_recording_does_not_touch_the_candidates(ledger):
    complete(ledger)
    before = ledger.list_candidates("exp", 0)

    ledger.record_update(record_of(ledger))

    assert ledger.list_candidates("exp", 0) == before
    assert all(r.state is CandidateState.COMMITTED for r in before)


def test_a_generation_that_is_still_open_cannot_be_recorded(ledger):
    complete(ledger, rewards={0: 0.5, 1: 0.25})
    full = GenerationRecord("exp", 0, RECIPE, PARENT, (1000, 1007, 1014), (0.5, 0.25, 0.75), (0.0, -1.0, 1.0), 1e-3)

    with pytest.raises(GenerationNotCompleteError):
        ledger.record_update(full)

    assert stored(ledger) is None


def test_a_failed_generation_cannot_be_recorded(ledger):
    complete(ledger, rewards={0: 0.5, 2: 0.75})
    for _ in range(3):
        fail(ledger, lease(ledger, 1))
    full = GenerationRecord("exp", 0, RECIPE, PARENT, (1000, 1007, 1014), (0.5, 0.25, 0.75), (0.0, -1.0, 1.0), 1e-3)

    with pytest.raises(GenerationFailedError):
        ledger.record_update(full)

    assert stored(ledger) is None


def test_the_update_of_a_generation_that_does_not_exist_is_refused(ledger):
    complete(ledger)
    record = dataclasses.replace(record_of(ledger), generation=5)

    with pytest.raises(LedgerError, match="unknown generation"):
        ledger.record_update(record)


@pytest.mark.parametrize("what, change", [
    ("seeds", lambda r: dict(seeds=(r.seeds[1], r.seeds[0], r.seeds[2]))),
    ("seeds", lambda r: dict(seeds=(r.seeds[0], r.seeds[1], r.seeds[2] + 1))),
    ("rewards", lambda r: dict(rewards=(r.rewards[0], r.rewards[1], 0.8))),
    ("recipe_hash", lambda r: dict(recipe_hash="e" * 64)),
    ("parent_weights_sha256", lambda r: dict(parent_weights_sha256="f" * 64)),
])
def test_a_record_that_does_not_say_what_was_committed_is_refused(ledger, what, change):
    complete(ledger)
    record = record_of(ledger)
    wrong = dataclasses.replace(record, **change(record))

    with pytest.raises(RecordMismatchError, match=what):
        ledger.record_update(wrong)

    assert stored(ledger) is None


@pytest.mark.parametrize("extra", [(1021, 0.5, 0.0), None])
def test_a_record_with_more_or_fewer_candidates_than_the_generation_is_refused(ledger, extra):
    complete(ledger)
    record = record_of(ledger)
    if extra is None:
        wrong = dataclasses.replace(record, seeds=record.seeds[:2], rewards=record.rewards[:2], coefficients=record.coefficients[:2])
    else:
        wrong = dataclasses.replace(record, seeds=record.seeds + (extra[0],), rewards=record.rewards + (extra[1],),
                                    coefficients=record.coefficients + (extra[2],))

    with pytest.raises(RecordMismatchError):
        ledger.record_update(wrong)

    assert stored(ledger) is None


def test_the_alpha_and_the_coefficients_are_the_coordinators_to_decide(ledger):
    complete(ledger)
    record = dataclasses.replace(record_of(ledger), alpha=0.125, coefficients=(0.0, -1.0, 1.0))

    assert ledger.record_update(record) is UpdateOutcome.RECORDED            # the ledger cannot know them: it keeps them


@pytest.mark.parametrize("bad", [None, {"experiment_id": "exp"}, "exp/g0", 3])
def test_something_that_is_not_a_record_is_a_type_error(ledger, bad):
    complete(ledger)

    with pytest.raises(TypeError):
        ledger.record_update(bad)


def test_a_no_op_update_is_recorded_like_any_other(ledger):
    complete(ledger, rewards={0: 0.5, 1: 0.5, 2: 0.5})
    record = record_of(ledger)

    assert record.noop is True
    assert ledger.record_update(record) is UpdateOutcome.RECORDED
    assert stored(ledger).record.noop is True


# ---------------------------------------------------------------------------
# recording again (a restart, a lost acknowledgement)
# ---------------------------------------------------------------------------

def test_the_same_record_again_is_acknowledged_and_changes_nothing(ledger, clock):
    complete(ledger)
    record = record_of(ledger)
    ledger.record_update(record)
    first = stored(ledger)
    clock.advance(100.0)

    assert ledger.record_update(record) is UpdateOutcome.ALREADY_RECORDED
    assert ledger.record_update(record_of(ledger)) is UpdateOutcome.ALREADY_RECORDED      # rebuilt from the results: the same

    assert stored(ledger) == first


@pytest.mark.parametrize("change", [dict(alpha=2e-3), dict(coefficients=(0.0, -1.0, 1.0))])
def test_another_record_for_a_recorded_generation_is_a_conflict_and_the_first_stays(ledger, change):
    complete(ledger)
    ledger.record_update(record_of(ledger))
    first = stored(ledger)

    with pytest.raises(ConflictingUpdateError):
        ledger.record_update(dataclasses.replace(record_of(ledger), **change))

    assert stored(ledger) == first


def test_a_generation_recorded_with_another_alpha_after_a_restart_is_refused_so_the_stored_one_must_be_used(ledger):
    complete(ledger)
    ledger.record_update(record_of(ledger, alpha=1e-3))

    with pytest.raises(ConflictingUpdateError, match="alpha|coefficients|another"):
        ledger.record_update(record_of(ledger, alpha=3e-3))


def test_each_generation_and_each_experiment_has_its_own_update(ledger):
    complete(ledger)
    ledger.open_generation(batch(3, generation=1))
    ledger.open_generation(batch(3, experiment_id="other"))
    complete(ledger, generation=1)
    complete(ledger, experiment="other")

    for experiment, generation in (("exp", 0), ("exp", 1), ("other", 0)):
        assert ledger.record_update(record_of(ledger, experiment=experiment, generation=generation)) is UpdateOutcome.RECORDED

    assert [stored(ledger, e, g).record.generation for e, g in (("exp", 0), ("exp", 1), ("other", 0))] == [0, 1, 0]
    assert stored(ledger, "other", 0).record.experiment_id == "other"


def test_marking_one_update_applied_marks_only_that_one(ledger):
    complete(ledger)
    ledger.open_generation(batch(3, generation=1))
    ledger.open_generation(batch(3, experiment_id="other"))
    complete(ledger, generation=1)
    complete(ledger, experiment="other")
    hashes = {}
    for experiment, generation in (("exp", 0), ("exp", 1), ("other", 0)):
        record = record_of(ledger, experiment=experiment, generation=generation)
        ledger.record_update(record)
        hashes[(experiment, generation)] = record.hash

    ledger.mark_applied("exp", 1, hashes[("exp", 1)], CHILD)

    assert stored(ledger, "exp", 1).child_weights_sha256 == CHILD
    assert stored(ledger, "exp", 0).child_weights_sha256 is None
    assert stored(ledger, "other", 0).child_weights_sha256 is None
    ledger.mark_applied("other", 0, hashes[("other", 0)], OTHER_CHILD)
    assert [stored(ledger, e, g).child_weights_sha256 for e, g in (("exp", 0), ("exp", 1), ("other", 0))] == [None, CHILD, OTHER_CHILD]


# ---------------------------------------------------------------------------
# applied
# ---------------------------------------------------------------------------

def recorded(ledger):
    complete(ledger)
    record = record_of(ledger)
    ledger.record_update(record)
    return record


def test_an_update_is_marked_applied_with_the_weights_that_came_out(ledger, clock):
    record = recorded(ledger)
    clock.advance(12.0)

    outcome = ledger.mark_applied("exp", 0, record.hash, CHILD)

    assert outcome is UpdateOutcome.APPLIED
    update = stored(ledger)
    assert (update.child_weights_sha256, update.applied_at, update.recorded_at) == (CHILD, 1012.0, 1000.0)
    assert update.record == record


def test_the_same_application_again_is_acknowledged_and_changes_nothing(ledger, clock):
    record = recorded(ledger)
    ledger.mark_applied("exp", 0, record.hash, CHILD)
    first = stored(ledger)
    clock.advance(50.0)

    assert ledger.mark_applied("exp", 0, record.hash, CHILD) is UpdateOutcome.ALREADY_APPLIED

    assert stored(ledger) == first


def test_another_child_for_the_same_update_is_a_conflict_because_the_update_is_deterministic(ledger):
    record = recorded(ledger)
    ledger.mark_applied("exp", 0, record.hash, CHILD)

    with pytest.raises(ConflictingUpdateError, match="child"):
        ledger.mark_applied("exp", 0, record.hash, OTHER_CHILD)

    assert stored(ledger).child_weights_sha256 == CHILD


def test_the_application_of_an_update_that_was_not_recorded_is_refused(ledger):
    complete(ledger)

    with pytest.raises(LedgerError, match="no update") as caught:
        ledger.mark_applied("exp", 0, "a" * 64, CHILD)
    assert type(caught.value) is LedgerError


def test_the_application_of_another_record_than_the_one_stored_is_a_conflict(ledger):
    recorded(ledger)

    with pytest.raises(ConflictingUpdateError, match="record"):
        ledger.mark_applied("exp", 0, "a" * 64, CHILD)

    assert stored(ledger).child_weights_sha256 is None


def test_the_application_of_a_generation_that_does_not_exist_is_refused(ledger):
    recorded(ledger)

    with pytest.raises(LedgerError, match="unknown generation"):
        ledger.mark_applied("exp", 7, "a" * 64, CHILD)


@pytest.mark.parametrize("record_hash, child, error", [
    ("g" * 64, CHILD, ValueError), ("a" * 63, CHILD, ValueError), (None, CHILD, TypeError),
    ("a" * 64, "C" * 64, ValueError), ("a" * 64, "c" * 65, ValueError), ("a" * 64, None, TypeError), ("a" * 64, 5, TypeError),
])
def test_hashes_that_are_not_hashes_are_refused_and_nothing_is_written(ledger, record_hash, child, error):
    record = recorded(ledger)

    with pytest.raises(error):
        ledger.mark_applied("exp", 0, record_hash, child)

    assert stored(ledger).child_weights_sha256 is None and stored(ledger).record == record


def test_an_applied_update_cannot_be_recorded_differently_either(ledger):
    record = recorded(ledger)
    ledger.mark_applied("exp", 0, record.hash, CHILD)

    with pytest.raises(ConflictingUpdateError):
        ledger.record_update(dataclasses.replace(record, alpha=5e-3))
    assert ledger.record_update(record) is UpdateOutcome.ALREADY_RECORDED
    assert stored(ledger).child_weights_sha256 == CHILD


# ---------------------------------------------------------------------------
# the file, two connections, failures in the middle, tampering
# ---------------------------------------------------------------------------

def test_a_recorded_and_applied_update_survives_closing_and_reopening_the_file(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as first:
        first.open_generation(batch(3))
        complete(first)
        record = record_of(first)
        first.record_update(record)
        clock.advance(5.0)
        first.mark_applied("exp", 0, record.hash, CHILD)

    with Ledger(path, clock=clock) as again:
        update = stored(again)
        assert update == StoredUpdate(record, record.hash, 1000.0, CHILD, 1005.0)
        assert again.record_update(record) is UpdateOutcome.ALREADY_RECORDED
        assert again.mark_applied("exp", 0, record.hash, CHILD) is UpdateOutcome.ALREADY_APPLIED


def test_a_recorded_update_that_was_not_applied_yet_is_found_after_a_restart(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as first:
        first.open_generation(batch(3))
        complete(first)
        record = record_of(first)
        first.record_update(record)                         # ... and the coordinator crashes before applying it

    with Ledger(path, clock=clock) as again:
        update = stored(again)
        assert update.record == record and update.child_weights_sha256 is None and update.applied_at is None
        assert again.mark_applied("exp", 0, record.hash, CHILD) is UpdateOutcome.APPLIED


def test_two_connections_agree_on_the_update(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as first, Ledger(path, clock=clock) as second:
        first.open_generation(batch(3))
        complete(first)
        record = record_of(first)
        first.record_update(record)

        assert second.record_update(record) is UpdateOutcome.ALREADY_RECORDED
        with pytest.raises(ConflictingUpdateError):
            second.record_update(dataclasses.replace(record, alpha=0.5))
        assert second.mark_applied("exp", 0, record.hash, CHILD) is UpdateOutcome.APPLIED
        assert first.mark_applied("exp", 0, record.hash, CHILD) is UpdateOutcome.ALREADY_APPLIED
        assert stored(first) == stored(second)


def test_a_failure_while_recording_writes_nothing(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(3))
        complete(ledger)
        record = record_of(ledger)
    raw = sqlite3.connect(path)
    raw.execute("CREATE TRIGGER boom BEFORE INSERT ON generation_update BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    raw.commit()

    with Ledger(path, clock=clock) as ledger:
        with pytest.raises(sqlite3.Error, match="injected failure"):
            ledger.record_update(record)
        assert stored(ledger) is None

        raw.execute("DROP TRIGGER boom")
        raw.commit()
        assert ledger.record_update(record) is UpdateOutcome.RECORDED
    raw.close()


def test_a_stored_record_that_was_tampered_with_is_found_when_it_is_read(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(3))
        complete(ledger)
        ledger.record_update(record_of(ledger))
    raw = sqlite3.connect(path)
    raw.execute("UPDATE generation_update SET record_json = replace(record_json, '0.001', '0.002')")
    raw.commit()
    raw.close()

    with Ledger(path, clock=clock) as ledger:
        with pytest.raises(LedgerError, match="corrupt|tamper|hash"):
            stored(ledger)


def test_a_stored_hash_that_no_longer_matches_its_record_is_found_when_it_is_read(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(3))
        complete(ledger)
        ledger.record_update(record_of(ledger))
    raw = sqlite3.connect(path)
    raw.execute("UPDATE generation_update SET record_hash = ?", ("9" * 64,))      # the record itself is intact and valid
    raw.commit()
    raw.close()

    with Ledger(path, clock=clock) as ledger:
        with pytest.raises(LedgerError, match="corrupt"):
            stored(ledger)


def test_a_record_stored_under_another_generation_is_found_when_it_is_read(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(3))
        ledger.open_generation(batch(3, generation=1))
        complete(ledger)
        complete(ledger, generation=1)
        ledger.record_update(record_of(ledger))
        ledger.record_update(record_of(ledger, generation=1))
    raw = sqlite3.connect(path)                                   # generation 0 now holds the (valid) record of generation 1
    json1, hash1 = raw.execute("SELECT record_json, record_hash FROM generation_update WHERE generation = 1").fetchone()
    raw.execute("DELETE FROM generation_update WHERE generation = 1")
    raw.execute("UPDATE generation_update SET record_json = ?, record_hash = ? WHERE generation = 0", (json1, hash1))
    raw.commit()
    raw.close()

    with Ledger(path, clock=clock) as ledger:
        with pytest.raises(LedgerError, match="corrupt"):
            stored(ledger, generation=0)


# ---------------------------------------------------------------------------
# the rules are in the database itself, not only in Python
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_after_record(tmp_path, clock):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=clock) as ledger:
        ledger.open_generation(batch(3))
        ledger.open_generation(batch(3, generation=1))
        complete(ledger)
        ledger.record_update(record_of(ledger))
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA foreign_keys = ON")
    yield raw
    raw.close()


def insert_update(raw, experiment="exp", generation=1, record_hash="1" * 64, child=None, applied_at=None):
    raw.execute("INSERT INTO generation_update (experiment_id, generation, record_json, record_hash, recorded_at, "
                "child_weights_sha256, applied_at) VALUES (?, ?, '{}', ?, 1000.0, ?, ?)",
                (experiment, generation, record_hash, child, applied_at))


def test_the_database_accepts_a_well_formed_update_row(raw_after_record):
    insert_update(raw_after_record)                              # the helper is sound: the refusals below are about one field


def test_the_database_refuses_a_second_update_for_a_generation(raw_after_record):
    with pytest.raises(sqlite3.IntegrityError):
        insert_update(raw_after_record, generation=0, record_hash="2" * 64)


def test_the_database_refuses_the_same_record_hash_twice(raw_after_record):
    existing = raw_after_record.execute("SELECT record_hash FROM generation_update").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        insert_update(raw_after_record, generation=1, record_hash=existing)


def test_the_database_refuses_an_update_of_a_generation_that_does_not_exist(raw_after_record):
    with pytest.raises(sqlite3.IntegrityError):
        insert_update(raw_after_record, generation=9)


@pytest.mark.parametrize("child, applied_at", [(CHILD, None), (None, 1005.0)])
def test_the_database_refuses_a_child_without_a_time_or_a_time_without_a_child(raw_after_record, child, applied_at):
    with pytest.raises(sqlite3.IntegrityError):
        insert_update(raw_after_record, child=child, applied_at=applied_at)
