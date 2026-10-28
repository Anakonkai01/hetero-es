"""By-value maps must survive capture, changing live values and exact restore without a descriptor upload."""
import numpy as np
import pytest
import torch
from heteroes.eval import integer_reference as reference
from tma_byvalue import TmaByValue

@pytest.mark.parametrize('rows,width,outputs,split',[(2,16,1,7),(33,80,35,3),(32,896,96,7),(888,896,96,1)])
def test_byvalue_matches_independent_b22_with_tails(rows,width,outputs,split):
    g=torch.Generator().manual_seed(82)
    x=torch.randn(rows,width,generator=g)
    w=(torch.randn(outputs,width,generator=g)*.02).half()
    c=TmaByValue(width,64 if rows>32 else 32,split,2,3 if rows>32 else 0)
    out,flag=c.linear(x.cuda(),w.cuda())
    assert flag.item()==0
    assert torch.equal(out.cpu().view(torch.int32),reference.linear(x,w,magnitude_bits=22).view(torch.int32))

def test_capture_keeps_addresses_live_without_gpu_map_upload():
    c=TmaByValue(80,32,3,2)
    g=torch.Generator().manual_seed(27)
    x=torch.randn(17,80,generator=g).cuda()
    w=(torch.randn(35,80,generator=g)*.02).half().cuda()
    oldx,oldw=x.clone(),w.clone()
    c.linear(x,w)
    graph=torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):out,flag=c.linear(x,w)
    assert all(isinstance(a,np.ndarray) and a.dtype==np.uint8 and a.size==128 for a in c.last_maps)
    for mode in ('parent','changed','restore'):
        if mode=='changed':x.mul_(.9);w.add_(.001)
        elif mode=='restore':x.copy_(oldx);w.copy_(oldw)
        graph.replay()
        assert flag.item()==0
        expected=reference.linear(x.cpu(),w.cpu(),magnitude_bits=22)
        assert torch.equal(out.cpu().view(torch.int32),expected.view(torch.int32)),mode
