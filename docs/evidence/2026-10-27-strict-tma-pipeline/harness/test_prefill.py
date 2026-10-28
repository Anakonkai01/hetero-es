"""The prefill-only adapter must preserve residuals, bias and the deferred monotonic flag."""
import pytest
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval import reference_ops
from prefill import PrefillTransport

@pytest.mark.parametrize('prepared',[False,True])
def test_adapter_preserves_existing_projection_and_residual(prepared):
    g=torch.Generator(device='cuda').manual_seed(69)
    k=IntegerCudaKernels('cuda',magnitude_bits=22)
    x=torch.randn(129,80,generator=g,device='cuda')
    w=torch.randn(35,80,generator=g,device='cuda').half()
    b=torch.randn(35,generator=g,device='cuda').half()
    residual=torch.randn(129,35,generator=g,device='cuda')
    flag=k.new_error_flag()
    p=k.quantize_input(x,_packed=True,error_flag=flag) if prepared else None
    expected=k._linear(x,w,b,prepared=p,residual=residual,error_flag=flag)
    t=PrefillTransport(k)
    for enabled in (False,True):
        t.enabled=enabled
        out=k._linear(x,w,b,prepared=p,residual=residual,error_flag=flag)
        assert flag.item()==0
        assert torch.equal(out.view(torch.int32),expected.view(torch.int32))
    assert t.calls==1
    flag.fill_(2)
    k._linear(x,w,b,prepared=p,error_flag=flag)
    assert flag.item()==2
