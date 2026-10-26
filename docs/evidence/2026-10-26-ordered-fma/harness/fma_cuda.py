"""Unselected ordered FP32 FMA chunks over one live FP16 weight set, without weight quantization."""
import hashlib
from pathlib import Path

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import strict_cuda as sc
from heteroes.eval.reference_ops import ReferenceArithmeticError

VERSION='f16_weight_f32_fma256_tree_ftz_v1_probe'

_SOURCE=sc._LINEAR_SOURCE.split('// One output column')[0]+r'''
__device__ __forceinline__ unsigned smem(const void* pointer) {
  unsigned long long address;
  asm volatile("cvta.to.shared.u64 %0, %1;" : "=l"(address) : "l"(pointer));
  return (unsigned)address;
}
__device__ __forceinline__ void copy_weight(u16* target,const u16* weight,int column,int outputs,int start,int end) {
  for(int copy=threadIdx.x;copy<64*4;copy+=128) {
    int n=copy/4,k=(copy%4)*8;
    u16* destination=target+n*32+k;
#if WIDTH % 8 == 0
    if((((unsigned long long)weight)&15ull)==0ull) {
      int valid=(column+n<outputs && start+k+7<end) ? 16 : 0;
      const u16* source=valid ? weight+(size_t)(column+n)*WIDTH+start+k : weight;
      unsigned address=smem(destination);
      asm volatile("cp.async.ca.shared.global [%0], [%1], 16, %2;" ::
        "r"(address),"l"(source),"r"(valid) : "memory");
    } else
#endif
    {
      #pragma unroll
      for(int i=0;i<8;++i)
        destination[i]=(column+n<outputs && start+k+i<end) ? weight[(size_t)(column+n)*WIDTH+start+k+i] : 0;
    }
  }
}

extern "C" __global__ void __launch_bounds__(128)
ordered_fma(const float* x,const u16* w,float* partials,int* error,int rows,int outputs) {
  int tx=threadIdx.x&15,ty=threadIdx.x>>4;
  int column=blockIdx.x*64,begin=blockIdx.z*256,end=begin+256<WIDTH ? begin+256 : WIDTH;
  __shared__ __align__(16) u16 raw[2][64*32];
  __shared__ float as[32][33],bs[32][65];
  for(int first=blockIdx.y*32;first<rows;first+=gridDim.y*32) {
    float accum[4][4]={};
    int phase=0;
    copy_weight(raw[0],w,column,outputs,begin,end);
    asm volatile("cp.async.commit_group;" ::: "memory");
    for(int start=begin;start<end;start+=32) {
      asm volatile("cp.async.wait_group 0;" ::: "memory");
      __syncthreads();
      copy_weight(raw[phase^1],w,column,outputs,start+32,end);
      asm volatile("cp.async.commit_group;" ::: "memory");
      for(int i=threadIdx.x;i<32*32;i+=128) {
        int row=i/32,k=i%32;
        as[row][k]=(first+row<rows && start+k<end) ? flush(x[(size_t)(first+row)*WIDTH+start+k]) : 0.0f;
      }
      for(int i=threadIdx.x;i<64*32;i+=128)bs[i%32][i/32]=widen(raw[phase][i]);
      __syncthreads();
#if WIDTH % 32 == 0
      const int valid=32;
#else
      int valid=end-start<32 ? end-start : 32;
#endif
      float a[4],b[4];
      #pragma unroll
      for(int m=0;m<4;++m)a[m]=as[ty+m*8][0];
      #pragma unroll
      for(int n=0;n<4;++n)b[n]=bs[0][tx+n*16];
      #pragma unroll
      for(int k=0;k<32;++k) {
        if(k>=valid)break;
        float an[4]={},bn[4]={};
        if(k+1<valid) {
          #pragma unroll
          for(int m=0;m<4;++m)an[m]=as[ty+m*8][k+1];
          #pragma unroll
          for(int n=0;n<4;++n)bn[n]=bs[k+1][tx+n*16];
        }
        #pragma unroll
        for(int m=0;m<4;++m) {
          #pragma unroll
          for(int n=0;n<4;++n)
            asm volatile("fma.rn.f32 %0, %1, %2, %0;" : "+f"(accum[m][n]) : "f"(a[m]),"f"(b[n]));
        }
        #pragma unroll
        for(int m=0;m<4;++m)a[m]=an[m];
        #pragma unroll
        for(int n=0;n<4;++n)b[n]=bn[n];
      }
      phase^=1;
    }
    asm volatile("cp.async.wait_group 0;" ::: "memory");
    __syncthreads();
    #pragma unroll
    for(int m=0;m<4;++m) {
      #pragma unroll
      for(int n=0;n<4;++n) {
        int row=first+ty+m*8,col=column+tx+n*16;
        if(row<rows && col<outputs) {
          float v=flush(accum[m][n]);
          partials[((size_t)blockIdx.z*rows+row)*outputs+col]=v;
          if((__float_as_uint(v)&0x7f800000u)==0x7f800000u)atomicOr(error,1);
        }
      }
    }
  }
}

extern "C" __global__ void ordered_finish(const float* partials,const u16* bias,float* output,int* error,int rows,int outputs) {
  int n=blockIdx.x*256+threadIdx.x,row=blockIdx.y;
  if(n>=outputs)return;
  float stack[LEVELS];unsigned occupied=0;
  #pragma unroll 1
  for(int p=0;p<PARTS;++p) {
    float value=partials[((size_t)p*rows+row)*outputs+n];
    int level=0;
    while(occupied&(1u<<level)) {value=add_rn(stack[level],value);occupied^=1u<<level;++level;}
    stack[level]=value;occupied|=1u<<level;
  }
  float value=0.0f;bool have=false;
  #pragma unroll
  for(int level=0;level<LEVELS;++level)if(occupied&(1u<<level)) {
    value=have ? add_rn(stack[level],value) : stack[level];have=true;
  }
#if HAS_BIAS
  value=add_rn(value,widen(bias[n]));
#endif
  output[(size_t)row*outputs+n]=flush(value);
  if((__float_as_uint(value)&0x7f800000u)==0x7f800000u)atomicOr(error,1);
}
'''


class OrderedFmaKernels(sc.StrictCudaKernels):
    def __init__(self,device,*,max_partial_bytes=16*1024**2):
        if type(max_partial_bytes)is not int or max_partial_bytes<4:raise ReferenceArithmeticError('FMA partial budget')
        super().__init__(device)
        if int(self.arch[3:])<80:raise ReferenceArithmeticError('FMA prefetch prototype needs sm80+')
        self.max_partial_bytes=max_partial_bytes

    def _functions_for(self,width,bias):
        name=f'ordered-fma-k{width}-bias{int(bias)}'
        if name not in self._functions:
            parts=(width+255)//256
            header=f'#define WIDTH {width}\n#define PARTS {parts}\n#define LEVELS {parts.bit_length()}\n#define HAS_BIAS {int(bias)}\n'
            self._functions[name]=self._compile(name,header+_SOURCE,['ordered_fma','ordered_finish'],
                                               ptx_exact=('fma.rn.f32',),sass_exact=('FFMA',))
        return self._functions[name]

    @torch.inference_mode()
    def linear(self,value,weight,bias=None,*,error_flag=None,**kwargs):
        rows,width,outputs=sc.validate_linear(value,weight,bias,device=self.device)
        parts=(width+255)//256
        capacity=self.max_partial_bytes//(parts*outputs*4)
        if capacity<1:raise ReferenceArithmeticError('One FMA row exceeds bounded partial workspace')
        functions=self._functions_for(width,bias is not None)
        flag=self.new_error_flag()if error_flag is None else error_flag
        x=value.contiguous().reshape(rows,width)
        result=torch.empty((rows,outputs),dtype=torch.float32,device=self.device)
        for first in range(0,rows,capacity):
            count=min(capacity,rows-first)
            partials=torch.empty((parts,count,outputs),dtype=torch.float32,device=self.device)
            self._launch(functions['ordered_fma'],grid=((outputs+63)//64,min(65535,(count+31)//32),parts),block=(128,1),
                         pointers=(x[first:first+count],weight,partials,flag),integers=(count,outputs))
            self._launch(functions['ordered_finish'],grid=((outputs+255)//256,count,1),block=(256,1),
                         pointers=(partials,weight if bias is None else bias,result[first:first+count],flag),integers=(count,outputs))
        self._finish(flag,error_flag)
        return result.reshape(*value.shape[:-1],outputs)

    def linear_decode(self,*args,**kwargs):
        kwargs.pop('target_ctas_per_sm',None)
        return self.linear(*args,**kwargs)

    def linear_many(self,value,weights,biases=None,*,error_flag=None,**kwargs):
        biases=(None,)*len(weights)if biases is None else biases
        return tuple(self.linear(value,w,b,error_flag=error_flag)for w,b in zip(weights,biases,strict=True))

    def identity(self):
        result={**super().identity(),'kernel':VERSION,'execution':'ordered_simt_fma256_shared_fp16_probe',
                'arithmetic':{'weight':'live_fp16','input':'normal_fp32','chunkK':256,
                              'chunkAccumulation':'serial_k_fma_rn_f32_preserve_subnormals',
                              'chunkPublication':'signed_ftz','merge':'pruned_adjacent_pair_f32_add_rn_signed_ftz'},
                'maxPartialBytes':self.max_partial_bytes,
                'prototypeSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        result['fingerprint']=canonical_json_hash({k:v for k,v in result.items()if k!='fingerprint'})
        return result
