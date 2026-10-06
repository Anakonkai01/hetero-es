import copy
import hashlib
import json
import re

import numpy as np
import pytest

from heteroes.canonical import canonical_json_bytes, canonical_json_hash
from heteroes.es.update import standardize_rewards
from heteroes.generation_record import RECORD_VERSION, GenerationRecord
from heteroes.ledger import GenerationResults
from heteroes.manifest import MAX_SEED, derive_seed

RECIPE = "a" * 64
PARENT = "b" * 64
SEEDS = (1000, 1007, 1014, 1021)
REWARDS = (0.5, 0.25, 0.75, 0.5)
ETA = 1e-9


def coefficients_of(rewards, eta=ETA):
    return tuple(float(v) for v in standardize_rewards(rewards, eta))


def make_record(**changes):
    values = dict(experiment_id="learn", generation=3, recipe_hash=RECIPE, parent_weights_sha256=PARENT,
                  seeds=SEEDS, rewards=REWARDS, coefficients=coefficients_of(REWARDS), alpha=1e-3)
    values.update(changes)
    return GenerationRecord(**values)


# ---------------------------------------------------------------------------
# the document and its hash
# ---------------------------------------------------------------------------

def test_the_record_document_has_exactly_the_agreed_shape():
    document = make_record().to_dict()

    assert set(document) == {"record_version", "experiment_id", "generation", "recipe_hash", "parent_weights_sha256", "seeds",
                             "rewards", "coefficients", "alpha", "alpha_float32"}
    assert document["record_version"] == RECORD_VERSION == 1
    assert document["seeds"] == list(SEEDS) and document["rewards"] == list(REWARDS)
    assert document["coefficients"] == list(coefficients_of(REWARDS))
    assert document["alpha"] == 1e-3 and document["alpha_float32"] == float(np.float32(1e-3)) != 1e-3     # derived, never given


def test_the_hash_is_the_sha256_of_the_canonical_json_of_the_document():
    record = make_record()

    assert re.fullmatch(r"[0-9a-f]{64}", record.hash)
    assert record.hash == canonical_json_hash(record.to_dict())
    assert make_record().hash == record.hash


@pytest.mark.parametrize("name, value", [
    ("experiment_id", "learn-b"),
    ("generation", 4),
    ("recipe_hash", "c" * 64),
    ("parent_weights_sha256", "d" * 64),
    ("seeds", (1000, 1007, 1014, 1022)),
    ("rewards", (0.5, 0.25, 0.75, 0.625)),
    ("coefficients", (0.0, -1.0, 1.0, 0.0)),
    ("alpha", 2e-3),
])
def test_changing_any_one_field_changes_the_hash(name, value):
    assert make_record(**{name: value}).hash != make_record().hash


def test_the_order_of_the_candidates_is_part_of_the_record():
    swapped = make_record(seeds=(1007, 1000, 1014, 1021), rewards=(0.25, 0.5, 0.75, 0.5),
                          coefficients=coefficients_of((0.25, 0.5, 0.75, 0.5)))

    assert swapped.hash != make_record().hash


def test_one_coefficient_one_float32_step_away_is_another_record():
    z = list(coefficients_of(REWARDS))
    z[2] = float(np.nextafter(np.float32(z[2]), np.float32(10.0)))

    assert make_record(coefficients=tuple(z)).hash != make_record().hash


def test_the_hash_is_that_of_a_document_written_by_hand():
    # no GenerationRecord here: the document is spelled out and hashed with the standard library, to check the serialization
    z = coefficients_of(REWARDS)
    by_hand = {
        "record_version": 1, "experiment_id": "learn", "generation": 3, "recipe_hash": "a" * 64,
        "parent_weights_sha256": "b" * 64, "seeds": [1000, 1007, 1014, 1021], "rewards": [0.5, 0.25, 0.75, 0.5],
        "coefficients": [z[0], z[1], z[2], z[3]], "alpha": 0.001, "alpha_float32": 0.0010000000474974513,
    }
    text = json.dumps(by_hand, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    assert make_record().hash == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_this_record_has_this_hash():
    # produced by this code: a guard against a change of the serialization, not independent evidence
    # (the test above is the independent one)
    assert make_record().hash == "13821ccb7541548c45b74a1865cd90f1ed612be8d1f08da2e4be47d89b97fde1"


def test_plain_numbers_and_lists_are_normalized_so_that_equal_records_have_equal_hashes():
    a = make_record(seeds=list(SEEDS), rewards=[1, 0, 0.5, 0.5], coefficients=[1, 0, -1, 0], alpha=1)
    b = make_record(seeds=SEEDS, rewards=(1.0, 0.0, 0.5, 0.5), coefficients=(1.0, 0.0, -1.0, 0.0), alpha=1.0)

    assert a.hash == b.hash
    assert isinstance(a.seeds, tuple) and isinstance(a.rewards, tuple) and isinstance(a.coefficients, tuple)
    assert all(type(x) is float for x in a.rewards + a.coefficients) and type(a.alpha) is float


def test_numpy_floats_are_accepted_as_numbers():
    record = make_record(rewards=tuple(np.float64(r) for r in REWARDS), coefficients=tuple(standardize_rewards(REWARDS, ETA)))

    assert record.hash == make_record().hash


def test_the_record_cannot_be_changed():
    with pytest.raises(Exception):
        make_record().alpha = 5.0


def test_a_record_for_a_few_candidates_is_small():
    seeds = tuple(derive_seed("learn", 3, i) for i in range(8))
    rewards = tuple(k / 96 for k in (60, 62, 70, 64, 66, 58, 69, 61))
    record = make_record(seeds=seeds, rewards=rewards, coefficients=coefficients_of(rewards))

    assert len(canonical_json_bytes(record.to_dict())) < 1024      # measured 744 bytes for N = 8 (artifacts/experiments/2026-10-06-coefficient-residue)


# ---------------------------------------------------------------------------
# reading it back
# ---------------------------------------------------------------------------

def test_a_record_survives_the_dict_and_the_json():
    record = make_record()

    assert GenerationRecord.from_dict(record.to_dict()) == record
    assert GenerationRecord.from_json(record.to_json()) == record
    assert GenerationRecord.from_json(record.to_json()).hash == record.hash


def test_the_json_is_the_canonical_one_and_any_equivalent_text_is_read():
    record = make_record()
    reordered = json.dumps(dict(reversed(list(record.to_dict().items()))), indent=3)

    assert record.to_json() == canonical_json_bytes(record.to_dict()).decode("ascii")
    assert GenerationRecord.from_json(reordered) == record


def test_a_key_that_is_missing_or_extra_is_refused():
    document = make_record().to_dict()
    for key in document:
        broken = copy.deepcopy(document)
        del broken[key]
        with pytest.raises(ValueError):
            GenerationRecord.from_dict(broken)
    with pytest.raises(ValueError):
        GenerationRecord.from_dict({**document, "worker": "w1"})


def test_another_version_of_the_record_is_refused():
    with pytest.raises(ValueError, match="version"):
        GenerationRecord.from_dict({**make_record().to_dict(), "record_version": 2})


def test_the_derived_float32_of_alpha_must_agree_with_alpha():
    with pytest.raises(ValueError, match="round-trip"):
        GenerationRecord.from_dict({**make_record().to_dict(), "alpha_float32": 0.5})


def test_json_with_nan_is_refused():
    text = make_record().to_json().replace('"alpha":0.001', '"alpha":NaN')

    with pytest.raises(ValueError):
        GenerationRecord.from_json(text)


# ---------------------------------------------------------------------------
# what a record may hold
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("changes, error", [
    (dict(experiment_id=""), ValueError), (dict(experiment_id="a/b"), ValueError), (dict(experiment_id=5), TypeError),
    (dict(generation=-1), ValueError), (dict(generation=True), TypeError), (dict(generation="3"), TypeError),
    (dict(recipe_hash="A" * 64), ValueError), (dict(recipe_hash="a" * 63), ValueError), (dict(recipe_hash=None), TypeError),
    (dict(parent_weights_sha256="g" * 64), ValueError), (dict(parent_weights_sha256=7), TypeError),
    (dict(seeds=(), rewards=(), coefficients=()), ValueError), (dict(seeds=()), ValueError), (dict(seeds=(1, 1, 2, 3)), ValueError), (dict(seeds=(-1, 1, 2, 3)), ValueError),
    (dict(seeds=(MAX_SEED, 1, 2, 3)), ValueError), (dict(seeds=(1.0, 1, 2, 3)), TypeError), (dict(seeds=(True, 1, 2, 3)), TypeError),
    (dict(seeds=("1", 1, 2, 3)), TypeError), (dict(seeds=(np.int64(5), 1, 2, 3)), TypeError), (dict(seeds=None), TypeError),
    (dict(seeds="abcd"), TypeError),
    (dict(rewards=(0.5, 0.25, 0.75)), ValueError), (dict(rewards=(0.5,) * 5), ValueError),
    (dict(rewards=(0.5, float("nan"), 0.75, 0.5)), ValueError), (dict(rewards=(0.5, float("inf"), 0.75, 0.5)), ValueError),
    (dict(rewards=(0.5, True, 0.75, 0.5)), TypeError), (dict(rewards=(0.5, "0.25", 0.75, 0.5)), TypeError),
    (dict(rewards=None), TypeError),
    (dict(coefficients=(0.0, 1.0, -1.0)), ValueError), (dict(coefficients=(0.0, float("nan"), 1.0, 0.0)), ValueError),
    (dict(coefficients=(0.0, float("inf"), 1.0, 0.0)), ValueError), (dict(coefficients=(0.0, 0.1, 1.0, 0.0)), ValueError),
    (dict(coefficients=(0.0, 1e300, 1.0, 0.0)), ValueError), (dict(coefficients=(0.0, True, 1.0, 0.0)), TypeError),
    (dict(coefficients=(0.0, "1.0", 1.0, 0.0)), TypeError),
    (dict(alpha=float("nan")), ValueError), (dict(alpha=float("inf")), ValueError), (dict(alpha=1e300), ValueError),
    (dict(alpha=True), TypeError), (dict(alpha="0.001"), TypeError), (dict(alpha=None), TypeError),
])
def test_a_record_with_something_wrong_in_it_is_refused(changes, error):
    with pytest.raises(error):
        make_record(**changes)


@pytest.mark.parametrize("alpha", [0.0, -1e-3, 3.4e38])
def test_alpha_may_be_zero_or_negative_as_long_as_it_fits_a_float32(alpha):
    assert make_record(alpha=alpha).alpha == alpha


def test_a_record_of_one_candidate_is_allowed():
    assert make_record(seeds=(5,), rewards=(1.0,), coefficients=(0.0,)).noop is True


# ---------------------------------------------------------------------------
# no signal, and checking the coefficients
# ---------------------------------------------------------------------------

def test_a_record_is_a_no_op_when_every_coefficient_is_zero():
    assert make_record().noop is False
    assert make_record(rewards=(0.5,) * 4, coefficients=(0.0,) * 4).noop is True
    assert make_record(rewards=(0.5,) * 4, coefficients=(-0.0, 0.0, 0.0, -0.0)).noop is True


def test_the_coefficients_of_the_rewards_are_verified():
    make_record().verify_coefficients(ETA)


def test_a_coefficient_that_is_not_the_one_of_the_rewards_is_found():
    z = list(coefficients_of(REWARDS))
    z[0] = float(np.nextafter(np.float32(z[0]), np.float32(10.0)))

    with pytest.raises(ValueError, match="coefficients"):
        make_record(coefficients=tuple(z)).verify_coefficients(ETA)


def test_coefficients_made_with_another_eta_are_found():
    record = make_record(coefficients=coefficients_of(REWARDS, eta=0.1))      # premise: the eta changes the float32 values

    assert record.coefficients != make_record().coefficients
    record.verify_coefficients(0.1)
    with pytest.raises(ValueError):
        record.verify_coefficients(ETA)


def test_a_residue_of_zero_is_found_by_the_exact_check_and_forgiven_by_a_tolerance():
    # two rewards equal the mean: their coefficients are 0.0 here, and +-1e-16 where the sum was made in another order
    z = list(coefficients_of(REWARDS))
    zero_positions = [i for i, v in enumerate(z) if v == 0.0]
    assert zero_positions                                                        # premise: this set has such coefficients
    z[zero_positions[0]] = float(np.float32(2.0e-16))
    record = make_record(coefficients=tuple(z))

    with pytest.raises(ValueError):
        record.verify_coefficients(ETA)
    record.verify_coefficients(ETA, atol=1e-9)


def test_the_tolerance_does_not_hide_a_real_difference():
    z = list(coefficients_of(REWARDS))
    z[2] = z[2] + 1e-3
    record = make_record(coefficients=tuple(float(np.float32(v)) for v in z))

    with pytest.raises(ValueError):
        record.verify_coefficients(ETA, atol=1e-9)


# ---------------------------------------------------------------------------
# built from the results of a complete generation
# ---------------------------------------------------------------------------

def make_results(rewards=REWARDS, seeds=SEEDS):
    return GenerationResults(recipe_hash=RECIPE, parent_weights_sha256=PARENT, seeds=tuple(seeds), rewards=tuple(rewards))


def test_a_record_is_built_from_the_results_with_the_coefficients_computed_once():
    record = GenerationRecord.from_results("learn", 3, make_results(), alpha=1e-3, eta=ETA)

    assert record == make_record()
    record.verify_coefficients(ETA)


def test_the_record_built_from_results_with_equal_rewards_is_a_no_op():
    record = GenerationRecord.from_results("learn", 3, make_results(rewards=(0.5,) * 4), alpha=1e-3, eta=ETA)

    assert record.noop is True and record.coefficients == (0.0,) * 4


def test_the_eta_given_is_the_one_used():
    assert GenerationRecord.from_results("learn", 3, make_results(), alpha=1e-3, eta=0.1).coefficients == coefficients_of(REWARDS, 0.1)


def test_an_unusable_reward_is_refused_when_building():
    with pytest.raises(ValueError):
        GenerationRecord.from_results("learn", 3, make_results(rewards=(0.5, float("nan"), 0.75, 0.5)), alpha=1e-3, eta=ETA)
