"""Unselected integer dot via FP16 MMA, with exact FP32 partials bounded by 2^24."""
import hashlib
from pathlib import Path

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_cuda as ic
from heteroes.eval.reference_ops import ReferenceArithmeticError
from bounded_reference import block_length

_MMA = r'''
__device__ __forceinline__ u16 half_integer(int value) {
  u16 result;
  asm("cvt.rn.f16.s32 %0, %1;" : "=h"(result) : "r"(value));
  return result;
}
__device__ __forceinline__ void bounded_mma(float* c,const unsigned* a,const unsigned* b) {
  asm volatile("mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32 "
    "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};"
    : "+f"(c[0]), "+f"(c[1]), "+f"(c[2]), "+f"(c[3])
    : "r"(a[0]), "r"(a[1]), "r"(a[2]), "r"(a[3]), "r"(b[0]), "r"(b[1]));
}
'''

_LINEAR = r'''
extern "C" __global__ void __launch_bounds__(32*WARPS)
integer_linear(const qi_t* x,const u16* w,const u16* bias,const int* ex,const int* ew,
               float* out,int* error,i64* partials,int rows,int outputs) {
  int lane=threadIdx.x&31, warp=threadIdx.x>>5, group=lane>>2, thread=lane&3;
  int column=blockIdx.x*(WARPS*8)+warp*8;
  int weight_row=column+group;
  int exponent=weight_row<outputs ? ew[weight_row] : 0;
  for(int first=blockIdx.y*(M_GROUPS*16);first<rows;first+=gridDim.y*(M_GROUPS*16)) {
    i64 total[M_GROUPS][4]={};
    for(int start=blockIdx.z*16;start<WIDTH;start+=SPLIT_K*BLOCK_K) {
      float accum[M_GROUPS][4]={};
      // All terms are integer and any partial sum has magnitude <= 2^24, independent of order.
      #pragma unroll
      for(int offset=0;offset<BLOCK_K;offset+=16) {
        int tile=start+offset*SPLIT_K;
        if(tile>=WIDTH)break;
        unsigned b[2]={};
        #pragma unroll
        for(int word=0;word<2;++word) {
          int k=tile+thread*2+word*8;
          #pragma unroll
          for(int i=0;i<2;++i) {
            u16 value=(weight_row<outputs && k+i<WIDTH) ?
              half_integer(quant_half(w[(size_t)weight_row*WIDTH+k+i],exponent)) : 0;
            b[word]|=((unsigned)value)<<(16*i);
          }
        }
        #pragma unroll
        for(int m=0;m<M_GROUPS;++m) {
          unsigned a[4]={};
          #pragma unroll
          for(int word=0;word<4;++word) {
            int row=first+m*16+group+(word&1)*8;
            int k=tile+thread*2+(word>>1)*8;
            if(row<rows) {
              if((WIDTH%2)==0 && k+1<WIDTH) a[word]=((const unsigned*)x)[((size_t)row*WIDTH+k)/2];
              else {
                if(k<WIDTH)a[word]=(unsigned)x[(size_t)row*WIDTH+k];
                if(k+1<WIDTH)a[word]|=((unsigned)x[(size_t)row*WIDTH+k+1])<<16;
              }
            }
          }
          bounded_mma(accum[m],a,b);
        }
      }
      #pragma unroll
      for(int m=0;m<M_GROUPS;++m) {
        #pragma unroll
        for(int i=0;i<4;++i) {
          i64 exact;
          asm("cvt.rzi.s64.f32 %0, %1;" : "=l"(exact) : "f"(accum[m][i]));
          total[m][i]+=exact;
        }
      }
    }
    #pragma unroll
    for(int m=0;m<M_GROUPS;++m) {
      #pragma unroll
      for(int d=0;d<4;++d) {
        int row=first+m*16+group+(d>>1)*8, n=column+thread*2+(d&1);
        if(row<rows && n<outputs) {
          i64 sum=total[m][d];
#if SPLIT_K > 1
          partials[((size_t)blockIdx.z*rows+row)*outputs+n]=sum;
#else
          float v=encode(sum,ex[row]+ew[n]-(MAGNITUDE_BITS-1)-(WEIGHT_BITS-1),error);
          if(HAS_BIAS)v=add_rn(v,widen(bias[n]));
          out[(size_t)row*outputs+n]=v;
          if((__float_as_uint(v)&0x7f800000u)==0x7f800000u)atomicOr(error,1);
#endif
        }
      }
    }
  }
}

'''


class BoundedKernels(ic.IntegerCudaKernels):
    def __init__(self, device, *, activation_bits=8, weight_bits=8, **kwargs):
        self.activation_bits, self.weight_bits = activation_bits, weight_bits
        self.block_k = block_length(activation_bits, weight_bits)
        # The inherited scheduling/budget controls remain; this is a separately identified arithmetic.
        super().__init__(device, magnitude_bits=14, **kwargs)

    def arithmetic(self):
        return {'operator':'bounded_half_integer_dot_v1_probe','activationBits':self.activation_bits,
                'weightBits':self.weight_bits,'blockK':self.block_k,'partialMagnitudeAtMost':2**24,
                'rounding':'row_power2_integer_rne_exact_dot_then_f32_rne_signed_ftz',
                'weightStorage':'live_fp16','coefficientStorage':'call_local_fp16_integers',
                'hardwareQualified':False}

    def identity(self):
        result={'kernel':'bounded_half_integer_mma_v1_probe','arithmetic':self.arithmetic(),
                'arch':self.arch,'gpu':torch.cuda.get_device_name(self.device),
                'nvrtcVersion':self.nvrtc_version,'builds':dict(sorted(self._builds.items())),
                'prototypeSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'baseIntegerSourceSha256':hashlib.sha256(Path(ic.__file__).read_bytes()).hexdigest(),
                'hardwareQualified':False}
        result['fingerprint']=canonical_json_hash(result)
        return result

    def _integer_functions(self, width, has_bias=False, row_tile=16, warps=4, split_k=1, *, packed_input=False):
        name=f'bounded-a{self.activation_bits}-w{self.weight_bits}-k{width}-bias{int(has_bias)}-m{row_tile}-w{warps}-s{split_k}'
        if name not in self._functions:
            source=ic._SOURCE
            start=source.index('#if MAGNITUDE_BITS == 14\ntypedef')
            end=source.index('#endif',start)+len('#endif')
            source=source[:start]+'typedef u16 qi_t;'+source[end:]
            start=source.index('__device__ __forceinline__ int quant_half(')
            end=source.index('__device__ __forceinline__ void pack_digits(',start)
            source=source[:start]+source[start:end].replace('MAGNITUDE_BITS','WEIGHT_BITS')+source[end:]
            pos=source.index('extern "C" __global__ void integer_input(')
            source=source[:pos]+_MMA+source[pos:]
            old='q[(size_t)row*WIDTH+k]=(qi_t)quant_float(__float_as_uint(x[(size_t)row*WIDTH+k]),exponent);'
            assert source.count(old)==1
            source=source.replace(old,'q[(size_t)row*WIDTH+k]=half_integer(quant_float(__float_as_uint(x[(size_t)row*WIDTH+k]),exponent));')
            start=source.index('extern "C" __global__ void __launch_bounds__')
            end=source.index('// Same arithmetic, different scheduling:',start)
            source=source[:start]+_LINEAR+source[end:]
            old='sum+=(i64)x[(size_t)row*WIDTH+k]*quant_half(w[(size_t)n*WIDTH+k],exponent);'
            assert source.count(old)==1
            source=source.replace(old,'sum+=(i64)(int)widen(x[(size_t)row*WIDTH+k])*quant_half(w[(size_t)n*WIDTH+k],exponent);')
            source=source.replace('-2*(MAGNITUDE_BITS-1)','-(MAGNITUDE_BITS-1)-(WEIGHT_BITS-1)')
            defines=dict(WIDTH=width,MAGNITUDE_BITS=self.activation_bits,WEIGHT_BITS=self.weight_bits,
                         DIGITS=2,HAS_BIAS=int(has_bias),M_GROUPS=row_tile//16,WARPS=warps,SPLIT_K=split_k,
                         PACKED_INPUT=0,WEIGHT_READ32=0,WEIGHT_PREFETCH=0,BLOCK_K=self.block_k)
            header=''.join(f'#define {k} {v}\n' for k,v in defines.items())
            self._functions[name]=self._compile(name,header+source,
                ['integer_input','integer_weights','integer_linear','integer_simt','integer_finish'],
                ptx_exact=('mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32',
                           'cvt.rn.f16.s32','cvt.rzi.s64.f32','cvt.rzi.s32.f32','cvt.rni.s32.f32'),
                sass_exact=('HMMA.16816.F32','I2FP.F16.S32','I2F.F16','F2I.NTZ','F2I.TRUNC.NTZ','F2I.U64.TRUNC.NTZ','F2I.S64.TRUNC'))
            assert not self._builds[name]['ptxAudit']['floatOps'].get('mul.rn.f32',0)
        return self._functions[name]

    @torch.inference_mode()
    def quantize_input(self, value, *, error_flag=None, _functions=None, _packed=False):
        if value.dtype!=torch.float32 or value.device!=self.device or value.ndim!=2 or not value.numel():
            raise ReferenceArithmeticError('Bounded integer encoding needs a nonempty CUDA FP32 matrix')
        if not 1<=value.shape[1]<=32768:
            raise ReferenceArithmeticError('Bounded integer input width')
        value=value.contiguous()
        functions=self._integer_functions(value.shape[1]) if _functions is None else _functions
        encoded=torch.empty_like(value,dtype=torch.float16)
        exponents=torch.empty(value.shape[0],dtype=torch.int32,device=self.device)
        flag=self.new_error_flag() if error_flag is None else error_flag
        self._launch(functions['integer_input'],grid=value.shape[0],block=(256,1),
                     pointers=(value,encoded,exponents,flag),integers=(value.shape[0],))
        self._finish(flag,error_flag)
        return encoded,exponents
