"""Independent numerical and batching oracles for the experimental one-model reference.

These CPU checks specify operations; they do not qualify a GPU or establish production throughput.
"""

import math
import struct

import pytest
import torch

from heteroes.eval import reference_ops as ops


def f32(value):
    rounded = struct.unpack("<f", struct.pack("<f", value))[0]
    return math.copysign(0.0, rounded) if abs(rounded) < 2**-126 else rounded


def scalar_tree(values):
    values = [f32(v) for v in values]
    while len(values) > 1:
        values = [f32(values[i] + values[i + 1]) for i in range(0, len(values) - 1, 2)] + (
            [values[-1]] if len(values) % 2 else []
        )
    return values[0]


def bits(value):
    return value.contiguous().view(torch.int32)


def test_pairwise_tree_has_fixed_order_and_preserves_an_odd_tail():
    value = torch.tensor([[1e20, 1.0, -1e20, 1.0, 3.0], [1e20, -1e20, 2.0, 4.0, 5.0]])
    expected = torch.tensor([scalar_tree(row) for row in value.tolist()])
    assert torch.equal(bits(ops.pairwise_sum(value)), bits(expected))
    assert expected.tolist() == [3.0, 11.0]


def test_subnormal_inputs_and_outputs_flush_to_signed_zero():
    tiny = torch.tensor([1, -2147483647], dtype=torch.int32).view(torch.float32)
    assert bits(ops.add(tiny, torch.zeros(2))).tolist() == [0, 0]
    assert bits(ops.mul(tiny, torch.ones(2))).tolist() == [0, -2147483648]
    normal = torch.tensor([2**-126, -(2**-126)])
    assert bits(ops.mul(normal, 0.5)).tolist() == [0, -2147483648]


def test_linear_agrees_with_scalar_rounding_oracle_without_materializing_fp32_weights():
    x = torch.tensor([[1e20, 1.0, -1e20, 1.0, 3.0], [1.5, -2.0, 0.25, 3.5, -4.0]])
    w = torch.tensor([[1, 1, 1, 1, 1], [-0.5, 0.25, 2, -1.5, 0.75], [0.1, -0.2, 0.3, 0.4, 0.5]], dtype=torch.float16)
    bias = torch.tensor([0.5, -0.25, 1.0], dtype=torch.float16)
    before = w.view(torch.int16).clone()
    expected = torch.tensor(
        [
            [
                f32(scalar_tree([f32(a * b) for a, b in zip(row, weight)]) + b)
                for weight, b in zip(w.tolist(), bias.tolist())
            ]
            for row in x.tolist()
        ]
    )

    actual = ops.linear(x, w, bias, row_tile=1, output_tile=2)

    assert torch.equal(bits(actual), bits(expected))
    assert w.dtype == torch.float16 and torch.equal(w.view(torch.int16), before)


def test_linear_is_bitwise_invariant_to_batch_composition_and_execution_tiles():
    generator = torch.Generator().manual_seed(2410)
    x = torch.randn(7, 3, 17, generator=generator)
    w = torch.randn(13, 17, generator=generator).half()
    reference = ops.linear(x, w, row_tile=2, output_tile=3)
    for rows, outputs in ((1, 1), (4, 7), (32, 32)):
        assert torch.equal(bits(ops.linear(x, w, row_tile=rows, output_tile=outputs)), bits(reference))
    separately = torch.cat([ops.linear(row, w).unsqueeze(0) for row in x], dim=0)
    assert torch.equal(bits(separately), bits(reference))


def test_linear_never_widens_more_than_one_bounded_weight_tile():
    from torch.utils._python_dispatch import TorchDispatchMode

    class TileLimit(TorchDispatchMode):
        def __torch_dispatch__(self, func, types, args=(), kwargs=None):
            if func._schema.name in ("aten::to", "aten::_to_copy") and args[0].dtype == torch.float16:
                assert args[0].numel() <= 3 * 21, "A full FP32 weight copy exceeds the configured tile"
            return func(*args, **(kwargs or {}))

    x = torch.ones(2, 21)
    weight = torch.ones(17, 21, dtype=torch.float16)
    with TileLimit():
        actual = ops.linear(x, weight, row_tile=1, output_tile=3)
    assert torch.equal(actual, torch.full((2, 17), 21.0))


def test_reciprocal_rsqrt_exp_and_silu_are_close_to_high_precision_math():
    positive = torch.logspace(-6, 6, 113)
    assert torch.allclose(ops.reciprocal(positive).double(), 1 / positive.double(), rtol=3e-7, atol=0)
    assert torch.allclose(ops.rsqrt(positive).double(), positive.double().rsqrt(), rtol=3e-7, atol=0)
    value = torch.linspace(-80, 80, 257)
    assert torch.allclose(ops.exp(value).double(), value.double().exp(), rtol=4e-6, atol=0)
    expected = value.double() * value.double().sigmoid()
    assert torch.allclose(ops.silu(value).double(), expected, rtol=4e-6, atol=1e-7)


def test_sin_cos_range_reduction_remains_accurate_at_long_positions():
    value = torch.cat((torch.linspace(-32768, 32768, 401), torch.tensor([0.0, math.pi / 2, -math.pi, 2 * math.pi])))
    sine, cosine = ops.sin_cos(value)
    assert torch.allclose(sine.double(), value.double().sin(), rtol=0, atol=4e-6)
    assert torch.allclose(cosine.double(), value.double().cos(), rtol=0, atol=4e-6)


def test_rmsnorm_uses_the_specified_reference_and_keeps_storage_fp16():
    x = torch.tensor([[1.0, -2.0, 3.0, -4.0, 0.125], [0.0, 0.0, 0.0, 0.0, 0.0]])
    weight = torch.tensor([0.5, 0.25, 1.5, -0.75, 1.0], dtype=torch.float16)
    expected = x.double() * (x.double().square().mean(-1, keepdim=True) + 1e-6).rsqrt() * weight.double()
    actual = ops.rms_norm(x, weight, 1e-6)
    assert torch.allclose(actual.double(), expected, rtol=2e-6, atol=1e-7)
    assert weight.dtype == torch.float16


def test_masked_softmax_handles_empty_rows_and_batch_changes():
    scores = torch.tensor([[0.0, 1.0, -1.0, 1e30], [3.0, 4.0, 5.0, 6.0], [-80.0, 0.0, 80.0, 10.0]])
    mask = torch.tensor([[True, True, True, False], [False, False, False, False], [True, True, True, True]])
    actual = ops.softmax(scores, mask)
    expected = torch.softmax(scores[0, :3].double(), dim=-1)
    assert torch.allclose(actual[0, :3].double(), expected, rtol=2e-6, atol=1e-8)
    assert actual[0, 3] == 0 and torch.equal(actual[1], torch.zeros(4))
    separate = torch.cat([ops.softmax(row[None], allowed[None]) for row, allowed in zip(scores, mask)])
    assert torch.equal(bits(actual), bits(separate))
    assert torch.isfinite(actual).all()


def test_no_vendor_gemm_or_transcendental_is_called(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("vendor arithmetic is not the reference contract")

    for name in ("mm", "matmul", "bmm", "exp", "rsqrt", "sin", "cos", "sum"):
        monkeypatch.setattr(torch, name, forbidden)
    x = torch.tensor([[1.0, -0.5, 2.0]])
    w = torch.tensor([[0.1, 0.2, 0.3]], dtype=torch.float16)
    assert torch.isfinite(ops.linear(x, w)).all()
    assert torch.isfinite(ops.exp(x)).all()
    assert torch.isfinite(ops.rsqrt(x.abs() + 1)).all()
    assert all(torch.isfinite(value).all() for value in ops.sin_cos(x))
    assert torch.isfinite(ops.silu(x)).all()
    assert torch.isfinite(ops.softmax(x, torch.ones_like(x, dtype=torch.bool))).all()


@pytest.mark.parametrize("bad", (float("nan"), float("inf"), -float("inf")))
def test_nonfinite_arithmetic_is_a_failure_not_a_silent_output(bad):
    with pytest.raises(ops.ReferenceArithmeticError):
        ops.mul(torch.tensor([bad]), 1.0)


@pytest.mark.parametrize("name,bad", [("reciprocal", 0.0), ("rsqrt", -1.0), ("exp", 81.0), ("sin_cos", 32769.0)])
def test_unsupported_numerical_domains_fail_explicitly(name, bad):
    with pytest.raises(ops.ReferenceArithmeticError):
        getattr(ops, name)(torch.tensor([bad]))
