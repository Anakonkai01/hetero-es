import os
import pytest
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval import integer_reference as ref
from projection_rows import install

pytestmark=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1',reason='GPU opt-in')

@pytest.mark.parametrize('rows,width,outputs',[(19,80,65),(65,96,129),(129,896,1152),(65,4864,80)])
@pytest.mark.parametrize('bias',[False,True])
def test_tile64_preserves_parent_and_cpu_bits(rows,width,outputs,bias):
    torch.manual_seed(4+rows)
    x=torch.randn(rows,width,device='cuda');w=torch.randn(outputs,width,device='cuda').half()
    b=torch.randn(outputs,device='cuda').half() if bias else None
    base=IntegerCudaKernels('cuda',magnitude_bits=22);new=IntegerCudaKernels('cuda',magnitude_bits=22)
    install(new)
    actual=new.linear(x,w,b,row_tile=64);expected=base.linear(x,w,b)
    assert torch.equal(actual.view(torch.int32),expected.view(torch.int32))
    if width==80:
        cpu=ref.linear(x.cpu(),w.cpu(),b.cpu() if b is not None else None,magnitude_bits=22)
        assert torch.equal(actual.cpu().view(torch.int32),cpu.view(torch.int32))
