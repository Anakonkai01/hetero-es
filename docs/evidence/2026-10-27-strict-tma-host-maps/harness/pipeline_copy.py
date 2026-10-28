"""Swizzled weight/activation TMA ring, using the same wait/consume/refill order as the streamed GEMM."""
import torch
from heteroes.eval import strict_cuda as sc
from tensor_map import maps

HELPERS=r'''
__device__ __forceinline__ unsigned tma_addr(const void* p) {
  unsigned long long address;
  asm volatile("cvta.to.shared.u64 %0,%1;" : "=l"(address) : "l"(p));
  return (unsigned)address;
}
__device__ __forceinline__ void tma_init(unsigned long long* barrier) {
  asm volatile("mbarrier.init.shared::cta.b64 [%0],1;" :: "r"(tma_addr(barrier)) : "memory");
}
__device__ __forceinline__ void tma_stage(unsigned char* sw,unsigned char* sa,const void* wd,const void* ad,
                                        unsigned long long* barrier,int k0,int column0,int first) {
  unsigned b=tma_addr(barrier);
  asm volatile("mbarrier.arrive.expect_tx.shared::cta.b64 _,[%0],%1;" :: "r"(b),"r"(W_STAGE+A_STAGE) : "memory");
  asm volatile("cp.async.bulk.tensor.2d.shared::cta.global.mbarrier::complete_tx::bytes [%0],[%1,{%2,%3}],[%4];"
      :: "r"(tma_addr(sw)),"l"(wd),"r"(k0),"r"(column0),"r"(b) : "memory");
  #pragma unroll
  for(int digit=0;digit<3;++digit)
    asm volatile("cp.async.bulk.tensor.3d.shared::cta.global.mbarrier::complete_tx::bytes [%0],[%1,{%2,%3,%4}],[%5];"
      :: "r"(tma_addr(sa+digit*MT*KS)),"l"(ad),"r"(k0),"r"(first),"r"(digit),"r"(b) : "memory");
}
__device__ __forceinline__ unsigned tma_wait(unsigned long long* barrier,unsigned phase) {
  unsigned ready=0,b=tma_addr(barrier);
  for(int attempt=0;attempt<100000 && !ready;++attempt)
    asm volatile("{ .reg .pred p; mbarrier.try_wait.parity.shared::cta.b64 p,[%1],%2; selp.u32 %0,1,0,p; }"
      : "=r"(ready) : "r"(b),"r"(phase) : "memory");
  return ready;
}
'''

COPY=r'''
extern "C" __global__ void pipeline_copy(const void* wd,const void* ad,const int* coords,
    unsigned short* outw,unsigned char* outa,int* status,int count) {
  __shared__ __align__(1024) unsigned char ws[STAGES][W_STAGE],as[STAGES][A_STAGE];
  __shared__ __align__(8) unsigned long long barriers[STAGES];
  __shared__ int failed;
  int tid=threadIdx.x;
  if(tid==0) {
    failed=0;
    for(int s=0;s<STAGES;++s) tma_init(barriers+s);
    asm volatile("fence.proxy.async.shared::cta;" ::: "memory");
  }
  __syncthreads();
  if(tid==0) for(int s=0;s<STAGES-1;++s)
    if(s<count) tma_stage(ws[s],as[s],wd,ad,barriers+s,coords[s*3],coords[s*3+1],coords[s*3+2]);
  for(int it=0;it<count;++it) {
    int slot=it%STAGES;
    unsigned ready=tma_wait(barriers+slot,(it/STAGES)&1);
    if(!ready) atomicExch(&failed,1);
    __syncthreads();
    if(failed) {if(tid==0) status[0]=4;return;}
    int next=it+STAGES-1;
    if(tid==0 && next<count)
      tma_stage(ws[next%STAGES],as[next%STAGES],wd,ad,barriers+next%STAGES,
                coords[next*3],coords[next*3+1],coords[next*3+2]);
    for(int i=tid;i<W_STAGE/2;i+=128) {
      int byte=i*2,physical=byte^((byte&0x380)>>3);
      outw[(size_t)it*(W_STAGE/2)+i]=*(const unsigned short*)(ws[slot]+physical);
    }
    for(int i=tid;i<A_STAGE;i+=128) {
      int digit=i/(MT*KS),byte=i%(MT*KS),physical=byte^((byte&0x180)>>3);
      outa[(size_t)it*A_STAGE+i]=as[slot][digit*MT*KS+physical];
    }
  }
}
'''

class PipelineCopy:
    def __init__(self,width,stages):
        self.context=torch.empty(1,device='cuda');self.k=sc.StrictCudaKernels('cuda')
        assert self.k.arch=='sm_120' and stages in (2,3)
        self.width,self.stages=width,stages
        header=f'#define KS 64\n#define MT 32\n#define W_STAGE 4096\n#define A_STAGE 6144\n#define STAGES {stages}\n'
        self.fn=self.k._compile(f'tma-pipeline-copy-s{stages}',header+HELPERS+COPY,['pipeline_copy'],sass_exact=('FENCE.VIEW.ASYNC.S',))['pipeline_copy']
    def run(self,weight,activation,coords):
        count=coords.shape[0];rows=activation.shape[1]
        w,a=maps(self.k,weight,activation,rows,self.width)
        ow=torch.empty((count,32,64),dtype=torch.int16,device='cuda')
        oa=torch.empty((count,3,32,64),dtype=torch.uint8,device='cuda');status=self.k.new_error_flag()
        self.k._launch(self.fn,grid=1,block=(128,1),pointers=(w,a,coords,ow,oa,status),integers=(count,))
        return ow,oa,status
