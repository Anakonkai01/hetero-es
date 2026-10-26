"""Query tiles share K/V without changing the original attention's rounded trees or failure flags."""

import os

import pytest
import torch

from heteroes.eval import strict_cuda as sc
from test_strict_attention_split import bits, tensors
from test_strict_cuda import _reference_attention

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@pytest.mark.parametrize(
    "dim,repeats,keys,queries,expected",
    [
        (64, 7, 142, 90, (2, 7)),
        (32, 1, 256, 20, (8, 1)),
        (64, 4, 128, 17, (4, 4)),
        (128, 2, 70, 9, (4, 2)),
        (256, 2, 32, 8, (4, 2)),
    ],
)
def test_prefill_plan_bounds_threads_shared_memory_and_query_reuse(dim, repeats, keys, queries, expected):
    plan = sc.prefill_attention_plan(dim, repeats, keys, queries)
    assert (plan.query_tile, plan.head_tile) == expected
    slots = plan.query_tile * plan.head_tile
    assert slots * 32 <= 512
    assert plan.shared_bytes == 4 * ((keys + slots) * (dim + dim // 32) + slots * keys)
    assert plan.shared_bytes <= 48 * 1024


@pytest.mark.parametrize(
    "args",
    [(80, 2, 32, 8), (16, 2, 32, 8), (64, 7, 512, 32), (64, 7, 32, 1), (64, 0, 32, 8), (64, 7, 0, 8), (True, 7, 32, 8)],
)
def test_ineligible_prefill_keeps_the_existing_attention_path(args):
    assert sc.prefill_attention_plan(*args) is None


def test_prefill_module_is_covered_by_the_portable_kernel_identity(tmp_path, monkeypatch):
    before = sc.static_identity()["sourceSha256"]
    source = tmp_path / "strict_prefill_cuda.py"
    from pathlib import Path

    source.write_bytes(Path(sc.strict_prefill_cuda.__file__).read_bytes() + b"\n# changed kernel\n")
    monkeypatch.setattr(sc.strict_prefill_cuda, "__file__", str(source))
    assert sc.static_identity()["sourceSha256"] != before


class Spy(sc.StrictCudaKernels):
    def _compile(self, name, *args, **kwargs):
        self.compiled.append(name)
        return super()._compile(name, *args, **kwargs)


@pytest.fixture(scope="module")
def kernels():
    original, tiled = sc.StrictCudaKernels("cuda"), Spy("cuda")
    original._attention_entry = "strict_attention"
    tiled._attention_entry = "strict_attention_prefill"
    tiled.compiled = []
    return original, tiled


def compare(kernels, args):
    original, tiled = kernels
    flags = [k.new_error_flag() for k in kernels]
    control = original.attention_packed(*args, error_flag=flags[0])
    actual = tiled.attention_packed(*args, error_flag=flags[1])
    assert torch.equal(bits(actual), bits(control))
    assert flags[0].item() == flags[1].item()
    return actual, int(flags[1].item())


@gpu
@pytest.mark.parametrize(
    "dim,repeats,spans",
    [
        (64, 7, [(17, 23, 6), (9, 142, 133), (1, 1, 0)]),
        (32, 1, [(8, 31, 23), (3, 33, 30), (9, 256, 247)]),
        (128, 2, [(9, 70, 61), (3, 5, 2)]),
        (64, 4, [(7, 8, 1), (8, 32, 24), (9, 65, 56)]),
        (256, 2, [(9, 32, 23), (3, 5, 2)]),
        (32, 9, [(5, 64, 59), (3, 7, 4)]),
    ],
)
@pytest.mark.parametrize(
    "pattern",
    ["normal", "cancellation", "negative_zero", "subnormal", "subnormal_keys", "subnormal_queries", "equal_scores"],
)
def test_prefill_tiles_match_original_bits_and_flags(kernels, dim, repeats, spans, pattern):
    qs, ks, vs = [], [], []
    for number, (length, keys, _) in enumerate(spans):
        q, k, v = tensors(number + 5, 2 * repeats, 2, length, keys, dim, pattern)
        if pattern == "subnormal_queries":
            q.fill_(torch.tensor([1 << 20], dtype=torch.int32).view(torch.float32).item())
            k = k * 2.0**124
        qs.append(q)
        ks.append(k)
        vs.append(v)
    layout = kernels[1].attention_layout(spans)
    args = (torch.cat(qs, 1), torch.cat(ks, 1), torch.cat(vs, 1), layout, repeats, 0.125)
    first, _ = compare(kernels, args)
    saved_tiles = dict(layout.prefill_tiles)
    assert saved_tiles
    again, _ = compare(kernels, args)
    assert torch.equal(bits(first), bits(again))
    assert all(layout.prefill_tiles[n] is t for n, t in saved_tiles.items())


@gpu
def test_prefill_tiles_equal_cpu_oracle_and_do_not_cross_sequences(kernels):
    spans = [(9, 33, 24), (3, 7, 4)]
    qs, ks, vs, expected = [], [], [], []
    for number, (length, keys, past) in enumerate(spans):
        q, k, v = tensors(number + 8, 14, 2, length, keys, 64, "normal")
        qs.append(q)
        ks.append(k)
        vs.append(v)
        expected.append(_reference_attention(q.cpu(), k.cpu(), v.cpu(), past, 7, 0.125))
    args = (torch.cat(qs, 1), torch.cat(ks, 1), torch.cat(vs, 1), spans, 7, 0.125)
    actual, flag = compare(kernels, args)
    assert flag == 0
    assert torch.equal(bits(actual.cpu()), bits(torch.cat(expected)))


@gpu
@pytest.mark.parametrize("where", ["masked_value_inf", "masked_score_overflow", "query_inf", "value_nan"])
def test_prefill_tiles_preserve_masked_loads_and_failure_flags(kernels, where):
    q, k, v = tensors(15, 14, 2, 9, 33, 64, "normal")
    if where == "masked_value_inf":
        v[0, 32, 3] = float("inf")
    elif where == "masked_score_overflow":
        k[1, 32] = 1e30
        q[7:, 0] = 1e30
    elif where == "query_inf":
        q[0, 0, 3] = float("inf")
    else:
        v[1, 5, 2] = float("nan")
    _, flag = compare(kernels, (q, k, v, [(9, 33, 24)], 7, 0.125))
    assert flag != 0


@gpu
@pytest.mark.parametrize("dim,keys,length", [(80, 33, 9), (64, 512, 2), (64, 8, 1)])
def test_prefill_fallback_still_matches_original(kernels, dim, keys, length):
    q, k, v = tensors(8, 14, 2, length, keys, dim, "normal")
    layout = kernels[1].attention_layout([(length, keys, keys - length)])
    compare(kernels, (q, k, v, layout, 7, 0.125))
    assert layout.prefill_tiles == {}


@gpu
def test_prefill_tiles_capture_and_replay_with_live_inputs(kernels):
    original, tiled = kernels
    spans = [(9, 33, 24), (3, 7, 4)]
    q, k, v = tensors(9, 14, 2, 12, 40, 64, "normal")
    layout = tiled.attention_layout(spans)
    flag = tiled.new_error_flag()
    tiled.attention_packed(q, k, v, layout, 7, 0.125, error_flag=flag)
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        captured = tiled.attention_packed(q, k, v, layout, 7, 0.125, error_flag=flag)
    q.add_(0.1)
    graph.replay()
    expected = original.attention_packed(q, k, v, spans, 7, 0.125)
    assert flag.item() == 0
    assert torch.equal(bits(captured), bits(expected))


@gpu
@pytest.mark.parametrize("arch", ["sm_75", "sm_80", "sm_86", "sm_89", "sm_90", "sm_120"])
@pytest.mark.parametrize("dim,queries,heads", [(32, 8, 1), (64, 2, 7), (128, 4, 2), (256, 4, 2)])
def test_prefill_source_passes_the_instruction_audit_on_other_architectures(kernels, arch, dim, queries, heads):
    import subprocess
    import tempfile
    from pathlib import Path

    owner = kernels[1]
    if not owner._nvdisasm:
        pytest.skip("nvdisasm unavailable")
    header = "".join(f"#define {k} 0x{v:08x}u\n" for k, v in sc.reference_constants().items())
    header += f"#define DIM {dim}\n#define QTILE {queries * heads}\n#define HEAD_TILE {heads}\n"
    nvrtc = owner._nvrtc
    program = sc._check(
        nvrtc.nvrtcCreateProgram((header + sc._OPS_SOURCE + sc._PREFILL_SOURCE).encode(), b"prefill.cu", 0, [], [])
    )
    try:
        options = [f"--gpu-architecture={arch}".encode(), *(o.encode() for o in sc.NVRTC_OPTIONS)]
        status = nvrtc.nvrtcCompileProgram(program, len(options), options)[0]
        if int(status):
            log = b" " * sc._check(nvrtc.nvrtcGetProgramLogSize(program))
            sc._check(nvrtc.nvrtcGetProgramLog(program, log))
            pytest.fail(log.decode(errors="replace"))
        ptx = b" " * sc._check(nvrtc.nvrtcGetPTXSize(program))
        sc._check(nvrtc.nvrtcGetPTX(program, ptx))
        cubin = b" " * sc._check(nvrtc.nvrtcGetCUBINSize(program))
        sc._check(nvrtc.nvrtcGetCUBIN(program, cubin))
    finally:
        nvrtc.nvrtcDestroyProgram(program)
    assert sc.audit_ptx(ptx.rstrip(b"\0").decode(), sc.OPS_PTX_EXACT)["violations"] == []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "prefill.cubin"
        path.write_bytes(cubin)
        sass = subprocess.run([owner._nvdisasm, str(path)], capture_output=True, text=True, check=True).stdout
    assert "strict_attention_prefill" in sass
    assert sc.audit_sass(sass, sc.OPS_SASS_EXACT)["violations"] == []
