"""
Tests of the perturbation and the update with the noise of the CUDA engine (G7). They need a CUDA device.

The oracles are plain NumPy written from the contract (O2 = c for the perturbation, O4 and the FP32 accumulation in candidate order for the
update); the noise they need is made by a loop of `torch.randn` calls of K elements written in this file (not by the engine's class).
"""
import hashlib

import numpy as np
import pytest
import torch
import torch.nn as nn

import heteroes.es.cuda_ops as ops
import heteroes.noise.cuda_engine as engine
from heteroes.es.cuda_ops import apply_coefficients_cuda_, perturb_model_cuda_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.model.schema import SchemaMismatchError, build_parameter_schema, resolve_tensors
from heteroes.noise.cuda_engine import CUDA_CALL_ELEMENTS, CUDA_ENGINE_VERSION

pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="the CUDA noise engine needs a CUDA device")


K = CUDA_CALL_ELEMENTS


class HalfToy(nn.Module):
    # FP16, a tied tensor first, then plain tensors; big enough that a tensor has several pieces when PIECE_ELEMENTS is made small
    def __init__(self):
        super().__init__()
        self.embed = nn.Embedding(25, 2000)                      # 50,000 elements, tied with head.weight
        self.head = nn.Linear(2000, 25, bias=False)
        self.head.weight = self.embed.weight
        self.fc = nn.Linear(100, 100)                            # 10,000 and 100 elements
        self.half()


def make_model():
    torch.manual_seed(0)
    return HalfToy().to("cuda")


def noise_oracle(schema_hash, seed, index, numel):
    address = f"{CUDA_ENGINE_VERSION}|candidate_seed={seed}|schema={schema_hash}|param={index}|call_elements={K}"
    gen = torch.Generator(device="cuda")
    gen.manual_seed(int.from_bytes(hashlib.sha256(address.encode()).digest()[:8], "little") & ((1 << 63) - 1))
    parts, left = [], numel
    while left > 0:
        size = min(K, left)
        parts.append(torch.randn((size,), generator=gen, dtype=torch.float32, device="cuda"))
        left -= size
    return torch.cat(parts).to(torch.float16).cpu().numpy()


def flat_weights(model, schema):
    return [t.detach().cpu().numpy().reshape(-1).copy() for t in resolve_tensors(model, schema)]


def expected_perturbed(before, schema, seed, sigma):
    out = []
    for theta, entry in zip(before, schema.entries):
        eps = noise_oracle(schema.hash, seed, entry.index, theta.size)
        out.append((theta.astype(np.float32) + np.float32(sigma) * eps.astype(np.float32)).astype(np.float16))
    return out


def expected_updated(before, schema, seeds, coefficients, alpha):
    out = []
    for theta, entry in zip(before, schema.entries):
        acc = np.zeros(theta.size, dtype=np.float32)
        for seed, z in zip(seeds, coefficients):
            eps = noise_oracle(schema.hash, seed, entry.index, theta.size).astype(np.float32)
            acc = acc + eps * np.float32(z)
        update = (acc / np.float32(len(seeds))) * np.float32(alpha)
        out.append((theta.astype(np.float32) + update).astype(np.float16))
    return out


def same_bits(a, b):
    return all(np.array_equal(x.view(np.int16), y.view(np.int16)) for x, y in zip(a, b, strict=True))


@pytest.fixture(params=[engine.PIECE_ELEMENTS, 2 * K], ids=["default-pieces", "many-pieces"])
def piece_elements(request, monkeypatch):
    monkeypatch.setattr(engine, "PIECE_ELEMENTS", request.param)
    monkeypatch.setattr(ops, "PIECE_ELEMENTS", request.param)
    return request.param


# ---- perturbation ---------------------------------------------------------------------------------------------------------------------

def test_the_perturbation_is_the_contract_arithmetic_on_the_noise_of_the_engine(piece_elements):
    model = make_model()
    schema = build_parameter_schema(model)
    before = flat_weights(model, schema)

    perturb_model_cuda_(model, schema, 7, 1e-3)

    assert same_bits(flat_weights(model, schema), expected_perturbed(before, schema, 7, 1e-3))


def test_the_perturbation_changes_the_weights_and_the_tied_tensor_once():
    model = make_model()
    schema = build_parameter_schema(model)
    before = flat_weights(model, schema)
    perturb_model_cuda_(model, schema, 7, 1e-3)
    after = flat_weights(model, schema)
    assert all(not np.array_equal(a, b) for a, b in zip(before, after))
    assert model.head.weight is model.embed.weight and len(schema.entries) == 3


def test_the_bits_do_not_depend_on_the_size_of_the_pieces(monkeypatch):
    results = []
    for size in (engine.PIECE_ELEMENTS, 2 * K, K):
        monkeypatch.setattr(engine, "PIECE_ELEMENTS", size)
        monkeypatch.setattr(ops, "PIECE_ELEMENTS", size)
        model = make_model()
        schema = build_parameter_schema(model)
        perturb_model_cuda_(model, schema, 9, 1e-3)
        results.append(flat_weights(model, schema))
    assert same_bits(results[0], results[1]) and same_bits(results[0], results[2])


def test_the_restore_from_the_snapshot_brings_the_bits_back():
    model = make_model()
    schema = build_parameter_schema(model)
    before = flat_weights(model, schema)
    snapshot = take_snapshot(model, schema)
    perturb_model_cuda_(model, schema, 3, 1e-3)
    restore_from_snapshot_(model, schema, snapshot)
    assert same_bits(flat_weights(model, schema), before)


def test_two_seeds_make_two_candidates_and_the_same_seed_the_same_one():
    schema = build_parameter_schema(make_model())
    out = {}
    for seed in (1, 2, 1):
        model = make_model()
        perturb_model_cuda_(model, schema, seed, 1e-3)
        out.setdefault(seed, []).append(flat_weights(model, schema))
    assert same_bits(out[1][0], out[1][1]) and not same_bits(out[1][0], out[2][0])


@pytest.mark.parametrize("sigma", [float("nan"), float("inf")])
def test_a_bad_sigma_is_refused_before_anything_is_written(sigma):
    model = make_model()
    schema = build_parameter_schema(model)
    before = flat_weights(model, schema)
    with pytest.raises(ValueError):
        perturb_model_cuda_(model, schema, 1, sigma)
    assert same_bits(flat_weights(model, schema), before)


def test_a_model_that_is_not_on_a_cuda_device_is_refused():
    model = make_model().to("cpu")
    with pytest.raises(ValueError, match="CUDA device"):
        perturb_model_cuda_(model, build_parameter_schema(model), 1, 1e-3)


def test_a_float32_tensor_is_refused_and_nothing_is_written():
    model = make_model()
    schema = build_parameter_schema(model)
    before = flat_weights(model, schema)
    model.fc.bias.data = model.fc.bias.data.float()
    with pytest.raises(SchemaMismatchError):                       # the schema says float16: the model no longer matches it
        perturb_model_cuda_(model, schema, 1, 1e-3)
    model.fc.bias.data = model.fc.bias.data.half()
    assert same_bits(flat_weights(model, schema), before)


# ---- update ---------------------------------------------------------------------------------------------------------------------------

COEFFICIENTS = [1.5, -0.5, 0.25, -1.25]
SEEDS = [11, 12, 13, 14]


def test_the_update_is_the_contract_arithmetic_on_the_noise_of_the_engine(piece_elements):
    model = make_model()
    schema = build_parameter_schema(model)
    before = flat_weights(model, schema)

    report = apply_coefficients_cuda_(model, schema, SEEDS, COEFFICIENTS, 1e-3)

    after = flat_weights(model, schema)
    assert same_bits(after, expected_updated(before, schema, SEEDS, COEFFICIENTS, 1e-3))
    assert not report.noop and report.numel == sum(t.size for t in before)
    assert report.changed == sum(int((a.view(np.int16) != b.view(np.int16)).sum()) for a, b in zip(before, after))


def test_the_report_has_the_norm_of_what_was_applied():
    model = make_model()
    schema = build_parameter_schema(model)
    before = flat_weights(model, schema)
    report = apply_coefficients_cuda_(model, schema, SEEDS, COEFFICIENTS, 1e-3)
    after = flat_weights(model, schema)
    applied = np.sqrt(sum(float(((a.astype(np.float64) - b.astype(np.float64)) ** 2).sum()) for a, b in zip(after, before)))
    assert report.applied_l2 == pytest.approx(applied, rel=1e-9)
    assert report.requested_l2 > 0


def test_an_update_of_one_candidate_with_coefficient_one_is_the_perturbation_with_sigma_alpha():
    # the property that ties the two operations: acc = eps * 1.0, / 1, * alpha is the same operations as eps * sigma
    a, b = make_model(), make_model()
    schema = build_parameter_schema(a)
    apply_coefficients_cuda_(a, schema, [5], [1.0], 2e-3)
    perturb_model_cuda_(b, schema, 5, 2e-3)
    assert same_bits(flat_weights(a, schema), flat_weights(b, schema))


def test_the_order_of_the_candidates_is_the_order_of_the_sum():
    # the float32 sum is not associative: the update is defined in the order given, and another order is another (equally valid) update
    model1, model2 = make_model(), make_model()
    schema = build_parameter_schema(model1)
    apply_coefficients_cuda_(model1, schema, SEEDS, COEFFICIENTS, 1e-3)
    apply_coefficients_cuda_(model2, schema, SEEDS[::-1], COEFFICIENTS[::-1], 1e-3)
    assert same_bits(flat_weights(model1, schema), expected_updated(flat_weights(make_model(), schema), schema, SEEDS, COEFFICIENTS, 1e-3))
    assert same_bits(flat_weights(model2, schema), expected_updated(flat_weights(make_model(), schema), schema, SEEDS[::-1], COEFFICIENTS[::-1], 1e-3))


def test_equal_rewards_are_a_logged_no_op():
    model = make_model()
    schema = build_parameter_schema(model)
    before = flat_weights(model, schema)
    report = apply_coefficients_cuda_(model, schema, SEEDS, [0.0] * 4, 1e-3)
    assert report.noop and report.changed == 0 and same_bits(flat_weights(model, schema), before)


@pytest.mark.parametrize("seeds,coefficients,alpha,error", [
    ([1, 1], [1.0, -1.0], 1e-3, ValueError),                      # duplicated seed
    ([1, 2, 3], [1.0, -1.0], 1e-3, ValueError),                   # length mismatch
    ([1, 2], [1.0, float("nan")], 1e-3, ValueError),              # NaN coefficient
    ([1, 2], [1.0, -1.0], float("nan"), ValueError),              # NaN alpha
    ([1.0, 2], [1.0, -1.0], 1e-3, TypeError),                     # a float seed
    ([True, 2], [1.0, -1.0], 1e-3, TypeError),                    # a bool seed
])
def test_a_bad_update_is_refused_and_nothing_is_written(seeds, coefficients, alpha, error):
    model = make_model()
    schema = build_parameter_schema(model)
    before = flat_weights(model, schema)
    with pytest.raises(error):
        apply_coefficients_cuda_(model, schema, seeds, coefficients, alpha)
    assert same_bits(flat_weights(model, schema), before)


def test_a_model_that_is_not_on_a_cuda_device_is_refused_by_the_update():
    model = make_model().to("cpu")
    with pytest.raises(ValueError, match="CUDA device"):
        apply_coefficients_cuda_(model, build_parameter_schema(model), [1, 2], [1.0, -1.0], 1e-3)
