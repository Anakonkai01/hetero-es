"""Exhaust normalized GPU mantissas and compare nonfinite/domain flags, then full SiLU outputs."""
import os
import numpy as np
import pytest
import torch

gpu=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')

@gpu
def test_all_normalized_mantissas_and_domain_edges_match_original_kernel():
    from gpu_lookup import LookupKernels
    k=LookupKernels()
    values=(torch.arange(1<<23,device='cuda',dtype=torch.int32)|0x3F800000).view(torch.float32)
    result=k.compare(values)
    assert torch.equal(result[:,0],result[:,1])
    assert torch.equal(result[:,2],result[:,3]) and not bool(result[:,2].any())
    gen=torch.Generator().manual_seed(741)
    bits=torch.randint(0x0DA24260,0x7149F2CB,(1<<20,),generator=gen,dtype=torch.int32)
    edges=torch.tensor([0.,-0.,-1.,1e-40,1e-31,1e31,float('inf'),float('-inf'),float('nan'),1e-30,1e30])
    result=k.compare(torch.cat((bits.view(torch.float32),edges)).cuda())
    assert torch.equal(result[:,0],result[:,1]) and torch.equal(result[:,2],result[:,3])
    assert k.table_bytes < 5*1024**2

@gpu
@pytest.mark.parametrize('rows',[32,888])
def test_silu_outputs_and_flags_match_original(rows):
    from gpu_lookup import LookupKernels
    k=LookupKernels();gen=torch.Generator(device='cuda').manual_seed(rows)
    gate=torch.randn((rows,4864),device='cuda',generator=gen)*5
    up=torch.randn((rows,4864),device='cuda',generator=gen)
    for nonfinite in (False,True):
        if nonfinite:gate[0,0]=float('nan');up[-1,-1]=float('inf')
        flags=[k.owner.new_error_flag(),k.owner.new_error_flag()]
        expected=k.owner.silu_mul(gate,up,error_flag=flags[0])
        actual=k.silu_mul(gate,up,error_flag=flags[1])
        assert torch.equal(expected.view(torch.int32),actual.view(torch.int32))
        assert int(flags[0].item())==int(flags[1].item())
