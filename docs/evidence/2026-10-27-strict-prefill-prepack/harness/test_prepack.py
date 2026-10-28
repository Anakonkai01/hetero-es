"""The bounded prefill scratch must reconstruct B22 weights and preserve full projection bits/flags."""
import pytest
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval import integer_reference as ref
from prepack import PackedPrefill

@pytest.mark.parametrize('width,outputs',[(64,37),(896,96),(4864,64)])
def test_projection_and_live_weight_refresh(width,outputs):
    k=IntegerCudaKernels('cuda',magnitude_bits=22)
    g=torch.Generator(device='cuda').manual_seed(851)
    x=torch.randn(65,width,device='cuda',generator=g)
    w=(torch.randn(outputs,width,device='cuda',generator=g)*.03).half()
    p=PackedPrefill(k,width,columns=32)
    for factor in (1,-4,0):
        w.mul_(factor)
        expected=k.linear(x,w)
        actual=p.linear(x,w)
        assert torch.equal(expected.view(torch.int32),actual.view(torch.int32))
        # Independent CPU integer oracle, including the final RNE encoding.
        assert torch.equal(actual[:2,:5].cpu().view(torch.int32),ref.linear(x[:2].cpu(),w[:5].cpu(),magnitude_bits=22).view(torch.int32))
        assert p.last_scratch_bytes==3*w.numel()
