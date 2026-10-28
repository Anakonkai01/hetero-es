import os
import pytest
import torch
from karatsuba_reference import digits,quantize,linear

def test_all_admitted_integers_have_byte_sized_sum_limbs_and_exact_three_product_identity():
    values=list(range(-8192,8193))
    for q in values:
        low,high,total=digits(q)
        assert -64<=low<=63 and -64<=high<=64 and -128<=total<=127
        assert low+128*high==q and total==low+high
    edge=[-8192,-8128,-8127,-129,-128,-65,-64,-1,0,1,63,64,127,128,8127,8191,8192]
    for a in edge:
        for b in edge:
            a0,a1,asum=digits(a);b0,b1,bsum=digits(b)
            assert -127*(a0*b0)+128*(asum*bsum)+16256*(a1*b1)==a*b
    assert 2*128**2*32768<2**31
    assert (127+128+16256)*128**2*32768<2**63

def test_independent_quantizer_rounds_ties_even_and_flushes_inputs():
    q,e=quantize(torch.tensor([[1.,2.**-13,3*2.**-13,-2.**-13,-3*2.**-13,2.**-140]]))
    assert e==[0] and q==[[4096,0,2,0,-2,0]]

gpu=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')

@gpu
@pytest.mark.parametrize('method',['schoolbook','karatsuba'])
def test_radix128_mma_matches_rational_oracle_for_tails_bias_splits_and_live_weights(method):
    from karatsuba_cuda import KaratsubaKernels
    kernel=KaratsubaKernels('cuda',method=method)
    generator=torch.Generator().manual_seed(2107)
    for rows,width,outputs,offset in [(1,1,7,0),(7,33,9,0),(19,128,17,1),(32,257,33,0)]:
        x=torch.randn(rows,width,generator=generator);x[0,0]=2.**-140
        w=(torch.randn(outputs,width,generator=generator)*.125).half()
        bias=torch.randn(outputs,generator=generator).half()
        backing=torch.empty(w.numel()+offset,dtype=torch.float16,device='cuda')
        live=backing[offset:].reshape(w.shape)
        for factor in (1.,-16.,1.):
            changed=(w*factor).half();live.copy_(changed)
            expected=linear(x,changed,bias)
            for split in (1,8):
                actual=kernel.linear(x.cuda(),live,bias.cuda(),split_k=split)
                assert torch.equal(actual.cpu().view(torch.int32),expected.view(torch.int32)),(method,rows,width,split,factor)

@gpu
def test_max_width_reconstruction_and_all_zero_rows():
    from karatsuba_cuda import KaratsubaKernels
    kernel=KaratsubaKernels('cuda')
    x=torch.full((2,32768),8127./4096);x[1].zero_()
    w=torch.full((3,32768),8124./4096,dtype=torch.float16);w[1].neg_();w[2].zero_()
    expected=linear(x,w)
    for split in (1,8):
        actual=kernel.linear(x.cuda(),w.cuda(),split_k=split)
        assert torch.equal(actual.cpu().view(torch.int32),expected.view(torch.int32))
