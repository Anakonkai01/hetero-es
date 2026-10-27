"""Larger shared K/V stages retain ordered 32-key value roots and all original failure checks."""
import pytest
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels
from stages import KeyStageKernels

@pytest.mark.parametrize('tile',[64,128])
@pytest.mark.parametrize('keys',[1,33,65,129,257,511])
@pytest.mark.parametrize('scenario',['normal','zeros','tiny','invalid','large'])
def test_key_staging_matches_original_nodes_and_flags(tile,keys,scenario):
    g=torch.Generator(device='cuda').manual_seed(keys)
    q=torch.randn(14,1,64,device='cuda',generator=g)
    k=torch.randn(2,keys,64,device='cuda',generator=g);v=torch.randn_like(k)
    if scenario=='zeros':q.zero_();k.fill_(-0.);v.fill_(-0.)
    elif scenario=='tiny':q.mul_(2.**-70);k.mul_(2.**-70);v.mul_(2.**-120)
    elif scenario=='invalid':k[0,-1,0]=float('nan');v[1,-1,1]=float('inf')
    elif scenario=='large':q.mul_(2.**64);k.mul_(2.**64);v.fill_(torch.finfo(torch.float32).max)
    base=StrictCudaKernels('cuda');base._attention_entry='strict_attention_gqa'
    fast=KeyStageKernels('cuda',key_tile=tile,magnitude_bits=22)
    fa,fb=base.new_error_flag(),fast.new_error_flag()
    args=(q,k,v,[(1,keys,keys-1)],7,.125)
    a=base.attention_packed(*args,error_flag=fa);b=fast.attention_packed(*args,error_flag=fb)
    assert fa.item()==fb.item()
    if not fa.item():assert torch.equal(a.view(torch.int32),b.view(torch.int32))

def test_optin_shared_stage_replays_with_changed_live_query():
    from dataclasses import replace
    c=KeyStageKernels('cuda',key_tile=128,magnitude_bits=22)
    base=StrictCudaKernels('cuda');q=torch.randn(14,1,64,device='cuda')
    k=torch.randn(2,77,64,device='cuda');v=torch.randn_like(k)
    layout=replace(c.attention_layout([(1,77,76)]),max_keys=512)
    flag=c.new_error_flag();c.attention_packed(q,k,v,layout,7,.125,error_flag=flag)
    graph=torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):out=c.attention_packed(q,k,v,layout,7,.125,error_flag=flag)
    for _ in range(2):
        q.mul_(.75);graph.replay()
        expected=base.attention_packed(q,k,v,layout,7,.125)
        assert flag.item()==0 and torch.equal(out.view(torch.int32),expected.view(torch.int32))
