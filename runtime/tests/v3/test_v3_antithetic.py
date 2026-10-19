"""
Antithetic pairs (ADR-008 section 5), checked against the frozen perturbation and update code as it is.
"""

import numpy as np
import pytest
import torch

from heteroes.es.perturb import perturb_model_
from heteroes.es.update import apply_coefficients_
from heteroes.manifest import derive_seed
from heteroes.model.schema import build_parameter_schema
from heteroes.noise.engine import iter_parameter_noise_chunks
from heteroes.noise.contracts import ParameterNoiseAddress
from heteroes.v3.antithetic import candidate_seeds, merged_update

CHUNK = 64


def toy(fill=0.0):
    torch.manual_seed(0)
    model = torch.nn.Sequential(torch.nn.Linear(16, 12), torch.nn.Linear(12, 5, bias=False)).half()
    with torch.no_grad():
        for p in model.parameters():
            p.copy_(torch.full_like(p, fill) if fill is not None else torch.randn_like(p))
    return model, build_parameter_schema(model)


def flat(model):
    return torch.cat([p.detach().reshape(-1) for p in model.parameters()])


def test_pairs_share_a_seed_and_plain_populations_are_todays_seeds():
    assert candidate_seeds("exp", 3, 4, False) == [(derive_seed("exp", 3, i), 1) for i in range(4)]
    pairs = candidate_seeds("exp", 3, 4, True)
    assert pairs == [
        (derive_seed("exp", 3, 0), 1),
        (derive_seed("exp", 3, 0), -1),
        (derive_seed("exp", 3, 1), 1),
        (derive_seed("exp", 3, 1), -1),
    ]
    with pytest.raises(ValueError):
        candidate_seeds("exp", 3, 5, True)
    with pytest.raises(ValueError):
        candidate_seeds("exp", 3, 0, False)


def test_a_negative_scale_gives_exactly_the_negated_perturbation():
    plus, schema = toy(0.0)
    minus, _ = toy(0.0)
    perturb_model_(plus, schema, 1234, 1e-3, CHUNK)
    perturb_model_(minus, schema, 1234, -1e-3, CHUNK)
    assert flat(plus).abs().sum() > 0  # premise: something moved
    assert torch.equal(flat(minus).view(torch.int16), (-flat(plus)).view(torch.int16))


def test_a_negative_scale_is_the_fp32_rule_with_the_noise_negated():
    model, schema = toy(None)
    before = [p.detach().clone() for p in model.parameters()]
    perturb_model_(model, schema, 99, -2e-3, CHUNK)
    sigma = np.float32(2e-3)
    for entry, old, new in zip(schema.entries, before, model.parameters()):
        address = ParameterNoiseAddress(99, schema.hash, entry.index, CHUNK)
        eps = np.concatenate([n for _, _, n in iter_parameter_noise_chunks(address, old.numel())]).astype(np.float32)
        expected = (old.reshape(-1).float().numpy() + (-eps) * sigma).astype(np.float16)
        assert np.array_equal(new.detach().reshape(-1).numpy().view(np.int16), expected.view(np.int16))


def test_without_pairs_the_coefficients_pass_unchanged():
    seeds = [(11, 1), (12, 1), (13, 1)]
    coefficients = np.array([0.5, -1.25, 0.75], dtype=np.float32)
    out_seeds, out = merged_update(seeds, coefficients)
    assert out_seeds == [11, 12, 13] and out.dtype == np.float32 and np.array_equal(out, coefficients)


def test_a_pair_becomes_half_its_difference_rounded_once():
    coefficients = np.array([1.1, -0.3, 0.2, 0.7], dtype=np.float32)
    seeds, merged = merged_update([(5, 1), (5, -1), (8, 1), (8, -1)], coefficients)
    expected = ((coefficients[0::2].astype(np.float64) - coefficients[1::2].astype(np.float64)) / 2).astype(np.float32)
    assert seeds == [5, 8] and merged.dtype == np.float32 and np.array_equal(merged, expected)


def test_the_merged_update_is_the_signed_sum_over_all_candidates():
    model, schema = toy(None)
    before = flat(model).double()
    pairs = [(21, 1), (21, -1), (22, 1), (22, -1)]
    coefficients = np.array([1.5, -0.5, -1.0, 0.25], dtype=np.float32)
    seeds, merged = merged_update(pairs, coefficients)
    alpha = 0.05
    apply_coefficients_(model, schema, seeds, merged, alpha, CHUNK)
    reference = torch.zeros_like(before)
    for (seed, sign), c in zip(pairs, coefficients):
        parts = []
        for entry, p in zip(schema.entries, model.parameters()):
            address = ParameterNoiseAddress(seed, schema.hash, entry.index, CHUNK)
            parts.append(np.concatenate([n for _, _, n in iter_parameter_noise_chunks(address, p.numel())]))
        reference += sign * float(c) * torch.from_numpy(np.concatenate(parts).astype(np.float64))
    target = alpha * reference / len(pairs)
    assert target.abs().max() > 1e-3  # premise: a step of several FP16 ulps, so a wrong merge (no halving) shows
    # the weights are rounded to FP16 once: each one must be within one FP16 spacing of parent + signed sum
    after = flat(model).double().numpy()
    ideal = (before + target).numpy()
    spacing = np.spacing(np.abs(after).astype(np.float16)).astype(np.float64)
    assert np.all(np.abs(after - ideal) <= spacing)


@pytest.mark.parametrize(
    "pairs, coefficients",
    [
        ([(5, -1), (5, 1)], [0.1, 0.2]),
        ([(5, 1), (6, -1)], [0.1, 0.2]),
        ([(5, 1), (5, -1), (6, 1)], [0.1, 0.2, 0.3]),
        ([(5, 1), (5, 2)], [0.1, 0.2]),
        ([(5, 1), (6, 1)], [0.1]),
        ([(5, 1), (6, 1)], [0.1, float("nan")]),
    ],
)
def test_malformed_pairs_are_refused(pairs, coefficients):
    with pytest.raises(ValueError):
        merged_update(pairs, np.array(coefficients, dtype=np.float32))


def test_coefficients_that_are_not_float32_values_are_refused():
    with pytest.raises(ValueError):
        merged_update([(5, 1)], np.array([0.1], dtype=np.float64))
    _, out = merged_update([(5, 1)], np.array([0.5], dtype=np.float64))  # exactly representable: accepted
    assert out.dtype == np.float32
