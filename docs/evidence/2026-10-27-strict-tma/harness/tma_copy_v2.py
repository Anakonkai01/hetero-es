"""Minimal SM120 TMA memory-only feasibility probe, not an inference implementation."""
import ctypes
import numpy as np
import torch
from heteroes.eval import strict_cuda as sc

SOURCE=r'''
extern "C" __global__ void tma_copy_u16(const void* desc,unsigned short* out,int* error,int x,int y) {
  __shared__ __align__(128) unsigned short tile[32*64];
  __shared__ __align__(8) unsigned long long barrier;
  unsigned long long tp,bp;
  asm volatile("cvta.to.shared.u64 %0,%1;" : "=l"(tp) : "l"(tile));
  asm volatile("cvta.to.shared.u64 %0,%1;" : "=l"(bp) : "l"(&barrier));
  unsigned t=(unsigned)tp,b=(unsigned)bp;
  if(threadIdx.x==0) {
    asm volatile("mbarrier.init.shared::cta.b64 [%0],1;" :: "r"(b) : "memory");
    asm volatile("fence.proxy.async.shared::cta;" ::: "memory");
  }
  __syncthreads();
  if(threadIdx.x==0) {
    asm volatile("mbarrier.arrive.expect_tx.shared::cta.b64 _,[%0],4096;" :: "r"(b) : "memory");
    asm volatile("cp.async.bulk.tensor.2d.shared::cta.global.mbarrier::complete_tx::bytes [%0],[%1,{%2,%3}],[%4];"
      :: "r"(t),"l"(desc),"r"(x),"r"(y),"r"(b) : "memory");
  }
  unsigned ready=0;
  // Bound a failed experimental transaction so an incorrect barrier cannot spin indefinitely.
  for(int attempt=0;attempt<100000 && !ready;++attempt)
    asm volatile("{ .reg .pred p; mbarrier.try_wait.parity.shared::cta.b64 p,[%1],0; selp.u32 %0,1,0,p; }"
      : "=r"(ready) : "r"(b) : "memory");
  __syncthreads();
  if(!ready) {atomicOr(error,1);return;}
  for(int i=threadIdx.x;i<32*64;i+=128) out[i]=tile[i];
}
'''

class TmaCopy:
    def __init__(self):
        self.context=torch.empty(1,device='cuda')
        self.k=sc.StrictCudaKernels('cuda')
        assert self.k.arch=='sm_120'
        self.fn=self.k._compile('tma-copy-u16-v2',SOURCE,['tma_copy_u16'],sass_exact=('FENCE.VIEW.ASYNC.S',))['tma_copy_u16']
    def descriptor(self,value):
        driver=self.k._driver;rows,width=value.shape
        desc=sc._check(driver.cuTensorMapEncodeTiled(driver.CUtensorMapDataType.CU_TENSOR_MAP_DATA_TYPE_UINT16,2,
                     value.data_ptr(),(width,rows),(width*2,),(64,32),(1,1),
                     driver.CUtensorMapInterleave.CU_TENSOR_MAP_INTERLEAVE_NONE,
                     driver.CUtensorMapSwizzle.CU_TENSOR_MAP_SWIZZLE_NONE,
                     driver.CUtensorMapL2promotion.CU_TENSOR_MAP_L2_PROMOTION_NONE,
                     driver.CUtensorMapFloatOOBfill.CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE))
        data=ctypes.string_at(desc.getPtr(),128)
        result=torch.from_numpy(np.frombuffer(data,dtype=np.uint8).copy()).cuda()
        assert result.data_ptr()%64==0
        return result
    def run(self,value,x,y):
        assert value.dtype==torch.int16 and value.is_contiguous() and value.shape[1]%8==0
        desc=self.descriptor(value)
        out=torch.empty((32,64),dtype=torch.int16,device=value.device);flag=self.k.new_error_flag()
        self.k._launch(self.fn,grid=1,block=(128,1),pointers=(desc,out,flag),integers=(x,y))
        return out,flag
