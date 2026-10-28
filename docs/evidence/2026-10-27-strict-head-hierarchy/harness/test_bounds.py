"""A signed four-bit coarse weight is an exact floor of the existing signed-byte coarse weight."""
import torch

def test_floor_composition_and_integer_interval_for_four_bit_head():
    g=torch.Generator().manual_seed(349)
    qa=torch.randint(-(2**22-1),2**22,(32,896),generator=g,dtype=torch.int64)
    qw=torch.randint(-(2**22-1),2**22,(97,896),generator=g,dtype=torch.int64)
    t8=qw>>15;t4=t8>>4
    assert torch.equal(t4,qw>>19) and t4.min()>=-8 and t4.max()<=7
    exact=qa@qw.T;p=qa@t4.T
    center=(p<<19)+(qa.sum(1,keepdim=True)<<18)
    radius=qa.abs().sum(1,keepdim=True)<<18
    assert bool(((center-radius<=exact)&(exact<=center+radius)).all())
