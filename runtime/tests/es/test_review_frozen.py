"""Review regression cases: validation before writes, CPU/CUDA parity and nonfinite update failures."""

import numpy as np
import pytest
import torch

from heteroes.es import cuda_ops
from heteroes.es.perturb import perturb_model_
from heteroes.es.update import apply_coefficients_, apply_es_update_
from heteroes.model.schema import build_parameter_schema
from heteroes.noise.contracts import ChunkNoiseAddress, ENGINE_V2, ENGINE_VERSION


@pytest.fixture(params=["cpu", "cuda"])
def model(request):
    if request.param == "cuda" and not torch.cuda.is_available():
        pytest.skip("requires CUDA")
    result = torch.nn.Linear(4, 4, bias=False).half().to(request.param)
    with torch.no_grad():
        result.weight.fill_(1)
    return result


def bits(model):
    return model.weight.detach().cpu().view(torch.int16).clone()


@pytest.mark.parametrize("alpha", [1e39, -1e39, float("nan"), float("inf")])
@pytest.mark.parametrize("mode", ["coefficients", "rewards"])
def test_alpha_outside_float32_is_refused_before_any_write(model, mode, alpha):
    before = bits(model)
    fn = {"coefficients": apply_coefficients_, "rewards": apply_es_update_, "cuda": cuda_ops.apply_coefficients_cuda_}[
        mode
    ]
    with pytest.raises(ValueError, match="alpha"):
        fn(model, build_parameter_schema(model), [1, 2], [1.0, -1.0], alpha)
    assert torch.equal(bits(model), before)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="requires CUDA")
@pytest.mark.parametrize("alpha", [1e39, -1e39, float("nan"), float("inf")])
def test_cuda_alpha_outside_float32_is_refused_before_writing(alpha):
    model = torch.nn.Linear(4, 4, bias=False).half().cuda()
    before = bits(model)
    with pytest.raises(ValueError, match="alpha"):
        cuda_ops.apply_coefficients_cuda_(model, build_parameter_schema(model), [1, 2], [1.0, -1.0], alpha)
    assert torch.equal(bits(model), before)


@pytest.mark.parametrize("bad", [True, 1.0, "1", -1])
def test_perturbation_rejects_invalid_seed_before_writing(model, bad):
    before = bits(model)
    with pytest.raises((TypeError, ValueError), match="seed"):
        perturb_model_(model, build_parameter_schema(model), bad, 0.1, 16)
    assert torch.equal(bits(model), before)
    if model.weight.is_cuda:
        with pytest.raises((TypeError, ValueError), match="seed"):
            cuda_ops.perturb_model_cuda_(model, build_parameter_schema(model), bad, 0.1)
        assert torch.equal(bits(model), before)


@pytest.mark.parametrize("seed", [True, 1.0, "1", -1])
def test_perturbation_validates_seed_even_when_schema_has_no_tensors(seed):
    model = torch.nn.Module()
    schema = build_parameter_schema(model)
    for fn in (perturb_model_, cuda_ops.perturb_model_cuda_):
        with pytest.raises((TypeError, ValueError), match="seed"):
            fn(model, schema, seed, 0.1)


@pytest.mark.parametrize("field", ["candidate_seed", "chunk_index"])
@pytest.mark.parametrize("bad", [True, 1.0, "1", -1])
def test_chunk_address_rejects_invalid_integer_identity(field, bad):
    values = dict(candidate_seed=1, schema_hash="a" * 64, parameter_index=0, chunk_index=0, chunk_elements=16)
    values[field] = bad
    with pytest.raises((TypeError, ValueError)):
        ChunkNoiseAddress(**values)


@pytest.mark.parametrize("seed", [np.int64(1), 2**53, 2**80])
def test_engine_address_keeps_unbounded_integer_seeds(seed):
    assert ChunkNoiseAddress(seed, "a" * 64, 0, 0, 16).candidate_seed == seed


@pytest.mark.parametrize(
    "seeds,coefficients,alpha",
    [
        ([True], [1.0], 0.1),
        ([1.0], [1.0], 0.1),
        ([-1], [1.0], 0.1),
        ([1, 1], [0.0, 0.0], 0.1),
        ([1, 2], [0.0], 0.1),
        ([1], [0.0], 1e39),
        ([1], [float("nan")], 0.1),
        ([1], [0.1], 0.1),
    ],
)
def test_update_validation_has_identical_errors_on_both_paths(monkeypatch, seeds, coefficients, alpha):
    monkeypatch.setattr(cuda_ops, "_check_cuda", lambda tensors: None)
    model = torch.nn.Linear(4, 4).half()
    schema = build_parameter_schema(model)
    errors = []
    for fn in (apply_coefficients_, cuda_ops.apply_coefficients_cuda_):
        with pytest.raises((TypeError, ValueError)) as caught:
            fn(model, schema, seeds, coefficients, alpha)
        errors.append((type(caught.value), str(caught.value)))
    assert errors[0] == errors[1]


@pytest.mark.parametrize("engine", [ENGINE_VERSION, ENGINE_V2])
def test_nonfinite_updated_weights_are_an_explicit_failure(model, engine):
    from heteroes.es.update import NonFiniteUpdateError

    schema = build_parameter_schema(model)
    with pytest.raises(NonFiniteUpdateError, match="finite"):
        apply_coefficients_(model, schema, [1], [1.0], 1e38, 16, engine=engine)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="requires CUDA")
def test_cuda_nonfinite_updated_weights_are_an_explicit_failure():
    from heteroes.es.update import NonFiniteUpdateError

    model = torch.nn.Linear(4, 4, bias=False).half().cuda()
    with pytest.raises(NonFiniteUpdateError, match="finite"):
        cuda_ops.apply_coefficients_cuda_(model, build_parameter_schema(model), [1], [1.0], 1e38)


def test_shared_noop_report_matches_both_paths(monkeypatch):
    monkeypatch.setattr(cuda_ops, "_check_cuda", lambda tensors: None)
    model = torch.nn.Linear(4, 4, bias=False).half()
    schema = build_parameter_schema(model)
    before = bits(model)
    reports = [
        fn(model, schema, [1, 2], [0.0, 0.0], 0.1) for fn in (apply_coefficients_, cuda_ops.apply_coefficients_cuda_)
    ]
    assert reports[0] == reports[1]
    assert reports[0].noop is True and reports[0].coefficients == (0.0, 0.0)
    assert reports[0].changed == 0 and reports[0].numel == 16
    assert reports[0].requested_l2 == reports[0].applied_l2 == 0.0
    assert torch.equal(bits(model), before)
