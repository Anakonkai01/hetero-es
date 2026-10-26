"""TMA must preserve all FP16 bit patterns and zero-fill the declared 2D tails."""
import pytest
import torch
from tma_copy_v2 import TmaCopy

@pytest.mark.parametrize('width,rows,x,y',[(64,32,0,0),(80,37,0,0),(80,37,64,32)])
def test_tma_u16_is_exact_with_tails(width,rows,x,y):
    values=((torch.arange(rows*width,dtype=torch.int64)*18181+16384)&65535).to(torch.int16).reshape(rows,width)
    gpu=values.cuda();copy=TmaCopy();actual,flag=copy.run(gpu,x,y)
    expected=torch.zeros((32,64),dtype=torch.int16)
    rr=min(32,rows-y);cc=min(64,width-x)
    expected[:rr,:cc]=values[y:y+rr,x:x+cc]
    assert int(flag.item())==0 and torch.equal(actual.cpu(),expected)
