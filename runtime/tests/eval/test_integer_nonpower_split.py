"""Nonpower split counts retain exact integer reduction, including empty K partitions and tails."""

import os

import pytest
import torch

from heteroes.eval import integer_reference as reference

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
@pytest.mark.parametrize("width", [16, 1040, 4864])
def test_nonpower_splits_match_cpu_integer_oracle(magnitude_bits, width):
    from heteroes.eval.integer_cuda import IntegerCudaKernels

    g = torch.Generator().manual_seed(width)
    x = torch.randn(17, width, generator=g)
    w = (torch.randn(35, width, generator=g) * 0.03).half()
    w[0, 0], w[-1, -1] = 65504.0, 2.0**-24
    bias = torch.randn(35, generator=g).half()
    expected = reference.linear(x, w, bias, magnitude_bits=magnitude_bits).view(torch.int32)
    kernels = IntegerCudaKernels("cuda", magnitude_bits=magnitude_bits)
    gx, gw, gb = x.cuda(), w.cuda(), bias.cuda()
    for split in (3, 5, 7):
        for columns in (32, 64):
            flag = kernels.new_error_flag()
            actual = kernels._linear(
                gx, gw, gb, error_flag=flag, split_k=split, implementation="mma", stream_columns=columns
            )
            assert int(flag.item()) == 0
            assert torch.equal(actual.cpu().view(torch.int32), expected), (split, columns)
