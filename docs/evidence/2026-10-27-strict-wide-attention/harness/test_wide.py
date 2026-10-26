"""Four score lanes and two value workers must retain all original rounded trees and flags."""
import pytest
import torch
from heteroes.eval import strict_cuda as sc
from test_strict_attention_split import tensors,bits
from test_strict_cuda import _reference_attention
from wide_attention import WideAttention

@pytest.fixture(scope='module')
def kernels():return sc.StrictCudaKernels('cuda'),WideAttention()

@pytest.mark.parametrize('keys',[1,31,32,33,64,65,80,127,128])
@pytest.mark.parametrize('pattern',['normal','negative_zero','cancellation','subnormal','subnormal_keys','equal_scores'])
def test_wide_block_equals_original_and_independent_cpu(kernels,keys,pattern):
    old,new=kernels
    q,k,v=tensors(keys+33,14,2,3,keys*3,64,pattern)
    limits=[keys-1,keys//2,max(0,keys-3)]
    layout=sc._PackedAttentionLayout(torch.tensor([[i*keys,keys,limits[i]] for i in range(3)],dtype=torch.int32,device='cuda'),3,keys*3,keys)
    flags=[old.new_error_flag(),old.new_error_flag()]
    control=old.attention_packed(q,k,v,layout,7,.125,error_flag=flags[0])
    actual=new.run(q,k,v,layout,flags[1])
    assert torch.equal(bits(control),bits(actual)) and flags[0].item()==flags[1].item()==0
    expected=torch.cat([_reference_attention(q[:,i:i+1].cpu(),k[:,i*keys:(i+1)*keys].cpu(),v[:,i*keys:(i+1)*keys].cpu(),limits[i],7,.125) for i in range(3)])
    assert torch.equal(bits(actual.cpu()),bits(expected))

@pytest.mark.parametrize('which',['q','k','v'])
def test_failure_flags_match_even_for_masked_nonfinites(kernels,which):
    old,new=kernels;q,k,v=tensors(88,14,2,1,65,64,'normal')
    {'q':q,'k':k,'v':v}[which][0,-1,3]=float('nan')
    layout=sc._PackedAttentionLayout(torch.tensor([[0,65,32]],dtype=torch.int32,device='cuda'),1,65,65)
    flags=[old.new_error_flag(),old.new_error_flag()]
    control=old.attention_packed(q,k,v,layout,7,.125,error_flag=flags[0]);actual=new.run(q,k,v,layout,flags[1])
    assert torch.equal(bits(control),bits(actual)) and flags[0].item()==flags[1].item()!=0
