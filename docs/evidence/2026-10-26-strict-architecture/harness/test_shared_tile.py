import os

import pytest
import torch

from heteroes.eval.integer_reference import linear
from shared_tile import SharedTileKernels


@pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')
@pytest.mark.parametrize('bits',[14,22])
@pytest.mark.parametrize('nsub,k_tile',[(1,32),(2,64)])
def test_shared_radix_tile_keeps_cpu_bits_for_ragged_rows_k_splits_and_offset_weights(bits,nsub,k_tile):
    kernel=SharedTileKernels('cuda',magnitude_bits=bits,nsub=nsub,k_tile=k_tile)
    generator=torch.Generator().manual_seed(8832)
    for rows,width,outputs,offset in ((3,33,7,0),(19,67,37,0),(32,128,65,0),(17,64,13,1),(5,1,7,0)):
        x=torch.randn(rows,width,generator=generator)
        x[0,0]=-0.
        w=(torch.randn(outputs,width,generator=generator)*.125).half()
        w[0,0]=2.0**-24
        bias=torch.randn(outputs,generator=generator).half()
        backing=torch.empty(w.numel()+offset,dtype=torch.float16,device='cuda')
        live=backing[offset:].reshape(w.shape);live.copy_(w)
        expected=linear(x,w,bias,magnitude_bits=bits).view(torch.int32)
        for split in (1,2,8):
            actual=kernel.linear(x.cuda(),live,bias.cuda(),implementation='mma',split_k=split)
            assert torch.equal(actual.cpu().view(torch.int32),expected),(rows,width,outputs,offset,split,bits,nsub,k_tile)
