"""A CTA may finish its own QKV and consume that cache slot after a CTA memory barrier."""
import pytest
import torch
from heteroes.eval import strict_cuda as sc
from heteroes.eval.integer_cuda import IntegerCudaKernels
from fusion import FusedKernels

@pytest.mark.parametrize('rows,bias',[(2,False),(17,True),(32,False)])
@pytest.mark.parametrize('scenario',['normal','zeros','invalid-weight','invalid-cache','overflow'])
def test_fused_attention_and_cache_match_existing_two_kernel_path(rows,bias,scenario):
    g=torch.Generator(device='cuda').manual_seed(657)
    base=IntegerCudaKernels('cuda',magnitude_bits=22);fast=FusedKernels('cuda',magnitude_bits=22)
    x=torch.randn(rows,896,device='cuda',generator=g)
    weights=tuple((torch.randn(n,896,device='cuda',generator=g)*.03).half() for n in (896,128,128))
    biases=tuple(torch.randn(n,device='cuda',generator=g).half() for n in (896,128,128)) if bias else (None,None,None)
    if scenario=='zeros':x.zero_()
    elif scenario=='invalid-weight':weights[0][0,0]=float('nan')
    elif scenario=='overflow':x.mul_(2.**110);weights[0].fill_(65504.)
    cos=torch.randn(rows,64,device='cuda',generator=g);sin=torch.randn_like(cos)
    ranges=torch.tensor([(i*64,2+i%17,1+i%17) for i in range(rows)],dtype=torch.int32,device='cuda')
    keys=torch.randn(2,rows*64,64,device='cuda',generator=g);values=torch.randn_like(keys)
    if scenario=='invalid-cache':keys[0,0,0]=float('nan');values[1,0,1]=float('inf')
    ka,va,kb,vb=keys.clone(),values.clone(),keys.clone(),values.clone()
    fa,fb=base.new_error_flag(),fast.new_error_flag()
    prepared=base.quantize_input(x,_packed=True,error_flag=fa)
    # Independent quantization preserves invalid-activation flags on both owners.
    other=fast.quantize_input(x,_packed=True,error_flag=fb)
    q=base.qkv_rope_store(prepared,weights,biases,cos,sin,14,2,ranges,ka,va,error_flag=fa,decode_target_ctas_per_sm=8)
    assert q is not None
    layout=sc._PackedAttentionLayout(ranges,rows,rows*64,64)
    expected=base.attention_packed(q,ka,va,layout,7,.125,error_flag=fa)
    actual=fast.qkv_attention(other,weights,biases,cos,sin,14,2,ranges,kb,vb,.125,max_keys=64,error_flag=fb,decode_target_ctas_per_sm=8)
    assert fa.item()==fb.item()
    assert torch.equal(ka.view(torch.int32),kb.view(torch.int32))
    assert torch.equal(va.view(torch.int32),vb.view(torch.int32))
    if not fa.item():assert torch.equal(expected.view(torch.int32),actual.view(torch.int32))
