"""Chunking cannot append zero nodes or omit arithmetic on causally masked keys."""

import os
import pytest
import torch
from heteroes.strict.strict_cuda import StrictCudaKernels
from heteroes.strict.reference_ops import ReferenceArithmeticError
from test_strict_cuda import _reference_attention

pytestmark = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@pytest.fixture(scope="module")
def kernels():
    return StrictCudaKernels("cuda")


@pytest.mark.parametrize("keys", [1, 3, 7, 8, 9, 15, 16, 17, 31, 32, 33, 65, 129, 257, 513, 1025, 4096])
@pytest.mark.parametrize("pattern", ["negative_zero", "negative_normal", "cancellation"])
def test_attention_chunk_tails_match_cpu_including_all_negative_zero(kernels, keys, pattern):
    gen = torch.Generator().manual_seed(keys)
    q = torch.randn(2, 1, 3, generator=gen) * 0.1
    k = torch.randn(1, keys, 3, generator=gen) * 0.1
    if pattern == "negative_zero":
        v = torch.full_like(k, -0.0)
    elif pattern == "negative_normal":
        v = torch.full_like(k, -(2.0**-126))
    else:
        v = torch.tensor([2.0**24, 1.0, -(2.0**24), 1.0]).repeat((keys * 3 + 3) // 4)[: keys * 3].reshape(1, keys, 3)
    expected = _reference_attention(q, k, v, keys - 1, 2, 0.5)
    actual = kernels.attention(q.cuda(), k.cuda(), v.cuda(), keys - 1, 2, 0.5)
    assert torch.equal(actual.cpu().view(torch.int32), expected.view(torch.int32)), (keys, pattern)


def test_causally_masked_dot_overflow_is_not_silently_skipped(kernels):
    q = torch.tensor([[[1e30] * 3, [0.0] * 3]], device="cuda")
    k = torch.tensor([[[0.0] * 3, [0.0] * 3, [1e30] * 3]], device="cuda")
    v = torch.zeros_like(k)
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        kernels.attention(q, k, v, 1, 1, 0.5)
