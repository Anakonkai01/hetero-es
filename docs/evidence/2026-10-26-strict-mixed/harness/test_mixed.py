import os

import pytest
import torch

from mixed_reference import quantize_rows, linear


def test_small_weight_quantizer_uses_even_ties_and_flushes_subnormal_inputs():
    x=torch.tensor([[1.,1.015625,1.046875,-1.015625,-1.046875,-0.,2**-127]])
    q,e=quantize_rows(x,6)
    assert q.tolist()==[[32,32,34,-32,-34,0,0]] and e.tolist()==[0]


def test_mixed_precision_known_dot_and_bias():
    actual=linear(torch.tensor([[1.,-1.]]),torch.tensor([[.5,-.5]],dtype=torch.float16),
                  torch.tensor([.25],dtype=torch.float16),activation_bits=14,weight_bits=6)
    assert actual.item()==1.25


@pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')
@pytest.mark.parametrize('activation_bits,weight_bits',[(22,6),(14,6),(22,22),(14,14)])
def test_mixed_cuda_matches_fraction_oracle_for_scalar_mma_tails_offsets_and_split(activation_bits,weight_bits):
    from mixed_cuda import MixedKernels
    k=MixedKernels('cuda',activation_bits=activation_bits,weight_bits=weight_bits)
    gen=torch.Generator().manual_seed(23971)
    for rows,width,outputs,offset in [(1,65,7,0),(8,128,9,1),(32,67,13,0)]:
        x=torch.randn(rows,width,generator=gen)
        w=(torch.randn(outputs,width,generator=gen)*.125).half()
        x[0,:2]=torch.tensor([-0.,2**-127])
        w[0,0]=2**-24
        backing=torch.empty(offset+w.numel(),dtype=torch.float16,device='cuda')
        live=backing[offset:].reshape(w.shape);live.copy_(w)
        bias=torch.randn(outputs,generator=gen).half()
        expected=linear(x,w,bias,activation_bits=activation_bits,weight_bits=weight_bits)
        for split in (1,2):
            actual=k.linear(x.cuda(),live,bias.cuda(),split_k=split)
            assert torch.equal(actual.cpu().view(torch.int32),expected.view(torch.int32)),(rows,width,offset,split)
    identity=k.identity()
    assert identity['mixedPrecision']['weightBits']==weight_bits
    assert identity['mixedPrecision']['activationBits']==activation_bits
