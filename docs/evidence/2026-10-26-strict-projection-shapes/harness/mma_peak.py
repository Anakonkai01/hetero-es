"""Peak int8 mma.sync m16n8k32 throughput on this GPU (independent accumulators, no memory traffic)."""
import argparse, os, statistics
p = argparse.ArgumentParser(); p.add_argument('--gpu', action='store_true'); a = p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1': p.error('GPU opt-in required')
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
SRC = r"""
__device__ __forceinline__ void mma(int* c,const unsigned* a,const unsigned* b) {
  asm volatile("mma.sync.aligned.m16n8k32.row.col.s32.s8.s8.s32 "
    "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};"
    : "+r"(c[0]), "+r"(c[1]), "+r"(c[2]), "+r"(c[3])
    : "r"(a[0]), "r"(a[1]), "r"(a[2]), "r"(a[3]), "r"(b[0]), "r"(b[1]));
}
extern "C" __global__ void peak(int* out, int iterations) {
  unsigned a[4], b[2];
  for(int i=0;i<4;++i) a[i]=threadIdx.x*(i+3);
  for(int i=0;i<2;++i) b[i]=threadIdx.x*(i+7);
  int c[CHAINS][4]={};
  for(int it=0;it<iterations;++it) {
    #pragma unroll
    for(int j=0;j<CHAINS;++j) mma(c[j],a,b);
  }
  int s=0;
  for(int j=0;j<CHAINS;++j) s+=c[j][0]+c[j][1]+c[j][2]+c[j][3];
  out[blockIdx.x*blockDim.x+threadIdx.x]=s;
}
"""
torch.zeros(1, device='cuda')
k = IntegerCudaKernels(torch.device('cuda'), magnitude_bits=22)
for chains, per_sm in ((1, 1), (4, 1), (8, 1), (16, 1), (4, 2), (8, 2), (8, 8)):
    for warps in (4,):
        f = k._compile(f'peak{chains}', f'#define CHAINS {chains}\n' + SRC, ['peak'], integer_mma=True)['peak']
        blocks, it = k.multiprocessors * per_sm, 4096
        out = torch.empty(blocks * 32 * warps, dtype=torch.int32, device='cuda')
        times = []
        for _ in range(5):
            s, e = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            s.record(); k._launch(f, grid=blocks, block=(32 * warps, 1), pointers=(out,), integers=(it,)); e.record()
            torch.cuda.synchronize(); times.append(s.elapsed_time(e) / 1e3)
        t = statistics.median(times[1:])
        ops = 2 * 16 * 8 * 32 * chains * it * blocks * warps
        print(f'chains {chains} CTAs/SM {per_sm} warps/CTA {warps}: {ops / t / 1e12:7.1f} TOPS ({t*1e3:.2f} ms)', flush=True)
