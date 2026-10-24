"""Scratch split-K SIMT projection: identical power-of-two subtrees, fixed partial workspace."""
import math
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels, _LINEAR_SOURCE

COMMON = _LINEAR_SOURCE.split('// One output column')[0]
SOURCE = COMMON + r'''
extern "C" __global__ void __launch_bounds__(32 * GROUPS)
strict_linear_tile(const float* __restrict__ x, const u16* __restrict__ w, const u16* __restrict__ bias,
                   float* __restrict__ out, int* __restrict__ error, int rows, int outputs) {
 const int lane=threadIdx.x, group=threadIdx.y;
 const int tid=group*32+lane;
 const int column=blockIdx.x*GROUPS+group;
 const int first=blockIdx.y*ROW_TILE;
 const int kbase=blockIdx.z*TILE_K;
 __shared__ float sw[GROUPS][32][PER+1];
 __shared__ float sx[ROW_TILE][32][PER+1];
 for(int p=lane;p<TILE_K;p+=32) {
  const int k=kbase+p;
  sw[group][p/PER][p%PER]=(column<outputs && k<WIDTH) ? widen(w[(size_t)column*WIDTH+k]) : 0.0f;
 }
 for(int p=tid;p<ROW_TILE*TILE_K;p+=32*GROUPS) {
  const int row=p/TILE_K, k=p%TILE_K;
  sx[row][k/PER][k%PER]=(first+row<rows && kbase+k<WIDTH) ? flush(x[(size_t)(first+row)*WIDTH+kbase+k]) : -0.0f;
 }
 __syncthreads();
 float weights[PER];
 #pragma unroll
 for(int i=0;i<PER;++i) weights[i]=sw[group][lane][i];
 #pragma unroll
 for(int r=0;r<ROW_TILE;++r) {
  float stack[LOG_PER+1];
  #pragma unroll
  for(int i=0;i<PER;++i) {
   const int k=kbase+lane*PER+i;
   float v=(column<outputs && first+r<rows && k<WIDTH) ? mul_rn(sx[r][lane][i],weights[i]) : -0.0f;
   int level=0;
   #pragma unroll
   for(;level<LOG_PER && ((i>>level)&1);++level) v=add_rn(stack[level],v);
   stack[level]=v;
  }
  float v=stack[LOG_PER];
  #pragma unroll
  for(int offset=1;offset<32;offset<<=1) v=add_rn(v,__shfl_xor_sync(0xffffffffu,v,offset));
  if(lane==0 && column<outputs && first+r<rows) {
   if(CHUNKS==1) {
    if(HAS_BIAS) v=add_rn(v,widen(bias[column]));
    if((__float_as_uint(v)&0x7f800000u)==0x7f800000u) atomicOr(error,1);
   }
   out[((size_t)blockIdx.z*rows+first+r)*outputs+column]=v;
  }
 }
}
extern "C" __global__ void strict_linear_finish(const float* partials, const u16* bias, float* out,
                                               int* error, int rows, int outputs) {
 size_t index=(size_t)blockIdx.x*blockDim.x+threadIdx.x;
 size_t count=(size_t)rows*outputs;
 if(index>=count) return;
 float stack[LOG_CHUNKS+1];
 #pragma unroll
 for(int i=0;i<PADDED_CHUNKS;++i) {
  float v=i<CHUNKS ? partials[(size_t)i*count+index] : -0.0f;
  int level=0;
  #pragma unroll
  for(;level<LOG_CHUNKS && ((i>>level)&1);++level) v=add_rn(stack[level],v);
  stack[level]=v;
 }
 float v=stack[LOG_CHUNKS];
 if(HAS_BIAS) v=add_rn(v,widen(bias[index%outputs]));
 out[index]=v;
 if((__float_as_uint(v)&0x7f800000u)==0x7f800000u) atomicOr(error,1);
}
'''

def prepare(x, w, *, rows=32, tile=16, per=8, groups=4, bias=None):
    kernels=StrictCudaKernels(x.device)
    width, outputs = w.shape[1],w.shape[0]
    kt=32*per; chunks=math.ceil(width/kt); padded=1<<(chunks-1).bit_length()
    defines={'WIDTH':width,'PER':per,'LOG_PER':per.bit_length()-1,'TILE_K':kt,
             'CHUNKS':chunks,'PADDED_CHUNKS':padded,'LOG_CHUNKS':padded.bit_length()-1,
             'ROW_TILE':tile,'GROUPS':groups,'HAS_BIAS':int(bias is not None)}
    header=''.join(f'#define {k} {v}\n' for k,v in defines.items())
    fn=kernels._compile('split-k-prototype',header+SOURCE,['strict_linear_tile','strict_linear_finish'])
    out=torch.empty((rows,outputs),device=x.device,dtype=torch.float32)
    parts=out if chunks==1 else torch.empty((chunks,rows,outputs),device=x.device,dtype=torch.float32)
    flag=kernels.new_error_flag()
    b=w if bias is None else bias
    def launch():
        kernels._launch(fn['strict_linear_tile'],grid=(math.ceil(outputs/groups),math.ceil(rows/tile),chunks),
                        block=(32,groups),pointers=(x,w,b,parts,flag),integers=(rows,outputs))
        if chunks!=1:
            kernels._launch(fn['strict_linear_finish'],grid=math.ceil(rows*outputs/256),block=(256,1),
                            pointers=(parts,b,out,flag),integers=(rows,outputs))
    return kernels,launch,out,parts,flag
