"""Integer MMA must implement the NEW row-scaled contract, with no float GEMM or hidden weight copy."""

import os

import pytest
import torch

from heteroes.eval import integer_reference as reference
from heteroes.eval import strict_cuda as sc
from heteroes.eval.reference_ops import ReferenceArithmeticError


def cuda_class():
    from heteroes.eval.integer_cuda import IntegerCudaKernels

    return IntegerCudaKernels


def test_integer_constructor_guards_before_cuda(monkeypatch):
    monkeypatch.delenv("HETEROES_GPU_ACCEPTANCE", raising=False)
    with pytest.raises(ReferenceArithmeticError, match="HETEROES_GPU_ACCEPTANCE"):
        cuda_class()("cuda")
    with pytest.raises(ReferenceArithmeticError, match="magnitude"):
        cuda_class()("cuda", magnitude_bits=True)


def test_integer_audit_requires_exact_signed_mma_and_refuses_float_multiply():
    clean = "mma.sync.aligned.m16n8k32.row.col.s32.s8.s8.s32 {d0,d1,d2,d3}, {a0,a1,a2,a3}, {b0,b1}, {c0,c1,c2,c3};"
    assert sc.audit_integer_ptx(clean)["violations"] == []
    assert sc.audit_integer_ptx(clean)["integerMmaOps"] == 1
    assert sc.audit_integer_ptx("add.rn.f32 f0,f1,f2;")["violations"]
    assert sc.audit_integer_ptx(clean + "\nmul.rn.f32 f0,f1,f2;")["violations"]
    assert sc.audit_integer_ptx(clean.replace(".s8.s8.s32", ".u8.u8.s32"))["violations"]


def test_integer_conversion_audit_only_admits_the_proved_nearest_even_mode():
    mma = "mma.sync.aligned.m16n8k32.row.col.s32.s8.s8.s32 {d0,d1,d2,d3}, {a0,a1,a2,a3}, {b0,b1}, {c0,c1,c2,c3};"
    assert not sc.audit_integer_ptx(mma + "\ncvt.rni.s32.f32 r0,f0;")["violations"]
    for rounding in ("rzi", "rmi", "rpi"):
        assert sc.audit_integer_ptx(mma + f"\ncvt.{rounding}.s32.f32 r0,f0;")["violations"]
    assert sc.audit_integer_ptx(mma + "\ncvt.rni.f32.f32 f0,f1;")["violations"]
    assert not sc.audit_integer_sass("IMMA.16832.S8.S8 R0,R1,R2,R3;\nF2I.NTZ R0,R1;")["violations"]
    assert sc.audit_integer_sass("IMMA.16832.S8.S8 R0,R1,R2,R3;\nF2I.FLOOR.NTZ R0,R1;")["violations"]


gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_every_admitted_finite_fp16_value_and_weight_row_exponent_quantizes_exactly(magnitude_bits):
    """All ~1M finite value/exponent pairs, not just random matmul outputs after cancellation."""
    from heteroes.eval.integer_cuda import _SOURCE

    context = torch.empty(1, device="cuda")
    kernels = cuda_class()("cuda", magnitude_bits=magnitude_bits)
    stub = r"""
extern "C" __global__ void probe_quant(int* out) {
  int i=blockIdx.x*256+threadIdx.x;
  if(i>=40*65536)return;
  int exponent=i/65536-24; u16 u=(u16)i; unsigned a=u&0x7fffu, e=a>>10;
  int actual=!a ? -1000 : e ? (int)e-15 : 31-__clz(a)-24;
  out[i]=(a>=0x7c00u || actual>exponent) ? (-2147483647-1) : quant_half(u,exponent);
}
"""
    defines = {
        "WIDTH": 32,
        "MAGNITUDE_BITS": magnitude_bits,
        "DIGITS": 2 if magnitude_bits == 14 else 3,
        "HAS_BIAS": 0,
        "M_GROUPS": 1,
        "WARPS": 4,
        "SPLIT_K": 1,
    }
    header = "".join(f"#define {key} {value}\n" for key, value in defines.items())
    fn = kernels._compile("exhaust-half-quant", header + _SOURCE + stub, ["probe_quant"], integer_mma=True)[
        "probe_quant"
    ]
    output = torch.empty((40, 65536), dtype=torch.int32, device="cuda")
    kernels._launch(fn, grid=output.numel() // 256, block=(256, 1), pointers=(output,), integers=())
    actual = output.cpu()
    patterns = torch.arange(65536, dtype=torch.int32)
    values = patterns.to(torch.int16).view(torch.float16).double()
    floor_exponents = torch.tensor(
        [
            -1000
            if not (u & 0x7FFF)
            else ((u & 0x7FFF) >> 10) - 15
            if (u & 0x7FFF) >> 10
            else (u & 1023).bit_length() - 1 - 24
            for u in range(65536)
        ]
    )
    finite = (patterns & 0x7FFF) < 0x7C00
    admitted = 0
    for row, exponent in enumerate(range(-24, 16)):
        valid = finite & (floor_exponents <= exponent)
        admitted += int(valid.sum())
        # FP16 has 11 significand bits; multiplying by this power of two is exact in binary64.
        # Its entire admitted magnitude range lies within [2^-26, 2^22], so no double rounding occurs.
        expected = torch.full((65536,), -(2**31), dtype=torch.int32)
        expected[valid] = torch.round(values[valid] * 2.0 ** (magnitude_bits - 1 - exponent)).to(torch.int32)
        assert bool((expected[valid].abs() <= 2**magnitude_bits).all())
        assert torch.equal(actual[row], expected), (magnitude_bits, exponent)
    assert admitted == 1017852


@gpu
def test_precision_namespaces_even_an_uncompiled_device_identity():
    low = cuda_class()("cuda", magnitude_bits=14).identity()
    high = cuda_class()("cuda", magnitude_bits=22).identity()
    assert low["fingerprint"] != high["fingerprint"]


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_cuda_input_quantization_matches_rationally_checked_cpu_reference(magnitude_bits):
    gen = torch.Generator().manual_seed(411)
    x = torch.randn(5, 69, generator=gen) * torch.logspace(-37, 37, 69)
    x[1] = -0.0
    x[2, :4] = torch.tensor([1, 0x007FFFFF, 0x00800000, 0x00800001], dtype=torch.int32).view(torch.float32)
    q, ex = reference.quantize_rows(x, magnitude_bits=magnitude_bits)
    kernels = cuda_class()("cuda", magnitude_bits=magnitude_bits)
    actual, exponent = kernels.quantize_input(x.cuda())
    assert torch.equal(actual.cpu().to(torch.int32), q)
    assert torch.equal(exponent.cpu(), ex)


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
@pytest.mark.parametrize("width", [1, 3, 31, 32, 33, 67, 129, 768, 1024, 2048, 4096, 32768])
def test_cuda_mma_matches_cpu_for_odd_shapes_tails_scales_and_execution_tiles(magnitude_bits, width):
    gen = torch.Generator().manual_seed(width)
    x = torch.randn(19, width, generator=gen)
    x[1] = -0.0
    x[2] *= 1e-38
    w = (torch.randn(11, width, generator=gen) * 0.03).half()
    b = (torch.randn(11, generator=gen) * 0.1).half()
    expected = reference.linear(x, w, b, magnitude_bits=magnitude_bits)
    kernels = cuda_class()("cuda", magnitude_bits=magnitude_bits)
    for tile, warps in ((16, 4), (32, 4), (32, 8)):
        actual = kernels.linear(x.cuda(), w.cuda(), b.cuda(), row_tile=tile, warps=warps)
        assert torch.equal(actual.cpu().view(torch.int32), expected.view(torch.int32)), (magnitude_bits, width, tile)


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_linear_permutation_batch_one_and_live_weight_updates_cannot_reuse_stale_exponents(magnitude_bits):
    gen = torch.Generator().manual_seed(881)
    x = torch.randn(5, 65, generator=gen)
    x[0, -1] = 16.0
    w = (torch.randn(9, 65, generator=gen) * 0.01).half()
    kernels = cuda_class()("cuda", magnitude_bits=magnitude_bits)
    gx, gw = x.cuda(), w.cuda()
    snapshot = gw.clone()
    for factor in (1.0, 1024.0, 1.0):
        gw.copy_(snapshot * factor)
        expected = reference.linear(x, (w * factor).half(), magnitude_bits=magnitude_bits)
        actual = kernels.linear(gx, gw)
        separate = torch.cat([kernels.linear(row[None], gw) for row in gx])
        assert torch.equal(actual.cpu().view(torch.int32), expected.view(torch.int32))
        assert torch.equal(actual.view(torch.int32), separate.view(torch.int32))
        assert torch.equal(kernels.linear(gx[[4, 1]], gw).view(torch.int32), actual[[4, 1]].view(torch.int32))
    assert torch.equal(gw.view(torch.int16), snapshot.view(torch.int16))


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_contiguous_but_unaligned_weight_storage_keeps_scalar_load_fallback(magnitude_bits):
    gen = torch.Generator().manual_seed(187)
    x = torch.randn(17, 64, generator=gen)
    base = (torch.randn(7 * 64 + 1, generator=gen) * 0.03).half()
    w = base[1:].reshape(7, 64)
    device_base = base.cuda()
    device_weight = device_base[1:].reshape(7, 64)
    assert device_weight.is_contiguous() and device_weight.data_ptr() % 8 != 0
    expected = reference.linear(x, w, magnitude_bits=magnitude_bits)
    actual = cuda_class()("cuda", magnitude_bits=magnitude_bits).linear(x.cuda(), device_weight)
    assert torch.equal(actual.cpu().view(torch.int32), expected.view(torch.int32))


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_integer_split_k_is_exact_for_global_row_scales_cancellation_and_partial_last_chunks(magnitude_bits):
    gen = torch.Generator().manual_seed(192)
    x = torch.randn(19, 263, generator=gen)
    x[0, -1] = 65504.0
    x[1] = -0.0
    w = (torch.randn(37, 263, generator=gen) * 0.02).half()
    w[0, -1] = 1024.0
    w[1] = -w[0]
    expected = reference.linear(x, w, magnitude_bits=magnitude_bits)
    kernels = cuda_class()("cuda", magnitude_bits=magnitude_bits)
    for split in (1, 2, 4, 8):
        actual = kernels.linear(x.cuda(), w.cuda(), split_k=split)
        assert torch.equal(actual.cpu().view(torch.int32), expected.view(torch.int32))


@gpu
def test_split_workspace_is_bounded_before_quantization(monkeypatch):
    kernels = cuda_class()("cuda", max_partial_bytes=1)
    monkeypatch.setattr(kernels, "quantize_input", lambda *a, **kw: pytest.fail("workspace guard must run first"))
    with pytest.raises(ReferenceArithmeticError, match="workspace"):
        kernels.linear(
            torch.ones((3, 33), device="cuda"), torch.ones((5, 33), dtype=torch.float16, device="cuda"), split_k=2
        )


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_simt_and_mma_implement_the_same_integer_contract_including_split_reductions(magnitude_bits):
    gen = torch.Generator().manual_seed(991)
    x = torch.randn(3, 257, generator=gen)
    x[0] = -0.0
    w = (torch.randn(9, 257, generator=gen) * 0.02).half()
    expected = reference.linear(x, w, magnitude_bits=magnitude_bits)
    kernels = cuda_class()("cuda", magnitude_bits=magnitude_bits)
    for mode in ("simt", "mma"):
        for split in (1, 4):
            actual = kernels.linear(x.cuda(), w.cuda(), implementation=mode, split_k=split)
            assert torch.equal(actual.cpu().view(torch.int32), expected.view(torch.int32))


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_integer_zero_smallest_normal_rounding_and_overflow(magnitude_bits):
    kernels = cuda_class()("cuda", magnitude_bits=magnitude_bits)
    x = torch.tensor([[-0.0], [2.0**-126], [-(2.0**-126)], [2.0**-100]])
    w = torch.tensor([[1.0], [1.0 - 2.0**-11], [2.0**-24]], dtype=torch.float16)
    expected = reference.linear(x, w, magnitude_bits=magnitude_bits)
    actual = kernels.linear(x.cuda(), w.cuda())
    assert torch.equal(actual.cpu().view(torch.int32), expected.view(torch.int32))
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        kernels.linear(
            torch.full((1, 33), 2.0**125, device="cuda"),
            torch.full((2, 33), 65504.0, dtype=torch.float16, device="cuda"),
        )


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_actual_projection_rounds_up_to_min_normal_and_handles_overflow_halfway(magnitude_bits):
    kernels = cuda_class()("cuda", magnitude_bits=magnitude_bits)
    # Exact scaled integer dot: (16383*1138 - 2049*911)*2^-150 = (2^24-1)*2^-150.
    # It rounds UP to min-normal; flushing an exact tiny result before RNE would incorrectly return zero.
    x = torch.tensor(
        [[v * 2.0**-137 for v in row] for row in ([16383, 2049, 0], [-16383, -2049, 0], [16382, 2049, 0])],
        dtype=torch.float32,
    )
    w = torch.tensor([[1138 / 8192, -911 / 8192, 1.0]], dtype=torch.float16)
    for mode in ("simt", "mma"):
        actual = kernels.linear(x.cuda(), w.cuda(), implementation=mode)
        assert actual.cpu().view(torch.int32).flatten().tolist() == [0x00800000, -2139095040, 0]
    # The neighbor is max-finite; adding one integer unit lands exactly on the overflow RNE midpoint.
    large = torch.tensor([[16383, 2049, 0, 0]], dtype=torch.float32) * 2.0**101
    weight = torch.tensor([[9104.0, -7288.0, 65504.0, 4.0]], dtype=torch.float16)
    for mode in ("simt", "mma"):
        actual = kernels.linear(large.cuda(), weight.cuda(), implementation=mode)
        assert actual.cpu().view(torch.int32).item() == 0x7F7FFFFF
        overflowing = large.clone()
        overflowing[0, -1] = 2.0**101
        with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
            kernels.linear(overflowing.cuda(), weight.cuda(), implementation=mode)


@gpu
def test_nonfinite_quantized_inputs_weights_and_bias_always_fail_including_deferred_capture():
    kernels = cuda_class()("cuda")
    x = torch.ones(3, 33, device="cuda")
    w = torch.ones(5, 33, dtype=torch.float16, device="cuda")
    for which in ("input", "weight", "bias"):
        xx, ww = x.clone(), w.clone()
        bias = torch.zeros(5, dtype=torch.float16, device="cuda")
        {"input": xx, "weight": ww, "bias": bias}[which].view(-1)[-1] = float("nan")
        flag = kernels.new_error_flag()
        kernels.linear(xx, ww, bias, error_flag=flag)
        with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
            kernels.raise_if_error(flag)


@gpu
def test_workspace_is_activation_sized_not_a_second_weight_matrix_and_build_is_integer_mma():
    kernels = cuda_class()("cuda")
    x = torch.ones(3, 1024, device="cuda")
    w = torch.ones(4096, 1024, dtype=torch.float16, device="cuda")
    kernels.linear(x, w)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    base = torch.cuda.memory_allocated()
    kernels.linear(x, w)
    torch.cuda.synchronize()
    extra = torch.cuda.max_memory_allocated() - base
    assert extra <= 3 * 4096 * 4 + 3 * 1024 * 4 + 4096 * 4 + 8192
    builds = kernels.identity()["builds"]
    assert builds and all(b["ptxAudit"]["integerMmaOps"] > 0 for b in builds.values())
    assert all(not b["ptxAudit"]["violations"] for b in builds.values())
