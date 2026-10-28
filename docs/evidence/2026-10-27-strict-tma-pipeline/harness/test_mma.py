"""TMA transport must leave the existing B22 MMA products, rounding, bias and flags unchanged."""
import pytest
import torch
from heteroes.eval import integer_reference as reference
from tma_mma import TmaMma

@pytest.mark.parametrize('rows,width,outputs',[(2,16,1),(17,80,35),(33,1040,65),(32,896,96)])
@pytest.mark.parametrize('stages',[2,3])
def test_tma_mma_matches_independent_reference_with_empty_splits_and_tails(rows,width,outputs,stages):
    gen=torch.Generator().manual_seed(width+rows)
    x=torch.randn(rows,width,generator=gen)
    w=(torch.randn(outputs,width,generator=gen)*.03).half()
    w[0,0]=65504.;w[-1,-1]=2.**-24
    bias=torch.randn(outputs,generator=gen).half()
    expected=reference.linear(x,w,bias,magnitude_bits=22).view(torch.int32)
    for columns in (32,64):
      for split in (1,3,7):
        c=TmaMma(width,columns,split,stages,has_bias=True)
        out,flag=c.linear(x.cuda(),w.cuda(),bias.cuda())
        assert int(flag.item())==0
        assert torch.equal(out.cpu().view(torch.int32),expected),(columns,split,stages)
