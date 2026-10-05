import hashlib
import os

import numpy as np
import pytest
import torch
import torch.nn as nn

from heteroes.es.perturb import perturb_model_
from heteroes.model.schema import SchemaMismatchError, build_parameter_schema, resolve_tensors
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, ParameterNoiseAddress
from heteroes.noise.engine import generate_parameter_noise

DEVICES = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])


class HalfToy(nn.Module):
    # FP16, with a tied tensor first and plain tensors after, like Qwen in miniature.
    # Parameters (canonical order): embed.weight (tied with head.weight), fc.weight, fc.bias.
    def __init__(self, with_bad_last=None):
        super().__init__()
        self.embed = nn.Embedding(10, 4)
        self.head = nn.Linear(4, 10, bias=False)
        self.head.weight = self.embed.weight
        self.fc = nn.Linear(4, 4)
        self.half()
        # A bad tensor that comes LAST in model.named_parameters(). It must live in a child module:
        # PyTorch lists a module's own parameters before the parameters of its children, so a
        # parameter attached directly to the model would come FIRST, not last.
        if with_bad_last is not None:
            self.tail = nn.Module()
            if with_bad_last == "non_contiguous":
                self.tail.w = nn.Parameter(torch.zeros(4, 3, dtype=torch.float16).t())
            elif with_bad_last == "float32":
                self.tail.w = nn.Parameter(torch.zeros(3, dtype=torch.float32))


def make_model(bad_last=None, device="cpu"):
    torch.manual_seed(0)
    model = HalfToy(bad_last)
    assert model.head.weight is model.embed.weight  # the tie survived
    return model.to(device)


def snapshot(model):
    return [p.detach().clone() for p in model.parameters()]


def unchanged(model, before):
    return all(torch.equal(a, b) for a, b in zip(before, model.parameters()))


def oracle(theta, eps, sigma):
    # Independent oracle from contract O2 = (c), plain NumPy.
    scaled = np.float32(sigma) * eps.astype(np.float32)
    return (theta.astype(np.float32) + scaled).astype(np.float16)


def expected_after(model_before, schema, seed, sigma, chunk_elements):
    # What every tensor must look like after the perturbation, built only from NumPy and the engine.
    expected = []
    for entry, tensor in zip(schema.entries, model_before):
        address = ParameterNoiseAddress(seed, schema.hash, entry.index, chunk_elements)
        eps = generate_parameter_noise(address, entry.numel)
        theta = tensor.detach().cpu().numpy().reshape(-1)
        expected.append(oracle(theta, eps, sigma).reshape(entry.shape))
    return expected


def bits(array):
    return np.asarray(array).view(np.int16)


# ---------------------------------------------------------------------------
# correctness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("device", DEVICES)
@pytest.mark.parametrize("chunk_elements", [4, 16, DEFAULT_CHUNK_ELEMENTS])
def test_every_tensor_matches_the_numpy_oracle(chunk_elements, device):
    model = make_model(device=device)
    schema = build_parameter_schema(model)
    before = [t.detach().cpu().clone() for t in resolve_tensors(model, schema)]

    perturb_model_(model, schema, candidate_seed=5, sigma=1e-2, chunk_elements=chunk_elements)

    expected = expected_after(before, schema, 5, 1e-2, chunk_elements)
    for tensor, want in zip(resolve_tensors(model, schema), expected):
        assert np.array_equal(bits(tensor.detach().cpu().numpy()), bits(want))


def test_default_chunk_size_is_the_contract_value():
    model = make_model()
    schema = build_parameter_schema(model)
    before = [t.detach().clone() for t in resolve_tensors(model, schema)]

    perturb_model_(model, schema, candidate_seed=5, sigma=1e-2)

    expected = expected_after(before, schema, 5, 1e-2, DEFAULT_CHUNK_ELEMENTS)
    for tensor, want in zip(resolve_tensors(model, schema), expected):
        assert np.array_equal(bits(tensor.detach().numpy()), bits(want))


def test_a_tied_tensor_is_perturbed_exactly_once():
    model = make_model()
    schema = build_parameter_schema(model)
    before = model.embed.weight.detach().clone()

    perturb_model_(model, schema, candidate_seed=5, sigma=1e-2, chunk_elements=8)

    address = ParameterNoiseAddress(5, schema.hash, 0, 8)
    once = oracle(before.numpy().reshape(-1), generate_parameter_noise(address, 40), 1e-2)
    assert np.array_equal(bits(model.embed.weight.detach().numpy().reshape(-1)), bits(once))
    assert model.head.weight is model.embed.weight


def test_different_tensors_get_different_noise():
    # Same shape would otherwise tempt a bug that reuses one stream for every tensor.
    model = make_model()
    schema = build_parameter_schema(model)
    for tensor in resolve_tensors(model, schema):
        tensor.data.zero_()

    perturb_model_(model, schema, candidate_seed=5, sigma=1.0, chunk_elements=8)

    weight, bias = model.fc.weight.detach().reshape(-1), model.fc.bias.detach()
    assert not torch.equal(weight[:4], bias)


def test_result_depends_on_the_candidate_seed_and_sigma():
    results = []
    for seed, sigma in [(1, 1e-2), (2, 1e-2), (1, 2e-2)]:
        model = make_model()
        perturb_model_(model, build_parameter_schema(model), seed, sigma, chunk_elements=8)
        results.append(model.fc.weight.detach().clone())

    assert not torch.equal(results[0], results[1])
    assert not torch.equal(results[0], results[2])


def test_is_deterministic():
    first, second = make_model(), make_model()
    for model in (first, second):
        perturb_model_(model, build_parameter_schema(model), 3, 1e-2, chunk_elements=8)

    assert all(torch.equal(a, b) for a, b in zip(first.parameters(), second.parameters()))


# ---------------------------------------------------------------------------
# all or nothing: bad input must be rejected BEFORE any tensor is changed
# ---------------------------------------------------------------------------

def test_model_that_does_not_match_the_schema_is_rejected_and_untouched():
    schema = build_parameter_schema(make_model())
    other = make_model()
    other.extra = nn.Parameter(torch.zeros(2, dtype=torch.float16))
    before = snapshot(other)

    with pytest.raises(SchemaMismatchError):
        perturb_model_(other, schema, candidate_seed=0, sigma=1e-2, chunk_elements=8)

    assert unchanged(other, before)


@pytest.mark.parametrize(
    "bad_last, error",
    [("non_contiguous", ValueError), ("float32", TypeError)],
)
def test_a_bad_last_tensor_is_found_before_the_first_tensor_is_changed(bad_last, error):
    # The bad tensor is the LAST one in canonical order. A loop that perturbs as it goes would
    # already have changed the earlier tensors when it reaches it.
    model = make_model(bad_last=bad_last)
    schema = build_parameter_schema(model)
    assert schema.entries[-1].canonical_name == "tail.w"  # guards the premise of this test
    before = snapshot(model)

    with pytest.raises(error):
        perturb_model_(model, schema, candidate_seed=0, sigma=1e-2, chunk_elements=8)

    assert unchanged(model, before)


@pytest.mark.parametrize("bad_sigma", [float("nan"), float("inf")])
def test_bad_sigma_is_rejected_and_the_model_untouched(bad_sigma):
    model = make_model()
    schema = build_parameter_schema(model)
    before = snapshot(model)

    with pytest.raises(ValueError):
        perturb_model_(model, schema, candidate_seed=0, sigma=bad_sigma, chunk_elements=8)

    assert unchanged(model, before)


# ---------------------------------------------------------------------------
# the real model: whole-model hash recorded by four environments on 2026-10-03
#   HETEROES_QWEN_PINNED_PATH=<snapshot dir of Qwen2.5-0.5B-Instruct @ 7ae55760...>
# It must be the ORIGINAL checkpoint (not an ES-modified one), or the hash cannot match.
# ---------------------------------------------------------------------------

PINNED_PATH = os.environ.get("HETEROES_QWEN_PINNED_PATH")
PRODUCTION_SCHEMA_HASH = "0b21250e331398a266785dc473da3a8b8f5e8f98fa15e9044637d742eb7845ec"
# Whole-model SHA-256 (first 16 hex characters) of the perturbed FP16 weights, seed 0, sigma 1e-3,
# computed with option (c) on RTX 5070 Ti, GTX 1660 SUPER, Colab T4 and Kaggle T4.
# See artifacts/regression/2026-10-03-o2-perturbation/README.md
O2_PERTURBED_HASH_PREFIX = "8aa3eb9af895cb4a"


@pytest.mark.skipif(PINNED_PATH is None, reason="set HETEROES_QWEN_PINNED_PATH to run the real-model check")
def test_qwen_whole_model_perturbation_matches_the_four_environment_hash():
    from transformers import AutoModelForCausalLM

    model = AutoModelForCausalLM.from_pretrained(PINNED_PATH, dtype=torch.float16)
    schema = build_parameter_schema(model)
    assert schema.hash == PRODUCTION_SCHEMA_HASH

    model.to("cuda" if torch.cuda.is_available() else "cpu")
    perturb_model_(model, schema, candidate_seed=0, sigma=1e-3)

    digest = hashlib.sha256()
    for tensor in resolve_tensors(model, schema):
        digest.update(tensor.detach().reshape(-1).view(torch.int16).cpu().numpy().tobytes())

    assert digest.hexdigest().startswith(O2_PERTURBED_HASH_PREFIX)
