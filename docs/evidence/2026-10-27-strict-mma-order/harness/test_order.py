"""Exact bounded int32 degree sums may be rescheduled, but no digit pair may be lost or duplicated."""
import pytest
import torch
from heteroes.eval import integer_reference
from schedule import ScheduledKernels

@pytest.mark.parametrize('rows,width,outputs',[(2,16,1),(17,80,35),(33,1040,65)])
@pytest.mark.parametrize('bias',[False,True])
def test_reordered_mma_pairs_keep_cpu_bits_and_flags(rows,width,outputs,bias):
    g=torch.Generator().manual_seed(174)
    x=torch.randn(rows,width,generator=g);w=(torch.randn(outputs,width,generator=g)*.03).half()
    w[0,0]=65504.;w[-1,-1]=2.**-24
    b=torch.randn(outputs,generator=g).half() if bias else None
    expected=integer_reference.linear(x,w,b,magnitude_bits=22).view(torch.int32)
    k=ScheduledKernels('cuda',magnitude_bits=22)
    for columns in (32,64):
        for split in (1,3,7):
            out=k._linear(x.cuda(),w.cuda(),None if b is None else b.cuda(),split_k=split,stream_columns=columns)
            assert torch.equal(out.cpu().view(torch.int32),expected),(columns,split)
