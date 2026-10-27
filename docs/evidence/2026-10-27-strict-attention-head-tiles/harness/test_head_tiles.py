"""Repeat-head tiling must retain all checked loads and exact tree nodes, including inactive head lanes."""
import pytest
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels
from head_tiles import HeadTileKernels

@pytest.mark.parametrize('tile',[2,4])
@pytest.mark.parametrize('repeats,keys,dim',[(6,1,64),(7,33,64),(7,129,64),(8,65,32),(7,33,128)])
@pytest.mark.parametrize('scenario',['normal','zeros','tiny','invalid','large'])
def test_partial_head_tiles_match_original_bits_and_flags(tile,repeats,keys,dim,scenario):
    g=torch.Generator(device='cuda').manual_seed(repeats+keys)
    q=torch.randn(2*repeats,1,dim,device='cuda',generator=g)
    k=torch.randn(2,keys,dim,device='cuda',generator=g);v=torch.randn_like(k)
    if scenario=='zeros':q.zero_();k.fill_(-0.);v.fill_(-0.)
    elif scenario=='tiny':q.mul_(2.**-70);k.mul_(2.**-70);v.mul_(2.**-120)
    elif scenario=='invalid':q[-1,0,-1]=float('nan');v[0,-1,0]=float('inf')
    elif scenario=='large':q.mul_(2.**64);k.mul_(2.**64);v.fill_(torch.finfo(torch.float32).max)
    base=StrictCudaKernels('cuda');base._attention_entry='strict_attention_gqa'
    fast=HeadTileKernels('cuda',head_tile=tile,magnitude_bits=22)
    fa,fb=base.new_error_flag(),fast.new_error_flag()
    args=(q,k,v,[(1,keys,keys-1)],repeats,.125)
    a=base.attention_packed(*args,error_flag=fa);b=fast.attention_packed(*args,error_flag=fb)
    assert fa.item()==fb.item(),scenario
    if not fa.item():assert torch.equal(a.view(torch.int32),b.view(torch.int32))
