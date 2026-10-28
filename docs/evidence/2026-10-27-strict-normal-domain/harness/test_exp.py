"""Range-reduced exp specialization preserves polynomial rounding, clipping and original failure flags."""
import torch
from heteroes.eval import strict_cuda as sc
from normal_exp import transform, NormalExpKernels

ENTRY=r'''
extern "C" __global__ void probe(const float* x,float* out,int* flags,int count) {
  int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=count)return;
  unsigned a=0,b=0;out[2*i]=original_exp_(x[i],a);out[2*i+1]=exp_(x[i],b);
  flags[2*i]=a;flags[2*i+1]=b;
}
'''
def test_exp_edges_random_values_and_all_error_flags():
    torch.empty(1,device='cuda');k=sc.StrictCudaKernels('cuda')
    h=''.join(f'#define {n} 0x{v:08x}u\n' for n,v in sc.reference_constants().items())
    fn=k._compile('normal-exp-probe-v2',h+transform(sc._OPS_SOURCE)+ENTRY,['probe'],
                  ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)['probe']
    g=torch.Generator().manual_seed(164)
    bits=torch.randint(-(2**31),2**31-1,(2**20,),generator=g,dtype=torch.int32)
    edges=torch.tensor([0,0x80000000,1,0x807fffff,0x00800000,0x7f7fffff,0x7f800000,0xff800000,
                       0x7fc12345,0x7fa00001],dtype=torch.uint32).view(torch.int32)
    borders=torch.tensor([-80.,80.,-2.**-26,2.**-26],dtype=torch.float32).view(torch.int32)
    around=torch.cat([borders+i for i in range(-16,17)])
    x=torch.cat((bits,edges,around)).view(torch.float32).cuda()
    out=torch.empty((x.numel(),2),device='cuda');flags=torch.empty_like(out,dtype=torch.int32)
    k._launch(fn,grid=(-(-x.numel()//256),1),block=(256,1),pointers=(x,out,flags),integers=(x.numel(),))
    assert torch.equal(flags[:,0],flags[:,1])
    finite=torch.isfinite(out[:,0]);assert torch.equal(finite,torch.isfinite(out[:,1]))
    assert torch.equal(out[:,0].view(torch.int32)[finite],out[:,1].view(torch.int32)[finite])
