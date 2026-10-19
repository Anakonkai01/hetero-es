"""
Ledger schema 6 (ADR-008): antithetic signs, the texts behind every committed reward, and audits that quarantine a worker
after AUDIT_QUARANTINE_AFTER mismatches without ever changing a committed reward.
"""

import hashlib
import json
import sqlite3

import pytest

from heteroes.canonical import canonical_json_bytes
from heteroes.generation_record import GenerationRecord
from heteroes.ledger import ConflictingResultError, LedgerError, SubmitOutcome
from heteroes.ledger.ledger import AUDIT_QUARANTINE_AFTER, Ledger
from ledger_helpers import PARENT, RECIPE, FakeClock, batch, lease, make


def sha_of(texts):
    return hashlib.sha256(canonical_json_bytes(texts)).hexdigest()


def pairs(n_pairs):
    return [make(2 * k + j, 5000 + k, sign=(1, -1)[j]) for k in range(n_pairs) for j in (0, 1)]


@pytest.fixture
def ledger():
    with Ledger(":memory:", clock=FakeClock()) as opened:
        yield opened


def commit(ledger, index, worker, texts=None, reward=0.5, descriptors=None):
    held = lease(ledger, index, worker)
    descriptor = (descriptors or batch(4))[index]
    return ledger.submit_result(descriptor, held.attempt_number, held.token, reward, completions=texts)


def test_an_antithetic_pair_shares_its_seed_and_the_results_carry_the_signs(ledger):
    descriptors = pairs(2)
    ledger.open_generation(descriptors)
    for index in range(4):
        commit(ledger, index, "worker-a", descriptors=descriptors, reward=float(index))
    results = ledger.get_generation_results("exp", 0)
    assert results.seeds == (5000, 5000, 5001, 5001) and results.signs == (1, -1, 1, -1)
    assert ledger.get_candidate("exp/g0/c1").descriptor.sign == -1


def test_the_same_seed_and_sign_twice_is_refused(ledger):
    with pytest.raises(LedgerError, match="different"):
        ledger.open_generation([make(0, 7), make(1, 7)])
    with pytest.raises(LedgerError, match="different"):
        ledger.open_generation([make(0, 7, sign=-1), make(1, 7, sign=-1)])


def test_an_antithetic_generation_is_recorded_by_a_version_2_record_only(ledger):
    descriptors = pairs(1)
    ledger.open_generation(descriptors)
    for index in range(2):
        commit(ledger, index, "worker-a", descriptors=descriptors, reward=float(index))
    with pytest.raises(ValueError, match="different"):  # a version-1 record cannot say a pair
        GenerationRecord("exp", 0, RECIPE, PARENT, (5000, 5000), (0.0, 1.0), (0.0, 0.0), 0.1)
    results = ledger.get_generation_results("exp", 0)
    record = GenerationRecord.from_results("exp", 0, results, alpha=0.1, eta=1e-9, coefficient_rule="zscore@1")
    assert record.signs == (1, -1) and record.to_dict()["record_version"] == 2
    ledger.record_update(record)
    assert ledger.get_update("exp", 0).record == record
    seeds, coefficients = record.update_inputs()
    assert seeds == [5000] and coefficients.tolist() == [-1.0]  # (c+ - c-) / 2 with z = (-1, +1)


def test_texts_are_stored_with_the_reward_and_read_back(ledger):
    ledger.open_generation(batch(4))
    texts = ["Answer: 41", "no idea", "Ünïcode ✓"]
    assert commit(ledger, 0, "worker-a", texts) is SubmitOutcome.COMMITTED
    assert ledger.get_completions("exp/g0/c0") == (sha_of(texts), texts)
    assert commit(ledger, 1, "worker-a") is SubmitOutcome.COMMITTED
    assert ledger.get_completions("exp/g0/c1") is None  # a Recipe v1/v2 style commit has no texts


def test_a_repeat_must_bring_the_same_texts(ledger):
    ledger.open_generation(batch(4))
    held = lease(ledger, 0, "worker-a")
    descriptor = batch(4)[0]
    ledger.submit_result(descriptor, held.attempt_number, held.token, 0.5, completions=["a"])
    again = ledger.submit_result(descriptor, held.attempt_number, held.token, 0.5, completions=["a"])
    assert again is SubmitOutcome.ALREADY_COMMITTED
    for other in (["b"], None):
        with pytest.raises(ConflictingResultError, match="other texts"):
            ledger.submit_result(descriptor, held.attempt_number, held.token, 0.5, completions=other)


@pytest.mark.parametrize("texts", [[], ["ok", 3], "not a list", [None]])
def test_malformed_texts_are_refused_and_nothing_is_committed(ledger, texts):
    ledger.open_generation(batch(4))
    held = lease(ledger, 0, "worker-a")
    with pytest.raises(TypeError):
        ledger.submit_result(batch(4)[0], held.attempt_number, held.token, 0.5, completions=texts)
    assert ledger.get_candidate("exp/g0/c0").result is None


def test_texts_that_no_longer_match_their_hash_are_an_error(tmp_path):
    path = tmp_path / "ledger.db"
    with Ledger(path, clock=FakeClock()) as opened:
        opened.open_generation(batch(2))
        commit(opened, 0, "worker-a", ["Answer: 1"])
    raw = sqlite3.connect(path)
    import zlib

    raw.execute("UPDATE completion SET body = ?", (zlib.compress(json.dumps(["Answer: 2"]).encode()),))
    raw.commit()
    raw.close()
    with Ledger(path, clock=FakeClock()) as reopened, pytest.raises(LedgerError, match="hash"):
        reopened.get_completions("exp/g0/c0")


def test_an_audit_that_matches_changes_nothing(ledger):
    ledger.open_generation(batch(4))
    commit(ledger, 0, "worker-a", ["x"], reward=0.25)
    assert ledger.record_audit("exp/g0/c0", "worker-b", sha_of(["x"])) is True
    assert ledger.record_audit("exp/g0/c0", "worker-b", sha_of(["x"])) is True  # the same audit again
    assert ledger.list_quarantined() == []
    assert ledger.get_candidate("exp/g0/c0").result.reward == 0.25


def test_an_audit_is_refused_by_the_same_worker_without_texts_or_with_a_changed_answer(ledger):
    ledger.open_generation(batch(4))
    commit(ledger, 0, "worker-a", ["x"])
    commit(ledger, 1, "worker-a")
    with pytest.raises(LedgerError, match="another worker"):
        ledger.record_audit("exp/g0/c0", "worker-a", sha_of(["x"]))
    with pytest.raises(LedgerError, match="no committed texts"):
        ledger.record_audit("exp/g0/c1", "worker-b", sha_of(["x"]))
    ledger.record_audit("exp/g0/c0", "worker-b", sha_of(["y"]))
    with pytest.raises(ConflictingResultError):
        ledger.record_audit("exp/g0/c0", "worker-b", sha_of(["x"]))


def test_mismatches_count_against_both_workers_and_quarantine_at_the_threshold(ledger):
    assert AUDIT_QUARANTINE_AFTER == 3  # the owner's choice (ADR-008, Q-B)
    ledger.open_generation(batch(4))
    for index in range(4):
        commit(ledger, index, "worker-a", [f"text {index}"], reward=0.5)
    for index, auditor in enumerate(["worker-b", "worker-c"]):
        assert ledger.record_audit(f"exp/g0/c{index}", auditor, sha_of(["different"])) is False
    assert ledger.list_quarantined() == []  # two mismatches are not enough
    assert ledger.record_audit("exp/g0/c2", "worker-d", sha_of(["different"])) is False
    quarantined = ledger.list_quarantined()
    assert [(q.worker_id, q.reason, q.candidate_id) for q in quarantined] == [
        ("worker-a", "AUDIT_MISMATCH", "exp/g0/c2")
    ]
    assert all(ledger.get_candidate(f"exp/g0/c{i}").result.reward == 0.5 for i in range(4))  # rewards never change
