"""Shared activation quantization must be call-local and equal independent projections on live weights."""

import os

import pytest
import torch

from heteroes.strict import integer_reference as reference
from heteroes.strict.integer_cuda import IntegerCudaKernels
from heteroes.strict.reference_ops import ReferenceArithmeticError

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_group_quantizes_once_matches_independent_oracles_and_never_caches_input_contents(monkeypatch, magnitude_bits):
    gen = torch.Generator().manual_seed(728)
    x = torch.randn(2, 67, 3, generator=gen).transpose(1, 2).cuda()
    weights = [torch.randn(n, 67, generator=gen).half().cuda() for n in (17, 11, 29)]
    biases = [None, torch.randn(11, generator=gen).half().cuda(), torch.randn(29, generator=gen).half().cuda()]
    kernels = IntegerCudaKernels("cuda", magnitude_bits=magnitude_bits)
    quantize = kernels.quantize_input
    calls = []

    def counted(*args, **kwargs):
        calls.append(True)
        return quantize(*args, **kwargs)

    monkeypatch.setattr(kernels, "quantize_input", counted)
    previous = None
    for iteration in range(3):
        if iteration:
            x.add_(0.25)
            weights[1].mul_(-16)
        outputs = kernels.linear_many(x, weights, biases)
        assert len(outputs) == 3 and len(calls) == iteration + 1
        for out, weight, bias in zip(outputs, weights, biases):
            expected = reference.linear(
                x.cpu(), weight.cpu(), None if bias is None else bias.cpu(), magnitude_bits=magnitude_bits
            )
            assert torch.equal(out.cpu().contiguous().view(torch.int32), expected.contiguous().view(torch.int32))
        if previous is not None:
            assert not torch.equal(previous, outputs[1])
        previous = outputs[1].clone()


@gpu
def test_group_validates_every_component_before_quantization_or_gpu_workspace(monkeypatch):
    kernels = IntegerCudaKernels("cuda")
    x = torch.ones((3, 33), device="cuda")
    weight = torch.ones((5, 33), device="cuda", dtype=torch.float16)
    monkeypatch.setattr(
        kernels, "quantize_input", lambda *args, **kwargs: pytest.fail("validate every component first")
    )
    bad = [
        ([], None),
        ([weight, weight], [None]),
        ([weight, weight[:, :32]], None),
        ([weight, weight.float()], None),
        ([weight], [torch.ones(4, device="cuda", dtype=torch.float16)]),
    ]
    for weights, biases in bad:
        with pytest.raises(ReferenceArithmeticError):
            kernels.linear_many(x, weights, biases)


@gpu
def test_group_preserves_deferred_nonfinite_errors_from_any_component():
    kernels = IntegerCudaKernels("cuda", magnitude_bits=22)
    x = torch.ones((2, 33), device="cuda")
    weight = torch.ones((5, 33), device="cuda", dtype=torch.float16)
    bad = weight.clone()
    bad[-1, -1] = float("nan")
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        kernels.linear_many(x, (weight, bad))
    flag = kernels.new_error_flag()
    result = kernels.linear_many(x, (bad, weight), error_flag=flag)
    assert len(result) == 2
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        kernels.raise_if_error(flag)


@gpu
@pytest.mark.parametrize("family", ["qwen2", "llama", "llama-wide", "mistral"])
def test_shared_graph_uses_one_quantization_per_projection_fanout_and_matches_cpu(monkeypatch, family):
    import copy

    from heteroes.strict.integer_decoder import IntegerDecoderGraph, IntegerDecoderReference
    from test_strict_decoder import model_for, bits

    cpu = model_for(family)
    backend = IntegerDecoderGraph(copy.deepcopy(cpu).cuda(), max_context=32, allow_fixture=True)
    oracle = IntegerDecoderReference(cpu, max_context=32, allow_fixture=True)
    rows = [torch.tensor([ids], device="cuda") for ids in ([3, 5, 7], [11, 13])]
    calls = []

    def counted(original):
        def wrapper(*args, **kwargs):
            calls.append(True)
            return original(*args, **kwargs)

        return wrapper

    # A quantization is either quantize_input or RMSNorm fused with it (the norms feeding QKV and gate/up).
    monkeypatch.setattr(backend.kernels, "quantize_input", counted(backend.kernels.quantize_input))
    monkeypatch.setattr(backend.kernels, "rms_norm_quantized", counted(backend.kernels.rms_norm_quantized))
    actual, _ = backend.forward_batch(rows)
    expected = torch.cat([oracle.forward_tokens(row.cpu())[0] for row in rows])
    assert torch.equal(bits(actual.cpu()), bits(expected))
    # Attention QKV share one input; MLP gate/up share another. Output/down/head stay independent.
    assert len(calls) == 4 * cpu.config.num_hidden_layers + 1
