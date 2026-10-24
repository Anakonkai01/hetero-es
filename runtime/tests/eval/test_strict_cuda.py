"""Checks for the experimental NVRTC strict linear kernel (ADR-012).

CPU tests prove the blocked decomposition equals the reference tree, audit compiler text and check that guards run
before any CUDA access. CUDA tests run only with HETEROES_GPU_ACCEPTANCE=1 on a visible GPU; they compare bits with
the eager reference on the same device and on CPU. None of this qualifies a GPU model/OS for managed use.
"""

import math
import os
import struct

import pytest
import torch

from heteroes.eval import reference_ops as ops
from heteroes.eval import strict_cuda
from heteroes.eval.reference_ops import ReferenceArithmeticError


def bits(value):
    return value.contiguous().view(torch.int32)


def f32_bits(value):
    return struct.unpack("<i", struct.pack("<f", value))[0]


# ---------------------------------------------------------------------------------------------------------------
# CPU: the kernel's blocked decomposition is exactly the reference adjacent-pair tree.


@pytest.mark.parametrize("width", [1, 2, 3, 5, 7, 8, 16, 17, 31, 32, 33, 63, 64, 65, 255, 896, 1000, 1025, 4864])
def test_blocked_plan_matches_reference_pairwise_tree(width):
    generator = torch.Generator().manual_seed(width)
    rows = torch.randn(9, width, generator=generator) * torch.logspace(-3, 3, width)
    rows[0] = -0.0
    rows[1] = 0.0
    rows[2, ::2] = -0.0
    rows[3] = torch.where(torch.arange(width) % 3 == 0, torch.tensor(1e20), torch.tensor(-1e20))
    plan = strict_cuda.linear_plan(width)
    assert plan.padded >= width and plan.padded & (plan.padded - 1) == 0
    assert plan.per_thread * 32 * plan.padded_warps == max(plan.padded, 32)  # a warp always spans 32 lanes
    assert (plan.warps - 1) * 32 * plan.per_thread < width <= plan.warps * 32 * plan.per_thread
    assert torch.equal(bits(strict_cuda.emulate_blocked_sum(rows, plan)), bits(ops.pairwise_sum(rows)))


def test_negative_zero_padding_is_required_positive_zero_would_change_signs():
    # The premise of the padded tree: x + (-0) == x for every finite x, but x + (+0) turns -0 into +0.
    rows = torch.full((1, 3), -0.0)
    plan = strict_cuda.linear_plan(3)
    assert bits(strict_cuda.emulate_blocked_sum(rows, plan)).tolist() == [f32_bits(-0.0)]
    assert bits(ops.pairwise_sum(rows)).tolist() == [f32_bits(-0.0)]
    assert bits(ops.add(rows[0, :1], 0.0)).tolist() == [0]


def test_plans_for_qwen_dimensions_bound_threads_and_skip_all_padding_warps():
    hidden, intermediate = strict_cuda.linear_plan(896), strict_cuda.linear_plan(4864)
    assert (hidden.padded, hidden.per_thread, hidden.warps, hidden.padded_warps) == (1024, 32, 1, 1)
    assert (intermediate.padded, intermediate.per_thread, intermediate.warps) == (8192, 32, 5)
    assert intermediate.padded_warps == 8 and intermediate.outputs_per_block == 1
    with pytest.raises(ReferenceArithmeticError):
        strict_cuda.linear_plan(0)
    with pytest.raises(ReferenceArithmeticError):
        strict_cuda.linear_plan(strict_cuda.MAX_LINEAR_WIDTH + 1)


# ---------------------------------------------------------------------------------------------------------------
# CPU: compiler-output audits reject contraction, flush modes, unrounded or transcendental floating operations.

CLEAN_PTX = """
	cvt.f32.f16 	%f1, %rs1;
	mul.rn.f32 %f3, %f1, %f2;
	add.rn.f32 %f4, %f3, %f2;
	setp.eq.s32 	%p1, %r1, 0;
	add.s32 	%r2, %r1, 1;
	mov.b32 	%f5, %r3;
	shfl.sync.bfly.b32	%r4, %r5, 1, 31, -1;
	abs.f32 	%r41, %r40;
	setp.ne.f32 	%p19, %r41, 0f7F800000;
"""


def test_ptx_audit_accepts_explicitly_rounded_add_mul_and_integer_ops():
    assert strict_cuda.audit_ptx(CLEAN_PTX) == {"floatOps": {"add.rn.f32": 1, "mul.rn.f32": 1}, "violations": []}


@pytest.mark.parametrize(
    "line",
    [
        "fma.rn.f32 %f1, %f2, %f3, %f4;",
        "mad.f32 %f1, %f2, %f3, %f4;",
        "add.f32 %f1, %f2, %f3;",
        "mul.f32 %f1, %f2, %f3;",
        "add.rn.ftz.f32 %f1, %f2, %f3;",
        "mul.rz.f32 %f1, %f2, %f3;",
        "sub.rn.f32 %f1, %f2, %f3;",
        "ex2.approx.f32 %f1, %f2;",
        "rcp.rn.f32 %f1, %f2;",
        "sqrt.rn.f32 %f1, %f2;",
        "div.rn.f32 %f1, %f2, %f3;",
        "add.rn.f64 %fd1, %fd2, %fd3;",
        "cvt.rn.f16.f32 %rs1, %f1;",
        "fma.rn.f16x2 %r1, %r2, %r3, %r4;",
        "setp.lt.ftz.f32 %p1, %f1, %f2;",
    ],
)
def test_ptx_audit_rejects_unspecified_floating_arithmetic(line):
    assert strict_cuda.audit_ptx(CLEAN_PTX + "\t" + line + "\n")["violations"] == [line]


CLEAN_SASS = """
        /*0090*/                   FMUL R5, R2, R3 ;
        /*00a0*/                   FADD R7, R5, R6 ;
        /*00b0*/                   FADD R7, -RZ, R6 ;
        /*00c0*/                   HADD2.F32 R2, -RZ, R4.H0_H0 ;
        /*00d0*/                   LOP3.LUT R9, R7, 0x7f800000, RZ, 0xc0, !PT ;
        /*00e0*/                   SHFL.BFLY PT, R8, R7, 0x1, 0x1f ;
        /*00f0*/                   ISETP.NE.AND P0, PT, R9, RZ, PT ;
        /*0100*/                   HFMA2 R8, -RZ, RZ, -0.0 , 0 ;
        /*0110*/                   FSETP.NEU.AND P0, PT, |R5|, +INF , PT ;
"""


def test_sass_audit_accepts_plain_fadd_fmul_and_exact_conversions():
    assert strict_cuda.audit_sass(CLEAN_SASS) == {"floatOps": {"FADD": 2, "FMUL": 1}, "violations": []}


@pytest.mark.parametrize(
    "line",
    [
        "/*0100*/ FFMA R1, R2, R3, R4 ;",
        "/*0100*/ FFMA32I R1, R2, 0x3f800000, R4 ;",
        "/*0100*/ FADD.FTZ R1, R2, R3 ;",
        "/*0100*/ FMUL.FTZ R1, R2, R3 ;",
        "/*0100*/ FMUL.RZ R1, R2, R3 ;",
        "/*0100*/ FADD.SAT R1, R2, R3 ;",
        "/*0100*/ MUFU.RCP R1, R2 ;",
        "/*0100*/ DADD R2, R4, R6 ;",
        "/*0100*/ HFMA2 R1, R2, R3, R4 ;",
        "/*0100*/ FMNMX R1, R2, R3, !PT ;",
        "/*0100*/ HFMA2 R1, -RZ, R2, 0, 0 ;",
        "/*0100*/ FSETP.GT.FTZ.AND P0, PT, R1, R2, PT ;",
    ],
)
def test_sass_audit_rejects_contraction_flush_rounding_and_vendor_units(line):
    assert strict_cuda.audit_sass(CLEAN_SASS + line + "\n")["violations"] == [line.split("*/", 1)[1].strip()]


# ---------------------------------------------------------------------------------------------------------------
# CPU: guards run before any CUDA access.


def test_kernels_refuse_without_gpu_acceptance_before_touching_cuda(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("CUDA was touched before the acceptance guard")

    monkeypatch.delenv("HETEROES_GPU_ACCEPTANCE", raising=False)
    for name in ("init", "is_available", "current_device", "get_device_capability", "current_stream"):
        monkeypatch.setattr(torch.cuda, name, forbidden)
    with pytest.raises(ReferenceArithmeticError, match="HETEROES_GPU_ACCEPTANCE"):
        strict_cuda.StrictCudaKernels(torch.device("cuda", 0))
    monkeypatch.setenv("HETEROES_GPU_ACCEPTANCE", "1")
    with pytest.raises(ReferenceArithmeticError, match="CUDA device"):
        strict_cuda.StrictCudaKernels(torch.device("cpu"))


@pytest.mark.parametrize(
    "value,weight,bias",
    [
        (torch.ones(2, 3), torch.ones(4, 3), None),  # FP32 weight
        (torch.ones(2, 3), torch.ones(4, 5, dtype=torch.float16), None),  # width mismatch
        (torch.ones(2, 3), torch.ones(3, dtype=torch.float16), None),  # 1-D weight
        (torch.ones(0, 3), torch.ones(4, 3, dtype=torch.float16), None),  # empty input
        (torch.ones(2, 3), torch.ones(4, 3, dtype=torch.float16), torch.ones(3, dtype=torch.float16)),
        (torch.ones(2, 3), torch.ones(4, 3, dtype=torch.float16), torch.ones(4)),  # FP32 bias
        (torch.ones(2, 3), torch.ones(3, 4, dtype=torch.float16).t(), None),  # noncontiguous weight
        (torch.ones(2, 3, dtype=torch.int32), torch.ones(4, 3, dtype=torch.float16), None),
    ],
)
def test_linear_validation_rejects_unsupported_inputs_before_launch(value, weight, bias):
    with pytest.raises(ReferenceArithmeticError):
        strict_cuda.validate_linear(value, weight, bias, device=torch.device("cpu"))


def test_linear_validation_rejects_mixed_devices_and_wrong_kernel_device():
    weight = torch.ones(4, 3, dtype=torch.float16)
    with pytest.raises(ReferenceArithmeticError, match="device"):
        strict_cuda.validate_linear(torch.ones(2, 3), weight, None, device=torch.device("cuda", 0))
    assert strict_cuda.validate_linear(torch.ones(5, 2, 3), weight, None, device=torch.device("cpu")) == (10, 3, 4)


def test_identity_covers_source_options_and_kernel_version():
    identity = strict_cuda.static_identity()
    assert identity["kernel"] == strict_cuda.KERNEL_VERSION
    assert identity["operators"] == ops.REFERENCE_OPS_VERSION
    assert {"--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true"} <= set(identity["nvrtcOptions"])
    assert len(identity["sourceSha256"]) == 64 and identity["hardwareQualified"] is False


@pytest.mark.parametrize("tile", [0, -1, 3, 16, True, 4.0, "4"])
def test_linear_row_tile_rejected_before_compilation_or_launch(tile):
    kernels = object.__new__(strict_cuda.StrictCudaKernels)
    kernels.device = torch.device("cpu")
    with pytest.raises(ReferenceArithmeticError, match="row tile"):
        kernels.linear(torch.ones(3, 5), torch.ones(7, 5, dtype=torch.float16), row_tile=tile)


# ---------------------------------------------------------------------------------------------------------------
# CUDA: bit equality with the eager reference (same device and CPU). Opt-in only.

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(),
    reason="strict CUDA kernel checks need HETEROES_GPU_ACCEPTANCE=1 and a visible GPU",
)


@pytest.fixture(scope="module")
def kernels():
    return strict_cuda.StrictCudaKernels(torch.device("cuda", 0))


def _reference_both(x, w, b):
    expected = ops.linear(x, w, b)
    on_cpu = ops.linear(x.cpu(), w.cpu(), None if b is None else b.cpu())
    assert torch.equal(bits(expected.cpu()), bits(on_cpu))
    return expected


@gpu
@pytest.mark.parametrize("width", [1, 2, 3, 5, 8, 16, 17, 31, 32, 33, 63, 64, 65, 127, 129, 896, 1000, 1025, 4864])
@pytest.mark.parametrize("rows", [1, 3])
def test_cuda_linear_matches_reference_bits(kernels, width, rows):
    generator = torch.Generator().manual_seed(width * 7 + rows)
    outputs = 11 if width > 1000 else 37
    x = (torch.randn(rows, width, generator=generator) * 3).cuda()
    w = (torch.randn(outputs, width, generator=generator) * 0.05).half().cuda()
    b = (torch.randn(outputs, generator=generator) * 0.1).half().cuda()
    before = w.view(torch.int16).clone()
    for bias in (None, b):
        assert torch.equal(bits(kernels.linear(x, w, bias)), bits(_reference_both(x, w, bias)))
    assert torch.equal(w.view(torch.int16), before)


@gpu
@pytest.mark.parametrize("width", [3, 33, 896, 4864])
def test_cuda_row_tiles_match_oracle_with_partial_tiles_and_permutations(kernels, width):
    generator = torch.Generator().manual_seed(width)
    x = torch.randn(9, width, generator=generator).cuda()
    x[2] = -0.0
    x[5] *= 1e-38
    w = torch.randn(11, width, generator=generator).half().cuda()
    bias = torch.randn(11, generator=generator).half().cuda()
    # Multiple rows, an incomplete last tile, output tails and cancellation use independent trees.
    expected = _reference_both(x, w, bias)
    permutation = torch.tensor([8, 2, 7, 1, 5, 0, 4, 3, 6], device="cuda")
    for tile in (1, 2, 4, 8):
        assert torch.equal(bits(kernels.linear(x, w, bias, row_tile=tile)), bits(expected))
        permuted = kernels.linear(x[permutation], w, bias, row_tile=tile)
        assert torch.equal(bits(permuted), bits(expected[permutation]))
        assert torch.equal(bits(kernels.linear(x[:3], w, bias, row_tile=tile)), bits(expected[:3]))


@gpu
@pytest.mark.parametrize("tile", [2, 4, 8])
def test_cuda_row_tile_preserves_negative_zero_and_reports_fault_in_last_row(kernels, tile):
    x = torch.full((tile + 1, 4864), -0.0, device="cuda")
    w = torch.ones(3, 4864, dtype=torch.float16, device="cuda")
    assert bits(kernels.linear(x, w, row_tile=tile)).tolist() == [[f32_bits(-0.0)] * 3] * (tile + 1)
    x[-1, -1] = float("inf")
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        kernels.linear(x, w, row_tile=tile)


@gpu
def test_cuda_linear_cancellation_signed_zeros_and_subnormal_flush(kernels):
    tiny = 2.0**-70  # tiny * tiny-ish weights produce subnormal FP32 products that must flush to signed zero
    x = torch.tensor(
        [
            [1e20, 1.0, -1e20, 1.0, 3.0, -2.0, 0.5],
            [-0.0, -0.0, -0.0, -0.0, -0.0, -0.0, -0.0],
            [tiny, -tiny, tiny, -tiny, tiny, -tiny, tiny],
            [2.0**-126, -(2.0**-126), 1.5 * 2.0**-126, 0.0, -0.0, 1.0, -1.0],
            [65504.0, -65504.0, 65504.0, 1.0, -1.0, 0.25, -0.25],
        ]
    ).cuda()
    w = torch.tensor(
        [
            [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            [2.0**-24, -(2.0**-24), 2.0**-14, -(2.0**-20), 0.0, -0.0, 1.0],
            [-1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [-0.0, -0.0, -0.0, -0.0, -0.0, -0.0, -0.0],
        ],
        dtype=torch.float16,
    ).cuda()
    for bias in (None, torch.tensor([0.0, -0.0, 1.0, -0.0, 0.0], dtype=torch.float16).cuda()):
        actual = kernels.linear(x, w, bias)
        assert torch.equal(bits(actual), bits(_reference_both(x, w, bias)))
    assert bits(kernels.linear(x[1:2], w[4:5]))[0].tolist() == [0]  # (-0)*(-0) = +0 products
    assert bits(kernels.linear(x[1:2], w[0:1]))[0].tolist() == [f32_bits(-0.0)]


@gpu
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), 3e38])
def test_cuda_linear_nonfinite_input_or_overflow_fails(kernels, bad):
    x = torch.ones(2, 33).cuda()
    x[1, 7] = bad
    w = torch.full((3, 33), 2.0, dtype=torch.float16).cuda()
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        kernels.linear(x, w)
    with pytest.raises(ReferenceArithmeticError):
        ops.linear(x, w)


@gpu
def test_cuda_linear_nonfinite_weight_fails_and_deferred_flag_reports_once(kernels):
    x = torch.ones(1, 40).cuda()
    w = torch.ones(5, 40, dtype=torch.float16).cuda()
    w[3, 39] = float("inf")
    flag = kernels.new_error_flag()
    out = kernels.linear(x, w, error_flag=flag)  # deferred: no host sync inside the call
    assert out.shape == (1, 5)
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        kernels.raise_if_error(flag)


@gpu
def test_cuda_linear_is_invariant_to_batch_composition_streams_and_repeats(kernels):
    generator = torch.Generator().manual_seed(77)
    x = torch.randn(7, 3, 896, generator=generator).cuda()
    w = (torch.randn(129, 896, generator=generator) * 0.03).half().cuda()
    reference = kernels.linear(x, w)
    assert reference.shape == (7, 3, 129)
    separately = torch.stack([kernels.linear(row, w) for row in x])
    assert torch.equal(bits(separately), bits(reference))
    stream = torch.cuda.Stream()
    with torch.cuda.stream(stream):
        other = kernels.linear(x, w)
    stream.synchronize()
    assert torch.equal(bits(other), bits(reference))
    assert all(torch.equal(bits(kernels.linear(x, w)), bits(reference)) for _ in range(3))
    sample = ops.linear(x[0, :1], w[:17])
    assert torch.equal(bits(reference[0, :1, :17]), bits(sample))


@gpu
def test_cuda_linear_qwen_shapes_against_reference_columns(kernels):
    # Full real-sized matrices; the slow eager oracle checks a strided sample of output columns.
    generator = torch.Generator().manual_seed(4864)
    for width, outputs in ((896, 4864), (4864, 896), (896, 151936)):
        x = (torch.randn(2, width, generator=generator)).cuda()
        w = (torch.randn(outputs, width, generator=generator) * 0.02).half().cuda()
        actual = kernels.linear(x, w)
        columns = torch.arange(0, outputs, max(1, outputs // 23), device="cuda")
        expected = ops.linear(x, w[columns])
        assert torch.equal(bits(actual[:, columns]), bits(expected))


@gpu
def test_cuda_linear_allocates_only_its_output(kernels):
    x = torch.randn(4, 896).cuda()
    w = torch.randn(4864, 896).half().cuda()
    kernels.linear(x, w)  # compile/load outside the measurement
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    base = torch.cuda.memory_allocated()
    kernels.linear(x, w)
    torch.cuda.synchronize()
    extra = torch.cuda.max_memory_allocated() - base
    assert extra <= 4 * 4864 * 4 + 4096, "no FP32 weight copy or matrix-sized workspace"


@gpu
def test_cuda_build_identity_records_audited_binaries(kernels):
    x = torch.ones(1, 896).cuda()
    kernels.linear(x, torch.ones(3, 896, dtype=torch.float16).cuda())
    identity = kernels.identity()
    build = identity["builds"]["linear-896-nobias"]
    assert build["ptxAudit"]["violations"] == [] and build["ptxAudit"]["floatOps"]["mul.rn.f32"] >= 1
    assert len(build["cubinSha256"]) == 64 and identity["arch"].startswith("sm_")
    assert build["sassAudit"] == "unavailable" or build["sassAudit"]["violations"] == []
    assert math.isfinite(identity["nvrtcVersion"][0])


@gpu
def test_cuda_linear_flushes_subnormal_inputs_and_products_before_summing(kernels):
    subnormal = torch.tensor([1 << 13], dtype=torch.int32).view(torch.float32)  # 2^-136, a subnormal input
    x = torch.tensor(
        [
            [1.5 * 2.0**-126, 1.5 * 2.0**-126, 2.0**-126, 2.0**-126],  # products 1.5*2^-140 and 2^-127: subnormal
            [subnormal[0].item(), subnormal[0].item(), subnormal[0].item(), subnormal[0].item()],  # subnormal input
        ]
    ).cuda()
    w = torch.tensor([[2.0**-14, 2.0**-14, 0.5, 0.5], [8192.0, 8192.0, 8192.0, 8192.0]], dtype=torch.float16).cuda()
    actual = kernels.linear(x, w)
    assert torch.equal(bits(actual), bits(_reference_both(x, w, None)))
    assert bits(actual)[:, 0].tolist() == [0, 0] and bits(actual)[1, 1].item() == 0  # all flushed to +0


@gpu
@pytest.mark.parametrize("width", [2049, 4864])
def test_cuda_linear_missing_warps_are_negative_zero(kernels, width):
    plan = strict_cuda.linear_plan(width)
    assert plan.padded_warps > plan.warps
    x = torch.full((1, width), -0.0).cuda()
    w = torch.ones(2, width, dtype=torch.float16).cuda()
    actual = kernels.linear(x, w)
    assert bits(actual).tolist() == [[f32_bits(-0.0)] * 2]
    assert torch.equal(bits(actual), bits(_reference_both(x, w, None)))


# ---------------------------------------------------------------------------------------------------------------
# Fused-operation kernels: RMSNorm, residual add, SiLU gate, RoPE and attention/softmax.


@pytest.mark.parametrize("count", [1, 2, 3, 5, 6, 7, 64, 100, 255, 256, 257, 4096, 4097])
def test_running_tree_with_final_fold_equals_reference_tree(count):
    # Kernels reduce runtime-length rows with a binary-counter stack, then fold pending nodes from the lowest
    # set bit of the count upward. That is the padded tree without padding work.
    generator = torch.Generator().manual_seed(count)
    values = torch.randn(3, count, generator=generator) * torch.logspace(-4, 4, count)
    values[1] = -0.0
    assert torch.equal(bits(strict_cuda.emulate_running_sum(values)), bits(ops.pairwise_sum(values)))


def test_scalar_constants_are_the_reference_float32_roundings():
    constants = strict_cuda.reference_constants()
    assert constants["LOG2E"] == f32_bits(1.4426950408889634)
    assert constants["EXP_C0"] == f32_bits(1.0 / 40320.0) and constants["EXP_C7"] == f32_bits(1.0)
    assert constants["LN2_LO"] == f32_bits(0.000001428606765330187)
    assert constants["DOMAIN_LOW"] == f32_bits(1e-30) and constants["DOMAIN_HIGH"] == f32_bits(1e30)


def _cuda_ops_cases():
    generator = torch.Generator().manual_seed(9)
    wide = torch.randn(5, 896, generator=generator) * 4
    wide[1] = 0.0
    wide[2, ::3] = -0.0
    wide[3] *= 1e-20
    edge = torch.tensor([0.0, -0.0, 1e-38, -1e-38, 80.0, -80.0, -81.0, -200.0, 1e-7, -1e-7, 30.0, -30.0, 88.0])
    return wide, edge


@gpu
def test_cuda_rms_norm_matches_reference_bits(kernels):
    wide, _ = _cuda_ops_cases()
    weight = (torch.randn(896) * 0.3).half()
    for rows, w in ((wide, weight), (wide[:, :16], weight[:16]), (wide[:, :5], weight[:5])):
        flag = kernels.new_error_flag()
        actual = kernels.rms_norm(rows.cuda(), w.cuda(), 1e-6, error_flag=flag)
        kernels.raise_if_error(flag)
        expected = ops.rms_norm(rows.cuda(), w.cuda(), 1e-6)
        assert torch.equal(bits(actual), bits(expected))
        assert torch.equal(bits(expected.cpu()), bits(ops.rms_norm(rows, w, 1e-6)))


@gpu
def test_cuda_add_and_silu_gate_match_reference_bits(kernels):
    wide, edge = _cuda_ops_cases()
    gate = torch.cat((wide.flatten(), edge[edge.abs() <= 80], torch.linspace(-90, 79, 1001)))
    up = torch.randn(gate.shape, generator=torch.Generator().manual_seed(3)) * 2
    flag = kernels.new_error_flag()
    actual = kernels.silu_mul(gate.cuda(), up.cuda(), error_flag=flag)
    summed = kernels.add(gate.cuda(), up.cuda(), error_flag=flag)
    kernels.raise_if_error(flag)
    expected = ops.mul(ops.silu(gate.cuda()), up.cuda())
    assert torch.equal(bits(actual), bits(expected))
    assert torch.equal(bits(expected.cpu()), bits(ops.mul(ops.silu(gate), up)))
    assert torch.equal(bits(summed), bits(ops.add(gate.cuda(), up.cuda())))


@gpu
def test_cuda_rope_matches_reference_rotation_and_layout(kernels):
    generator = torch.Generator().manual_seed(5)
    length, heads, dim = 7, 3, 8
    x = torch.randn(length, heads * dim, generator=generator).cuda()
    angles = ops.mul(torch.arange(3, 3 + length, dtype=torch.float32)[:, None], torch.rand(dim // 2) * 0.9 + 0.01)
    sine, cosine = ops.sin_cos(angles)
    sine, cosine = (torch.cat((p, p), dim=-1).cuda() for p in (sine, cosine))
    flag = kernels.new_error_flag()
    actual = kernels.rope(x, cosine, sine, heads, error_flag=flag)
    kernels.raise_if_error(flag)
    value = x.reshape(1, length, heads, dim).transpose(1, 2)
    rotated = torch.cat((-value[..., dim // 2 :], value[..., : dim // 2]), dim=-1)
    expected = ops.add(ops.mul(value, cosine[None, None]), ops.mul(rotated, sine[None, None]))[0]
    assert actual.shape == (heads, length, dim) and actual.is_contiguous()
    assert torch.equal(bits(actual), bits(expected))


def _reference_attention(q, k, v, past, repeats, scale):
    # Same sequence as Qwen2Reference._attention (written out here as an independent oracle).
    key = k.repeat_interleave(repeats, dim=0)
    value = v.repeat_interleave(repeats, dim=0)
    scores = ops.mul(ops.pairwise_sum(ops.mul(q[:, :, None, :], key[:, None, :, :])), scale)
    positions = torch.arange(past, past + q.shape[1], device=q.device)
    causal = torch.arange(key.shape[1], device=q.device)[None, None, :] <= positions[None, :, None]
    probabilities = ops.softmax(scores, causal)
    out = ops.pairwise_sum(ops.mul(probabilities[:, :, None, :], value.transpose(-1, -2)[:, None, :, :]))
    return out.transpose(0, 1).reshape(q.shape[1], -1)


@gpu
@pytest.mark.parametrize(
    "length,past,dim", [(1, 0, 64), (1, 37, 64), (5, 0, 64), (3, 129, 64), (6, 2, 4), (1, 255, 64)]
)
def test_cuda_attention_matches_reference_bits(kernels, length, past, dim):
    generator = torch.Generator().manual_seed(length * 1000 + past)
    heads, kv_heads = 14 if dim == 64 else 4, 2
    q = (torch.randn(heads, length, dim, generator=generator) * 2).cuda()
    k = (torch.randn(kv_heads, past + length, dim, generator=generator) * 2).cuda()
    v = torch.randn(kv_heads, past + length, dim, generator=generator).cuda()
    scale = 1 / math.sqrt(dim)
    flag = kernels.new_error_flag()
    actual = kernels.attention(q, k, v, past, heads // kv_heads, scale, error_flag=flag)
    kernels.raise_if_error(flag)
    expected = _reference_attention(q, k, v, past, heads // kv_heads, scale)
    assert actual.shape == (length, heads * dim)
    assert torch.equal(bits(actual), bits(expected))
    assert torch.equal(
        bits(expected.cpu()), bits(_reference_attention(q.cpu(), k.cpu(), v.cpu(), past, heads // 2, scale))
    )


@gpu
def test_cuda_attention_extreme_scores_and_masked_signed_zero_products(kernels):
    q = torch.tensor([[[30.0, -30.0, 0.5, 1.0]]]).repeat(2, 3, 1).cuda()
    k = torch.tensor([[[30.0, -30.0, 0.0, 0.0], [-30.0, 30.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0], [1.0, 1, 1, 1]]]).cuda()
    v = torch.tensor([[[-1.0, 2.0, -0.0, 0.0], [3.0, -4.0, -5.0, 0.0], [-0.0, -0.0, -0.0, -0.0], [-7.0, 8, -9, 1]]])
    actual = kernels.attention(q, k, v.cuda(), 1, 2, 0.5)
    assert torch.equal(bits(actual), bits(_reference_attention(q, k, v.cuda(), 1, 2, 0.5)))


@gpu
@pytest.mark.parametrize("operation", ["rms_overflow", "silu_overflow", "add_overflow", "attention_inf", "rms_nan"])
def test_cuda_fused_operations_flag_nonfinite_and_domain_failures(kernels, operation):
    flag = kernels.new_error_flag()
    big = torch.full((2, 16), 3e38).cuda()
    if operation == "rms_overflow":
        kernels.rms_norm(big, torch.ones(16, dtype=torch.float16).cuda(), 1e-6, error_flag=flag)
    elif operation == "rms_nan":
        kernels.rms_norm(big * float("nan"), torch.ones(16, dtype=torch.float16).cuda(), 1e-6, error_flag=flag)
    elif operation == "silu_overflow":
        kernels.silu_mul(big.flatten(), big.flatten(), error_flag=flag)
    elif operation == "add_overflow":
        kernels.add(big.flatten(), big.flatten(), error_flag=flag)
    else:
        q = torch.full((2, 1, 4), 3e30).cuda()
        k = torch.full((1, 3, 4), 3e30).cuda()  # masked-in and masked-out scores overflow alike
        kernels.attention(q, k, torch.ones(1, 3, 4).cuda(), 2, 2, 0.5, error_flag=flag)
    with pytest.raises(ReferenceArithmeticError):
        kernels.raise_if_error(flag)


@gpu
def test_cuda_fused_operations_validate_shapes_before_launch(kernels):
    with pytest.raises(ReferenceArithmeticError):
        kernels.rms_norm(torch.ones(2, 16).cuda(), torch.ones(15, dtype=torch.float16).cuda(), 1e-6)
    with pytest.raises(ReferenceArithmeticError):
        kernels.add(torch.ones(4).cuda(), torch.ones(5).cuda())
    with pytest.raises(ReferenceArithmeticError):
        kernels.attention(torch.ones(3, 1, 4).cuda(), torch.ones(2, 1, 4).cuda(), torch.ones(2, 1, 4).cuda(), 0, 2, 0.5)
    with pytest.raises(ReferenceArithmeticError):
        too_long = strict_cuda.MAX_ATTENTION_KEYS + 1
        kernels.attention(
            torch.ones(2, 1, 4).cuda(),
            torch.ones(1, too_long, 4).cuda(),
            torch.ones(1, too_long, 4).cuda(),
            too_long - 1,
            2,
            0.5,
        )


@gpu
def test_cuda_rms_norm_out_of_domain_mean_square_fails(kernels):
    flag = kernels.new_error_flag()
    kernels.rms_norm(
        torch.full((1, 16), 1e16).cuda(), torch.ones(16, dtype=torch.float16).cuda(), 1e-6, error_flag=flag
    )
    with pytest.raises(ReferenceArithmeticError, match="domain"):
        kernels.raise_if_error(flag)
    with pytest.raises(ReferenceArithmeticError):
        ops.rms_norm(torch.full((1, 16), 1e16), torch.ones(16, dtype=torch.float16), 1e-6)


@gpu
def test_cuda_fused_operations_flush_subnormal_inputs(kernels):
    tiny = torch.tensor([1 << 10], dtype=torch.int32).view(torch.float32).item()  # a subnormal FP32 input
    gate, up = torch.tensor([1e30, 2.0, -3.0]), torch.tensor([tiny, tiny, -tiny])
    assert torch.equal(bits(kernels.silu_mul(gate.cuda(), up.cuda())), bits(ops.mul(ops.silu(gate), up).cuda()))
    rows = torch.full((2, 16), tiny)
    weight = torch.ones(16, dtype=torch.float16)
    actual = kernels.rms_norm(rows.cuda(), weight.cuda(), 1e-6)
    assert torch.equal(bits(actual), bits(ops.rms_norm(rows, weight, 1e-6).cuda()))
    q = torch.full((2, 1, 4), tiny)
    k = torch.full((1, 2, 4), 1e30)
    v = torch.tensor([[[1.0, 2.0, 3.0, 4.0], [tiny, tiny, -tiny, 5.0]]])
    expected = _reference_attention(q, k, v, 1, 2, 0.5)
    assert torch.equal(bits(kernels.attention(q.cuda(), k.cuda(), v.cuda(), 1, 2, 0.5)), bits(expected.cuda()))


@gpu
@pytest.mark.parametrize("dim", [8, 6])
def test_cuda_attention_with_inexact_scale(kernels, dim):
    generator = torch.Generator().manual_seed(dim)
    q = torch.randn(4, 3, dim, generator=generator).cuda()
    k = torch.randn(2, 5, dim, generator=generator).cuda()
    v = torch.randn(2, 5, dim, generator=generator).cuda()
    scale = 1 / math.sqrt(dim)
    assert torch.equal(bits(kernels.attention(q, k, v, 2, 2, scale)), bits(_reference_attention(q, k, v, 2, 2, scale)))
