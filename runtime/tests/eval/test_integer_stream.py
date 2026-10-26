"""The streamed MMA schedule must reproduce the row-scaled integer contract bit for bit, flags included."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest
import torch

from heteroes.eval import integer_reference as reference
from heteroes.eval import strict_cuda as sc
from heteroes.eval.reference_ops import ReferenceArithmeticError


def cuda_class():
    from heteroes.eval.integer_cuda import IntegerCudaKernels

    return IntegerCudaKernels


def test_schedule_is_validated_before_cuda_and_named_in_the_static_identity(monkeypatch):
    from heteroes.eval import integer_cuda

    monkeypatch.delenv("HETEROES_GPU_ACCEPTANCE", raising=False)
    with pytest.raises(ReferenceArithmeticError, match="schedule"):
        cuda_class()("cuda", mma_schedule="vendor")
    with pytest.raises(ReferenceArithmeticError, match="schedule"):
        integer_cuda.static_identity(22, mma_schedule="fast")
    tile = integer_cuda.static_identity(22, mma_schedule="tile")
    stream = integer_cuda.static_identity(22, mma_schedule="stream")
    assert tile["mmaSchedule"] == "tile" and stream["mmaSchedule"] == "stream"
    assert integer_cuda.static_identity(22)["mmaSchedule"] == "auto"


gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


def bits(value):
    return value.contiguous().view(torch.int32)


def entries_used(kernels, monkeypatch):
    """Record which compiled entry each launch used, by function handle."""
    names, original = [], kernels._launch

    def spy(function, **kwargs):
        for build in kernels._functions.values():
            if isinstance(build, dict):
                names.extend(name for name, handle in build.items() if handle is function)
        return original(function, **kwargs)

    monkeypatch.setattr(kernels, "_launch", spy)
    return names


def case(seed, rows, width, outputs, *, bias=True, scale=0.03):
    gen = torch.Generator().manual_seed(seed)
    x = torch.randn(rows, width, generator=gen) * torch.exp(torch.randn(rows, 1, generator=gen) * 4)
    x[0, : min(width, 5)] = torch.tensor([0.0, -0.0, 2.0**-127, -(2.0**-130), 1.0])[: min(width, 5)]
    w = (torch.randn(outputs, width, generator=gen) * scale).half()
    w[0, 0] = 65504.0
    w[-1, -1] = 2.0**-24
    w[min(1, outputs - 1), : min(width, 3)] = -0.0
    b = (torch.randn(outputs, generator=gen) * 0.1).half() if bias else None
    return x, w, b


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
@pytest.mark.parametrize(
    "rows,width,outputs",
    [(2, 16, 1), (9, 48, 7), (16, 64, 64), (17, 80, 65), (32, 1040, 130), (33, 960, 64), (70, 128, 9)],
)
def test_streamed_tiles_match_cpu_oracle_and_tile_kernel_for_every_split(
    magnitude_bits, rows, width, outputs, monkeypatch
):
    x, w, b = case(rows * 1000 + width, rows, width, outputs)
    expected = reference.linear(x, w, b, magnitude_bits=magnitude_bits)
    stream = cuda_class()("cuda", magnitude_bits=magnitude_bits, max_partial_bytes=1 << 30)
    tile = cuda_class()("cuda", magnitude_bits=magnitude_bits, max_partial_bytes=1 << 30, mma_schedule="tile")
    used = entries_used(stream, monkeypatch)
    gx, gw, gb = x.cuda(), w.cuda(), b.cuda()
    for row_tile in (16, 32):
        for split in (1, 2, 4, 8):  # 16-wide K has one stage: splits 2..8 include empty K partitions
            flags = [stream.new_error_flag(), tile.new_error_flag()]
            actual = stream.linear(
                gx, gw, gb, error_flag=flags[0], row_tile=row_tile, split_k=split, implementation="mma"
            )
            control = tile.linear(
                gx, gw, gb, error_flag=flags[1], row_tile=row_tile, split_k=split, implementation="mma"
            )
            assert int(flags[0].item()) == int(flags[1].item()) == 0
            assert torch.equal(bits(actual.cpu()), bits(expected)), (row_tile, split)
            assert torch.equal(bits(actual), bits(control)), (row_tile, split)
    assert "integer_stream" in used and "integer_linear" not in used


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_ineligible_width_or_alignment_keeps_the_tile_kernel_exact(magnitude_bits, monkeypatch):
    kernels = cuda_class()("cuda", magnitude_bits=magnitude_bits)
    used = entries_used(kernels, monkeypatch)
    x, w, b = case(5, 9, 72, 11)  # 72 % 16 != 0
    actual = kernels.linear(x.cuda(), w.cuda(), b.cuda(), implementation="mma")
    assert torch.equal(bits(actual.cpu()), bits(reference.linear(x, w, b, magnitude_bits=magnitude_bits)))
    assert used == ["integer_input", "integer_weights", "integer_linear"]
    used.clear()
    x, w, _ = case(6, 9, 64, 11, bias=False)
    backing = torch.empty(w.numel() + 4, dtype=torch.float16, device="cuda")
    offset = backing[4:].view(11, 64)  # 8-byte but not 16-byte aligned rows
    offset.copy_(w)
    assert offset.data_ptr() % 16 == 8
    actual = kernels.linear(x.cuda(), offset, implementation="mma")
    assert torch.equal(bits(actual.cpu()), bits(reference.linear(x, w, magnitude_bits=magnitude_bits)))
    assert "integer_linear" in used and "integer_stream" not in used


@gpu
def test_streamed_decode_plans_match_tile_on_trained_like_shapes_and_record_effective_schedule():
    stream = cuda_class()("cuda", magnitude_bits=22)
    tile = cuda_class()("cuda", magnitude_bits=22, mma_schedule="tile")
    assert stream.identity()["mmaScheduleEffective"] == "stream"
    assert tile.identity()["mmaScheduleEffective"] == "tile"
    assert stream.identity()["fingerprint"] != tile.identity()["fingerprint"]
    gen = torch.Generator(device="cuda").manual_seed(17)
    for width, outputs in ((896, 1152), (896, 4864), (4864, 896), (2048, 256)):
        w = (torch.randn(outputs, width, device="cuda", generator=gen) * 0.02).half()
        for rows in (2, 8, 17, 32, 40):
            x = torch.randn(rows, width, device="cuda", generator=gen) * 3
            flags = [stream.new_error_flag(), tile.new_error_flag()]
            actual = stream.linear_decode(x, w, error_flag=flags[0])
            control = tile.linear_decode(x, w, error_flag=flags[1])
            assert int(flags[0].item()) == int(flags[1].item()) == 0
            assert torch.equal(bits(actual), bits(control)), (width, outputs, rows)


@gpu
def test_streamed_overflow_and_nonfinite_weights_flag_like_the_tile_kernel():
    stream = cuda_class()("cuda", magnitude_bits=22)
    tile = cuda_class()("cuda", magnitude_bits=22, mma_schedule="tile")
    x = torch.full((3, 64), 2.0**120, device="cuda")  # 64 * 2^120 * 65504 overflows FP32
    w = torch.full((5, 64), 65504.0, dtype=torch.float16, device="cuda")
    for split in (1, 4):
        flags = [stream.new_error_flag(), tile.new_error_flag()]
        actual = stream.linear(x, w, error_flag=flags[0], split_k=split, implementation="mma")
        control = tile.linear(x, w, error_flag=flags[1], split_k=split, implementation="mma")
        assert int(flags[0].item()) == int(flags[1].item()) == 1
        assert torch.equal(bits(actual), bits(control))
    # In-request Inf/NaN written after the exponent refresh: both schedules quantize those weights to zero.
    gen = torch.Generator(device="cuda").manual_seed(3)
    x = torch.randn(4, 64, device="cuda", generator=gen)
    w = (torch.randn(7, 64, device="cuda", generator=gen) * 0.1).half()
    outputs = []
    for kernels in (stream, tile):
        weight = w.clone()
        kernels._begin_request((weight,))
        try:
            weight[1, 3], weight[2, 60], weight[5, 0] = float("inf"), float("-inf"), float("nan")
            flag = kernels.new_error_flag()
            outputs.append(kernels.linear(x, weight, error_flag=flag, implementation="mma"))
            assert int(flag.item()) == 0
        finally:
            kernels._end_request()
    assert torch.equal(bits(outputs[0]), bits(outputs[1]))


@gpu
def test_fast_digit_conversion_matches_quant_half_for_every_half_and_admitted_row_exponent():
    """All 65536 half patterns x 40 exponents: admitted values, signed zeros and Inf/NaN (which quantize to zero)."""
    from heteroes.eval.integer_cuda import _SOURCE

    context = torch.empty(1, device="cuda")
    kernels = cuda_class()("cuda", magnitude_bits=22)
    stub = r"""
extern "C" __global__ void probe_digits(unsigned* out) {
  int i=blockIdx.x*256+threadIdx.x;
  if(i>=40*16384)return;
  int exponent=i/16384-24, base=(i%16384)*4;
  unsigned h01=(unsigned)base|((unsigned)(base+1)<<16), h23=(unsigned)(base+2)|((unsigned)(base+3)<<16);
  unsigned fast[3], slow[3]={0,0,0}, admitted=1;
  convert4(fast,h01,h23,(unsigned)((MAGNITUDE_BITS-1-exponent)*0x800000));
  for(int e=0;e<4;++e) {
    u16 u=(u16)(base+e); unsigned a=u&0x7fffu, x=a>>10;
    int actual=!a ? -1000 : x ? (int)x-15 : 31-__clz(a)-24;
    if(a<0x7c00u && actual>exponent) admitted=0; // never stored in a row with this exponent
    pack_digits(slow,quant_half(u,exponent),e);
  }
  for(int d=0;d<3;++d) out[(size_t)i*7+d]=fast[d], out[(size_t)i*7+3+d]=slow[d];
  out[(size_t)i*7+6]=admitted;
}
"""
    defines = {"WIDTH": 32, "MAGNITUDE_BITS": 22, "DIGITS": 3, "HAS_BIAS": 0, "M_GROUPS": 1, "WARPS": 4}
    defines.update({"SPLIT_K": 1, "FAST_CONVERT": 1})
    header = "".join(f"#define {key} {value}\n" for key, value in defines.items())
    fn = kernels._compile("exhaust-fast-digits", header + _SOURCE + stub, ["probe_digits"], integer_mma=True)
    output = torch.empty((40 * 16384, 7), dtype=torch.int32, device="cuda")
    kernels._launch(fn["probe_digits"], grid=40 * 16384 // 256, block=(256, 1), pointers=(output,), integers=())
    result = output.cpu()
    admitted = result[:, 6] == 1
    patterns = torch.arange(65536)
    magnitude = patterns & 0x7FFF
    field = magnitude >> 10
    subnormal = torch.floor(torch.log2(magnitude.clamp(min=1).double())).long() - 24
    floor_exponent = torch.where(magnitude == 0, -1000, torch.where(field > 0, field - 15, subnormal))
    floor_exponent = torch.where(magnitude >= 0x7C00, -1000, floor_exponent).view(16384, 4)  # Inf/NaN: always stored
    expected = torch.cat([(floor_exponent <= e).all(dim=1) for e in range(-24, 16)])
    assert torch.equal(admitted, expected) and int(admitted.sum()) > 250000
    assert torch.equal(result[admitted, :3], result[admitted, 3:6])
    del context


@gpu
def test_stream_shared_buffers_are_sixteen_byte_aligned_for_cp_async(monkeypatch):
    audited = []
    original = sc.audit_integer_ptx

    def inspect(ptx):
        if "cp.async.cg.shared.global" in ptx:
            for name in ("weights_shared", "inputs_shared"):
                alignment = re.search(rf"\.shared\s+\.align\s+(\d+)\s+\.b8\s+\S*{name}", ptx)
                assert alignment and int(alignment[1]) >= 16, name
            audited.append(True)
        return original(ptx)

    monkeypatch.setattr(sc, "audit_integer_ptx", inspect)
    context = torch.empty(1, device="cuda")
    cuda_class()("cuda", magnitude_bits=22)._integer_functions(64, row_tile=32, packed_input=True)
    assert audited
    del context


@gpu
@pytest.mark.parametrize("arch", ["sm_80", "sm_86", "sm_89", "sm_90", "sm_120"])
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_integer_source_passes_the_instruction_audit_on_other_architectures(arch, magnitude_bits):
    # Code generation differs by target (sm_86 once turned a runtime-stride loop into MUFU.RCP division).
    from heteroes.eval.integer_cuda import _SOURCE

    context = torch.empty(1, device="cuda")
    owner = cuda_class()("cuda", magnitude_bits=magnitude_bits)
    if not owner._nvdisasm:
        pytest.skip("nvdisasm unavailable")
    for width, tile, split in ((896, 32, 1), (4864, 32, 8), (896, 16, 4), (80, 16, 2)):
        defines = {
            "WIDTH": width,
            "MAGNITUDE_BITS": magnitude_bits,
            "DIGITS": 2 if magnitude_bits == 14 else 3,
            "HAS_BIAS": 1,
            "M_GROUPS": tile // 16,
            "WARPS": 4,
            "SPLIT_K": split,
            "PACKED_INPUT": 1,
            "WEIGHT_READ32": 0,
            "WEIGHT_PREFETCH": 1,
            "FAST_CONVERT": int(magnitude_bits == 22),
        }
        source = "".join(f"#define {k} {v}\n" for k, v in defines.items()) + _SOURCE
        nvrtc = owner._nvrtc
        program = sc._check(nvrtc.nvrtcCreateProgram(source.encode(), b"integer.cu", 0, [], []))
        try:
            options = [f"--gpu-architecture={arch}".encode(), *(o.encode() for o in sc.NVRTC_OPTIONS)]
            assert int(nvrtc.nvrtcCompileProgram(program, len(options), options)[0]) == 0
            ptx = b" " * sc._check(nvrtc.nvrtcGetPTXSize(program))
            sc._check(nvrtc.nvrtcGetPTX(program, ptx))
            cubin = b" " * sc._check(nvrtc.nvrtcGetCUBINSize(program))
            sc._check(nvrtc.nvrtcGetCUBIN(program, cubin))
        finally:
            nvrtc.nvrtcDestroyProgram(program)
        assert sc.audit_integer_ptx(ptx.rstrip(b"\0").decode())["violations"] == []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integer.cubin"
            path.write_bytes(cubin)
            text = subprocess.run([owner._nvdisasm, str(path)], capture_output=True, text=True, check=True).stdout
        assert "integer_stream" in text
        assert sc.audit_integer_sass(text)["violations"] == []
    del context


@gpu
@pytest.mark.parametrize("arch", ["sm_75", "sm_80", "sm_86", "sm_89", "sm_90", "sm_120"])
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_fused_quantization_source_passes_the_ops_instruction_audit_on_other_architectures(arch, magnitude_bits):
    # The fused RMSNorm/SiLU module is built from the ops source, so it must pass the ops audit on every target.
    from heteroes.eval.integer_cuda import _FUSED_SOURCE, RMS_THREADS, SILU_THREADS

    context = torch.empty(1, device="cuda")
    owner = cuda_class()("cuda", magnitude_bits=magnitude_bits)
    if not owner._nvdisasm:
        pytest.skip("nvdisasm unavailable")
    header = "".join(f"#define {k} 0x{v:08x}u\n" for k, v in sc.reference_constants().items())
    header += f"#define MAGNITUDE_BITS {magnitude_bits}\n#define DIGITS {2 if magnitude_bits == 14 else 3}\n"
    header += f"#define RMS_THREADS {RMS_THREADS}\n#define SILU_THREADS {SILU_THREADS}\n"
    nvrtc = owner._nvrtc
    program = sc._check(
        nvrtc.nvrtcCreateProgram((header + sc._OPS_SOURCE + _FUSED_SOURCE).encode(), b"fused.cu", 0, [], [])
    )
    try:
        options = [f"--gpu-architecture={arch}".encode(), *(o.encode() for o in sc.NVRTC_OPTIONS)]
        assert int(nvrtc.nvrtcCompileProgram(program, len(options), options)[0]) == 0
        ptx = b" " * sc._check(nvrtc.nvrtcGetPTXSize(program))
        sc._check(nvrtc.nvrtcGetPTX(program, ptx))
        cubin = b" " * sc._check(nvrtc.nvrtcGetCUBINSize(program))
        sc._check(nvrtc.nvrtcGetCUBIN(program, cubin))
    finally:
        nvrtc.nvrtcDestroyProgram(program)
    assert sc.audit_ptx(ptx.rstrip(b"\0").decode(), sc.OPS_PTX_EXACT)["violations"] == []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "fused.cubin"
        path.write_bytes(cubin)
        text = subprocess.run([owner._nvdisasm, str(path)], capture_output=True, text=True, check=True).stdout
    assert "strict_rms_quant" in text and "strict_silu_quant" in text
    assert sc.audit_sass(text, sc.OPS_SASS_EXACT)["violations"] == []
    del context


@gpu
@pytest.mark.parametrize("counts", [(896, 128, 128), (64, 1, 65), (130, 7), (4864, 4864)])
@pytest.mark.parametrize("bias", [False, True])
def test_grouped_decode_launch_matches_separate_tile_projections(counts, bias, monkeypatch):
    stream = cuda_class()("cuda", magnitude_bits=22)
    tile = cuda_class()("cuda", magnitude_bits=22, mma_schedule="tile")
    used = entries_used(stream, monkeypatch)
    gen = torch.Generator(device="cuda").manual_seed(sum(counts))
    width = 96 if max(counts) < 4864 else 896
    weights = [(torch.randn(n, width, device="cuda", generator=gen) * 0.03).half() for n in counts]
    weights[0][0, 0] = 65504.0
    biases = [(torch.randn(n, device="cuda", generator=gen) * 0.1).half() for n in counts] if bias else None
    for rows in (2, 9, 17, 32, 40):
        x = torch.randn(rows, width, device="cuda", generator=gen) * torch.exp(torch.randn(rows, 1, device="cuda") * 3)
        flags = [stream.new_error_flag(), tile.new_error_flag()]
        actual = stream.linear_many(x, weights, biases, error_flag=flags[0], decode_target_ctas_per_sm=8)
        control = [
            tile.linear_decode(x, w, None if biases is None else b, error_flag=flags[1])
            for w, b in zip(weights, biases or [None] * len(weights))
        ]
        assert int(flags[0].item()) == int(flags[1].item()) == 0
        assert all(torch.equal(bits(a), bits(c)) for a, c in zip(actual, control)), rows
    assert "integer_stream_group" in used and "integer_stream" not in used


# A CTA target high enough that every split-K test shape selects split-K on any GPU size (28..170 SMs).
SPLIT_TARGET = 32


@gpu
@pytest.mark.parametrize("width,counts", [(896, (896, 128, 128)), (512, (256, 64, 192)), (896, (4864, 4864))])
@pytest.mark.parametrize("bias", [False, True])
def test_grouped_split_k_launch_matches_separate_tile_projections_and_flags(width, counts, bias, monkeypatch):
    # Decode-sized widths select split-K, so every matrix of the group goes through the shared partial matrix
    # and integer_finish_group (column offsets of the second and third matrix included).
    stream = cuda_class()("cuda", magnitude_bits=22)
    tile = cuda_class()("cuda", magnitude_bits=22, mma_schedule="tile")
    used = entries_used(stream, monkeypatch)
    gen = torch.Generator(device="cuda").manual_seed(width + sum(counts))
    weights = [(torch.randn(n, width, device="cuda", generator=gen) * 0.03).half() for n in counts]
    biases = [(torch.randn(n, device="cuda", generator=gen) * 0.1).half() for n in counts] if bias else None
    for rows in (2, 9, 32):
        assert stream._decode_plan(width, rows, sum(counts), SPLIT_TARGET).split_k > 1
        x = torch.randn(rows, width, device="cuda", generator=gen) * torch.exp(torch.randn(rows, 1, device="cuda") * 3)
        flags = [stream.new_error_flag(), tile.new_error_flag()]
        actual = stream.linear_many(x, weights, biases, error_flag=flags[0], decode_target_ctas_per_sm=SPLIT_TARGET)
        control = [
            tile.linear_decode(x, w, None if biases is None else b, error_flag=flags[1])
            for w, b in zip(weights, biases or [None] * len(weights))
        ]
        assert int(flags[0].item()) == int(flags[1].item()) == 0
        assert all(torch.equal(bits(a), bits(c)) for a, c in zip(actual, control)), rows
    assert "integer_stream_group" in used and "integer_finish_group" in used
    # A nonfinite bias (added after encoding, so only the finish check sees it) and an encoding overflow.
    if bias:
        biases[-1][3] = float("inf")
        x = torch.randn(4, width, device="cuda", generator=gen)
    else:
        x = torch.full((4, width), 2.0**120, device="cuda")
        weights[-1][3] = 65504.0
    flags = [stream.new_error_flag(), tile.new_error_flag()]
    actual = stream.linear_many(x, weights, biases, error_flag=flags[0], decode_target_ctas_per_sm=SPLIT_TARGET)
    control = [
        tile.linear_decode(x, w, None if biases is None else b, error_flag=flags[1])
        for w, b in zip(weights, biases or [None] * len(weights))
    ]
    assert int(flags[0].item()) == int(flags[1].item()) == 1
    assert all(torch.equal(bits(a), bits(c)) for a, c in zip(actual, control))


@gpu
def test_grouped_launch_falls_back_for_mixed_bias_single_rows_and_flags_overflow_like_separate_calls(monkeypatch):
    stream = cuda_class()("cuda", magnitude_bits=22)
    tile = cuda_class()("cuda", magnitude_bits=22, mma_schedule="tile")
    used = entries_used(stream, monkeypatch)
    gen = torch.Generator(device="cuda").manual_seed(8)
    weights = [(torch.randn(n, 64, device="cuda", generator=gen) * 0.03).half() for n in (70, 9)]
    biases = [(torch.randn(70, device="cuda", generator=gen) * 0.1).half(), None]
    x = torch.randn(5, 64, device="cuda", generator=gen)
    stream.linear_many(x, weights, biases, decode_target_ctas_per_sm=8)
    assert "integer_stream" in used and "integer_stream_group" not in used
    used.clear()
    stream.linear_many(x[:1], weights, decode_target_ctas_per_sm=8)
    assert "integer_simt" in used and "integer_stream_group" not in used
    used.clear()
    huge = torch.full((4, 64), 2.0**120, device="cuda")
    weights[1][3] = 65504.0
    flags = [stream.new_error_flag(), tile.new_error_flag()]
    actual = stream.linear_many(huge, weights, error_flag=flags[0], decode_target_ctas_per_sm=8)
    control = [tile.linear_decode(huge, w, error_flag=flags[1]) for w in weights]
    assert int(flags[0].item()) == int(flags[1].item()) == 1
    assert all(torch.equal(bits(a), bits(c)) for a, c in zip(actual, control))
    assert "integer_stream_group" in used


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
@pytest.mark.parametrize("width", [1, 3, 64, 255, 300, 896, 960, 2048, 4096, 4864, 8192])
def test_fused_rmsnorm_and_silu_planes_equal_quantizing_the_unfused_rows(magnitude_bits, width):
    kernels = cuda_class()("cuda", magnitude_bits=magnitude_bits)
    gen = torch.Generator(device="cuda").manual_seed(width)
    for rows in (2, 17, 40):
        x = torch.randn(rows, width, device="cuda", generator=gen) * torch.exp(torch.randn(rows, 1, device="cuda") * 6)
        x[0] = 0.0  # zero row: RMSNorm of zeros and exponent 0
        x[1, : min(width, 3)] = torch.tensor([1e-40, -0.0, 3e38], device="cuda")[: min(width, 3)]
        weight = (torch.randn(width, device="cuda", generator=gen) * 0.5).half()
        gate = torch.randn(rows, width, device="cuda", generator=gen) * 8
        up = torch.randn(rows, width, device="cuda", generator=gen) * torch.exp(torch.randn(rows, 1, device="cuda") * 4)
        up[1, : min(width, 2)] = torch.tensor([1e-39, -0.0], device="cuda")[: min(width, 2)]
        for fused, unfused in (
            (
                lambda f: kernels.rms_norm_quantized(x, weight, 1e-6, error_flag=f),
                lambda f: kernels.rms_norm(x, weight, 1e-6, error_flag=f),
            ),
            (
                lambda f: kernels.silu_mul_quantized(gate, up, error_flag=f),
                lambda f: kernels.silu_mul(gate, up, error_flag=f),
            ),
        ):
            flags = [kernels.new_error_flag(), kernels.new_error_flag()]
            planes, exponents = fused(flags[0])
            control = kernels.quantize_input(unfused(flags[1]), error_flag=flags[1], _packed=True)
            assert int(flags[0].item()) == int(flags[1].item())
            assert torch.equal(planes, control[0]) and torch.equal(exponents, control[1]), rows


@gpu
def test_fused_ops_report_the_same_failures_and_reject_unsupported_shapes():
    kernels = cuda_class()("cuda", magnitude_bits=22)
    x = torch.randn(4, 64, device="cuda")
    weight = torch.ones(64, dtype=torch.float16, device="cuda")
    for poison in (float("nan"), float("inf")):
        bad = x.clone()
        bad[2, 5] = poison
        flags = [kernels.new_error_flag(), kernels.new_error_flag()]
        kernels.rms_norm_quantized(bad, weight, 1e-6, error_flag=flags[0])
        kernels.quantize_input(
            kernels.rms_norm(bad, weight, 1e-6, error_flag=flags[1]), error_flag=flags[1], _packed=True
        )
        assert int(flags[0].item()) == int(flags[1].item()) != 0
        flags = [kernels.new_error_flag(), kernels.new_error_flag()]
        kernels.silu_mul_quantized(bad, x, error_flag=flags[0])
        kernels.quantize_input(kernels.silu_mul(bad, x, error_flag=flags[1]), error_flag=flags[1], _packed=True)
        assert int(flags[0].item()) == int(flags[1].item()) != 0
    with pytest.raises(ReferenceArithmeticError, match="fused"):
        kernels.rms_norm_quantized(x[:1], weight, 1e-6)
    with pytest.raises(ReferenceArithmeticError, match="fused"):
        kernels.silu_mul_quantized(x, x[:, :32])
    planes = kernels.rms_norm_quantized(x, weight, 1e-6)
    with pytest.raises(ReferenceArithmeticError, match="Prepared"):
        kernels.linear_many(None, (torch.ones(8, 32, dtype=torch.float16, device="cuda"),), prepared=planes)
    w = (torch.randn(70, 64, device="cuda") * 0.1).half()
    expected = kernels.linear_decode(kernels.rms_norm(x, weight, 1e-6), w)
    assert torch.equal(bits(kernels.linear_decode(None, w, prepared=planes)), bits(expected))
