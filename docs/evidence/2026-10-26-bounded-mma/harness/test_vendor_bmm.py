import os

import pytest
import torch

from bounded_reference import linear

gpu=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')


@gpu
def test_vendor_partials_match_integer_oracle_across_live_change_restore_and_clear_bounded_scratch():
    from vendor_bmm import VendorBoundedKernels
    torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction=False
    torch.backends.cuda.matmul.allow_fp16_accumulation=False
    kernel=VendorBoundedKernels('cuda',activation_bits=8,weight_bits=8,max_quantized_bytes=1024**2,max_partial_bytes=1024**2)
    generator=torch.Generator().manual_seed(8752)
    for rows,width,outputs,offset in ((3,64,7,0),(19,128,13,1),(32,896,17,0)):
        x=torch.randn(rows,width,generator=generator)
        w=(torch.randn(outputs,width,generator=generator)*.125).half()
        backing=torch.empty(w.numel()+offset,dtype=torch.float16,device='cuda')
        live=backing[offset:].reshape(w.shape)
        for factor in (1.,-16.,1.):
            candidate=(w*factor).half();live.copy_(candidate)
            kernel._begin_request((live,))
            try:
                actual=kernel.linear(x.cuda(),live)
                expected=linear(x,candidate,activation_bits=8,weight_bits=8)
                assert torch.equal(actual.cpu().view(torch.int32),expected.view(torch.int32))
                assert torch.equal(live.cpu().view(torch.int16),candidate.view(torch.int16))
            finally:kernel._end_request()
        assert all(not bool(buffer.any())for buffer in kernel.operator_workspaces())
    assert kernel.vendor_calls>=9


@gpu
def test_vendor_full_precision_accumulation_and_stream_ownership_are_required():
    from vendor_bmm import VendorBoundedKernels
    from heteroes.eval.reference_ops import ReferenceArithmeticError
    torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction=False
    torch.backends.cuda.matmul.allow_fp16_accumulation=False
    kernel=VendorBoundedKernels('cuda',activation_bits=8,weight_bits=8,max_quantized_bytes=1024**2,max_partial_bytes=1024**2)
    x=torch.ones((16,64),device='cuda')
    w=torch.ones((9,64),dtype=torch.float16,device='cuda')
    torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction=True
    with pytest.raises(ReferenceArithmeticError,match='FP32'):
        kernel._begin_request((w,))
    torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction=False
    kernel._begin_request((w,))
    try:
        other=torch.cuda.Stream()
        with torch.cuda.stream(other),pytest.raises(ReferenceArithmeticError,match='stream'):
            kernel.linear(x,w)
    finally:kernel._end_request()
