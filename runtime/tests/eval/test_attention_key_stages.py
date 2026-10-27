"""Larger shared K/V stages must keep the ordered 32-key score/value subtrees: same bits and flags as the GQA kernel."""

import os

import pytest
import torch

from heteroes.eval import attention_stages


def test_stage_source_keeps_ordered_32_key_subtrees():
    source = attention_stages.source(128)
    assert "#define KEY_TILE 128\n" in source and "#define LOADS 8\n" in source
    assert "key_stage_attention(" in source and source.count("for(int sub=0;sub<KEY_TILE;sub+=32)") == 1
    assert "for(int sub=0;sub<rows;sub+=32)" in source
    assert attention_stages.source(128) == source
    with pytest.raises(AssertionError):
        attention_stages.source(96)


@pytest.mark.parametrize(
    "arch, dim, repeats, max_keys, expected",
    [
        ("sm_120", 64, 7, 512, True),
        ("sm_120", 64, 7, 693, True),  # the largest context whose original launch is the GQA kernel
        ("sm_120", 64, 7, 694, False),  # the original uses the split kernel: keep it
        ("sm_86", 64, 7, 512, False),
        ("sm_120", 128, 4, 64, False),
        ("sm_120", 64, 3, 64, False),
        ("sm_120", 64, 9, 64, False),
    ],
)
def test_stage_route_only_replaces_launches_of_the_original_gqa_kernel(arch, dim, repeats, max_keys, expected):
    assert attention_stages.eligible(arch, dim, repeats, max_keys) is expected


gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


def decode_layout(lengths, context):
    """The captured decoder's layout: one query per owner, no prefill spans, bound = physical context."""
    from heteroes.eval import strict_cuda as sc

    ranges = torch.tensor([(i * context, n, n - 1) for i, n in enumerate(lengths)], dtype=torch.int32, device="cuda")
    return sc._PackedAttentionLayout(ranges, len(lengths), len(lengths) * context, context)


def pair():
    from heteroes.eval.integer_cuda import IntegerCudaKernels

    torch.empty(1, device="cuda")
    staged, original = (IntegerCudaKernels("cuda", magnitude_bits=22) for _ in range(2))
    if staged.arch != "sm_120":
        pytest.skip("key stages are an SM120 route")
    original.attention_key_tile = 0
    return staged, original


@gpu
@pytest.mark.parametrize("keys", [1, 33, 65, 129, 257, 511, 691])  # 692+: the original GQA launch fails (static shared)
@pytest.mark.parametrize("scenario", ["normal", "zeros", "tiny", "invalid", "large"])
def test_key_stages_match_the_original_bits_and_flags(keys, scenario):
    staged, original = pair()
    g = torch.Generator(device="cuda").manual_seed(keys)
    q = torch.randn(14, 1, 64, device="cuda", generator=g)
    k = torch.randn(2, keys, 64, device="cuda", generator=g)
    v = torch.randn_like(k)
    if scenario == "zeros":
        q.zero_()
        k.fill_(-0.0)
        v.fill_(-0.0)
    elif scenario == "tiny":
        q.mul_(2.0**-70)
        k.mul_(2.0**-70)
        v.mul_(2.0**-120)
    elif scenario == "invalid":
        k[0, -1, 0] = float("nan")
        v[1, -1, 1] = float("inf")
    elif scenario == "large":
        q.mul_(2.0**64)
        k.mul_(2.0**64)
        v.fill_(torch.finfo(torch.float32).max)
    flags = staged.new_error_flag(), original.new_error_flag()
    layout = decode_layout([keys], keys)
    a = staged.attention_packed(q, k, v, layout, 7, 0.125, error_flag=flags[0])
    b = original.attention_packed(q, k, v, layout, 7, 0.125, error_flag=flags[1])
    assert staged.attention_stage_launches == 1 and original.attention_stage_launches == 0
    assert flags[0].item() == flags[1].item()
    if not flags[0].item():
        assert torch.equal(a.view(torch.int32), b.view(torch.int32))


@gpu
def test_packed_batch_of_ragged_owners_matches_original():
    staged, original = pair()
    g = torch.Generator(device="cuda").manual_seed(71)
    lengths = [5 + 37 * i for i in range(12)]
    q = torch.randn(14, len(lengths), 64, device="cuda", generator=g)
    k = torch.randn(2, len(lengths) * 512, 64, device="cuda", generator=g)
    v = torch.randn_like(k)
    layout = decode_layout(lengths, 512)
    a = staged.attention_packed(q, k, v, layout, 7, 0.125)
    b = original.attention_packed(q, k, v, layout, 7, 0.125)
    assert torch.equal(a.view(torch.int32), b.view(torch.int32))


@gpu
def test_opt_in_shared_stage_replays_with_changed_live_query():
    staged, original = pair()
    q = torch.randn(14, 1, 64, device="cuda")
    k = torch.randn(2, 512, 64, device="cuda")
    v = torch.randn_like(k)
    layout = decode_layout([77], 512)  # a 64 KiB stage: needs the opt-in shared-memory limit
    flag = staged.new_error_flag()
    staged.attention_packed(q, k, v, layout, 7, 0.125, error_flag=flag)
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        out = staged.attention_packed(q, k, v, layout, 7, 0.125, error_flag=flag)
    for _ in range(2):
        q.mul_(0.75)
        graph.replay()
        expected = original.attention_packed(q, k, v, layout, 7, 0.125)
        assert flag.item() == 0 and torch.equal(out.view(torch.int32), expected.view(torch.int32))
