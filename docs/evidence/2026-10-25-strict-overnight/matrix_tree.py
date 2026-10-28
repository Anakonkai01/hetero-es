"""Scratch SIMT GEMM: each thread owns output columns, K uses the exact adjacent-pair tree."""
import math
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels, _LINEAR_SOURCE

SOURCE = _LINEAR_SOURCE.split('// One output column')[0] + r'''
extern "C" __global__ void __launch_bounds__(OUT_TILE)
strict_matrix_tree(const float* __restrict__ x, const u16* __restrict__ w, const u16* __restrict__ bias,
                   float* __restrict__ out, int* __restrict__ error, int rows, int outputs) {
 const int t=threadIdx.x, o=blockIdx.x*OUT_TILE+t, first=blockIdx.y*ROW_TILE;
 __shared__ u16 sw[OUT_TILE][TILE_K+2];
 __shared__ float sx[ROW_TILE][TILE_K+1];
 float high[ROW_TILE][LOG_CHUNKS+1];
 for(int chunk=0;chunk<PADDED_CHUNKS;++chunk) {
  const int kbase=chunk*TILE_K;
  for(int p=t;p<OUT_TILE*TILE_K;p+=OUT_TILE) {
   const int column=blockIdx.x*OUT_TILE+p/TILE_K, k=p%TILE_K;
   sw[p/TILE_K][k]=(column<outputs && kbase+k<WIDTH) ? w[(size_t)column*WIDTH+kbase+k] : 0;
  }
  for(int p=t;p<ROW_TILE*TILE_K;p+=OUT_TILE) {
   const int r=p/TILE_K, k=p%TILE_K;
   sx[r][k]=(first+r<rows && kbase+k<WIDTH) ? flush(x[(size_t)(first+r)*WIDTH+kbase+k]) : -0.0f;
  }
  __syncthreads();
  float low[ROW_TILE][LOG_TILE_K+1];
  #pragma unroll
  for(int i=0;i<TILE_K;++i) {
   float weight=widen(sw[t][i]);
   #pragma unroll
   for(int r=0;r<ROW_TILE;++r) {
    float v=(o<outputs && first+r<rows && kbase+i<WIDTH) ? mul_rn(sx[r][i],weight) : -0.0f;
    int level=0;
    #pragma unroll
    for(;level<LOG_TILE_K && ((i>>level)&1);++level) v=add_rn(low[r][level],v);
    low[r][level]=v;
   }
  }
  #pragma unroll
  for(int r=0;r<ROW_TILE;++r) {
   float v=low[r][LOG_TILE_K];
   bool carry=true;
   #pragma unroll
   for(int level=0;level<=LOG_CHUNKS;++level) {
    if(carry) {
     if((chunk>>level)&1) v=add_rn(high[r][level],v);
     else {high[r][level]=v;carry=false;}
    }
   }
  }
  __syncthreads();
 }
 if(o<outputs) {
  float b=HAS_BIAS ? widen(bias[o]) : 0.0f;
  #pragma unroll
  for(int r=0;r<ROW_TILE;++r) {
   if(first+r<rows) {
    float v=high[r][LOG_CHUNKS];
    if(HAS_BIAS) v=add_rn(v,b);
    out[(size_t)(first+r)*outputs+o]=v;
    if((__float_as_uint(v)&0x7f800000u)==0x7f800000u) atomicOr(error,1);
   }
  }
 }
}
'''

def prepare(x,w,*,rows=32,tile=4,kt=64,outputs_per_block=128,bias=None):
    kernels=StrictCudaKernels(x.device)
    width,outputs=w.shape[1],w.shape[0]
    chunks=math.ceil(width/kt); padded=1<<(chunks-1).bit_length()
    defines={'WIDTH':width,'TILE_K':kt,'LOG_TILE_K':kt.bit_length()-1,'LOG_CHUNKS':padded.bit_length()-1,
             'PADDED_CHUNKS':padded,'ROW_TILE':tile,'OUT_TILE':outputs_per_block,'HAS_BIAS':int(bias is not None)}
    header=''.join(f'#define {k} {v}\n' for k,v in defines.items())
    fn=kernels._compile('matrix-tree-prototype',header+SOURCE,['strict_matrix_tree'])['strict_matrix_tree']
    out=torch.empty((rows,outputs),device=x.device,dtype=torch.float32)
    flag=kernels.new_error_flag();b=w if bias is None else bias
    def launch():
        kernels._launch(fn,grid=(math.ceil(outputs/outputs_per_block),math.ceil(rows/tile)),
                        block=(outputs_per_block,1),pointers=(x,w,b,out,flag),integers=(rows,outputs))
    return kernels,launch,out,out,flag
