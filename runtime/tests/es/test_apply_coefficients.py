"""
apply_coefficients_: the update of the ES step given the coefficients directly, the way a worker applies a generation record.
The coefficients are NOT recomputed from rewards here: the coordinator computes them once and they travel.
"""
import numpy as np
import pytest
import torch

from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.es.update import UpdateReport, apply_coefficients_, apply_es_update_, standardize_rewards
from heteroes.model.schema import SchemaMismatchError, build_parameter_schema, resolve_tensors
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS
from test_update import (  # the toy models and the independent oracle of test_update.py
    DEVICES,
    REWARDS,
    SEEDS,
    bits,
    make_big,
    make_model,
    oracle_new_tensor,
    same_bits,
    snapshot_bits,
)


def as_floats(z):
    return [float(v) for v in z]


# ---------------------------------------------------------------------------
# the same result as the update that standardizes the rewards itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("device", DEVICES)
@pytest.mark.parametrize("chunk_elements", [4, 16, DEFAULT_CHUNK_ELEMENTS])
def test_the_coefficients_of_the_rewards_give_the_same_bits_as_the_rewards(chunk_elements, device):
    a, b = make_model(device=device), make_model(device=device)
    schema = build_parameter_schema(a)

    report_rewards = apply_es_update_(a, schema, SEEDS, REWARDS, alpha=0.05, chunk_elements=chunk_elements)
    report_coefficients = apply_coefficients_(b, schema, SEEDS, standardize_rewards(REWARDS), alpha=0.05,
                                              chunk_elements=chunk_elements)

    assert same_bits(b, snapshot_bits(a))
    assert report_rewards == report_coefficients
    assert report_coefficients.changed > 0                                   # the comparison is not between two no-ops


def test_the_same_bits_on_a_big_tensor_where_rare_rounding_effects_show():
    a, b = make_big(), make_big()
    schema = build_parameter_schema(a)

    apply_es_update_(a, schema, [11, 12, 13, 14], [0.2, 0.9, 0.1, 0.5], alpha=1e-3)
    apply_coefficients_(b, schema, [11, 12, 13, 14], standardize_rewards([0.2, 0.9, 0.1, 0.5]), alpha=1e-3)

    assert same_bits(b, snapshot_bits(a))


@pytest.mark.parametrize("coefficients", [
    [1.0, -1.0, 0.5, -0.5],
    [0.25, 0.0, -2.0, 1.75],
    [3.0, 0.0, 0.0, 0.0],
])
def test_the_coefficients_given_are_the_ones_applied_and_nothing_is_standardized_again(coefficients):
    model = make_model()
    schema = build_parameter_schema(model)
    expected = []
    for entry, tensor in zip(schema.entries, resolve_tensors(model, schema)):
        theta = tensor.detach().cpu().numpy().reshape(-1)
        new, _ = oracle_new_tensor(theta, schema, entry.index, SEEDS, coefficients, 0.05, 16)
        expected.append(new.reshape(entry.shape))

    apply_coefficients_(model, schema, SEEDS, coefficients, alpha=0.05, chunk_elements=16)

    for tensor, want in zip(resolve_tensors(model, schema), expected):
        assert np.array_equal(bits(tensor.detach().cpu().numpy()), bits(want))
    standardized = standardize_rewards(coefficients)                          # premise: they would be told apart if it did
    assert not np.array_equal(np.asarray(coefficients, np.float32), standardized)


def test_a_coefficient_that_is_only_a_residue_of_zero_still_counts_as_a_coefficient():
    # why the coefficients travel: "the reward equals the mean" gives 0.0 on one machine and +-1e-16 on another
    residue = float(np.float32(2.0e-16))
    model = make_model()
    schema = build_parameter_schema(model)

    report = apply_coefficients_(model, schema, SEEDS, [1.0, -1.0, residue, 0.0], alpha=0.05)

    assert report.noop is False and report.coefficients == (1.0, -1.0, residue, 0.0)


# ---------------------------------------------------------------------------
# no signal
# ---------------------------------------------------------------------------

def test_all_zero_coefficients_leave_the_model_untouched_and_say_so():
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)

    report = apply_coefficients_(model, schema, SEEDS, [0.0, 0.0, 0.0, 0.0], alpha=0.05)

    assert same_bits(model, before)
    assert report == UpdateReport(noop=True, coefficients=(0.0,) * 4, requested_l2=0.0, applied_l2=0.0, changed=0,
                                  numel=sum(t.numel() for t in resolve_tensors(model, schema)))


def test_negative_zero_is_no_signal_either():
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)

    report = apply_coefficients_(model, schema, SEEDS, [-0.0, 0.0, -0.0, 0.0], alpha=0.05)

    assert report.noop is True and same_bits(model, before)


# ---------------------------------------------------------------------------
# bad arguments: refused, and the model is untouched
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("coefficients, error", [
    ([1.0, float("nan"), 0.5, -0.5], ValueError),
    ([1.0, float("inf"), 0.5, -0.5], ValueError),
    ([1.0, -float("inf"), 0.5, -0.5], ValueError),
    ([1.0, -1.0, 0.1, -0.5], ValueError),                  # 0.1 is not a float32 value: it would be rounded in silence
    ([1.0, -1.0, 1e300, -0.5], ValueError),                # does not even fit in a float32
    ([[1.0, -1.0], [0.5, -0.5]], ValueError),              # not a vector
    ([[1.0], [-1.0], [0.5], [-0.5]], ValueError),          # a column: as long as the seeds, but not a vector
    ([], ValueError),
    ([1.0, -1.0, 0.5], ValueError),                        # fewer coefficients than seeds
    ([1.0, -1.0, 0.5, -0.5, 0.25], ValueError),            # more
    ([True, False, True, False], TypeError),               # booleans are not numbers here
    (["1.0", "-1.0", "0.5", "-0.5"], TypeError),
    ([None, 1.0, 0.5, -0.5], TypeError),
])
def test_bad_coefficients_are_refused_and_the_model_is_untouched(coefficients, error):
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)

    with pytest.raises(error):
        apply_coefficients_(model, schema, SEEDS, coefficients, alpha=0.05)

    assert same_bits(model, before)


@pytest.mark.parametrize("coefficients", [[0.0] * 4, [1.0, -1.0, 0.5, -0.5]])
@pytest.mark.parametrize("kwargs, error", [
    (dict(alpha=float("nan")), ValueError),
    (dict(alpha=float("inf")), ValueError),
    (dict(chunk_elements=0), ValueError),
    (dict(chunk_elements=-8), ValueError),
    (dict(seeds=[0, 1, 2]), ValueError),
    (dict(seeds=[0, 1, 1, 3]), ValueError),                 # a duplicated seed
    (dict(seeds=[0, 1.0, 2, 3]), TypeError),
    (dict(seeds=[0, True, 2, 3]), TypeError),
    (dict(seeds=[0, "1", 2, 3]), TypeError),
])
def test_the_other_arguments_are_checked_as_well_even_when_there_is_no_signal(coefficients, kwargs, error):
    # all-zero coefficients would otherwise hide a mistake behind a silent "no-op" answer
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)
    arguments = dict(seeds=SEEDS, alpha=0.05, chunk_elements=8)
    arguments.update(kwargs)

    with pytest.raises(error):
        apply_coefficients_(model, schema, arguments.pop("seeds"), coefficients, **arguments)

    assert same_bits(model, before)


def test_a_model_that_does_not_match_the_schema_is_refused_and_untouched():
    schema = build_parameter_schema(make_model())
    other = make_model()
    other.extra = torch.nn.Parameter(torch.zeros(2, dtype=torch.float16))
    before = snapshot_bits(other)

    with pytest.raises(SchemaMismatchError):
        apply_coefficients_(other, schema, SEEDS, [1.0, -1.0, 0.5, -0.5], alpha=0.05)

    assert same_bits(other, before)


@pytest.mark.parametrize("bad_last, error", [("non_contiguous", ValueError), ("float32", TypeError)])
def test_a_bad_tensor_is_found_before_the_first_tensor_is_changed(bad_last, error):
    model = make_model(bad_last=bad_last)
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)

    with pytest.raises(error):
        apply_coefficients_(model, schema, SEEDS, [1.0, -1.0, 0.5, -0.5], alpha=0.05)

    assert same_bits(model, before)


def test_numpy_arrays_and_tuples_are_accepted_like_lists():
    coefficients = [1.0, -1.0, 0.5, -0.5]
    reference = make_model()
    schema = build_parameter_schema(reference)
    apply_coefficients_(reference, schema, SEEDS, coefficients, alpha=0.05)

    for variant in (tuple(coefficients), np.array(coefficients, dtype=np.float32), np.array(coefficients, dtype=np.float64)):
        model = make_model()
        apply_coefficients_(model, schema, SEEDS, variant, alpha=0.05)
        assert same_bits(model, snapshot_bits(reference))


def test_the_update_can_be_undone_from_a_snapshot():
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot_bits(model)
    snapshot = take_snapshot(model, schema)

    apply_coefficients_(model, schema, SEEDS, [1.0, -1.0, 0.5, -0.5], alpha=0.05, chunk_elements=8)
    assert not same_bits(model, before)

    restore_from_snapshot_(model, schema, snapshot)
    assert same_bits(model, before)
