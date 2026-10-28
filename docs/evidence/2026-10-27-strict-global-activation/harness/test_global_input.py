"""Removing activation shared staging must retain the exact canonical MMA input fragments and sums."""
import torch
import pytest
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval import integer_reference as reference
from global_input import GlobalInput

@pytest.mark.parametrize('width',[64,80,1040])
def test_direct_global_input_matches_independent_cpu_and_original_stream(width):
    g=torch.Generator().manual_seed(width)
    x=torch.randn(33,width,generator=g)
    w=(torch.randn(35,width,generator=g)*.03).half()
    w[0,0]=65504.;w[-1,-1]=2.**-24
    expected=reference.linear(x,w,magnitude_bits=22).view(torch.int32)
    k=IntegerCudaKernels('cuda',magnitude_bits=22);gx,gw=x.cuda(),w.cuda()
    flag=k.new_error_flag();prep=k.quantize_input(gx,_packed=True,error_flag=flag)
    ew=k._weight_exponents(gw,flag)
    for columns in (32,64):
      for split in (1,3,7):
        candidate=GlobalInput(k,width,columns,split,min_blocks=3)
        actual=candidate.project(prep,gw,ew,flag)
        assert flag.item()==0 and torch.equal(actual.cpu().view(torch.int32),expected),(width,columns,split)
