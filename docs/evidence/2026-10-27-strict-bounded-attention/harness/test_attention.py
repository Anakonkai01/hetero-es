"""A bounded score tree must keep rounded nodes and fallback on tiny/large/masked invalid inputs."""
import pytest
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels
from bounded import BoundedAttentionKernels

@pytest.mark.parametrize('length,keys',[(1,1),(1,33),(1,129),(2,7),(7,33),(33,33),(65,65)])
@pytest.mark.parametrize('scenario',['normal','tiny','large','zeros','masked-invalid'])
def test_score_guard_keeps_all_bits_and_error_flags(length,keys,scenario):
    g=torch.Generator(device='cuda').manual_seed(length+keys)
    q=torch.randn(14,length,64,generator=g,device='cuda')
    k=torch.randn(2,keys,64,generator=g,device='cuda');v=torch.randn_like(k)
    if scenario=='tiny':q.fill_(2.**-65);k.fill_(2.**-65);k[:,0,:]=0
    elif scenario=='large':q[0,0,:]=2.**70;k[0,-1,:]=2.**70
    elif scenario=='zeros':q.zero_();k.fill_(-0.);v.fill_(-0.)
    elif scenario=='masked-invalid':k[0,-1,0]=float('nan');v[0,-1,1]=float('inf')
    spans=[(length,keys,keys-length)]
    base=StrictCudaKernels('cuda');fast=BoundedAttentionKernels('cuda',magnitude_bits=22)
    fa,fb=base.new_error_flag(),fast.new_error_flag()
    scale=2.**120 if scenario=='tiny' else .125
    a=base.attention_packed(q,k,v,spans,7,scale,error_flag=fa)
    b=fast.attention_packed(q,k,v,spans,7,scale,error_flag=fb)
    assert fa.item()==fb.item()
    if fa.item()==0:assert torch.equal(a.view(torch.int32),b.view(torch.int32)),(length,keys,scenario)


def test_fused_quant_source_suffix_is_preserved():
    from heteroes.eval.integer_cuda import IntegerCudaKernels
    base=IntegerCudaKernels('cuda',magnitude_bits=22);fast=BoundedAttentionKernels('cuda',magnitude_bits=22)
    torch.manual_seed(14)
    a=torch.randn(17,80,device='cuda');b=torch.randn_like(a)
    x=base.silu_mul_quantized(a,b);y=fast.silu_mul_quantized(a,b)
    assert all(torch.equal(l.view(torch.uint8),r.view(torch.uint8)) for l,r in zip(x,y))
