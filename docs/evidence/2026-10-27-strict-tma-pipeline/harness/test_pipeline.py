"""TMA swizzle/ring reuse must preserve both weights and separate radix planes, with zero-filled tails."""
import pytest
import torch
from pipeline_copy import PipelineCopy

@pytest.mark.parametrize('stages',[2,3])
@pytest.mark.parametrize('count',[1,2,3,7,17])
def test_swizzled_ring_matches_source_bits_and_does_not_cross_radix_planes(stages,count):
    width,n,rows=80,37,33
    weight=((torch.arange(n*width)*18181+16384)&65535).to(torch.int16).reshape(n,width)
    activation=((torch.arange(3*rows*width)*97+19)&255).to(torch.uint8).reshape(3,rows,width)
    coords=torch.tensor([[(i%2)*64,(i%2)*32,(i%2)*32] for i in range(count)],dtype=torch.int32)
    c=PipelineCopy(width,stages)
    actual_w,actual_a,status=c.run(weight.cuda(),activation.cuda(),coords.cuda())
    expected_w=torch.zeros((count,32,64),dtype=torch.int16)
    expected_a=torch.zeros((count,3,32,64),dtype=torch.uint8)
    for i,(k0,n0,m0) in enumerate(coords.tolist()):
        nk=min(64,width-k0);nn=min(32,n-n0);nm=min(32,rows-m0)
        expected_w[i,:nn,:nk]=weight[n0:n0+nn,k0:k0+nk]
        expected_a[i,:,:nm,:nk]=activation[:,m0:m0+nm,k0:k0+nk]
    assert int(status.item())==0
    assert torch.equal(actual_w.cpu(),expected_w)
    assert torch.equal(actual_a.cpu(),expected_a)
