"""Shared staging must preserve the tree at its memory cutoff and across capped grid-stride tiles."""

import os
import pytest
import torch
from heteroes.eval import reference_ops as ops
from heteroes.eval.strict_cuda import StrictCudaKernels

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@gpu
@pytest.mark.parametrize("width", [9216, 9217, 32768])
def test_staging_cutoff_and_max_width_match_cpu_oracle(width):
    gen = torch.Generator().manual_seed(width)
    x = torch.randn(3, width, generator=gen)
    x[1] = -0.0
    w = (torch.randn(5, width, generator=gen) * 0.03).half()
    expected = ops.linear(x, w)
    actual = StrictCudaKernels("cuda").linear(x.cuda(), w.cuda())
    assert torch.equal(actual.cpu().view(torch.int32), expected.view(torch.int32))


@gpu
def test_grid_stride_keeps_register_weights_after_shared_activation_reuse():
    rows = 262145
    values = torch.arange(rows, dtype=torch.float32, device="cuda")
    x = values[:, None].expand(rows, 3).contiguous()
    w = torch.ones(2, 3, dtype=torch.float16, device="cuda")
    actual = StrictCudaKernels("cuda").linear(x, w, row_tile=4)
    expected = (values * 3)[:, None].expand_as(actual)
    assert torch.equal(actual.view(torch.int32), expected.contiguous().view(torch.int32))
