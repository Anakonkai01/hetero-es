"""Integer bounds may skip logits only when exact greedy selection and every failure flag are preserved."""

import copy
import os
from pathlib import Path
import subprocess
import tempfile

import pytest
import torch

from heteroes.strict import integer_reference as reference
from heteroes.strict.reference_ops import ReferenceArithmeticError

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


def make(seed, rows, width, vocab):
    gen = torch.Generator().manual_seed(seed)
    x = torch.randn(rows, width, generator=gen)
    x *= torch.exp(torch.randn(rows, 1, generator=gen) * 2)
    w = (torch.randn(vocab, width, generator=gen) * 0.1).half()
    return x.cuda(), w.cuda()


def setup(weight):
    from heteroes.strict.integer_cuda import IntegerCudaKernels
    from heteroes.strict.integer_lm_head import BoundedLmHead

    kernels = IntegerCudaKernels("cuda", magnitude_bits=22)
    kernels._begin_request([weight])
    head = BoundedLmHead(kernels)
    head.prepare(weight)
    return kernels, head


def selected(kernels, head, x, w, *, bounded, flag=None, prepared=None):
    from heteroes.strict.strict_decode_cuda import DecodeKernels

    rows, vocab = x.shape[0], w.shape[0]
    decode = DecodeKernels(kernels)
    # Nontrivial row ownership and preexisting state check the publication contract too.
    owners = torch.arange(rows - 1, -1, -1, dtype=torch.int64, device="cuda")
    seen = torch.zeros((rows, vocab), dtype=torch.uint8, device="cuda")
    seen[:, -1] = 1
    tokens = torch.full((rows,), -7, dtype=torch.int64, device="cuda")
    result = torch.full((rows + 1,), -9, dtype=torch.int64, device="cuda")
    flag = kernels.new_error_flag() if flag is None else flag
    if bounded:
        prepared = kernels.quantize_input(x, error_flag=flag, _packed=True) if prepared is None else prepared
        head.select(prepared, w, decode, seen, owners, tokens, result, flag)
    else:
        logits = kernels.linear_decode(x, w, error_flag=flag)
        decode.greedy(logits, seen, owners, tokens, result, flag, 1.0, 1.0)
    return tokens.cpu(), seen.cpu(), result.cpu(), flag.cpu()


@gpu
@pytest.mark.parametrize(
    "rows,width,vocab", [(2, 16, 1), (9, 48, 67), (16, 64, 1025), (17, 80, 129), (32, 896, 4097), (2, 32768, 33)]
)
def test_bounded_tokens_seen_result_and_flags_equal_full_projection(rows, width, vocab):
    x, w = make(rows + width, rows, width, vocab)
    kernels, head = setup(w)
    try:
        actual, expected = selected(kernels, head, x, w, bounded=True), selected(kernels, head, x, w, bounded=False)
        assert all(torch.equal(a, b) for a, b in zip(actual, expected))
        assert int(actual[-1]) == 0
    finally:
        head.clear()
        kernels._end_request()


@gpu
@pytest.mark.parametrize(
    "kind", ["equal", "duplicate", "zeros", "subnormal", "overflow", "negative_overflow", "false_positive_overflow"]
)
def test_ties_signed_zero_flush_and_nonwinning_overflow_are_preserved(kind):
    x, w = make(731, 17, 64, 97)
    if kind == "equal":
        w[:] = w[0].clone()  # all tiles survive, including a one-column tail
    elif kind == "duplicate":
        x.fill_(1)
        w.zero_()
        w[0] = w[65] = 1
    elif kind == "zeros":
        x.zero_()
        x[0] = -0.0
        w[0] = -0.0
    elif kind == "subnormal":
        x.fill_(2.0**-120)
        x[0] = 2.0**-140
        w.fill_(2.0**-24)
        w[65] = -(2.0**-24)
    elif kind == "false_positive_overflow":
        x.fill_(2.0**120)
        w[:, ::2] = 65504
        w[:, 1::2] = -65504  # exact logits cancel to zero, while both conservative bounds overflow
    else:
        x.fill_(2.0**120)
        w.zero_()
        w[0] = 1  # a finite winner when another, negative logit overflows
        w[65] = 65504 if kind == "overflow" else -65504
    kernels, head = setup(w)
    try:
        actual, expected = selected(kernels, head, x, w, bounded=True), selected(kernels, head, x, w, bounded=False)
        assert all(torch.equal(a, b) for a, b in zip(actual, expected))
        assert int(actual[-1]) == int(kind in ("overflow", "negative_overflow"))
        if kind in ("equal", "duplicate", "zeros"):
            assert bool((actual[0] == 0).all())
    finally:
        head.clear()
        kernels._end_request()


@gpu
def test_bounds_contain_the_independent_exact_integer_dot_and_rounding():
    x, w = make(919, 17, 80, 97)
    kernels, head = setup(w)
    try:
        prepared = kernels.quantize_input(x, _packed=True)
        hi, lo = head.bounds(prepared, w)
        qa, ex = reference.quantize_rows(x.cpu(), magnitude_bits=22)
        # Half weights use their actual (including subnormal) exponent, as in the CPU linear oracle.
        qw, ew = reference.quantize_rows(w.cpu().float(), magnitude_bits=22)
        coarse = head.buffer.cpu().to(torch.int64)
        assert torch.equal(coarse, qw.to(torch.int64) // 32768)
        for r in range(x.shape[0]):
            q = qa[r].to(torch.int64)
            center = (coarse * q).sum(1) * 32768 + int(q.sum()) * 16384
            radius = int(q.abs().sum()) * 16384
            exact = (qw.to(torch.int64) * q).sum(1)
            assert bool(((center - radius <= exact) & (exact <= center + radius)).all())
            lows, highs = [], []
            for v in range(w.shape[0]):
                scale = int(ex[r]) + int(ew[v]) - 42
                lows.append(reference.scaled_integer_bits(int(center[v]) - radius, scale))
                highs.append(reference.scaled_integer_bits(int(center[v]) + radius, scale))
            lower = torch.tensor(lows, dtype=torch.int64).to(torch.int32).view(torch.float32)
            upper = torch.tensor(highs, dtype=torch.int64).to(torch.int32).view(torch.float32)
            for tile in range(hi.shape[1]):
                # A common exponent may widen intervals with directed integer rounding before the
                # final RNE/FTZ encoding. It must still enclose the independent, narrower intervals.
                assert float(lo[r, tile]) <= float(lower[tile * 32 : (tile + 1) * 32].max())
                assert float(hi[r, tile]) >= float(upper[tile * 32 : (tile + 1) * 32].max())
    finally:
        head.clear()
        kernels._end_request()


@gpu
def test_head_refresh_clear_pointer_stability_and_changed_weight_binding():
    x, w = make(15, 9, 64, 97)
    kernels, head = setup(w)
    snapshot, pointer = w.clone(), head.buffer.data_ptr()
    parent = selected(kernels, head, x, w, bounded=True)
    for factor in (-32, 1):
        head.clear()
        kernels._end_request()
        assert not bool(head.buffer.any())
        w.copy_(snapshot * factor)
        kernels._begin_request([w])
        head.prepare(w)
        assert head.buffer.data_ptr() == pointer
        actual, expected = selected(kernels, head, x, w, bounded=True), selected(kernels, head, x, w, bounded=False)
        assert all(torch.equal(a, b) for a, b in zip(actual, expected))
    assert all(torch.equal(a, b) for a, b in zip(actual, parent))
    with pytest.raises(ReferenceArithmeticError, match="binding"):
        head.bounds(kernels.quantize_input(x, _packed=True), w.clone())
    head.clear()
    kernels._end_request()


@gpu
def test_wide_graph_reuses_capture_matches_full_path_and_penalty_falls_back(monkeypatch):
    from test_strict_decoder import model_for
    from heteroes.strict.integer_decoder import IntegerDecoderGraph

    torch.manual_seed(612)
    cpu = model_for("llama")
    # A wide enough vocabulary exercises the production route without downloading a trained model.
    cpu.resize_token_embeddings(4097, mean_resizing=False)
    bounded = IntegerDecoderGraph(copy.deepcopy(cpu).cuda(), magnitude_bits=22, max_context=32, allow_fixture=True)
    full = IntegerDecoderGraph(copy.deepcopy(cpu).cuda(), magnitude_bits=22, max_context=32, allow_fixture=True)
    monkeypatch.setattr(
        full, "_decode_output", lambda h, e, s: super(IntegerDecoderGraph, full)._decode_output(h, e, s)
    )
    ids = torch.tensor([[3, 5, 7], [11, 13, 17]], device="cuda")
    head = bounded._bounded_head
    import heteroes.strict.strict_decoder_graph as graph_module

    bound = bounded._request_workspace_bytes(2)
    assert bound >= bounded.model.lm_head.weight.numel()
    with monkeypatch.context() as changes:
        changes.setattr(graph_module, "graph_memory_bound", lambda *args, **kwargs: 0)
        changes.setattr(bounded, "max_graph_bytes", bound - 1)
        changes.setattr(bounded, "_session_for", lambda *args: pytest.fail("admit before allocating capture/weights"))
        with pytest.raises(ReferenceArithmeticError, match="budget"):
            bounded.generate(ids, max_new_tokens=4, eos_token_id=[])
    used, original = [], head.select

    def record(*args, **kwargs):
        used.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(head, "select", record)
    saved = bounded.model.lm_head.weight.clone()
    for factor in (1, -4, 1):
        for backend in (bounded, full):
            backend.model.lm_head.weight.data.copy_(saved * factor)
        actual = bounded.generate(ids, max_new_tokens=4, eos_token_id=[])
        expected = full.generate(ids, max_new_tokens=4, eos_token_id=[])
        assert torch.equal(actual, expected)
        assert bounded._session.capture_count == 1
        assert not bool(head.buffer.any())
    assert used
    pointer = head.buffer.data_ptr()
    used.clear()
    for backend in (bounded, full):
        expected = backend.generate(ids, max_new_tokens=4, eos_token_id=[], repetition_penalty=1.2)
        if backend is bounded:
            actual = expected
    assert torch.equal(actual, expected)
    assert not used and head.buffer.data_ptr() == pointer
    bounded.release_graph()
    full.release_graph()


@gpu
@pytest.mark.parametrize("sign", [-1, 1])
def test_common_scale_directed_rounding_keeps_small_nonintegral_bounds(sign):
    x = torch.full((2, 16), 2.0**-21, device="cuda")
    x[:, 0] = 1
    w = torch.full((33, 16), sign * 2.0**-24, dtype=torch.float16, device="cuda")
    kernels, head = setup(w)
    try:
        hi, lo = head.bounds(kernels.quantize_input(x, _packed=True), w)
        exact = reference.linear(x.cpu(), w.cpu(), magnitude_bits=22).max(1).values.cuda()
        assert bool((lo <= exact[:, None]).all())
        assert bool((hi >= exact[:, None]).all())
    finally:
        head.clear()
        kernels._end_request()


@gpu
@pytest.mark.parametrize("sign", [-1, 1])
@pytest.mark.parametrize("below", [False, True])
def test_exact_rne_overflow_boundary_retains_flags_and_finite_neighbors(sign, below):
    # At scale 79, the integer overflow threshold is 2^49-2^24. Weight quanta have a 2^11 gcd.
    # Solve 2047*sum(qa)-qa[0] = (2^49-2^24)/2^11, or one quantum below, using two FP16 values.
    target = 2**38 - 8192 - int(below)
    total = -(-target // 2047)
    first = 2047 * total - target
    rest, remainder = divmod(total - first, 63)
    qa = [first] + [rest + int(i < remainder) for i in range(63)]
    x = (torch.tensor([qa, qa], dtype=torch.float32, device="cuda") * 2.0**85).contiguous()
    w = torch.zeros((97, 64), dtype=torch.float16, device="cuda")
    w[65] = sign * 65504
    w[65, 0] = sign * 65472
    kernels, head = setup(w)
    try:
        actual, expected = selected(kernels, head, x, w, bounded=True), selected(kernels, head, x, w, bounded=False)
        assert all(torch.equal(a, b) for a, b in zip(actual, expected))
        assert int(actual[-1]) == int(not below)
    finally:
        head.clear()
        kernels._end_request()


@gpu
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_activations_keep_the_quantizer_error(value):
    x, w = make(415, 9, 64, 97)
    x[3, 13] = value
    kernels, head = setup(w)
    try:
        actual, expected = selected(kernels, head, x, w, bounded=True), selected(kernels, head, x, w, bounded=False)
        assert all(torch.equal(a, b) for a, b in zip(actual, expected))
        assert int(actual[-1]) == 1
    finally:
        head.clear()
        kernels._end_request()


@gpu
@pytest.mark.parametrize("arch", ["sm_80", "sm_86", "sm_89", "sm_90", "sm_120"])
def test_bounded_source_passes_the_instruction_audit_on_supported_architectures(arch):
    from heteroes.strict import strict_cuda as sc
    from heteroes.strict.integer_cuda import IntegerCudaKernels
    from heteroes.strict.integer_lm_head import source

    owner = IntegerCudaKernels("cuda", magnitude_bits=22)
    if not owner._nvdisasm:
        pytest.skip("nvdisasm unavailable")
    for width, tile in ((896, 32), (80, 16)):
        nvrtc = owner._nvrtc
        program = sc._check(nvrtc.nvrtcCreateProgram(source(width, tile).encode(), b"bounds.cu", 0, [], []))
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
            path = Path(directory) / "bounds.cubin"
            path.write_bytes(cubin)
            sass = subprocess.run([owner._nvdisasm, str(path)], capture_output=True, text=True, check=True).stdout
        assert sc.audit_integer_sass(sass)["violations"] == []


@gpu
@pytest.mark.parametrize("exponent", [-126, -80, 0, 92, 93, 96, 100, 120, 126, 127])
def test_common_scale_outward_rounding_covers_the_entire_admitted_exponent_range(exponent):
    gen = torch.Generator(device="cuda").manual_seed(721)
    x = (torch.rand((2, 64), generator=gen, device="cuda") * 2 - 1) * 2.0**exponent
    x[:, 0] = 2.0**exponent
    w = torch.empty((65, 64), dtype=torch.float16, device="cuda")
    for v in range(65):
        e = (-24, -14, -5, 0, 8, 15)[v % 6]
        w[v] = (torch.rand(64, generator=gen, device="cuda") * 2 - 1) * 2.0**e
        w[v, 0] = 2.0**e
    kernels, head = setup(w)
    try:
        actual, expected = selected(kernels, head, x, w, bounded=True), selected(kernels, head, x, w, bounded=False)
        assert all(torch.equal(a, b) for a, b in zip(actual, expected))
    finally:
        head.clear()
        kernels._end_request()
