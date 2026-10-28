import os
import pytest
import torch

from heteroes.eval import reference_ops as ops
from heteroes.eval.reference_ops import ReferenceArithmeticError

pytestmark=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')

def reference(q,k,v,past,repeats,scale):
    k=k.repeat_interleave(repeats,0);v=v.repeat_interleave(repeats,0)
    scores=ops.mul(ops.pairwise_sum(ops.mul(q[:,:,None,:],k[:,None,:,:])),scale)
    mask=torch.arange(k.shape[1])[None,:]<=past+torch.arange(q.shape[1])[:,None]
    weights=ops.softmax(scores,mask)
    out=ops.pairwise_sum(ops.mul(weights[:,:,None,:],v.transpose(-1,-2)[:,None,:,:]))
    return out.transpose(0,1).reshape(q.shape[1],-1)

@pytest.mark.parametrize('mode',['score','full'])
def test_warp_attention_matches_cpu_for_pruned_trees_gqa_tails_and_packed_ranges(mode):
    from warp_attention import WarpAttentionKernels
    kernel=WarpAttentionKernels('cuda',mode=mode)
    rng=torch.Generator().manual_seed(1949)
    for dim,spans in [(1,[(1,1,0)]),(13,[(2,33,31),(1,65,64)]),
                      (32,[(3,31,28),(1,32,31)]),(64,[(2,65,63),(1,257,256)]),
                      (128,[(2,129,127)]),(256,[(1,17,16)])]:
        qs=[];ks=[];vs=[];expected=[]
        for length,keys,past in spans:
            q=torch.randn((4,length,dim),generator=rng)*.25
            k=torch.randn((2,keys,dim),generator=rng)*.25
            v=torch.randn((2,keys,dim),generator=rng)
            q[0,0,0]=-0.;v[0,0,0]=2.0**-140
            qs.append(q);ks.append(k);vs.append(v)
            expected.append(reference(q,k,v,past,2,.125))
        actual=kernel.attention_packed(torch.cat(qs,1).cuda(),torch.cat(ks,1).cuda(),
                                       torch.cat(vs,1).cuda(),spans,2,.125)
        assert torch.equal(actual.cpu().view(torch.int32),torch.cat(expected,0).view(torch.int32)),(mode,dim)

@pytest.mark.parametrize('mode',['score','full'])
@pytest.mark.parametrize('failure',['nan_key','inf_value','masked_overflow'])
def test_masked_invalid_values_still_fail(mode,failure):
    from warp_attention import WarpAttentionKernels
    kernel=WarpAttentionKernels('cuda',mode=mode)
    q=torch.ones((2,2,64));k=torch.ones((1,2,64));v=torch.ones_like(k)
    if failure=='nan_key':k[0,1,0]=float('nan')
    elif failure=='inf_value':v[0,1,0]=float('inf')
    else:q[0,0,0]=2.0**100;k[0,1,0]=2.0**100
    with pytest.raises(ReferenceArithmeticError):
        kernel.attention_packed(q.cuda(),k.cuda(),v.cuda(),[(2,2,0)],2,.125)
