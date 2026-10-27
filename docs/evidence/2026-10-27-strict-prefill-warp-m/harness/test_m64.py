"""Warp-M mapping must retain canonical B22 dots, tails, bias and empty split partitions."""
import pytest
import torch
from heteroes.eval import integer_reference
from m64 import M64

@pytest.mark.parametrize('rows,width,outputs',[(2,16,1),(17,80,35),(33,1040,65),(65,80,33),(129,256,65)])
def test_warp_m_tile_matches_independent_cpu_integer_oracle(rows,width,outputs):
    g=torch.Generator().manual_seed(455)
    x=torch.randn(rows,width,generator=g);w=(torch.randn(outputs,width,generator=g)*.02).half()
    x[0,0]=-0.;w[0,0]=65504.;w[-1,-1]=2.**-24
    bias=torch.randn(outputs,generator=g).half()
    expected=integer_reference.linear(x,w,bias,magnitude_bits=22).view(torch.int32)
    for split in (1,3,7):
        c=M64(width,split=split,has_bias=True)
        actual,flag=c.linear(x.cuda(),w.cuda(),bias.cuda())
        assert flag.item()==0
        assert torch.equal(actual.cpu().view(torch.int32),expected),split
