"""Normal-domain arithmetic must match all result bits and both failure bits, including fallback inputs."""
import pytest
import torch
from heteroes.eval import strict_cuda as sc
from normal import transform, NormalKernels

ENTRY=r'''
extern "C" __global__ void probe(const float* x,float* out,int* flags,int count) {
  int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=count)return;
  unsigned a=0,b=0,c=0,d=0;
  out[4*i]=original_reciprocal_(x[i],a);out[4*i+1]=reciprocal_(x[i],b);
  out[4*i+2]=original_rsqrt_(x[i],c);out[4*i+3]=rsqrt_(x[i],d);
  flags[4*i]=a;flags[4*i+1]=b;flags[4*i+2]=c;flags[4*i+3]=d;
}
'''
def build():
    torch.empty(1,device='cuda')
    k=sc.StrictCudaKernels('cuda')
    h=''.join(f'#define {n} 0x{v:08x}u\n' for n,v in sc.reference_constants().items())
    fn=k._compile('normal-probe-v1',h+transform(sc._OPS_SOURCE)+ENTRY,['probe'],
                  ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)['probe']
    return k,fn

def test_edges_and_random_bits_keep_outputs_and_error_flags():
    k,fn=build();g=torch.Generator().manual_seed(314)
    bits=torch.randint(-(2**31),2**31-1,(2**20,),generator=g,dtype=torch.int32)
    edges=torch.tensor([0,0x80000000,1,0x807fffff,0x00800000,0x7f7fffff,0x7f800000,0xff800000,
                       0x7fc12345,0x7fa00001],dtype=torch.uint32).view(torch.int32)
    bounds=torch.tensor([1e-30,1e30],dtype=torch.float32).view(torch.int32)
    around=torch.cat([bounds+i for i in range(-4,5)])
    x=torch.cat((bits,edges,around)).view(torch.float32).cuda()
    out=torch.empty((x.numel(),4),device='cuda');flags=torch.empty_like(out,dtype=torch.int32)
    k._launch(fn,grid=(-(-x.numel()//256),1),block=(256,1),pointers=(x,out,flags),integers=(x.numel(),))
    for a,b in ((0,1),(2,3)):
        assert torch.equal(flags[:,a],flags[:,b])
        finite=torch.isfinite(out[:,a])
        assert torch.equal(out[:,a].view(torch.int32)[finite],out[:,b].view(torch.int32)[finite])
        assert torch.equal(torch.isfinite(out[:,a]),torch.isfinite(out[:,b]))

def test_composed_silu_norm_and_attention_keep_original_bits():
    base=sc.StrictCudaKernels('cuda');fast=NormalKernels('cuda',magnitude_bits=22)
    g=torch.Generator(device='cuda').manual_seed(655)
    x=torch.randn(129,80,device='cuda',generator=g);w=torch.randn(80,device='cuda',generator=g).half()
    gate=torch.randn(17,80,device='cuda',generator=g)*20;up=torch.randn_like(gate)
    for fn,args in (('silu_mul',(gate,up)),('rms_norm',(x,w,1e-6))):
        expected=getattr(base,fn)(*args);actual=getattr(fast,fn)(*args)
        assert torch.equal(expected.view(torch.int32),actual.view(torch.int32))
    q=torch.randn(14,33,64,device='cuda',generator=g);k=torch.randn(2,33,64,device='cuda',generator=g);v=torch.randn_like(k)
    a=base.attention_packed(q,k,v,[(33,33,0)],7,.125)
    b=fast.attention_packed(q,k,v,[(33,33,0)],7,.125)
    assert torch.equal(a.view(torch.int32),b.view(torch.int32))
