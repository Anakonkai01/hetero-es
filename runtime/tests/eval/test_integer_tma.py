"""SM120 B22 prefill projections whose operands arrive by TMA must give the streamed projection's bits and flags."""

import os

import pytest
import torch

from heteroes.eval import integer_tma
from heteroes.eval.reference_ops import ReferenceArithmeticError, StrictTransportError
from heteroes.eval.strict_cuda import StrictCudaKernels
from heteroes.eval.strict_decoder_graph import _DecodeSession


@pytest.mark.parametrize("status", [8, 9, 8 | 2 | 4])
def test_transport_timeout_is_an_infrastructure_failure_that_wins_over_arithmetic(status):
    for check in (StrictCudaKernels.raise_if_error, _DecodeSession.check):
        value = torch.tensor([status], dtype=torch.int32) if check is StrictCudaKernels.raise_if_error else status
        with pytest.raises(StrictTransportError) as caught:
            check(value)
        assert not isinstance(caught.value, ReferenceArithmeticError)


@pytest.mark.parametrize("status, message", [(1, "Nonfinite"), (2, "domain"), (4, "domain")])
def test_arithmetic_and_layout_bits_keep_their_meaning(status, message):
    with pytest.raises(ReferenceArithmeticError, match=message):
        StrictCudaKernels.raise_if_error(torch.tensor([status], dtype=torch.int32))
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite" if status == 1 else "domain"):
        _DecodeSession.check(status)


def test_derived_source_replaces_only_operand_transport():
    source = integer_tma.projection_source(896, 64, 1, 2, 3, False)
    body = source[source.index("void tma_stream_body(") :]
    # the asynchronous copy ring is gone; bulk tensor copies complete on shared-memory barriers instead
    assert "cp.async.wait_group" not in body and "cp.async.commit_group" not in body
    assert "cp.async.bulk.tensor.2d" in source and "cp.async.bulk.tensor.3d" in source
    assert "atomicOr(error,8)" in body and "atomicOr(error,4)" not in body
    assert "const __grid_constant__ TensorMap128 wd" in source
    for define in ("#define WIDTH 896\n", "#define MAGNITUDE_BITS 22\n", "#define DIGITS 3\n", "#define JN 2\n"):
        assert define in source
    # the integer products, finish and encoding are the shared ones: the streamed body is derived, not rewritten
    assert source.count("integer_finish(") >= 1 and "mma.sync.aligned.m16n8k32.row.col.s32.s8.s8.s32" in source
    assert integer_tma.projection_source(896, 64, 1, 2, 3, False) == source
    assert integer_tma.projection_source(896, 64, 1, 2, 3, True) != source


def test_eligibility_is_limited_to_the_measured_prefill_route():
    ok = dict(arch="sm_120", magnitude_bits=22, rows=129, width=896, split_k=1, row_tile=None, implementation="auto")
    assert integer_tma.eligible(**ok)
    for change in (
        dict(arch="sm_86"),
        dict(magnitude_bits=14),
        dict(rows=128),
        dict(rows=65535 * 32 + 1),
        dict(width=900),
        dict(split_k=2),
        dict(row_tile=16),
        dict(implementation="simt"),
    ):
        assert not integer_tma.eligible(**{**ok, **change})
    assert integer_tma.eligible(**{**ok, "row_tile": 32, "implementation": "mma"})


gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


def kernels(tma):
    from heteroes.eval.integer_cuda import IntegerCudaKernels

    torch.empty(1, device="cuda")
    k = IntegerCudaKernels("cuda", magnitude_bits=22, mma_schedule="stream")
    if k.arch != "sm_120":
        pytest.skip("TMA prefill route is SM120 only")
    k.prefill_tma = tma
    return k


@gpu
@pytest.mark.parametrize("width, outputs", [(80, 35), (896, 1152), (4864, 896)])
@pytest.mark.parametrize("rows", [129, 200, 1100])
@pytest.mark.parametrize("bias", [False, True])
@pytest.mark.parametrize("residual", [False, True])
def test_tma_projection_matches_streamed_projection_bits(width, outputs, rows, bias, residual):
    fast, base = kernels(True), kernels(False)
    g = torch.Generator(device="cuda").manual_seed(width + rows)
    x = torch.randn(rows, width, device="cuda", generator=g)
    w = (torch.randn(outputs, width, device="cuda", generator=g) * 0.03).half()
    b = (torch.randn(outputs, device="cuda", generator=g) * 0.1).half() if bias else None
    r = torch.randn(rows, outputs, device="cuda", generator=g) if residual else None
    flags = fast.new_error_flag(), base.new_error_flag()
    calls = fast.tma_calls
    actual = fast._linear(x, w, b, residual=r, error_flag=flags[0])
    expected = base._linear(x, w, b, residual=r, error_flag=flags[1])
    assert fast.tma_calls == calls + 1 and base.tma_calls == 0
    assert flags[0].item() == flags[1].item() == 0
    assert torch.equal(actual.view(torch.int32), expected.view(torch.int32))


@gpu
@pytest.mark.parametrize("scenario", ["nonfinite", "overflow", "zeros"])
def test_tma_projection_reports_the_same_flags(scenario):
    fast, base = kernels(True), kernels(False)
    g = torch.Generator(device="cuda").manual_seed(5)
    x = torch.randn(160, 896, device="cuda", generator=g)
    w = (torch.randn(128, 896, device="cuda", generator=g) * 0.03).half()
    if scenario == "nonfinite":
        x[7, 3] = float("nan")
    elif scenario == "overflow":
        x.mul_(2.0**120)
        w.fill_(65504.0)
    else:
        x.zero_()
    flags = fast.new_error_flag(), base.new_error_flag()
    actual = fast._linear(x, w, error_flag=flags[0])
    expected = base._linear(x, w, error_flag=flags[1])
    assert flags[0].item() == flags[1].item()
    if not flags[0].item():
        assert torch.equal(actual.view(torch.int32), expected.view(torch.int32))


@gpu
def test_ineligible_calls_keep_the_streamed_route():
    fast = kernels(True)
    x = torch.randn(128, 896, device="cuda")
    w = (torch.randn(64, 896, device="cuda") * 0.03).half()
    fast._linear(x, w)
    fast._linear(torch.randn(200, 896, device="cuda"), w, split_k=2)
    fast._linear(torch.randn(200, 896, device="cuda"), w, row_tile=16)
    assert fast.tma_calls == 0


@gpu
def test_two_captured_launches_reusing_one_host_template_keep_their_own_tensors():
    k = kernels(True)
    g = torch.Generator(device="cuda").manual_seed(496)
    xs = [torch.randn(160, 80, device="cuda", generator=g) for _ in range(2)]
    ws = [(torch.randn(35, 80, device="cuda", generator=g) * 0.03).half() for _ in range(2)]
    flags = [k.new_error_flag() for _ in range(2)]
    for x, w, f in zip(xs, ws, flags):
        k._linear(x, w, error_flag=f)
    assert len(k._tma.maps.entries) == 2  # one weight and one activation template, shared by both projections
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        captured = [k._linear(x, w, error_flag=f) for x, w, f in zip(xs, ws, flags)]
    base = kernels(False)
    for sign in (1.0, -1.0):
        for w in ws:
            w.mul_(sign)
        for x in xs:
            x.mul_(0.5)
        graph.replay()
        for x, w, f, out in zip(xs, ws, flags, captured):
            assert f.item() == 0
            assert torch.equal(base._linear(x, w).view(torch.int32), out.view(torch.int32))


@gpu
def test_host_template_cache_stays_bounded_across_layout_changes():
    k = kernels(True)
    cache = integer_tma.HostMapCache(k, capacity=2)
    w = torch.ones(35, 80, device="cuda", dtype=torch.float16)
    for rows in (17, 33, 65, 17):
        planes = k.quantize_input(torch.ones(rows, 80, device="cuda"), _packed=True)[0]
        a, b = cache.maps(w, planes, rows, 80, 64)
        assert a.size == b.size == 128 and a.ctypes.data % 64 == 0 and len(cache.entries) <= 2
    assert cache.encoded >= 3
