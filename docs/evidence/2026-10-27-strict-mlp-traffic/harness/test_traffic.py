"""S1 FP32 handoff must equal the original projected-pair/SiLU/quantization sequence."""
import pytest
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval import integer_reference,reference_ops
from traffic import TrafficKernels

@pytest.mark.parametrize('rows,width,n',[(17,80,35),(32,896,4864),(33,1040,65)])
@pytest.mark.parametrize('bias',[False,True])
def test_gate_up_planes_and_flags_match_original_sequence(rows,width,n,bias):
    g=torch.Generator(device='cuda').manual_seed(178)
    x=torch.randn(rows,width,device='cuda',generator=g)
    a=(torch.randn(n,width,device='cuda',generator=g)*.03).half()
    b=(torch.randn(n,width,device='cuda',generator=g)*.03).half()
    biases=tuple(torch.randn(n,device='cuda',generator=g).half() for _ in range(2)) if bias else (None,None)
    k=IntegerCudaKernels('cuda',magnitude_bits=22);fast=TrafficKernels('cuda',magnitude_bits=22)
    fa,fb=k.new_error_flag(),fast.new_error_flag()
    prepared=k.quantize_input(x,_packed=True,error_flag=fa)
    pair=k.linear_many(x,(a,b),biases,error_flag=fa,decode_target_ctas_per_sm=8,prepared=prepared)
    expected=k.silu_mul_quantized(*pair,error_flag=fa)
    actual=fast.gate_up_silu_quantized(prepared,a,b,biases,error_flag=fb,decode_target_ctas_per_sm=8)
    assert fa.item()==fb.item()==0
    assert all(torch.equal(l.view(torch.uint8),r.view(torch.uint8)) for l,r in zip(expected,actual))
    if width==80:
        y=integer_reference.linear(x.cpu(),a.cpu(),None if not bias else biases[0].cpu(),magnitude_bits=22)
        z=integer_reference.linear(x.cpu(),b.cpu(),None if not bias else biases[1].cpu(),magnitude_bits=22)
        cpu=k.quantize_input(reference_ops.mul(reference_ops.silu(y),z).cuda(),_packed=True)
        assert all(torch.equal(l.view(torch.uint8),r.view(torch.uint8)) for l,r in zip(cpu,actual))
    fb.fill_(2)
    fast.gate_up_silu_quantized(prepared,a,b,biases,error_flag=fb,decode_target_ctas_per_sm=8)
    assert fb.item()==2
