"""Prefill gate packing has the original strict SiLU, integer rounding, flags and live weights."""

import os
from types import SimpleNamespace

import pytest
import torch

from heteroes.eval import integer_reference as reference
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.eval.reference_ops import ReferenceArithmeticError

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
@pytest.mark.parametrize("rows,width", [(1, 17), (33, 64), (2, 12289)])
def test_prefill_gate_uses_fused_planes_when_eligible_and_preserves_results(magnitude_bits, rows, width, monkeypatch):
    from heteroes.eval.integer_cuda import IntegerCudaKernels
    from heteroes.eval import reference_ops

    g = torch.Generator().manual_seed(322)
    gate = torch.randn(rows, width, generator=g)
    up = torch.randn(rows, width, generator=g)
    weight = (torch.randn(3, width, generator=g) * 0.03).half()
    bias = torch.tensor([0.0, -0.01, 0.02], dtype=torch.float16)
    decoder = object.__new__(IntegerDecoderGraph)
    decoder.kernels = IntegerCudaKernels("cuda", magnitude_bits=magnitude_bits)
    calls, original = [], decoder.kernels.silu_mul_quantized

    def spy(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(decoder.kernels, "silu_mul_quantized", spy)
    module = SimpleNamespace(weight=weight.cuda(), bias=bias.cuda())
    for factor in (1, -4, 0):
        weight.mul_(factor)
        module.weight.copy_(weight)
        gated = reference_ops.mul(reference_ops.silu(gate), up)
        expected = reference.linear(gated, weight, bias, magnitude_bits=magnitude_bits)
        flag = decoder.kernels.new_error_flag()
        actual = decoder._prefill_gated_project(gate.cuda(), up.cuda(), module, flag)
        assert int(flag.item()) == 0
        assert torch.equal(actual.cpu().view(torch.int32), expected.view(torch.int32))
    assert len(calls) == (3 if rows > 1 and width <= 12288 else 0)


@gpu
def test_prefill_gate_fusion_preserves_nonfinite_flag():
    from heteroes.eval.integer_cuda import IntegerCudaKernels

    decoder = object.__new__(IntegerDecoderGraph)
    decoder.kernels = IntegerCudaKernels("cuda", magnitude_bits=22)
    gate = torch.zeros((2, 16), device="cuda")
    gate[1, 3] = float("nan")
    up = torch.ones_like(gate)
    module = SimpleNamespace(weight=torch.ones((5, 16), dtype=torch.float16, device="cuda"), bias=None)
    flag = decoder.kernels.new_error_flag()
    decoder._prefill_gated_project(gate, up, module, flag)
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        decoder.kernels.raise_if_error(flag)
