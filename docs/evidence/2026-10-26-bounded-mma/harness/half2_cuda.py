"""Unselected packed-half RNE quantizer for the same bounded integer coefficient contract."""
import hashlib
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_cuda as ic
from bounded_cuda import BoundedKernels, _MMA

_PAIR = r'''
__device__ __forceinline__ unsigned quant_half_pair(unsigned raw,int exponent) {
#if WEIGHT_BITS <= 10
  int delta=WEIGHT_BITS-1-exponent;
  unsigned absolute=raw&0x7fff7fffu;
  if(delta<=15 && delta>=-14 && (absolute&65535u)<0x7c00u && (absolute>>16)<0x7c00u) {
    unsigned half_scale=(unsigned)(delta+15)<<10;
    unsigned scale=half_scale|(half_scale<<16),magic=0x64006400u;
    unsigned scaled,rounded,encoded;
    asm volatile("mul.rn.f16x2 %0, %1, %2;" : "=r"(scaled) : "r"(absolute),"r"(scale));
    asm volatile("add.rn.f16x2 %0, %1, %2;" : "=r"(rounded) : "r"(scaled),"r"(magic));
    asm volatile("sub.rn.f16x2 %0, %1, %2;" : "=r"(encoded) : "r"(rounded),"r"(magic));
    return encoded|(raw&0x80008000u);
  }
#endif
  return (unsigned)half_integer(quant_half((u16)raw,exponent))|
         ((unsigned)half_integer(quant_half((u16)(raw>>16),exponent))<<16);
}
'''

_OLD = r'''          #pragma unroll
          for(int i=0;i<2;++i) {
            u16 value=(weight_row<outputs && k+i<WIDTH) ?
              half_integer(quant_half(w[(size_t)weight_row*WIDTH+k+i],exponent)) : 0;
            b[word]|=((unsigned)value)<<(16*i);
          }'''

_NEW = r'''          unsigned raw=0;
          if(weight_row<outputs) {
            if((WIDTH%2)==0 && (((unsigned long long)w)&3ull)==0ull && k+1<WIDTH)
              asm volatile("ld.global.u32 %0, [%1];" : "=r"(raw) : "l"(w+(size_t)weight_row*WIDTH+k));
            else {
              if(k<WIDTH)raw=(unsigned)w[(size_t)weight_row*WIDTH+k];
              if(k+1<WIDTH)raw|=((unsigned)w[(size_t)weight_row*WIDTH+k+1])<<16;
            }
          }
          b[word]=quant_half_pair(raw,exponent);'''


class Half2BoundedKernels(BoundedKernels):
    def _compile(self, name, source, entries, **kwargs):
        if name.startswith('bounded-'):
            if _OLD in source:
                assert source.count(_OLD)==1
                source=source.replace(_OLD,_NEW)
                pos=source.index('extern "C" __global__ void integer_input(')
                source=source[:pos]+_PAIR+source[pos:]
            else:
                assert entries==['probe_pairs']
            kwargs['ptx_exact']=(*kwargs.get('ptx_exact',()),'mul.rn.f16x2','add.rn.f16x2','sub.rn.f16x2')
            kwargs['sass_exact']=(*kwargs.get('sass_exact',()),'HMUL2','HADD2')
        return super()._compile(name,source,entries,**kwargs)

    def identity(self):
        result={**super().identity(),'weightQuantization':'packed_half2_magic_rne_v1_probe',
                'quantizerSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        result['fingerprint']=canonical_json_hash({k:v for k,v in result.items() if k!='fingerprint'})
        return result


def pair_probe_source(bits):
    prefix=ic._SOURCE[:ic._SOURCE.index('__device__ __forceinline__ void pack_digits(')]
    start=prefix.index('__device__ __forceinline__ int quant_half(')
    prefix=prefix[:start]+prefix[start:].replace('MAGNITUDE_BITS','WEIGHT_BITS')
    stub=r'''
extern "C" __global__ void probe_pairs(unsigned* output,int selector) {
  int i=blockIdx.x*256+threadIdx.x;
  if(i>=40*65536)return;
  int exponent=i/65536-24;
  u16 first=(u16)i,second=selector ? (u16)(first*73+19) : (u16)(first^32768u);
  unsigned a=first&0x7fffu,b=second&0x7fffu;
  int ea=!a ? -1000 : (a>>10) ? (int)(a>>10)-15 : 31-__clz(a)-24;
  int eb=!b ? -1000 : (b>>10) ? (int)(b>>10)-15 : 31-__clz(b)-24;
  output[i]=(a>=0x7c00u || b>=0x7c00u || ea>exponent || eb>exponent) ? 0xffffffffu :
    quant_half_pair((unsigned)first|((unsigned)second<<16),exponent);
}
'''
    return f'#define MAGNITUDE_BITS 8\n#define WEIGHT_BITS {bits}\n'+prefix+_MMA+_PAIR+stub
