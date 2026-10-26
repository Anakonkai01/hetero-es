"""IMMA m16n8k32 throughput vs warps per SM and the B22 digit-product pattern (2 m-groups x 9 products, 10 accumulators)."""
import os, statistics, torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
SRC = r"""
__device__ __forceinline__ void mma_i8(int* c,const unsigned* a,const unsigned* b) {
  asm volatile("mma.sync.aligned.m16n8k32.row.col.s32.s8.s8.s32 {%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};"
    : "+r"(c[0]), "+r"(c[1]), "+r"(c[2]), "+r"(c[3]) : "r"(a[0]), "r"(a[1]), "r"(a[2]), "r"(a[3]), "r"(b[0]), "r"(b[1]));
}
extern "C" __global__ void indep(int* out, int iterations) {
  unsigned a[4], b[2];
  for(int i=0;i<4;++i) a[i]=threadIdx.x*(i+3)&0x0f0f0f0fu;
  for(int i=0;i<2;++i) b[i]=threadIdx.x*(i+7)&0x0f0f0f0fu;
  int c[8][4]={};
  for(int it=0;it<iterations;++it) {
    #pragma unroll
    for(int j=0;j<8;++j) mma_i8(c[j],a,b);
  }
  int s=0; for(int j=0;j<8;++j) s+=c[j][0]+c[j][1];
  out[blockIdx.x*blockDim.x+threadIdx.x]=s;
}
extern "C" __global__ void digits(int* out, int iterations) {
  unsigned a[2][3][4], b[3][2];
  for(int m=0;m<2;++m) for(int d=0;d<3;++d) for(int i=0;i<4;++i) a[m][d][i]=(threadIdx.x*(i+3+d+m))&0x0f0f0f0fu;
  for(int d=0;d<3;++d) for(int i=0;i<2;++i) b[d][i]=threadIdx.x*(i+7+d)&0x0f0f0f0fu;
  int c[2][5][4]={};
  for(int it=0;it<iterations;++it) {
    #pragma unroll
    for(int m=0;m<2;++m)
      #pragma unroll
      for(int i=0;i<3;++i)
        #pragma unroll
        for(int j=0;j<3;++j) mma_i8(c[m][i+j],a[m][i],b[j]);
  }
  int s=0; for(int m=0;m<2;++m) for(int j=0;j<5;++j) s+=c[m][j][0]+c[m][j][1];
  out[blockIdx.x*blockDim.x+threadIdx.x]=s;
}
"""
torch.zeros(1, device='cuda')
k = IntegerCudaKernels(torch.device('cuda'), magnitude_bits=22)
f = k._compile('imma-peak', SRC, ['indep', 'digits'], integer_mma=True)
for name, per in (('indep', 8), ('digits', 18)):
    for ctas_per_sm, warps in ((1, 4), (2, 4), (3, 4), (4, 4), (2, 8), (4, 8)):
        blocks, it = k.multiprocessors * ctas_per_sm, 1024
        out = torch.empty(blocks * 32 * warps, dtype=torch.int32, device='cuda')
        times = []
        for _ in range(5):
            s, e = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            s.record(); k._launch(f[name], grid=blocks, block=(32 * warps, 1), pointers=(out,), integers=(it,)); e.record()
            torch.cuda.synchronize(); times.append(s.elapsed_time(e) / 1e3)
        t_ = statistics.median(times[1:])
        ops = 2 * 16 * 8 * 32 * per * it * blocks * warps
        print(f'{name:6s} {ctas_per_sm} CTAs x {warps} warps/SM={ctas_per_sm*warps:2d}: {ops / t_ / 1e12:6.1f} TOPS', flush=True)
