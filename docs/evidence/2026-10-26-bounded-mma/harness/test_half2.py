import os

import pytest
import torch

from bounded_reference import linear

gpu = pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or not torch.cuda.is_available(), reason='GPU opt-in')


@gpu
@pytest.mark.parametrize('bits', [6, 8, 10, 11])
def test_pair_rounding_matches_every_admitted_finite_half_and_row_exponent(bits):
    from half2_cuda import Half2BoundedKernels, pair_probe_source
    context = torch.empty(1, device='cuda')
    kernel = Half2BoundedKernels('cuda', activation_bits=8 if bits<=10 else 6, weight_bits=bits)
    fn = kernel._compile('bounded-pair-probe', pair_probe_source(bits), ['probe_pairs'],
                         ptx_exact=('cvt.rn.f16.s32','cvt.rni.s32.f32'),
                         sass_exact=('I2F.F16','I2FP.F16.S32','F2I.NTZ'))['probe_pairs']
    output = torch.empty((40, 65536), dtype=torch.int32, device='cuda')
    patterns = torch.arange(65536, dtype=torch.int32)
    first = patterns.to(torch.int16).view(torch.float16).double()
    def exponent(u):
        a = u & 0x7fff
        return torch.where(a == 0, -1000, torch.floor(torch.log2(a.to(torch.int16).view(torch.float16).double().abs())).to(torch.int32))
    for selector in (0, 1):
        other = patterns ^ 32768 if selector==0 else (patterns*73+19)&65535
        second = other.to(torch.int16).view(torch.float16).double()
        finite = ((patterns&0x7fff)<0x7c00)&((other&0x7fff)<0x7c00)
        actual_exp = torch.maximum(exponent(patterns), exponent(other))
        kernel._launch(fn, grid=(output.numel()+255)//256, block=(256,1), pointers=(output,), integers=(selector,))
        actual = output.cpu().view(torch.float16).reshape(40,65536,2).float()
        for row,e in enumerate(range(-24,16)):
            valid = finite & (actual_exp<=e)
            expected = torch.stack((torch.round(first[valid]*2.0**(bits-1-e)),torch.round(second[valid]*2.0**(bits-1-e))),1).float()
            # Signed zero is an integer zero; its sign is discarded before final output encoding.
            assert torch.equal(actual[row,valid],expected),(bits,selector,e)
    del context


@gpu
def test_half2_linear_preserves_bounded_arithmetic_with_odd_width_and_offset_storage():
    from half2_cuda import Half2BoundedKernels
    kernel = Half2BoundedKernels('cuda', activation_bits=8, weight_bits=8)
    generator = torch.Generator().manual_seed(7365)
    for width,offset in ((65,0),(128,1),(128,0)):
        x = torch.randn(19,width,generator=generator)
        w = (torch.randn(11,width,generator=generator)*.125).half()
        w[0,0] = 2.0**-24
        backing = torch.empty(w.numel()+offset,dtype=torch.float16,device='cuda')
        live = backing[offset:].reshape(w.shape);live.copy_(w)
        expected = linear(x,w,activation_bits=8,weight_bits=8)
        for split in (1,8):
            actual = kernel.linear(x.cuda(),live,split_k=split)
            assert torch.equal(actual.cpu().view(torch.int32),expected.view(torch.int32))
