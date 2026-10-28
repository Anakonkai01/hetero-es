import os,sys
from pathlib import Path
import pytest,torch
sys.path.insert(0,str(Path('runtime/tests/eval').resolve()))
from heteroes.eval.strict_cuda import StrictCudaKernels
from test_strict_attention_split import tensors,bits
from test_strict_cuda import _reference_attention
from gqa_fast import install
pytestmark=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1',reason='GPU opt-in')

@pytest.fixture(scope='module')
def kernels():
    a,b=StrictCudaKernels('cuda'),StrictCudaKernels('cuda')
    a._attention_entry='strict_attention';b._attention_entry='strict_attention_gqa';install(b)
    return a,b

@pytest.mark.parametrize('dim,repeats,keys,length',[(64,7,31,1),(64,7,128,1),(64,7,270,1),(64,7,512,1),(128,2,1025,1),(32,3,1025,1),(64,7,300,4),(256,2,65,2)])
@pytest.mark.parametrize('pattern',['normal','cancellation','negative_zero','subnormal','subnormal_keys','equal_scores'])
def test_fast_gqa_preserves_all_bits(kernels,dim,repeats,keys,length,pattern):
    q,k,v=tensors(47,2*repeats,2,length,keys,dim,pattern)
    fs=[x.new_error_flag() for x in kernels]
    outs=[o.attention(q,k,v,keys-length,repeats,.125,error_flag=f) for o,f in zip(kernels,fs)]
    assert torch.equal(bits(outs[0]),bits(outs[1]));assert fs[0].item()==fs[1].item()

@pytest.mark.parametrize('where',['masked_value_inf','masked_score_overflow','query_inf','value_nan'])
def test_fast_gqa_preserves_failures_and_cpu(kernels,where):
    q,k,v=tensors(15,14,2,4,270,64,'normal')
    if where=='masked_value_inf':v[0,269,3]=float('inf')
    elif where=='masked_score_overflow':k[1,269]=1e30;q[7:,0]=1e30
    elif where=='query_inf':q[0,0,3]=float('inf')
    else:v[1,5,2]=float('nan')
    fs=[x.new_error_flag() for x in kernels]
    outs=[o.attention(q,k,v,266,7,.125,error_flag=f) for o,f in zip(kernels,fs)]
    assert torch.equal(bits(outs[0]),bits(outs[1]));assert fs[0].item()==fs[1].item()!=0

def test_fast_gqa_matches_cpu_and_packed_spans(kernels):
    qs,ks,vs,expected=[],[],[],[];spans=[(3,33,30),(1,512,511),(2,257,255)]
    for length,keys,past in spans:
        q,k,v=tensors(7,14,2,length,keys,64,'normal');qs.append(q);ks.append(k);vs.append(v)
        expected.append(_reference_attention(q.cpu(),k.cpu(),v.cpu(),past,7,.125))
    out=kernels[1].attention_packed(torch.cat(qs,1),torch.cat(ks,1),torch.cat(vs,1),spans,7,.125)
    assert torch.equal(bits(out.cpu()),bits(torch.cat(expected)))
