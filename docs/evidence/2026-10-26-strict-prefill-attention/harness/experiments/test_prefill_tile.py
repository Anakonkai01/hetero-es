import os
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path('runtime/tests/eval').resolve()))
from test_strict_attention_split import tensors, bits, run
from test_strict_cuda import _reference_attention
from heteroes.eval.strict_cuda import StrictCudaKernels
from prefill_tile import install

pytestmark = pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1', reason='GPU opt-in')

@pytest.fixture(scope='module',params=[(8,1),(2,7),(4,3)])
def kernels(request):
    original = StrictCudaKernels('cuda'); original.used = []
    original._attention_entry = 'strict_attention'
    tiled = StrictCudaKernels('cuda'); tiled.used = []
    install(tiled,*request.param)
    return original, tiled

@pytest.mark.parametrize('dim,repeats,spans', [
    (64, 7, [(17, 23, 6), (9, 142, 133), (1, 1, 0)]),
    (32, 1, [(8, 31, 23), (3, 33, 30)]),
    (128, 2, [(9, 70, 61), (3, 5, 2)]),
    (64, 2, [(7, 8, 1), (8, 32, 24), (9, 65, 56)]),
])
@pytest.mark.parametrize('pattern', ['normal', 'cancellation', 'negative_zero', 'subnormal', 'subnormal_keys', 'equal_scores'])
def test_bits_and_flags(kernels, dim, repeats, spans, pattern):
    original, tiled = kernels
    qs, ks, vs = [], [], []
    for j, (length, keys, past) in enumerate(spans):
        q, k, v = tensors(j+5, 2*repeats, 2, length, keys, dim, pattern)
        qs.append(q); ks.append(k); vs.append(v)
    args = (torch.cat(qs,1), torch.cat(ks,1), torch.cat(vs,1), spans, repeats, 0.125)
    flag = tiled.new_error_flag()
    actual = tiled.attention_packed(*args, error_flag=flag)
    expected_flag = original.new_error_flag()
    expected = original.attention_packed(*args, error_flag=expected_flag)
    assert torch.equal(bits(actual), bits(expected))
    assert flag.item() == expected_flag.item()
    assert tiled.tile_launches > 0

def test_cpu_oracle_and_masked_failures(kernels):
    original, tiled = kernels
    spans = [(9, 33, 24), (3, 7, 4)]
    qs, ks, vs, cpu = [], [], [], []
    for j, (length, keys, past) in enumerate(spans):
        q,k,v = tensors(j+8, 14, 2, length, keys, 64, 'normal')
        qs.append(q); ks.append(k); vs.append(v)
        cpu.append(_reference_attention(q.cpu(), k.cpu(), v.cpu(), past, 7, .125))
    q,k,v = torch.cat(qs,1),torch.cat(ks,1),torch.cat(vs,1)
    actual=tiled.attention_packed(q,k,v,spans,7,.125)
    assert torch.equal(bits(actual.cpu()), bits(torch.cat(cpu)))
    for where in ('masked_value_inf', 'masked_score_overflow', 'query_inf'):
        a,b,c=q.clone(),k.clone(),v.clone()
        if where == 'masked_value_inf': c[0,32,3]=float('inf')
        elif where == 'masked_score_overflow': b[1,32]=1e30; a[7:,0]=1e30
        else: a[0,0,3]=float('inf')
        f,g=tiled.new_error_flag(),original.new_error_flag()
        out=tiled.attention_packed(a,b,c,spans,7,.125,error_flag=f)
        control=original.attention_packed(a,b,c,spans,7,.125,error_flag=g)
        assert f.item() == g.item() != 0
        assert torch.equal(bits(out),bits(control))
