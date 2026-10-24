"""Decode copy/layout/selection kernels have independent ownership and scalar arithmetic oracles."""

import os

import pytest
import torch

from heteroes.eval import reference_ops as ops
from heteroes.eval.strict_cuda import StrictCudaKernels

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


def decode_kernels():
    from heteroes.eval.strict_decode_cuda import DecodeKernels

    kernels = StrictCudaKernels("cuda")
    return kernels, DecodeKernels(kernels)


@gpu
def test_layout_and_prefix_decode_copy_preserve_bits_and_original_sequence_slots():
    kernels, decode = decode_kernels()
    heads, dim, capacity, context = 2, 8, 3, 16
    keys = torch.zeros((heads, capacity * context, dim), device="cuda")
    values = torch.zeros_like(keys)
    source = torch.arange(heads * 8 * dim, dtype=torch.float32, device="cuda").reshape(heads, 8, dim)
    source[0, 1, 2] = -0.0
    spans = torch.tensor([[0, 3, 0], [3, 5, 32]], dtype=torch.int32, device="cuda")
    decode.prefix(source, -source, spans, keys, values)
    assert torch.equal(keys[:, :3].contiguous().view(torch.int32), source[:, :3].contiguous().view(torch.int32))
    assert torch.equal(keys[:, 32:37].contiguous().view(torch.int32), source[:, 3:].contiguous().view(torch.int32))
    assert not bool(keys[:, 16:32].any())
    owners = torch.tensor([2, 0], device="cuda")
    lengths = torch.tensor([3, 5, 7], dtype=torch.int32, device="cuda")
    ranges = torch.empty((2, 3), dtype=torch.int32, device="cuda")
    positions = torch.empty(2, dtype=torch.long, device="cuda")
    flag = kernels.new_error_flag()
    decode.layout(owners, lengths, ranges, positions, flag, capacity, context)
    kernels.raise_if_error(flag)
    assert positions.tolist() == [7, 3]
    assert ranges.tolist() == [[32, 8, 7], [0, 4, 3]]
    k = torch.arange(heads * 2 * dim, dtype=torch.float32, device="cuda").reshape(heads, 2, dim) + 1000
    v = -torch.arange(2 * heads * dim, dtype=torch.float32, device="cuda").reshape(2, heads * dim) - 2000
    decode.store(k, v, ranges, keys, values)
    assert torch.equal(keys[:, 39], k[:, 0]) and torch.equal(keys[:, 3], k[:, 1])
    assert torch.equal(values[:, 39], v[0].reshape(heads, dim))
    assert torch.equal(values[:, 3], v[1].reshape(heads, dim))
    assert not bool(keys[:, 16:32].any())


@gpu
def test_invalid_layout_positions_set_an_error_and_publish_only_safe_ranges():
    kernels, decode = decode_kernels()
    owners = torch.tensor([0, 1], device="cuda")
    lengths = torch.tensor([-1, 16], dtype=torch.int32, device="cuda")
    ranges = torch.empty((2, 3), dtype=torch.int32, device="cuda")
    positions = torch.empty(2, dtype=torch.long, device="cuda")
    flag = kernels.new_error_flag()
    decode.layout(owners, lengths, ranges, positions, flag, 2, 16)
    assert flag.item() == 4
    assert ranges.tolist() == [[0, 1, 0], [0, 1, 0]] and positions.tolist() == [0, 0]


@gpu
@pytest.mark.parametrize("penalty", [1.0, 1.000000001, 1.3, 0.7])
def test_greedy_ties_penalty_and_publication_use_original_owner_and_canonical_operations(penalty):
    kernels, decode = decode_kernels()
    owners = torch.tensor([2, 0], device="cuda")
    vocab = 513
    scores = torch.zeros((2, vocab), dtype=torch.float32)
    scores[0, [3, 300]] = 12.5
    scores[1] = -1.0
    seen = torch.zeros((3, vocab), dtype=torch.uint8)
    seen[2, 3] = 1
    seen[0, :7] = 1
    inverse = float(ops.reciprocal(torch.tensor(penalty)).item())
    expected = scores.clone()
    if penalty != 1.0:
        for i, owner in enumerate(owners.tolist()):
            used = seen[owner].bool()
            selected = expected[i, used]
            expected[i, used] = torch.where(selected < 0, ops.mul(selected, penalty), ops.mul(selected, inverse))
    maximum = expected.max(dim=1, keepdim=True).values
    ids = torch.arange(vocab)[None]
    expected_ids = torch.where(expected == maximum, ids, vocab).amin(dim=1).tolist()
    tokens = torch.full((3,), -1, dtype=torch.long, device="cuda")
    lengths = torch.tensor([3, 5, 7], dtype=torch.int32, device="cuda")
    result = torch.empty(3, dtype=torch.long, device="cuda")
    gpu_seen, flag = seen.cuda(), kernels.new_error_flag()
    decode.greedy(scores.cuda(), gpu_seen, owners, tokens, result, flag, penalty, inverse)
    decode.publish(owners, lengths, flag, result, advance=False)
    assert result.tolist() == [*expected_ids, 0]
    assert tokens.tolist() == [expected_ids[1], -1, expected_ids[0]]
    assert lengths.tolist() == [3, 5, 7]
    assert not bool(gpu_seen[1].any())
    flag.fill_(2)
    decode.publish(owners, lengths, flag, result, advance=True)
    assert result[-1].item() == 2 and lengths.tolist() == [4, 5, 8]
