import os

import pytest
import torch

from fma_reference import linear


def test_one_round_fma_differs_from_separate_product_and_preserves_internal_subnormals():
    x=torch.tensor([[-(1+2.0**-10),1+2.0**-23]])
    w=torch.tensor([[1.,1+2.0**-10]],dtype=torch.float16)
    actual=linear(x,w)
    assert actual.item()==2.0**-23+2.0**-33
    assert actual.item()!=float((x*w.float()).sum())
    x=torch.tensor([[2.0**-102,2.0**-126,2.0**-126]])
    w=torch.tensor([[2.0**-24,-2.0**-23,2.0**-23]],dtype=torch.float16)
    assert linear(x,w).item()==2.0**-126
    negative=linear(torch.tensor([[2.0**-126]]),torch.tensor([[-2.0**-24]],dtype=torch.float16))
    assert negative.view(torch.int32).item()==-(2**31)


@pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')
def test_fixed_fma_chunks_match_fraction_oracle_for_ragged_shapes_and_live_weights():
    from fma_cuda import OrderedFmaKernels
    kernel=OrderedFmaKernels('cuda')
    generator=torch.Generator().manual_seed(4093)
    for rows,width,outputs,offset in ((1,1,7,0),(3,33,7,0),(19,67,13,0),(32,128,65,0),(5,257,9,1)):
        x=torch.randn(rows,width,generator=generator)
        x[0,0]=-0.
        w=(torch.randn(outputs,width,generator=generator)*.125).half()
        bias=torch.randn(outputs,generator=generator).half()
        backing=torch.empty(w.numel()+offset,dtype=torch.float16,device='cuda')
        live=backing[offset:].reshape(w.shape)
        for factor in (1.,-16.,1.):
            candidate=(w*factor).half();live.copy_(candidate)
            expected=linear(x,candidate,bias)
            actual=kernel.linear(x.cuda(),live,bias.cuda())
            assert torch.equal(actual.cpu().view(torch.int32),expected.view(torch.int32)),(rows,width,offset,factor)


@pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')
def test_gpu_fma_does_not_flush_internal_subnormal_or_change_negative_zero_by_padding():
    from fma_cuda import OrderedFmaKernels
    kernel=OrderedFmaKernels('cuda')
    x=torch.tensor([[2.0**-102,2.0**-126,2.0**-126]])
    w=torch.tensor([[2.0**-24,-2.0**-23,2.0**-23]],dtype=torch.float16)
    expected=linear(x,w)
    actual=kernel.linear(x.cuda(),w.cuda())
    assert torch.equal(actual.cpu().view(torch.int32),expected.view(torch.int32))
    x=torch.tensor([[2.0**-126]])
    w=torch.tensor([[-2.0**-24]],dtype=torch.float16)
    assert kernel.linear(x.cuda(),w.cuda()).cpu().view(torch.int32).item()==-(2**31)
