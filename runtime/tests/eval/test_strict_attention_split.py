"""Distributed attention kernels must reproduce the original kernel's bits and failure flags."""

import os

import pytest
import torch

from heteroes.strict import strict_cuda
from heteroes.strict.strict_cuda import StrictCudaKernels, attention_chunk, gqa_attention_eligible
from test_strict_cuda import _reference_attention

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)
VARIANTS = ["strict_attention_split", "strict_attention_gqa"]


def bits(t):
    return t.contiguous().view(torch.int32)


@pytest.mark.parametrize("keys", [1, 8, 31, 32, 33, 512, 1025, 4096])
@pytest.mark.parametrize("dim", [1, 3, 8, 13, 64, 80, 128, 256])
def test_attention_chunk_is_an_aligned_power_of_two_with_a_bounded_root_plane(keys, dim):
    chunk = attention_chunk(keys, dim)
    assert chunk >= 8 and chunk & (chunk - 1) == 0
    assert -(-keys // chunk) * dim <= 2048
    assert chunk == 32 or -(-keys // (chunk // 2)) * dim > 2048


def test_gqa_eligibility_needs_whole_warps_one_block_and_default_shared_memory():
    assert gqa_attention_eligible(64, 7, 48 * 1024)
    assert gqa_attention_eligible(128, 4, 1024)
    assert not gqa_attention_eligible(128, 8, 1024)
    assert not gqa_attention_eligible(80, 2, 1024)
    assert not gqa_attention_eligible(96, 2, 1024)
    assert not gqa_attention_eligible(64, 1, 1024)
    assert not gqa_attention_eligible(16, 2, 1024)
    assert not gqa_attention_eligible(64, 17, 1024)
    assert not gqa_attention_eligible(64, 7, 48 * 1024 + 4)


class Spy(StrictCudaKernels):
    def _ops(self, entry):
        self.used.append(entry)
        return super()._ops(entry)


@pytest.fixture(scope="module")
def kernels():
    made = {}
    for entry in ["strict_attention", *VARIANTS]:
        made[entry] = Spy("cuda")
        made[entry].used = []
        made[entry]._attention_entry = entry
    assert StrictCudaKernels._attention_entry == "strict_attention_prefill"
    return made


def run(kernels, *args, packed=False):
    kernels.used.clear()
    flag = kernels.new_error_flag()
    out = (kernels.attention_packed if packed else kernels.attention)(*args, error_flag=flag)
    return out, int(flag.item())


def check_ran(kernels, variant, dim, repeats, keys):
    shared = 4 * ((repeats + 32) * (dim + max(1, dim // 32)) + 2 * repeats * keys)
    expected = variant
    if variant == "strict_attention_gqa" and not gqa_attention_eligible(dim, repeats, shared):
        expected = "strict_attention_split"
    assert kernels.used == [expected]
    return expected


def tensors(seed, heads, kv_heads, length, keys, dim, pattern):
    gen = torch.Generator().manual_seed(seed)
    q = torch.randn(heads, length, dim, generator=gen) * 2
    k = torch.randn(kv_heads, keys, dim, generator=gen) * 2
    v = torch.randn(kv_heads, keys, dim, generator=gen)
    if pattern == "negative_zero":
        v = torch.full_like(v, -0.0)
        q[:, :, ::2] = -0.0
    elif pattern == "cancellation":
        v = torch.tensor([2.0**24, 1.0, -(2.0**24), 1.0]).repeat(v.numel() // 4 + 1)[: v.numel()].reshape(v.shape)
        k = k * 8
    elif pattern == "subnormal":
        tiny = torch.tensor([1 << 10], dtype=torch.int32).view(torch.float32).item()
        v[..., ::3] = tiny
        q[..., ::5] = -tiny
    elif pattern == "subnormal_keys":
        # Queries near 2**125 turn unflushed random subnormal keys into normal products that differ per key:
        # scores, and so the probabilities, change visibly if a flush is missing.
        q = q * 2.0**124
        magnitude = torch.randint(1, 1 << 22, k.shape, generator=gen, dtype=torch.int32)
        sign = torch.randint(0, 2, k.shape, generator=gen, dtype=torch.int32) << 31
        k = torch.where(torch.arange(dim) % 3 == 0, (magnitude | sign).view(torch.float32), 0.0)
    elif pattern == "equal_scores":
        k = torch.zeros_like(k)
    return q.cuda(), k.cuda(), v.cuda()


@gpu
@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize(
    "dim,keys,length,repeats",
    [
        (1, 1, 1, 2),
        (3, 9, 2, 2),
        (8, 33, 1, 2),
        (13, 64, 3, 2),
        (32, 5, 5, 3),
        (32, 70, 1, 1),
        (96, 40, 2, 2),
        (64, 1, 1, 7),
        (64, 31, 1, 7),
        (64, 257, 1, 7),
        (64, 300, 4, 7),
        (64, 512, 1, 8),
        (80, 129, 2, 2),
        (128, 1025, 1, 2),
        (256, 65, 2, 4),
        (256, 4096, 1, 2),
    ],
)
@pytest.mark.parametrize(
    "pattern", ["normal", "negative_zero", "cancellation", "subnormal", "subnormal_keys", "equal_scores"]
)
def test_distributed_attention_equals_original_bits_and_flags(kernels, variant, dim, keys, length, repeats, pattern):
    q, k, v = tensors(dim * 7919 + keys, 2 * repeats, 2, length, keys, dim, pattern)
    args = (q, k, v, keys - length, repeats, 0.125)
    actual, actual_flag = run(kernels[variant], *args)
    check_ran(kernels[variant], variant, dim, repeats, keys)
    expected, expected_flag = run(kernels["strict_attention"], *args)
    assert torch.equal(bits(actual), bits(expected))
    assert actual_flag == expected_flag


@gpu
@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("dim,keys", [(64, 300), (13, 70), (128, 257)])
def test_distributed_attention_matches_the_independent_cpu_oracle(kernels, variant, dim, keys):
    repeats = 7 if dim == 64 else 2
    q, k, v = tensors(dim + keys, 2 * repeats, 2, 2, keys, dim, "normal")
    actual, flag = run(kernels[variant], q, k, v, keys - 2, repeats, 0.125)
    expected = _reference_attention(q.cpu(), k.cpu(), v.cpu(), keys - 2, repeats, 0.125)
    assert flag == 0
    assert torch.equal(bits(actual.cpu()), bits(expected))


@gpu
@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize(
    "where", ["masked_score_overflow", "masked_value_inf", "visible_value_nan", "query_inf", "visible_score_overflow"]
)
def test_distributed_attention_reports_the_same_failures(kernels, variant, where):
    q, k, v = tensors(5, 4, 2, 3, 40, 32, "normal")
    if where == "masked_score_overflow":
        k[1, 39] = 1e30
        q[:, 0] = 1e30
    elif where == "masked_value_inf":
        v[0, 39, 3] = float("inf")
    elif where == "visible_value_nan":
        v[1, 5, 0] = float("nan")
    elif where == "query_inf":
        q[2, 1, 7] = float("inf")
    else:
        k[0, 10] = 1e30
        q[:2] = 1e30
    args = (q, k, v, 37, 2, 0.125)
    actual, actual_flag = run(kernels[variant], *args)
    expected, expected_flag = run(kernels["strict_attention"], *args)
    assert expected_flag != 0
    assert actual_flag == expected_flag
    assert torch.equal(bits(actual), bits(expected))


@gpu
@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize(
    "spans",
    [
        [(3, 3, 0), (1, 8, 7), (2, 5, 3)],
        [(1, 1, 0), (1, 257, 256), (1, 143, 142), (4, 40, 36)],
        [(1, 512, 511)] * 3 + [(1, 33, 32)],
    ],
)
def test_distributed_packed_attention_equals_original_and_cpu(kernels, variant, spans):
    gen = torch.Generator().manual_seed(len(spans))
    qs, ks, vs, expected = [], [], [], []
    for length, keys, past in spans:
        q = torch.randn(14, length, 64, generator=gen)
        k = torch.randn(2, keys, 64, generator=gen)
        v = torch.randn(2, keys, 64, generator=gen)
        qs.append(q)
        ks.append(k)
        vs.append(v)
        expected.append(_reference_attention(q, k, v, past, 7, 0.125))
    args = (torch.cat(qs, 1).cuda(), torch.cat(ks, 1).cuda(), torch.cat(vs, 1).cuda(), spans, 7, 0.125)
    actual, actual_flag = run(kernels[variant], *args, packed=True)
    check_ran(kernels[variant], variant, 64, 7, max(s[1] for s in spans))
    control, control_flag = run(kernels["strict_attention"], *args, packed=True)
    assert actual_flag == control_flag == 0
    assert torch.equal(bits(actual), bits(control))
    assert torch.equal(bits(actual.cpu()), bits(torch.cat(expected)))


@gpu
@pytest.mark.parametrize("variant", VARIANTS)
def test_distributed_attention_has_no_kernel_state_between_calls(kernels, variant):
    q, k, v = tensors(11, 14, 2, 1, 300, 64, "normal")
    first, _ = run(kernels[variant], q, k, v, 299, 7, 0.125)
    other = tensors(12, 14, 2, 1, 70, 64, "normal")
    run(kernels[variant], *other, 69, 7, 0.125)
    again, _ = run(kernels[variant], q, k, v, 299, 7, 0.125)
    assert torch.equal(bits(first), bits(again))
    assert strict_cuda.ATTENTION_THREADS % 32 == 0


@gpu
@pytest.mark.parametrize("arch", ["sm_75", "sm_80", "sm_86", "sm_89", "sm_90", "sm_120"])
def test_ops_source_passes_the_instruction_audit_on_other_architectures(kernels, arch):
    # Code generation differs by target: an unrolled runtime-stride loop compiled to MUFU.RCP integer division
    # on sm_86 although sm_120 was clean. Compile for each target here, without loading the module.
    import subprocess
    import tempfile
    from pathlib import Path

    owner = kernels["strict_attention"]
    if not owner._nvdisasm:
        pytest.skip("nvdisasm unavailable")
    header = "".join(f"#define {k} 0x{v:08x}u\n" for k, v in strict_cuda.reference_constants().items())
    nvrtc = owner._nvrtc
    program = strict_cuda._check(
        nvrtc.nvrtcCreateProgram((header + strict_cuda._OPS_SOURCE).encode(), b"ops.cu", 0, [], [])
    )
    try:
        options = [f"--gpu-architecture={arch}".encode(), *(o.encode() for o in strict_cuda.NVRTC_OPTIONS)]
        assert int(nvrtc.nvrtcCompileProgram(program, len(options), options)[0]) == 0
        ptx = b" " * strict_cuda._check(nvrtc.nvrtcGetPTXSize(program))
        strict_cuda._check(nvrtc.nvrtcGetPTX(program, ptx))
        cubin = b" " * strict_cuda._check(nvrtc.nvrtcGetCUBINSize(program))
        strict_cuda._check(nvrtc.nvrtcGetCUBIN(program, cubin))
    finally:
        nvrtc.nvrtcDestroyProgram(program)
    assert strict_cuda.audit_ptx(ptx.rstrip(b"\0").decode(), strict_cuda.OPS_PTX_EXACT)["violations"] == []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "ops.cubin"
        path.write_bytes(cubin)
        sass = subprocess.run([owner._nvdisasm, str(path)], capture_output=True, text=True, check=True).stdout
    assert "strict_attention_gqa" in sass and "strict_attention_split" in sass
    assert strict_cuda.audit_sass(sass, strict_cuda.OPS_SASS_EXACT)["violations"] == []
