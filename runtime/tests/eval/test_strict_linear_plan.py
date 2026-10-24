"""Execution decomposition changes must preserve the tree, cache identity and allocation bounds."""

import os

import pytest
import torch

from heteroes.eval import reference_ops as ops
from heteroes.eval import strict_cuda as sc
from heteroes.eval.reference_ops import ReferenceArithmeticError


@pytest.mark.parametrize("width", [3, 31, 33, 129, 768, 896, 1024, 2048, 4096, 4864, 8193, 32768])
def test_execution_plans_keep_the_same_cpu_tree_for_every_selected_batch(width):
    gen = torch.Generator().manual_seed(width)
    values = torch.randn(4, width, generator=gen) * torch.logspace(-5, 5, width)
    values[1] = -0.0
    values[2, ::3] = -0.0
    expected = ops.pairwise_sum(values).view(torch.int32)
    for rows in (1, 2, 8, 32, 129):
        plan, tile = sc.linear_execution_plan(width, rows)
        assert tile in (1, 2, 4, 8)
        assert plan.warps * plan.outputs_per_block * 32 <= 1024
        assert plan.per_thread in (1, 2, 4, 8, 16, 32)
        actual = sc.emulate_blocked_sum(values, plan)
        assert torch.equal(actual.view(torch.int32), expected)


@pytest.mark.parametrize("width,rows", [(0, 1), (32769, 1), (3, 0), (3, True), (3, 1.5)])
def test_execution_plan_rejects_invalid_dimensions(width, rows):
    with pytest.raises(ReferenceArithmeticError):
        sc.linear_execution_plan(width, rows)


gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@gpu
def test_one_kernel_owner_cannot_reuse_the_wrong_decomposition_between_batch_sizes():
    kernels = sc.StrictCudaKernels("cuda")
    gen = torch.Generator().manual_seed(918)
    x = torch.randn(9, 1024, generator=gen)
    x[1] = -0.0
    x[2] *= 1e-38
    w = torch.randn(7, 1024, generator=gen).half()
    b = torch.randn(7, generator=gen).half()
    expected = ops.linear(x, w, b)
    # Explicit one-row tiles make the cache key collide unless the decomposition is part of the key.
    for rows in (1, 9, 3, 1, 9):
        for tile in (None, 1, 4, 8):
            actual = kernels.linear(x[:rows].cuda(), w.cuda(), b.cuda(), row_tile=tile)
            assert torch.equal(actual.cpu().view(torch.int32), expected[:rows].view(torch.int32))
    builds = kernels.identity()["builds"]
    assert any("-per8" in name for name in builds)
    assert any("-per16" in name for name in builds)


@gpu
def test_projection_underflow_rounding_must_not_be_replaced_with_unrestricted_native_ftz():
    # min_normal * the largest half below 1: some normal inputs round upward to min_normal.
    # Native mul.rn.ftz flushes *before* that rounding on the surveyed GPUs. The strict path must not.
    values = torch.arange(0x00800000, 0x00802000, dtype=torch.int32).view(torch.float32)[:, None]
    w = torch.tensor([[1.0 - 2.0**-11], [-1.0 + 2.0**-11]], dtype=torch.float16)
    expected = ops.mul(values, w[:, 0][None])
    assert bool((expected.abs() == torch.finfo(torch.float32).tiny).any())
    kernels = sc.StrictCudaKernels("cuda")
    actual = kernels.linear(values.cuda(), w.cuda())
    assert torch.equal(actual.cpu().view(torch.int32), expected.view(torch.int32))
