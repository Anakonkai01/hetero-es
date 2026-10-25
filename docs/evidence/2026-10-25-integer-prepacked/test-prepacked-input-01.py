"""Packed activation planes must reconstruct independently checked q, including all padded bytes and carries."""
import os
import pytest
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval.integer_reference import quantize_rows
pytestmark=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1'or not torch.cuda.is_available(),reason='GPU opt-in')

@pytest.mark.parametrize('bits',[14,22])
@pytest.mark.parametrize('width',[1,3,4,31,33,67,257,32768])
def test_packed_planes_reconstruct_quantized_rows_and_zero_padding(bits,width):
 g=torch.Generator().manual_seed(width+bits);x=torch.randn(5,width,generator=g);x[1]=-0.;x[2]=torch.tensor(1,dtype=torch.int32).view(torch.float32)
 carries=torch.tensor([0,1,-1,127,128,129,-127,-128,-129,32767,32768,32769,-32767,-32768,-32769,2**bits-1],dtype=torch.float32)/2**(bits-1)
 x[3,:min(width,len(carries))]=carries[:width];x[4]=1.9999998807907104
 expected,ex=quantize_rows(x,magnitude_bits=bits);k=IntegerCudaKernels('cuda',magnitude_bits=bits);packed,actual_ex=k.quantize_input(x.cuda(),_packed=True)
 digits=2 if bits==14 else 3;words=(width+3)//4;assert packed.shape==(digits,5,words)and packed.dtype==torch.int32
 raw=packed.cpu().to(torch.int64)&0xffffffff;reconstructed=torch.zeros((5,words,4),dtype=torch.int64)
 for d in range(digits):
  byte=(raw[d,:,:,None]>>torch.tensor([0,8,16,24]))&255;digit=torch.where(byte>=128,byte-256,byte);reconstructed+=digit*256**d
 padded=torch.zeros((5,words*4),dtype=torch.int64);padded[:,:width]=expected.to(torch.int64)
 assert torch.equal(actual_ex.cpu(),ex)and torch.equal(reconstructed.reshape(5,-1),padded)
