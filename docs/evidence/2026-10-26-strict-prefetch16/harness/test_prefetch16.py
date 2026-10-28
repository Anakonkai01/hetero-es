import os

import pytest
import torch

from heteroes.eval.integer_reference import linear
from prefetch16_cuda import Prefetch16Kernels


@pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or not torch.cuda.is_available(), reason='GPU opt-in')
@pytest.mark.parametrize('bits', [14, 22])
def test_warp_shared_tile_reads_keep_cpu_bits_for_tails_offsets_splits_and_empty_partitions(bits):
    kernel = Prefetch16Kernels('cuda', magnitude_bits=bits)
    generator = torch.Generator().manual_seed(33037)
    for rows, width, outputs, offset in ((3, 33, 7, 0), (32, 64, 19, 0), (17, 66, 11, 0),
                                          (8, 128, 9, 1), (19, 64, 9, 4), (3, 1, 7, 0)):
        x = torch.randn(rows, width, generator=generator)
        x[0, 0] = -0.0
        w = (torch.randn(outputs, width, generator=generator) * .125).half()
        w[0, 0] = 2.0**-24
        bias = torch.randn(outputs, generator=generator).half()
        backing = torch.empty(w.numel()+offset, dtype=torch.float16, device='cuda')
        live = backing[offset:].reshape(w.shape)
        live.copy_(w)
        expected = linear(x, w, bias, magnitude_bits=bits).view(torch.int32)
        for split, warps, tile in ((1, 4, 16), (8, 4, 16), (2, 8, 32)):
            actual = kernel.linear(x.cuda(), live, bias.cuda(), implementation='mma', split_k=split,
                                   warps=warps, row_tile=tile)
            assert torch.equal(actual.cpu().view(torch.int32), expected), (rows, width, offset, split, warps)
