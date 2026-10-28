import os
import pytest
import torch
from staged_prefetch import StagedPrefetchKernels
from heteroes.eval.integer_reference import linear

gpu=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')

@gpu
@pytest.mark.parametrize('bits',[14,22])
@pytest.mark.parametrize('stages',[2,4,8])
def test_pipeline_keeps_the_cpu_bits_for_tails_unaligned_storage_and_split(bits,stages):
    k=StagedPrefetchKernels('cuda',magnitude_bits=bits,stages=stages)
    gen=torch.Generator().manual_seed(99731)
    for rows,width,outputs,offset in ((3,33,7,0),(16,64,16,0),(32,66,17,0),(8,128,9,1),(5,64,13,1)):
        x=torch.randn(rows,width,generator=gen)
        x[0,:3]=torch.tensor([-0.,2**-127,-2**-127])
        w=(torch.randn(outputs,width,generator=gen)*.125).half()
        w[0,0]=2**-24
        bias=torch.randn(outputs,generator=gen).half()
        backing=torch.empty(w.numel()+offset,dtype=torch.float16,device='cuda')
        live=backing[offset:].reshape(w.shape);live.copy_(w)
        expected=linear(x,w,bias,magnitude_bits=bits)
        for split in (1,2,8):
            actual=k.linear(x.cuda(),live,bias.cuda(),split_k=split,implementation='mma')
            assert torch.equal(actual.cpu().view(torch.int32),expected.view(torch.int32)),(rows,width,offset,split)
