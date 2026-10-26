"""Experimental NVRTC signed-integer MMA for the separately versioned row-scaled reference.

No quantized weight matrix is materialized. Live FP16 weights are quantized inside each MMA tile. Input
quantization is per call. Weight exponents are per call unless the locked graph adapter explicitly refreshes
them at request entry; retained buffers are cleared at exit. It is NOT the prior FP32-tree arithmetic.
"""

import hashlib
import math
from pathlib import Path
import weakref

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_reference as reference
from heteroes.eval import integer_plan as planning
from heteroes.eval import strict_cuda as sc
from heteroes.eval import integer_lm_head
from heteroes.eval.reference_ops import ReferenceArithmeticError

INTEGER_CUDA_VERSION = "row_scaled_integer_mma_cuda_v1_experimental"
# "stream" schedules eligible MMA projections (K % 16 == 0, 16-byte aligned operands) through the multistage
# kernel; "tile" keeps the per-warp tile kernel. Both compute the same exact integer dot and final encoding.
MMA_SCHEDULES = ("auto", "tile", "stream")
STREAM_COLUMNS = 64  # prefill: 16 columns per warp amortize the weight conversion over many row tiles
# Prefill (64 columns) is MMA-bound: two stages and a 168-register bound fit three CTAs per SM (measured,
# SM120: 896x9728 at 888 rows 546 -> 496 us). Decode (32 columns) keeps three stages to hide DRAM latency.
PREFILL_STAGES, PREFILL_MIN_BLOCKS = 2, 3
DECODE_STREAM_COLUMNS = 32  # decode: 8 columns per warp, twice the CTAs and fewer registers (measured, SM120)
RMS_THREADS, SILU_THREADS = 256, 1024  # RMS rows up to 32 * RMS_THREADS = MAX_NORM_WIDTH


def _mma_schedule(requested):
    if requested not in MMA_SCHEDULES:
        raise ReferenceArithmeticError("Integer MMA schedule must be auto, tile or stream")
    return "stream" if requested == "auto" else requested


def weight_read_plan(magnitude_bits, arch, requested):
    reference._precision(magnitude_bits)
    if requested not in ("auto", "scalar", "paired", "prefetch2"):
        raise ReferenceArithmeticError("Integer weight load must be auto, scalar, paired or prefetch2")
    if requested == "auto":
        return "prefetch2" if magnitude_bits == 22 and arch in ("sm_86", "sm_120") else "scalar"
    return requested


def static_identity(magnitude_bits=14, max_partial_bytes=16 * 1024**2, *, weight_load="auto", mma_schedule="auto"):
    reference._precision(magnitude_bits)
    weight_read_plan(magnitude_bits, "sm_120", weight_load)
    _mma_schedule(mma_schedule)
    if type(max_partial_bytes) is not int or max_partial_bytes < 1:
        raise ReferenceArithmeticError("Integer workspace budget must be a positive integer")
    return {
        "kernel": INTEGER_CUDA_VERSION,
        "linear": reference.identity(magnitude_bits),
        "nonlinear": sc.static_identity(),
        "integerSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "boundedLmHeadSourceSha256": integer_lm_head.source_sha256(),
        "maxPartialBytes": max_partial_bytes,
        "activationPacking": "radix_planes_once_v1_experimental",
        "weightLoad": weight_load,
        "weightReadPolicy": "raw_half_prefetch2_sm86_sm120_b22_v2_experimental",
        "mmaSchedule": mma_schedule,
        "streamPolicy": "multistage_cp_async_k16_aligned_v1_experimental",
        "decodePlanning": planning.identity(),
        "hardwareQualified": False,
    }


# integer_weights for every live matrix of a request in one launch: one warp per row and 16-byte loads. The
# maximum magnitude, exponent and nonfinite flag of each row are those of integer_weights (order-independent).
_WEIGHTS_BATCHED_SOURCE = r"""
typedef unsigned short u16;
// table: [matrices + 1] first CTA of each matrix, then per matrix (weight, exponents, rows, width).
extern "C" __global__ void __launch_bounds__(256) integer_weights_batched(const long long* table, int* error,
                                                                           int matrices) {
  const long long block = blockIdx.x;
  int lo = 0, hi = matrices - 1;
  while (lo < hi) {
    const int mid = (lo + hi + 1) >> 1;
    if (table[mid] <= block) lo = mid; else hi = mid - 1;
  }
  const long long* meta = table + matrices + 1 + 4 * lo;
  const int rows = (int)meta[2], width = (int)meta[3], lane = threadIdx.x & 31;
  const int row = (int)(block - table[lo]) * 8 + (threadIdx.x >> 5);
  if (row >= rows) return;
  const uint4* source = reinterpret_cast<const uint4*>(reinterpret_cast<const u16*>(meta[0]) + (size_t)row * width);
  unsigned maximum = 0, bad = 0;
  for (int c = lane; c < (width >> 3); c += 32) {
    const uint4 v = source[c];
    const unsigned words[4] = {v.x, v.y, v.z, v.w};
#pragma unroll
    for (int i = 0; i < 8; ++i) {
      unsigned a = (words[i >> 1] >> (16 * (i & 1))) & 0x7fffu;
      if (a >= 0x7c00u) {bad = 1; a = 0;}
      maximum = a > maximum ? a : maximum;
    }
  }
#pragma unroll
  for (int m = 16; m; m >>= 1) {
    const unsigned other = __shfl_xor_sync(0xffffffffu, maximum, m);
    maximum = other > maximum ? other : maximum;
  }
  const unsigned e = maximum >> 10;
  const int exponent = !maximum ? 0 : e ? (int)e - 15 : 31 - __clz(maximum) - 24;
  if (lane == 0) reinterpret_cast<int*>(meta[1])[row] = exponent;
  if (bad) atomicOr(error, 1);
}
"""

# Shared by the projection module and the fused strict-op module (which has its own float helpers).
_QUANT_FLOAT = r"""__device__ __forceinline__ unsigned rne_shift(unsigned value, int shift) {
  if(shift<=0) return value << -shift;
  if(shift>=32) return 0;
  unsigned whole=value>>shift, remainder=value&((1u<<shift)-1u), halfway=1u<<(shift-1);
  return whole + (remainder>halfway || (remainder==halfway && (whole&1u)));
}
__device__ __forceinline__ int quant_float(unsigned u, int exponent) {
  unsigned a=u&0x7fffffffu, e=a>>23;
  if(e==0 || e==255) return 0;
  int q=(int)rne_shift((a&0x7fffffu)|0x800000u, exponent-((int)e-127)+24-MAGNITUDE_BITS);
  return u>>31 ? -q : q;
}
"""
_PACK_DIGITS = r"""__device__ __forceinline__ void pack_digits(unsigned* words, int q, int element) {
  #pragma unroll
  for(int d=0;d<DIGITS;++d) {
    int low=q&255;
    if(low>=128) low-=256;
    words[d] |= ((unsigned)low&255u) << (8*element);
    q=(q-low)/256; // exact division, including negative values; no signed-left-shift assumption
  }
}

"""

# Exact int64 -> FP32 encoding of a reconstructed projection sum (round to nearest even, overflow flagged).
_ENCODE = r"""__device__ __forceinline__ u64 rne64(u64 value, int shift) {
  if(shift<=0) return value << -shift;
  if(shift>=64) return 0; // all admitted magnitudes are <2^63; no half-way case at shift 64
  u64 whole=value>>shift, remainder=value&((1ull<<shift)-1ull), halfway=1ull<<(shift-1);
  return whole + (remainder>halfway || (remainder==halfway && (whole&1ull)));
}
__device__ __forceinline__ float encode(i64 sum,int scale,int* error) {
  if(!sum) return 0.0f;
  unsigned sign=sum<0 ? 0x80000000u : 0;
  u64 magnitude=sum<0 ? (u64)(-sum) : (u64)sum;
  int leading=63-__clzll(magnitude), exponent=leading+scale;
  if(exponent < -126) {
    u64 rounded=rne64(magnitude,-scale-149);
    return __uint_as_float(sign | (rounded>=0x800000ull ? 0x00800000u : 0));
  }
  u64 rounded=rne64(magnitude,leading-23);
  if(rounded>=0x1000000ull) {rounded>>=1; ++exponent;}
  if(exponent>127) {atomicOr(error,1); return __uint_as_float(sign|0x7f800000u);}
  return __uint_as_float(sign | ((unsigned)(exponent+127)<<23) | ((unsigned)rounded&0x7fffffu));
}

"""

_SOURCE = (
    sc._LINEAR_SOURCE.split("// One output column")[0]
    + r"""
typedef unsigned long long u64;
typedef long long i64;
#if MAGNITUDE_BITS == 14
typedef short qi_t;
#else
typedef int qi_t;
#endif

"""
    + _QUANT_FLOAT
    + r"""__device__ __forceinline__ int quant_half(u16 u, int exponent) {
  unsigned a=u&0x7fffu;
  if(!a || a>=0x7c00u) return 0;
  // Exact FP16 widening and exponent-bit scaling. For every admitted live row exponent in [-24,15],
  // the nonzero scaled weight is normal FP32: >=2^-26 (B14) or >=2^-18 (B22), and <2^B.
  // Thus no intermediate rounding/underflow/overflow occurs; integer RNE matches the CPU contract.
  unsigned bits=__float_as_uint(widen(u));
  bits+=(unsigned)((MAGNITUDE_BITS-1-exponent)*0x800000);
  int result;
  asm("cvt.rni.s32.f32 %0, %1;" : "=r"(result) : "f"(__uint_as_float(bits)));
  return result;
}
"""
    + _PACK_DIGITS
    + r"""#if WEIGHT_PREFETCH
// Each lane owns four words in each stage. Copies and their consumers use the same lane;
// no other thread reads this storage, so the per-thread async wait needs no CTA barrier.
__device__ __forceinline__ void prefetch_half_tile(unsigned* destination,const u16* w,
                                                  int n,int outputs,int start,int thread) {
  #pragma unroll
  for(int word=0;word<2;++word) {
    int k=start+thread*4+word*16;
#if WIDTH % 4 == 0
    if((((unsigned long long)w)&7ull)==0ull) {
      int valid=(n<outputs && k+3<WIDTH) ? 8 : 0;
      const u16* pointer=valid ? w+(size_t)n*WIDTH+k : w;
      unsigned long long address;
      asm volatile("cvta.to.shared.u64 %0, %1;" : "=l"(address) : "l"(destination+word*2));
      asm volatile("cp.async.ca.shared.global [%0], [%1], 8, %2;" ::
                   "r"((unsigned)address), "l"(pointer), "r"(valid) : "memory");
    } else
#endif
    {
      unsigned lo=0,hi=0;
      if(n<outputs) {
        if(k<WIDTH)lo=(unsigned)w[(size_t)n*WIDTH+k];
        if(k+1<WIDTH)lo|=((unsigned)w[(size_t)n*WIDTH+k+1])<<16;
        if(k+2<WIDTH)hi=(unsigned)w[(size_t)n*WIDTH+k+2];
        if(k+3<WIDTH)hi|=((unsigned)w[(size_t)n*WIDTH+k+3])<<16;
      }
      destination[word*2]=lo;destination[word*2+1]=hi;
    }
  }
}
#endif

extern "C" __global__ void integer_input(const float* x, qi_t* q, int* exponents, int* error, int rows) {
  int row=blockIdx.x, t=threadIdx.x;
  unsigned maximum=0, bad=0;
  for(int k=t;k<WIDTH;k+=256) {
    unsigned a=__float_as_uint(x[(size_t)row*WIDTH+k])&0x7fffffffu;
    if(a>=0x7f800000u) {bad=1; a=0;}
    if((a&0x7f800000u)==0) a=0;
    maximum=a>maximum ? a : maximum;
  }
  __shared__ unsigned shared[256];
  shared[t]=maximum;
  __syncthreads();
  for(int stride=128;stride;stride>>=1) {
    if(t<stride) shared[t]=shared[t+stride]>shared[t] ? shared[t+stride] : shared[t];
    __syncthreads();
  }
  int exponent=shared[0] ? (int)(shared[0]>>23)-127 : 0;
  if(t==0) exponents[row]=exponent;
#if PACKED_INPUT
  for(int word=t;word<(WIDTH+3)/4;word+=256) {
    unsigned packed[DIGITS]={};
    #pragma unroll
    for(int i=0;i<4;++i) {
      int k=word*4+i;
      int value=k<WIDTH ? quant_float(__float_as_uint(x[(size_t)row*WIDTH+k]),exponent) : 0;
      pack_digits(packed,value,i);
    }
    #pragma unroll
    for(int d=0;d<DIGITS;++d) ((unsigned*)q)[((size_t)d*rows+row)*((WIDTH+3)/4)+word]=packed[d];
  }
#else
  for(int k=t;k<WIDTH;k+=256) q[(size_t)row*WIDTH+k]=(qi_t)quant_float(__float_as_uint(x[(size_t)row*WIDTH+k]),exponent);
#endif
  if(bad) atomicOr(error,1);
}

extern "C" __global__ void integer_weights(const u16* w, int* exponents, int* error, int outputs) {
  int row=blockIdx.x, t=threadIdx.x;
  unsigned maximum=0,bad=0;
  for(int k=t;k<WIDTH;k+=256) {
    unsigned a=w[(size_t)row*WIDTH+k]&0x7fffu;
    if(a>=0x7c00u) {bad=1; a=0;}
    maximum=a>maximum ? a : maximum;
  }
  __shared__ unsigned shared[256];
  shared[t]=maximum;
  __syncthreads();
  for(int stride=128;stride;stride>>=1) {
    if(t<stride) shared[t]=shared[t+stride]>shared[t] ? shared[t+stride] : shared[t];
    __syncthreads();
  }
  unsigned a=shared[0], e=a>>10;
  int exponent=!a ? 0 : e ? (int)e-15 : 31-__clz(a)-24;
  if(t==0) exponents[row]=exponent;
  if(bad) atomicOr(error,1);
}

"""
    + _ENCODE
    + r"""__device__ __forceinline__ void mma(int* c,const unsigned* a,const unsigned* b) {
  asm volatile("mma.sync.aligned.m16n8k32.row.col.s32.s8.s8.s32 "
    "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};"
    : "+r"(c[0]), "+r"(c[1]), "+r"(c[2]), "+r"(c[3])
    : "r"(a[0]), "r"(a[1]), "r"(a[2]), "r"(a[3]), "r"(b[0]), "r"(b[1]));
}

extern "C" __global__ void __launch_bounds__(32*WARPS)
integer_linear(const qi_t* x,const u16* w,const u16* bias,const int* ex,const int* ew,
               float* out,int* error,i64* partials,int rows,int outputs) {
  int lane=threadIdx.x&31, warp=threadIdx.x>>5, group=lane>>2, thread=lane&3;
  int column=blockIdx.x*(WARPS*8)+warp*8;
#if WEIGHT_PREFETCH
  __shared__ __align__(16) unsigned raw_shared[2][32*WARPS][4];
#endif
  for(int first=blockIdx.y*(M_GROUPS*16);first<rows;first+=gridDim.y*(M_GROUPS*16)) {
    // Equal radix degrees share an int32 accumulator. At most three limb products contribute to a
    // degree: 3*128^2*32768 < 2^31, including every possible signed partial sum.
    int accum[M_GROUPS][2*DIGITS-1][4]={};
#if WEIGHT_PREFETCH
    int phase=0;
    prefetch_half_tile(raw_shared[0][threadIdx.x],w,column+group,outputs,blockIdx.z*32,thread);
    asm volatile("cp.async.commit_group;" ::: "memory");
#endif
    for(int start=blockIdx.z*32;start<WIDTH;start+=SPLIT_K*32) {
#if WEIGHT_PREFETCH
      asm volatile("cp.async.wait_group 0;" ::: "memory");
      unsigned current[4];
      #pragma unroll
      for(int i=0;i<4;++i)current[i]=raw_shared[phase][threadIdx.x][i];
      phase^=1;
      prefetch_half_tile(raw_shared[phase][threadIdx.x],w,column+group,outputs,start+SPLIT_K*32,thread);
      asm volatile("cp.async.commit_group;" ::: "memory");
#endif
      unsigned b[DIGITS][2]={};
      int n=column+group;
      int exponent=n<outputs ? ew[n] : 0;
      #pragma unroll
      for(int word=0;word<2;++word) {
        unsigned packed[DIGITS]={};
#if WEIGHT_PREFETCH
        #pragma unroll
        for(int pair=0;pair<2;++pair) {
          unsigned halves=current[word*2+pair];
          pack_digits(packed,quant_half((u16)halves,exponent),pair*2);
          pack_digits(packed,quant_half((u16)(halves>>16),exponent),pair*2+1);
        }
#elif WEIGHT_READ32
        #pragma unroll
        for(int pair=0;pair<2;++pair) {
          int k=start+thread*4+word*16+pair*2;
          unsigned halves=0;
          if(n<outputs) {
            if((WIDTH%2)==0 && (((unsigned long long)w)&3ull)==0ull && k+1<WIDTH) {
              const u16* address=w+(size_t)n*WIDTH+k;
              asm volatile("ld.global.u32 %0, [%1];" : "=r"(halves) : "l"(address));
            } else {
              if(k<WIDTH) halves=(unsigned)w[(size_t)n*WIDTH+k];
              if(k+1<WIDTH) halves|=((unsigned)w[(size_t)n*WIDTH+k+1])<<16;
            }
          }
          pack_digits(packed,quant_half((u16)halves,exponent),pair*2);
          pack_digits(packed,quant_half((u16)(halves>>16),exponent),pair*2+1);
        }
#else
        #pragma unroll
        for(int i=0;i<4;++i) {
          int k=start+thread*4+word*16+i;
          int q=(n<outputs && k<WIDTH) ? quant_half(w[(size_t)n*WIDTH+k],exponent) : 0;
          pack_digits(packed,q,i);
        }
#endif
        #pragma unroll
        for(int d=0;d<DIGITS;++d) b[d][word]=packed[d];
      }
      #pragma unroll
      for(int m=0;m<M_GROUPS;++m) {
        unsigned a[DIGITS][4]={};
        #pragma unroll
        for(int word=0;word<4;++word) {
          int row=first+m*16+group+(word&1)*8;
#if PACKED_INPUT
          int k=start+thread*4+(word>>1)*16;
          #pragma unroll
          for(int d=0;d<DIGITS;++d)
            a[d][word]=(row<rows && k<WIDTH) ? ((const unsigned*)x)[((size_t)d*rows+row)*((WIDTH+3)/4)+k/4] : 0;
#else
          unsigned packed[DIGITS]={};
          #pragma unroll
          for(int i=0;i<4;++i) {
            int k=start+thread*4+(word>>1)*16+i;
            int q=(row<rows && k<WIDTH) ? (int)x[(size_t)row*WIDTH+k] : 0;
            pack_digits(packed,q,i);
          }
          #pragma unroll
          for(int d=0;d<DIGITS;++d) a[d][word]=packed[d];
#endif
        }
        #pragma unroll
        for(int i=0;i<DIGITS;++i) {
          #pragma unroll
          for(int j=0;j<DIGITS;++j) mma(accum[m][i+j],a[i],b[j]);
        }
      }
    }
#if WEIGHT_PREFETCH
    // Includes the last zero-filled lookahead and split partitions with no live K tile.
    asm volatile("cp.async.wait_group 0;" ::: "memory");
#endif
    #pragma unroll
    for(int m=0;m<M_GROUPS;++m) {
      #pragma unroll
      for(int d=0;d<4;++d) {
        int row=first+m*16+group+(d>>1)*8, n=column+thread*2+(d&1);
        if(row<rows && n<outputs) {
          i64 sum=0;
          #pragma unroll
          for(int degree=0;degree<2*DIGITS-1;++degree) sum+=(i64)accum[m][degree][d]*(1ll<<(8*degree));
#if SPLIT_K > 1
          partials[((size_t)blockIdx.z*rows+row)*outputs+n]=sum;
#else
          float v=encode(sum,ex[row]+ew[n]-2*(MAGNITUDE_BITS-1),error);
          if(HAS_BIAS) v=add_rn(v,widen(bias[n]));
          out[(size_t)row*outputs+n]=v;
          if((__float_as_uint(v)&0x7f800000u)==0x7f800000u) atomicOr(error,1);
#endif
        }
      }
    }
  }
}

// Same arithmetic, different scheduling: small row counts do not need padded Tensor Core rows.
extern "C" __global__ void integer_simt(const qi_t* x,const u16* w,const u16* bias,const int* ex,const int* ew,
                                        float* out,int* error,i64* partials,int rows,int outputs) {
  int lane=threadIdx.x&31, n=blockIdx.x*8+(threadIdx.x>>5);
  if(n>=outputs) return; // whole warp is inactive; every live warp executes each shuffle with all 32 lanes
  int exponent=ew[n];
  for(int row=blockIdx.y;row<rows;row+=gridDim.y) {
    i64 sum=0;
    for(int k=blockIdx.z*32+lane;k<WIDTH;k+=SPLIT_K*32)
      sum+=(i64)x[(size_t)row*WIDTH+k]*quant_half(w[(size_t)n*WIDTH+k],exponent);
    for(int offset=16;offset;offset>>=1) {
      i64 other=__shfl_down_sync(0xffffffffu,sum,offset);
      if(lane<offset) sum+=other; // never duplicate inactive-lane partials or exceed the nonoverflow bound
    }
    if(lane==0) {
#if SPLIT_K > 1
      partials[((size_t)blockIdx.z*rows+row)*outputs+n]=sum;
#else
      float v=encode(sum,ex[row]+ew[n]-2*(MAGNITUDE_BITS-1),error);
      if(HAS_BIAS) v=add_rn(v,widen(bias[n]));
      out[(size_t)row*outputs+n]=v;
      if((__float_as_uint(v)&0x7f800000u)==0x7f800000u) atomicOr(error,1);
#endif
    }
  }
}

extern "C" __global__ void integer_finish(const i64* partials,const u16* bias,const int* ex,const int* ew,
                                          float* out,int* error,int rows,int outputs) {
  int n=blockIdx.x*256+threadIdx.x;
  if(n>=outputs) return;
  for(int row=blockIdx.y;row<rows;row+=gridDim.y) {
    i64 sum=0;
    #pragma unroll
    for(int s=0;s<SPLIT_K;++s) sum+=partials[((size_t)s*rows+row)*outputs+n];
    float v=encode(sum,ex[row]+ew[n]-2*(MAGNITUDE_BITS-1),error);
    if(HAS_BIAS) v=add_rn(v,widen(bias[n]));
    out[(size_t)row*outputs+n]=v;
    if((__float_as_uint(v)&0x7f800000u)==0x7f800000u) atomicOr(error,1);
  }
}
// ---- Multistage streamed decode projection (same exact integer dot as integer_linear) ----
// Requires WIDTH % 16 == 0 and 16-byte aligned x/w. A CTA owns NT=32*JN output columns and one row tile;
// each warp owns 8*JN columns (JN n8 MMA tiles). Raw FP16 weights and packed activation planes stream
// through STAGES shared-memory buffers of KS=64 K values with cp.async. The K order inside each k32 MMA
// step is permuted identically for both operands (thread t holds physical K 8t..8t+7); an exact integer
// sum does not depend on the order of its terms, so every int32 degree accumulator and output is unchanged.
#ifndef JN
#define JN 2
#endif
#define NT (32*JN)  // a CTA owns NT columns: four warps of 8*JN
#define KS 64
#ifndef STAGES
#define STAGES 3
#endif
#define MT (M_GROUPS*16)
#define W_STAGE (NT*KS*2)
#define A_STAGE (DIGITS*MT*KS)

__device__ __forceinline__ void cp16(void* destination, const void* source, int bytes) {
  unsigned long long address;
  asm volatile("cvta.to.shared.u64 %0, %1;" : "=l"(address) : "l"(destination));
  asm volatile("cp.async.cg.shared.global [%0], [%1], 16, %2;" ::
               "r"((unsigned)address), "l"(source), "r"(bytes) : "memory");
}

__device__ __forceinline__ void stream_stage(unsigned char* sw, unsigned char* sa, const qi_t* x, const u16* w,
                                             int rows, int outputs, int first, int column0, int k0) {
  int tid=threadIdx.x;
  // Weights: NT rows of 8 sixteen-byte chunks. Chunk c of row r lives at chunk c^((r&1)<<2).
  #pragma unroll
  for(int i=0;i<NT*8/128;++i) {
    int c=tid+i*128, r=c>>3, chunk=c&7, n=column0+r, k=k0+chunk*8;
    int valid=(n<outputs && k<WIDTH) ? 16 : 0;
    cp16(sw+r*128+((chunk^((r&1)<<2))<<4), valid ? (const void*)(w+(size_t)n*WIDTH+k) : (const void*)w, valid);
  }
  // Activation planes: DIGITS*MT rows of four chunks; chunk c of row r lives at c^(((r>>1)&1)<<1).
  for(int c=tid;c<DIGITS*MT*4;c+=128) {
    int d=c/(MT*4), rr=(c>>2)%MT, chunk=c&3, row=first+rr, k=k0+chunk*16;
    int valid=(row<rows && k<WIDTH) ? 16 : 0;
    const unsigned* source=(const unsigned*)x+((size_t)d*rows+row)*(WIDTH/4)+k/4;
    cp16(sa+(d*MT+rr)*KS+((chunk^(((rr>>1)&1)<<1))<<4), valid ? (const void*)source : (const void*)x, valid);
  }
}

#if FAST_CONVERT
#if MAGNITUDE_BITS != 22
#error "The byte-digit conversion is proved for B22 only (B14 row scales can be negative)"
#endif
__device__ __forceinline__ unsigned digit_source(u16 h, unsigned scale) {
  // Same exact exponent-bit scaling as quant_half; B22 adds s<<23 with s=21-exponent in [6,45]. A zero half
  // becomes a normal float of magnitude below 2^-80. An Inf/NaN half (exponent field 255) wraps modulo 2^32
  // to exponent field s-1 with any sign: also below 2^-80. Both round to integer zero, as quant_half returns
  // zero for them (an exhaustive test covers every half and row exponent). For |g|<2^22, g+1.5*2^23 lies in
  // [2^23,2^24) where the FP32 ulp is one, so add.rn performs the same ties-to-even integer rounding as
  // cvt.rni and leaves bits = 0x4B400000 + q. Adding 0x8080-0x400000 gives q+0x8080 (plus 0x4B000000), whose
  // bytes are the balanced radix-256 digits: byte0 = d0^0x80, byte1 = d1^0x80, byte2 = d2.
  float g=__uint_as_float(__float_as_uint(widen(h))+scale), r;
  asm("add.rn.f32 %0, %1, 0f4B400000;" : "=f"(r) : "f"(g));
  return __float_as_uint(r)+(0x8080u-0x400000u);
}
__device__ __forceinline__ unsigned prmt(unsigned a, unsigned b, unsigned selector) {
  unsigned r;
  asm("prmt.b32 %0, %1, %2, %3;" : "=r"(r) : "r"(a), "r"(b), "r"(selector));
  return r;
}
__device__ __forceinline__ void convert4(unsigned* digits, unsigned h01, unsigned h23, unsigned scale) {
  unsigned v0=digit_source((u16)h01,scale), v1=digit_source((u16)(h01>>16),scale);
  unsigned v2=digit_source((u16)h23,scale), v3=digit_source((u16)(h23>>16),scale);
  unsigned t01=prmt(v0,v1,0x5140u), t23=prmt(v2,v3,0x5140u);
  digits[0]=prmt(t01,t23,0x5410u)^0x80808080u;
  digits[1]=prmt(t01,t23,0x7632u)^0x80808080u;
  digits[2]=prmt(prmt(v0,v1,0x0062u),prmt(v2,v3,0x0062u),0x5410u);
}
#else
__device__ __forceinline__ void convert4(unsigned* digits, unsigned h01, unsigned h23, int exponent) {
  #pragma unroll
  for(int d=0;d<DIGITS;++d) digits[d]=0;
  pack_digits(digits,quant_half((u16)h01,exponent),0);
  pack_digits(digits,quant_half((u16)(h01>>16),exponent),1);
  pack_digits(digits,quant_half((u16)h23,exponent),2);
  pack_digits(digits,quant_half((u16)(h23>>16),exponent),3);
}
#endif

// Split partials of matrix columns [partial_offset, partial_offset+outputs) inside rows of partial_columns.
__device__ __forceinline__ void stream_body(const qi_t* x,const u16* w,const u16* bias,const int* ex,const int* ew,
                                            float* out,int* error,i64* partials,int rows,int outputs,int column0,
                                            int partial_columns,int partial_offset) {
  __shared__ __align__(16) unsigned char weights_shared[STAGES][W_STAGE];
  __shared__ __align__(16) unsigned char inputs_shared[STAGES][A_STAGE];
  int lane=threadIdx.x&31, warp=threadIdx.x>>5, group=lane>>2, thread=lane&3;
  const int tiles=(WIDTH+KS-1)/KS, per=(tiles+SPLIT_K-1)/SPLIT_K;
  int begin=blockIdx.z*per, count=min(tiles,begin+per)-begin;
#if FAST_CONVERT
  unsigned scale[2];
#else
  int scale[2];
#endif
  #pragma unroll
  for(int j=0;j<JN;++j) {
    int n=column0+warp*8*JN+j*8+group, e=n<outputs ? ew[n] : 0;
#if FAST_CONVERT
    scale[j]=(unsigned)((MAGNITUDE_BITS-1-e)*0x800000);
#else
    scale[j]=e;
#endif
  }
  for(int first=blockIdx.y*MT;first<rows;first+=gridDim.y*MT) {
    int accum[M_GROUPS][JN][2*DIGITS-1][4]={};
    #pragma unroll
    for(int s=0;s<STAGES-1;++s) {
      if(s<count) stream_stage(weights_shared[s],inputs_shared[s],x,w,rows,outputs,first,column0,(begin+s)*KS);
      asm volatile("cp.async.commit_group;" ::: "memory");
    }
    for(int it=0;it<count;++it) {
      asm volatile("cp.async.wait_group %0;" :: "n"(STAGES-2) : "memory");
      __syncthreads();
      int next=it+STAGES-1;
      if(next<count) stream_stage(weights_shared[next%STAGES],inputs_shared[next%STAGES],x,w,rows,outputs,first,
                                  column0,(begin+next)*KS);
      asm volatile("cp.async.commit_group;" ::: "memory");
      const unsigned char* sw=weights_shared[it%STAGES];
      const unsigned char* sa=inputs_shared[it%STAGES];
      #pragma unroll
      for(int step=0;step<KS/32;++step) {
        unsigned b[JN][DIGITS][2];
        #pragma unroll
        for(int j=0;j<JN;++j) {
          int r=warp*8*JN+j*8+group;
          uint4 h=*(const uint4*)(sw+r*128+(((step*4+thread)^((r&1)<<2))<<4));
          unsigned lo[DIGITS], hi[DIGITS];
          convert4(lo,h.x,h.y,scale[j]);
          convert4(hi,h.z,h.w,scale[j]);
          #pragma unroll
          for(int d=0;d<DIGITS;++d) {b[j][d][0]=lo[d]; b[j][d][1]=hi[d];}
        }
        #pragma unroll
        for(int m=0;m<M_GROUPS;++m) {
          unsigned a[DIGITS][4];
          int row=m*16+group, offset=(((step*2+(thread>>1))^(((row>>1)&1)<<1))<<4)+(thread&1)*8;
          #pragma unroll
          for(int d=0;d<DIGITS;++d) {
            uint2 top=*(const uint2*)(sa+(d*MT+row)*KS+offset);
            uint2 bottom=*(const uint2*)(sa+(d*MT+row+8)*KS+offset);
            a[d][0]=top.x; a[d][2]=top.y; a[d][1]=bottom.x; a[d][3]=bottom.y;
          }
          #pragma unroll
          for(int i=0;i<DIGITS;++i) {
            #pragma unroll
            for(int jd=0;jd<DIGITS;++jd) {
              #pragma unroll
              for(int j=0;j<JN;++j) mma(accum[m][j][i+jd],a[i],b[j][jd]);
            }
          }
        }
      }
    }
    asm volatile("cp.async.wait_group 0;" ::: "memory");
    __syncthreads(); // every warp is done with the buffers before the next row tile refills them
    #pragma unroll
    for(int m=0;m<M_GROUPS;++m) {
      #pragma unroll
      for(int j=0;j<JN;++j) {
        #pragma unroll
        for(int d=0;d<4;++d) {
          int row=first+m*16+group+(d>>1)*8, n=column0+warp*8*JN+j*8+thread*2+(d&1);
          if(row<rows && n<outputs) {
            i64 sum=0;
            #pragma unroll
            for(int degree=0;degree<2*DIGITS-1;++degree) sum+=(i64)accum[m][j][degree][d]*(1ll<<(8*degree));
#if SPLIT_K > 1
            partials[((size_t)blockIdx.z*rows+row)*partial_columns+partial_offset+n]=sum;
#else
            float v=encode(sum,ex[row]+ew[n]-2*(MAGNITUDE_BITS-1),error);
            if(HAS_BIAS) v=add_rn(v,widen(bias[n]));
            out[(size_t)row*outputs+n]=v;
            if((__float_as_uint(v)&0x7f800000u)==0x7f800000u) atomicOr(error,1);
#endif
          }
        }
      }
    }
  }
}

#if STREAM_MIN_BLOCKS > 1
extern "C" __global__ void __launch_bounds__(128, STREAM_MIN_BLOCKS)
#else
extern "C" __global__ void __launch_bounds__(128)
#endif
integer_stream(const qi_t* x,const u16* w,const u16* bias,const int* ex,const int* ew,
               float* out,int* error,i64* partials,int rows,int outputs) {
  stream_body(x,w,bias,ex,ew,out,error,partials,rows,outputs,blockIdx.x*NT,outputs,0);
}

// Up to three matrices sharing one activation in one launch: blockIdx.x walks their column tiles in order.
// Split partials are laid out as one [split][rows][n0+n1+n2] matrix; integer_finish_group encodes them.
#define GROUP_SELECT(g,a,b,c) ((g)==0 ? (a) : (g)==1 ? (b) : (c))
extern "C" __global__ void __launch_bounds__(128)
integer_stream_group(const qi_t* x,const int* ex,int* error,i64* partials,
                     const u16* w0,const u16* w1,const u16* w2,const u16* b0,const u16* b1,const u16* b2,
                     const int* e0,const int* e1,const int* e2,float* o0,float* o1,float* o2,
                     unsigned* zeroed,int rows,int n0,int n1,int n2,int zero_count) {
  // A fused consumer accumulates per-row maxima into `zeroed` after this grid; clear it here (one CTA).
  if(zero_count && !blockIdx.x && !blockIdx.y && !blockIdx.z)
    for(int i=threadIdx.x;i<zero_count;i+=blockDim.x) zeroed[i]=0u;
  int t0=(n0+NT-1)/NT, t1=(n1+NT-1)/NT, tile=blockIdx.x;
  int g=tile<t0 ? 0 : tile<t0+t1 ? 1 : 2;
  int column0=(tile-(g>0 ? t0 : 0)-(g>1 ? t1 : 0))*NT;
  stream_body(x,GROUP_SELECT(g,w0,w1,w2),GROUP_SELECT(g,b0,b1,b2),ex,GROUP_SELECT(g,e0,e1,e2),
              GROUP_SELECT(g,o0,o1,o2),error,partials,rows,GROUP_SELECT(g,n0,n1,n2),column0,n0+n1+n2,
              g==0 ? 0 : g==1 ? n0 : n0+n1);
}

extern "C" __global__ void integer_finish_group(const i64* partials,const int* ex,int* error,
                                                const u16* b0,const u16* b1,const u16* b2,
                                                const int* e0,const int* e1,const int* e2,
                                                float* o0,float* o1,float* o2,int rows,int n0,int n1,int n2) {
  int c=blockIdx.x*256+threadIdx.x, total=n0+n1+n2;
  if(c>=total) return;
  int g=c<n0 ? 0 : c<n0+n1 ? 1 : 2, n=c-(g>0 ? n0 : 0)-(g>1 ? n1 : 0), outputs=GROUP_SELECT(g,n0,n1,n2);
  const u16* bias=GROUP_SELECT(g,b0,b1,b2);
  const int* ew=GROUP_SELECT(g,e0,e1,e2);
  float* out=GROUP_SELECT(g,o0,o1,o2);
  for(int row=blockIdx.y;row<rows;row+=gridDim.y) {
    i64 sum=0;
    #pragma unroll
    for(int s=0;s<SPLIT_K;++s) sum+=partials[((size_t)s*rows+row)*total+c];
    float v=encode(sum,ex[row]+ew[n]-2*(MAGNITUDE_BITS-1),error);
    if(HAS_BIAS) v=add_rn(v,widen(bias[n]));
    out[(size_t)row*outputs+n]=v;
    if((__float_as_uint(v)&0x7f800000u)==0x7f800000u) atomicOr(error,1);
  }
}
"""
)


# Strict RMSNorm / SiLU-gate kernels whose FP32 row is only ever quantized for a projection. Each CTA owns one
# row: it computes the row exactly as strict_rms_norm / strict_silu_mul (same loads, rounded ops and flags),
# keeps it in shared memory and then performs integer_input's maximum, exponent and packed-digit quantization on
# those values. The FP32 row is never stored; the planes and exponents equal quantize_input(op(...)).
_FUSED_SOURCE = (
    _QUANT_FLOAT
    + _PACK_DIGITS
    + r"""
template <int THREADS>
__device__ void quantize_row(const float* a, int n, unsigned* planes, int* exponents, int rows, unsigned& bad) {
  __shared__ unsigned maxima[THREADS];
  unsigned maximum=0;
  for(int k=threadIdx.x;k<n;k+=THREADS) {
    unsigned u=__float_as_uint(a[k])&0x7fffffffu;
    if(u>=0x7f800000u) {bad|=1u; u=0;}
    if((u&0x7f800000u)==0) u=0;
    maximum=u>maximum ? u : maximum;
  }
  maxima[threadIdx.x]=maximum;
  __syncthreads();
  for(int stride=THREADS/2;stride;stride>>=1) {
    if(threadIdx.x<stride) maxima[threadIdx.x]=maxima[threadIdx.x+stride]>maxima[threadIdx.x] ? maxima[threadIdx.x+stride] : maxima[threadIdx.x];
    __syncthreads();
  }
  int exponent=maxima[0] ? (int)(maxima[0]>>23)-127 : 0;
  if(threadIdx.x==0) exponents[blockIdx.x]=exponent;
  const int words=(n+3)/4;
  for(int word=threadIdx.x;word<words;word+=THREADS) {
    unsigned packed[DIGITS]={};
    #pragma unroll
    for(int i=0;i<4;++i) {
      int k=word*4+i;
      pack_digits(packed,k<n ? quant_float(__float_as_uint(a[k]),exponent) : 0,i);
    }
    #pragma unroll
    for(int d=0;d<DIGITS;++d) planes[((size_t)d*rows+blockIdx.x)*words+word]=packed[d];
  }
}

// strict_rms_norm's sum of squares is block_tree: the pruned aligned in-place tree (level stride s adds a[i+s]
// into a[i] for i a multiple of 2s when i+s < n). Here thread t owns the aligned chunk [tC, tC+C) (C a power of
// two): levels below C run in registers, the next five through warp shuffles and the rest across warp leaders,
// each with the same pruning test, so every rounded node and flag is the same as block_tree's.
template <int C>
__device__ __forceinline__ void rms_quant_row(const float* row, const u16* w, int n, float inv_n, float eps,
                                              float* a, unsigned* planes, int* exponents, int rows, unsigned& bad) {
  __shared__ float nodes[RMS_THREADS / 32];
  __shared__ unsigned maxima[RMS_THREADS / 32];
  const int t = threadIdx.x, lane = t & 31, warp = t >> 5, base = t * C;
  float x[C], v[C];
#pragma unroll
  for (int j = 0; j < C; ++j) {
    x[j] = base + j < n ? load(row + base + j, bad) : 0.0f;
    v[j] = base + j < n ? mul_(x[j], x[j], bad) : 0.0f;
  }
#pragma unroll
  for (int s = 1; s < C; s <<= 1) {
#pragma unroll
    for (int j = 0; j < C; j += 2 * s)
      if (base + j + s < n) v[j] = add_(v[j], v[j + s], bad);
  }
  float node = v[0];
#pragma unroll
  for (int m = 1; m < 32; m <<= 1) {
    float other = __shfl_down_sync(0xffffffffu, node, m);
    if ((lane & (2 * m - 1)) == 0 && base + m * C < n) node = add_(node, other, bad);
  }
  if (!lane) nodes[warp] = node;
  __syncthreads();
  // Warp leaders hold the nodes at multiples of 32C; every thread replays the same short pruned tree over them.
  float carry[RMS_THREADS / 32];
#pragma unroll
  for (int k = 0; k < RMS_THREADS / 32; ++k) carry[k] = nodes[k];
#pragma unroll
  for (int m = 1; m < RMS_THREADS / 32; m <<= 1) {
#pragma unroll
    for (int k = 0; k + m < RMS_THREADS / 32; k += 2 * m)
      if ((k + m) * 32 * C < n) carry[k] = add_(carry[k], carry[k + m], bad);
  }
  const float sum = carry[0];
  float inverse = rsqrt_(add_(mul_(sum, inv_n, bad), eps, bad), bad);
  unsigned maximum = 0;
#pragma unroll
  for (int j = 0; j < C; ++j) {
    if (base + j < n) {
      float y = mul_(mul_(x[j], inverse, bad), widen(w[base + j]), bad);
      a[base + j] = y;
      unsigned u = __float_as_uint(y) & 0x7fffffffu;
      if (u >= 0x7f800000u) {bad |= 1u; u = 0;}
      if ((u & 0x7f800000u) == 0) u = 0;
      maximum = u > maximum ? u : maximum;
    }
  }
#pragma unroll
  for (int m = 16; m; m >>= 1) {
    unsigned other = __shfl_xor_sync(0xffffffffu, maximum, m);
    maximum = other > maximum ? other : maximum;
  }
  if (!lane) maxima[warp] = maximum;
  __syncthreads();
#pragma unroll
  for (int k = 0; k < RMS_THREADS / 32; ++k) maximum = maxima[k] > maximum ? maxima[k] : maximum;
  const int exponent = maximum ? (int)(maximum >> 23) - 127 : 0;
  if (!t) exponents[blockIdx.x] = exponent;
  const int words = (n + 3) / 4;
  for (int word = t; word < words; word += RMS_THREADS) {
    unsigned packed[DIGITS] = {};
#pragma unroll
    for (int i = 0; i < 4; ++i) {
      int k = word * 4 + i;
      pack_digits(packed, k < n ? quant_float(__float_as_uint(a[k]), exponent) : 0, i);
    }
#pragma unroll
    for (int d = 0; d < DIGITS; ++d) planes[((size_t)d * rows + blockIdx.x) * words + word] = packed[d];
  }
}

extern "C" __global__ void __launch_bounds__(RMS_THREADS) strict_rms_quant(const float* x, const u16* w, unsigned* planes,
    int* exponents, int* error, int rows, int n, float inv_n, float eps) {
  extern __shared__ float a[];
  unsigned bad = 0;
  const float* row = x + (size_t)blockIdx.x * n;
  // Smallest power-of-two chunk covering the row with RMS_THREADS threads (n <= 32 * RMS_THREADS).
  if (n <= RMS_THREADS) rms_quant_row<1>(row, w, n, inv_n, eps, a, planes, exponents, rows, bad);
  else if (n <= 2 * RMS_THREADS) rms_quant_row<2>(row, w, n, inv_n, eps, a, planes, exponents, rows, bad);
  else if (n <= 4 * RMS_THREADS) rms_quant_row<4>(row, w, n, inv_n, eps, a, planes, exponents, rows, bad);
  else if (n <= 8 * RMS_THREADS) rms_quant_row<8>(row, w, n, inv_n, eps, a, planes, exponents, rows, bad);
  else if (n <= 16 * RMS_THREADS) rms_quant_row<16>(row, w, n, inv_n, eps, a, planes, exponents, rows, bad);
  else rms_quant_row<32>(row, w, n, inv_n, eps, a, planes, exponents, rows, bad);
  report(error, bad);
}

extern "C" __global__ void __launch_bounds__(SILU_THREADS) strict_silu_quant(const float* gate, const float* up, unsigned* planes,
    int* exponents, int* error, int rows, int n) {
  extern __shared__ float a[];
  unsigned bad = 0;
  for (int i = threadIdx.x; i < n; i += SILU_THREADS) {
    size_t j = (size_t)blockIdx.x * n + i;
    a[i] = mul_(silu_(load(gate + j, bad), bad), load(up + j, bad), bad);
  }
  __syncthreads();
  quantize_row<SILU_THREADS>(a, n, planes, exponents, rows, bad);
  report(error, bad);
}
"""
)


# Decode finishes fused with the strict ops the decoder applies to the projection outputs. Each sums the same
# split-K partials and performs the same encoding, bias add and nonfinite flag as integer_finish(_group); the
# encoded value is then consumed exactly as the stored output would be (strict load: flush + flag), so outputs,
# rounding and failure flags equal the unfused kernel sequence. Only intermediate stores are skipped.
_DECODE_FINISH_SOURCE = r"""
typedef unsigned long long u64;
typedef long long i64;
"""
_DECODE_FINISH_SOURCE += (
    _ENCODE
    + _QUANT_FLOAT
    + _PACK_DIGITS
    + r"""
__device__ __forceinline__ float add_rn(float a, float b) {
  float r;
  asm volatile("add.rn.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
  return flush(r);
}
// integer_finish(_group) for one element: exact partial sum, encoding, bias, nonfinite flag.
__device__ __forceinline__ float projected(const i64* partials, int rows, int columns, int row, int c, int scale,
                                           const u16* bias, int n, int* error) {
  i64 sum = 0;
#pragma unroll
  for (int s = 0; s < SPLIT_K; ++s) sum += partials[((size_t)s * rows + row) * columns + c];
  float v = encode(sum, scale, error);
  if (HAS_BIAS) v = add_rn(v, widen(bias[n]));
  if ((__float_as_uint(v) & 0x7f800000u) == 0x7f800000u) atomicOr(error, 1);
  return v;
}
// The strict load of a stored value.
__device__ __forceinline__ float loaded(float v, unsigned& bad) {
  v = flush(v);
  note(v, bad);
  return v;
}

// out = strict_add(residual, projection): the residual stream update after o_proj / down_proj.
extern "C" __global__ void finish_residual(const i64* partials, const u16* bias, const int* ex, const int* ew,
                                           const float* residual, float* out, int* error, int rows, int outputs) {
  int n = blockIdx.x * 256 + threadIdx.x;
  if (n >= outputs) return;
  unsigned bad = 0;
  for (int row = blockIdx.y; row < rows; row += gridDim.y) {
    float v = projected(partials, rows, outputs, row, n, ex[row] + ew[n] - 2 * (MAGNITUDE_BITS - 1), bias, n, error);
    size_t i = (size_t)row * outputs + n;
    out[i] = add_(load(residual + i, bad), loaded(v, bad), bad);
  }
  report(error, bad);
}

// gated = strict_silu_mul(gate, up) from a [gate | up] group of n columns each, plus the per-row maximum that
// integer_input / quantize_row derive from the gated row (order-independent; nonfinite flagged and ignored,
// subnormals ignored). `maxima` was cleared by the group projection that produced the partials.
extern "C" __global__ void finish_silu(const i64* partials, const u16* b0, const u16* b1, const int* ex,
                                       const int* e0, const int* e1, float* gated, unsigned* maxima, int* error,
                                       int rows, int n) {
  const int k = blockIdx.x * 256 + threadIdx.x;
  const bool live = k < n;
  unsigned bad = 0;
  for (int row = blockIdx.y; row < rows; row += gridDim.y) {
    unsigned u = 0;
    if (live) {
      float gate = projected(partials, rows, 2 * n, row, k, ex[row] + e0[k] - 2 * (MAGNITUDE_BITS - 1), b0, k, error);
      float up = projected(partials, rows, 2 * n, row, n + k, ex[row] + e1[k] - 2 * (MAGNITUDE_BITS - 1), b1, k, error);
      float g = mul_(silu_(loaded(gate, bad), bad), loaded(up, bad), bad);
      gated[(size_t)row * n + k] = g;
      u = __float_as_uint(g) & 0x7fffffffu;
      if (u >= 0x7f800000u) {bad |= 1u; u = 0;}
      if ((u & 0x7f800000u) == 0) u = 0;
    }
#pragma unroll
    for (int m = 16; m; m >>= 1) {
      unsigned other = __shfl_xor_sync(0xffffffffu, u, m);
      u = other > u ? other : u;
    }
    if (!(threadIdx.x & 31) && u) atomicMax(maxima + row, u);  // one atomic per warp and row
  }
  report(error, bad);
}

// quantize_input's packed planes and exponents of rows whose maxima are already known.
extern "C" __global__ void pack_rows(const float* a, const unsigned* maxima, unsigned* planes, int* exponents,
                                     int rows, int n) {
  const int row = blockIdx.y, words = (n + 3) >> 2, word = blockIdx.x * 256 + threadIdx.x;
  const unsigned m = maxima[row];
  const int exponent = m ? (int)(m >> 23) - 127 : 0;
  if (!blockIdx.x && !threadIdx.x) exponents[row] = exponent;
  if (word >= words) return;
  unsigned packed[DIGITS] = {};
#pragma unroll
  for (int i = 0; i < 4; ++i) {
    int k = word * 4 + i;
    pack_digits(packed, k < n ? quant_float(__float_as_uint(a[(size_t)row * n + k]), exponent) : 0, i);
  }
#pragma unroll
  for (int d = 0; d < DIGITS; ++d) planes[((size_t)d * rows + row) * words + word] = packed[d];
}

// The q/k/v group finish fused with strict_rope of q and k and decode_store of k and v. Grid (heads + 2*kv,
// rows), block dim: CTAs [0, heads) are q heads, then kv k heads, then kv v heads. A q/k thread d < dim/2 owns
// the rotation pair (d, d + dim/2) and performs strict_rope's loads, products and add for both channels.
extern "C" __global__ void finish_qkv_rope(const i64* partials, const u16* bq, const u16* bk, const u16* bv,
                                           const int* ex, const int* eq, const int* ek, const int* ev,
                                           const float* cosine, const float* sine, const int* ranges, float* q,
                                           float* keys, float* values, int* error, int rows, int heads,
                                           int kv_heads, int dim, int total) {
  const int head = blockIdx.x, row = blockIdx.y, d = threadIdx.x, half = dim >> 1;
  const int columns = (heads + 2 * kv_heads) * dim, scale = ex[row] - 2 * (MAGNITUDE_BITS - 1);
  const int position = ranges[3 * row] + ranges[3 * row + 1] - 1;
  unsigned bad = 0;
  if (head >= heads + kv_heads) {
    const int h = head - heads - kv_heads, n = h * dim + d, c = (heads + kv_heads) * dim + n;
    if (d < dim)
      values[((size_t)h * total + position) * dim + d] = projected(partials, rows, columns, row, c, scale + ev[n], bv, n, error);
    return;
  }
  if (d >= half) return;
  const bool is_q = head < heads;
  const int h = is_q ? head : head - heads, n = h * dim + d, c = (is_q ? 0 : heads * dim) + n;
  const int* ew = is_q ? eq : ek;
  const u16* bias = is_q ? bq : bk;
  float lo = loaded(projected(partials, rows, columns, row, c, scale + ew[n], bias, n, error), bad);
  float hi = loaded(projected(partials, rows, columns, row, c + half, scale + ew[n + half], bias, n + half, error), bad);
  const float* cr = cosine + (size_t)row * dim;
  const float* sr = sine + (size_t)row * dim;
  float first = add_(mul_(lo, load(cr + d, bad), bad), mul_(-hi, load(sr + d, bad), bad), bad);
  float second = add_(mul_(hi, load(cr + d + half, bad), bad), mul_(lo, load(sr + d + half, bad), bad), bad);
  float* target = is_q ? q + ((size_t)h * rows + row) * dim : keys + ((size_t)h * total + position) * dim;
  target[d] = first;
  target[d + half] = second;
  report(error, bad);
}
"""
)


class IntegerCudaKernels(sc.StrictCudaKernels):
    def __init__(
        self, device, *, magnitude_bits=14, max_partial_bytes=16 * 1024**2, weight_load="auto", mma_schedule="auto"
    ):
        reference._precision(magnitude_bits)
        weight_read_plan(magnitude_bits, "sm_120", weight_load)
        _mma_schedule(mma_schedule)
        if type(max_partial_bytes) is not int or max_partial_bytes < 1:
            raise ReferenceArithmeticError("Integer workspace budget must be a positive integer")
        super().__init__(device)
        if int(self.arch[3:]) < 80:
            raise ReferenceArithmeticError("Integer MMA prototype currently requires sm80 or newer")
        self.magnitude_bits = magnitude_bits
        self.weight_load = weight_load
        self.mma_schedule = mma_schedule
        self.max_partial_bytes = max_partial_bytes
        self.multiprocessors = int(torch.cuda.get_device_properties(self.device).multi_processor_count)
        self._weight_metadata, self._request_active = {}, False

    def weight_metadata_buffers(self):
        return (entry[2] for entry in self._weight_metadata.values())

    @staticmethod
    def _weight_binding(weight):
        return (weight.data_ptr(), tuple(weight.shape), tuple(weight.stride()), weight.dtype, weight.device)

    def _refresh_weight_exponents(self, weight, exponents, flag):
        functions = self._integer_functions(weight.shape[1])
        self._launch(
            functions["integer_weights"],
            grid=weight.shape[0],
            block=(256, 1),
            pointers=(weight, exponents, flag),
            integers=(weight.shape[0],),
        )

    def _refresh_exponents_batched(self, entries, flag):
        """integer_weights of every (weight, exponents) pair in one launch; the table is call-local."""
        if "weights-batched" not in self._functions:
            self._functions["weights-batched"] = self._compile(
                "weights-batched", _WEIGHTS_BATCHED_SOURCE, ["integer_weights_batched"]
            )["integer_weights_batched"]
        offsets, meta, blocks = [], [], 0
        for weight, exponents in entries:
            offsets.append(blocks)
            blocks += -(-weight.shape[0] // 8)
            meta += [weight.data_ptr(), exponents.data_ptr(), weight.shape[0], weight.shape[1]]
        table = torch.tensor(offsets + [blocks] + meta, dtype=torch.int64, device=self.device)
        self._launch(
            self._functions["weights-batched"],
            grid=blocks,
            block=(256, 1),
            pointers=(table, flag),
            integers=(len(entries),),
        )

    @torch.inference_mode()
    def _begin_request(self, weights):
        if self._request_active:
            raise ReferenceArithmeticError("Integer metadata request is already active")
        retained = {}
        for weight in weights:
            if (
                weight.device != self.device
                or weight.dtype != torch.float16
                or weight.ndim != 2
                or not weight.is_contiguous()
                or not 1 <= weight.shape[1] <= reference.MAX_WIDTH
            ):
                raise ReferenceArithmeticError("Integer request needs supported live FP16 linear weights")
            key, binding = id(weight), self._weight_binding(weight)
            previous = self._weight_metadata.get(key)
            if previous is None or previous[0]() is not weight or previous[1] != binding:
                previous = (
                    weakref.ref(weight),
                    binding,
                    torch.empty(weight.shape[0], dtype=torch.int32, device=self.device),
                )
            retained[key] = previous
        self._weight_metadata = retained
        flag = self.new_error_flag()
        entries = [(target(), exponents) for target, _, exponents in retained.values()]
        batched = [(w, e) for w, e in entries if w.shape[1] % 8 == 0 and w.data_ptr() % 16 == 0]
        if batched:
            self._refresh_exponents_batched(batched, flag)
        for weight, exponents in entries:
            if not (weight.shape[1] % 8 == 0 and weight.data_ptr() % 16 == 0):
                self._refresh_weight_exponents(weight, exponents, flag)
        self.raise_if_error(flag)  # a bad scale may never be hidden by resetting a later decode flag
        self._request_active = True

    @torch.inference_mode()
    def _end_request(self):
        self._request_active = False
        buffers = list(self.weight_metadata_buffers())
        if buffers:
            torch._foreach_zero_(buffers)

    def _weight_exponents(self, weight, flag):
        if self._request_active:
            entry = self._weight_metadata.get(id(weight))
            if entry is None or entry[0]() is not weight or entry[1] != self._weight_binding(weight):
                raise ReferenceArithmeticError("Integer weight binding changed inside a request")
            return entry[2]
        result = torch.empty(weight.shape[0], dtype=torch.int32, device=self.device)
        self._refresh_weight_exponents(weight, result, flag)
        return result

    def identity(self):
        identity = {
            **super().identity(),
            **static_identity(
                self.magnitude_bits,
                self.max_partial_bytes,
                weight_load=self.weight_load,
                mma_schedule=self.mma_schedule,
            ),
            "integerKernel": INTEGER_CUDA_VERSION,
            "integerReference": reference.identity(self.magnitude_bits),
            "integerSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "maxPartialBytes": self.max_partial_bytes,
            "multiprocessors": self.multiprocessors,
            "weightLoadEffective": weight_read_plan(self.magnitude_bits, self.arch, self.weight_load),
            "mmaScheduleEffective": _mma_schedule(self.mma_schedule),
            "hardwareQualified": False,
        }
        identity["fingerprint"] = canonical_json_hash({k: v for k, v in identity.items() if k != "fingerprint"})
        return identity

    def _integer_functions(
        self, width, has_bias=False, row_tile=16, warps=4, split_k=1, *, packed_input=False, columns=STREAM_COLUMNS
    ):
        if columns not in (32, 64):
            raise ReferenceArithmeticError("Streamed projections use 32 or 64 columns per CTA")
        name = f"integer-{self.magnitude_bits}-{width}-bias{int(has_bias)}-m{row_tile}-w{warps}-s{split_k}-p{int(packed_input)}"
        if columns != STREAM_COLUMNS:
            name += f"-n{columns}"
        mode = weight_read_plan(self.magnitude_bits, self.arch, self.weight_load)
        paired, prefetch = mode == "paired", mode == "prefetch2"
        if paired:
            name += "-load32"
        if prefetch:
            name += "-prefetch2"
        if name not in self._functions:
            defines = dict(
                WIDTH=width,
                MAGNITUDE_BITS=self.magnitude_bits,
                DIGITS=2 if self.magnitude_bits == 14 else 3,
                HAS_BIAS=int(has_bias),
                M_GROUPS=row_tile // 16,
                WARPS=warps,
                SPLIT_K=split_k,
                PACKED_INPUT=int(packed_input),
                WEIGHT_READ32=int(paired),
                WEIGHT_PREFETCH=int(prefetch),
                FAST_CONVERT=int(self.magnitude_bits == 22),
                JN=columns // 32,
                **(
                    {"STAGES": PREFILL_STAGES, "STREAM_MIN_BLOCKS": PREFILL_MIN_BLOCKS}
                    if columns == STREAM_COLUMNS
                    else {}
                ),
            )
            header = "".join(f"#define {k} {v}\n" for k, v in defines.items())
            self._functions[name] = self._compile(
                name,
                header + _SOURCE,
                [
                    "integer_input",
                    "integer_weights",
                    "integer_linear",
                    "integer_simt",
                    "integer_finish",
                    "integer_stream",
                    "integer_stream_group",
                    "integer_finish_group",
                ],
                integer_mma=True,
            )
        return self._functions[name]

    def _stream_eligible(self, width, quantized, weight):
        # cp.async moves 16-byte chunks: whole packed-input chunks per row and 16-byte aligned weight rows.
        return (
            _mma_schedule(self.mma_schedule) == "stream"
            and width % 16 == 0
            and quantized.ndim == 3
            and quantized.data_ptr() % 16 == 0
            and weight.data_ptr() % 16 == 0
        )

    @torch.inference_mode()
    def quantize_input(self, value, *, error_flag=None, _functions=None, _packed=False):
        """Raw q by default; MMA packs signed radix bytes once into [digit, row, ceil(K/4)] planes."""
        if type(_packed) is not bool:
            raise ReferenceArithmeticError("Unsupported integer activation layout")
        if (
            not isinstance(value, torch.Tensor)
            or value.dtype != torch.float32
            or value.device != self.device
            or value.ndim != 2
            or not value.numel()
            or not 1 <= value.shape[1] <= reference.MAX_WIDTH
        ):
            raise ReferenceArithmeticError("Integer quantization needs a nonempty FP32 matrix on its CUDA device")
        value = value.contiguous()
        functions = self._integer_functions(value.shape[1], packed_input=_packed) if _functions is None else _functions
        quantized = (
            torch.empty(
                (2 if self.magnitude_bits == 14 else 3, value.shape[0], (value.shape[1] + 3) // 4),
                dtype=torch.int32,
                device=self.device,
            )
            if _packed
            else torch.empty_like(value, dtype=torch.int16 if self.magnitude_bits == 14 else torch.int32)
        )
        exponents = torch.empty(value.shape[0], dtype=torch.int32, device=self.device)
        flag = self.new_error_flag() if error_flag is None else error_flag
        self._launch(
            functions["integer_input"],
            grid=value.shape[0],
            block=(256, 1),
            pointers=(value, quantized, exponents, flag),
            integers=(value.shape[0],),
        )
        self._finish(flag, error_flag)
        return quantized, exponents

    @torch.inference_mode()
    def linear(
        self, value, weight, bias=None, *, error_flag=None, row_tile=None, warps=4, split_k=1, implementation="auto"
    ):
        return self._linear(
            value,
            weight,
            bias,
            error_flag=error_flag,
            row_tile=row_tile,
            warps=warps,
            split_k=split_k,
            implementation=implementation,
        )

    @torch.inference_mode()
    def linear_decode(
        self, value, weight, bias=None, *, error_flag=None, target_ctas_per_sm=8, prepared=None, residual=None
    ):
        if prepared is not None:
            value = self._prepared_shape(prepared, weight)
        if not isinstance(value, torch.Tensor) or value.dtype != torch.float32:
            raise ReferenceArithmeticError("Integer linear activation must be FP32")
        rows, width, outputs = sc.validate_linear(value, weight, bias, device=self.device)
        plan = self._decode_plan(width, rows, outputs, target_ctas_per_sm)
        return self._linear(
            value,
            weight,
            bias,
            error_flag=error_flag,
            row_tile=plan.row_tile,
            split_k=plan.split_k,
            implementation=plan.implementation,
            stream_columns=DECODE_STREAM_COLUMNS,
            prepared=prepared,
            residual=residual,
        )

    def _prepared_shape(self, prepared, weight):
        """A storage-free [rows, width] FP32 view standing for the activation behind fused packed planes."""
        if not isinstance(weight, torch.Tensor) or weight.ndim != 2:
            raise ReferenceArithmeticError("Unsupported strict linear dtype, layout or shape")
        planes, exponents = prepared
        digits, width = (2 if self.magnitude_bits == 14 else 3), weight.shape[1]
        if (
            not isinstance(planes, torch.Tensor)
            or not isinstance(exponents, torch.Tensor)
            or planes.dtype != torch.int32
            or exponents.dtype != torch.int32
            or planes.device != self.device
            or exponents.device != self.device
            or planes.ndim != 3
            or planes.shape[0] != digits
            or planes.shape[1] < 2
            or planes.shape[2] != (width + 3) // 4
            or not planes.is_contiguous()
            or exponents.shape != (planes.shape[1],)
        ):
            raise ReferenceArithmeticError("Prepared integer planes do not match the projection")
        return torch.empty(1, dtype=torch.float32, device=self.device).expand(planes.shape[1], width)

    def _fused_functions(self):
        name = f"fused-quant-{self.magnitude_bits}"
        if name not in self._functions:
            header = "".join(f"#define {k} 0x{v:08x}u\n" for k, v in sc.reference_constants().items())
            header += f"#define MAGNITUDE_BITS {self.magnitude_bits}\n#define DIGITS {2 if self.magnitude_bits == 14 else 3}\n"
            header += f"#define RMS_THREADS {RMS_THREADS}\n#define SILU_THREADS {SILU_THREADS}\n"
            self._functions[name] = self._compile(
                name,
                header + sc._OPS_SOURCE + _FUSED_SOURCE,
                ["strict_rms_quant", "strict_silu_quant"],
                ptx_exact=sc.OPS_PTX_EXACT,
                sass_exact=sc.OPS_SASS_EXACT,
            )
        return self._functions[name]

    def _planes(self, rows, width):
        return (
            torch.empty(
                (2 if self.magnitude_bits == 14 else 3, rows, (width + 3) // 4), dtype=torch.int32, device=self.device
            ),
            torch.empty(rows, dtype=torch.int32, device=self.device),
        )

    @torch.inference_mode()
    def rms_norm_quantized(self, value, weight, epsilon, *, error_flag=None):
        """Packed planes of quantize_input(rms_norm(value)) for a [rows>=2, width] activation, in one kernel."""
        (value,) = self._float32(value)
        width = value.shape[-1] if value.ndim == 2 else 0
        if (
            value.ndim != 2
            or value.shape[0] < 2
            or not isinstance(weight, torch.Tensor)
            or weight.dtype != torch.float16
            or weight.shape != (width,)
            or weight.device != self.device
            or not weight.is_contiguous()
            or not 1 <= width <= sc.MAX_NORM_WIDTH
            or not (isinstance(epsilon, float) and math.isfinite(epsilon) and epsilon > 0)
        ):
            raise ReferenceArithmeticError("Unsupported fused RMSNorm quantization input")
        rows = value.shape[0]
        planes, exponents = self._planes(rows, width)
        flag = self.new_error_flag() if error_flag is None else error_flag
        self._launch(
            self._fused_functions()["strict_rms_quant"],
            grid=rows,
            block=(RMS_THREADS, 1),
            pointers=(value, weight, planes, exponents, flag),
            integers=(rows, width),
            floats=(1.0 / width, epsilon),
            shared=4 * width,
        )
        self._finish(flag, error_flag)
        return planes, exponents

    @torch.inference_mode()
    def silu_mul_quantized(self, gate, up, *, error_flag=None):
        """Packed planes of quantize_input(silu_mul(gate, up)) for [rows>=2, width<=12288], in one kernel."""
        gate, up = self._float32(gate, up)
        if gate.shape != up.shape or gate.ndim != 2 or gate.shape[0] < 2 or not 1 <= gate.shape[1] <= 12288:
            raise ReferenceArithmeticError("Unsupported fused SiLU quantization input")
        rows, width = gate.shape
        planes, exponents = self._planes(rows, width)
        flag = self.new_error_flag() if error_flag is None else error_flag
        self._launch(
            self._fused_functions()["strict_silu_quant"],
            grid=rows,
            block=(SILU_THREADS, 1),
            pointers=(gate, up, planes, exponents, flag),
            integers=(rows, width),
            shared=4 * width,
        )
        self._finish(flag, error_flag)
        return planes, exponents

    def _finish_functions(self, split_k, has_bias):
        name = f"decode-finish-{self.magnitude_bits}-s{split_k}-b{int(has_bias)}"
        if name not in self._functions:
            header = "".join(f"#define {k} 0x{v:08x}u\n" for k, v in sc.reference_constants().items())
            defines = dict(
                MAGNITUDE_BITS=self.magnitude_bits,
                DIGITS=2 if self.magnitude_bits == 14 else 3,
                SPLIT_K=split_k,
                HAS_BIAS=int(has_bias),
            )
            header += "".join(f"#define {k} {v}\n" for k, v in defines.items())
            self._functions[name] = self._compile(
                name,
                header + sc._OPS_SOURCE + _DECODE_FINISH_SOURCE,
                ["finish_residual", "finish_silu", "pack_rows", "finish_qkv_rope"],
                ptx_exact=sc.OPS_PTX_EXACT,
                sass_exact=sc.OPS_SASS_EXACT,
            )
        return self._functions[name]

    def _fused_group(self, value, weights, biases, prepared, flag, target, maxima=None):
        """Raw split partials of an eligible grouped decode projection, or None (the caller keeps unfused ops)."""
        if target is None or prepared is None:
            return None
        if biases is None:
            biases = (None,) * len(weights)
        rows, width = prepared[1].shape[0], weights[0].shape[1]
        value = self._prepared_shape(prepared, weights[0])
        for weight, bias in zip(weights, biases):
            sc.validate_linear(value, weight, bias, device=self.device)
        if not self._group_eligible(rows, width, weights, biases, prepared[0], target):
            return None
        if self._decode_plan(width, rows, sum(w.shape[0] for w in weights), target).split_k == 1:
            return None
        return self._linear_group(value, rows, width, weights, biases, prepared, flag, target, maxima=maxima, raw=True)

    @torch.inference_mode()
    def gate_up_silu_quantized(
        self, prepared, gate, up, biases=None, *, error_flag=None, decode_target_ctas_per_sm=None
    ):
        """quantize_input(silu_mul(gate projection, up projection)) as packed planes, or None if not eligible.

        One grouped streamed launch, a finish that applies strict_silu_mul to the encoded pair and records each
        row's maximum, and a packing kernel. Outputs and flags equal the unfused sequence.
        """
        flag = self.new_error_flag() if error_flag is None else error_flag
        if gate.shape != up.shape:
            return None
        rows, n = prepared[1].shape[0], gate.shape[0]
        maxima = torch.empty(rows, dtype=torch.int32, device=self.device)
        raw = self._fused_group(None, (gate, up), biases, prepared, flag, decode_target_ctas_per_sm, maxima)
        if raw is None:
            return None
        partials, ex, (e0, e1), plan = raw
        has_bias = biases is not None and biases[0] is not None
        functions = self._finish_functions(plan.split_k, has_bias)
        gated = torch.empty((rows, n), dtype=torch.float32, device=self.device)
        b0, b1 = biases if has_bias else (gate, up)
        self._launch(
            functions["finish_silu"],
            grid=(-(-n // 256), min(65535, rows)),
            block=(256, 1),
            pointers=(partials, b0, b1, ex, e0, e1, gated, maxima, flag),
            integers=(rows, n),
        )
        planes, exponents = self._planes(rows, n)
        self._launch(
            functions["pack_rows"],
            grid=(-(-((n + 3) // 4) // 256), rows),
            block=(256, 1),
            pointers=(gated, maxima, planes, exponents),
            integers=(rows, n),
        )
        self._finish(flag, error_flag)
        return planes, exponents

    @torch.inference_mode()
    def qkv_rope_store(
        self,
        prepared,
        weights,
        biases,
        cosine,
        sine,
        heads,
        kv_heads,
        ranges,
        keys,
        values,
        *,
        error_flag=None,
        decode_target_ctas_per_sm=None,
    ):
        """strict_rope(q) as [heads, rows, dim]; stores strict_rope(k) and v at each row's last cache position.

        Equal to the q/k/v projections followed by strict_rope and decode_store. Returns None if not eligible.
        """
        q_weight, k_weight, v_weight = weights
        dim = q_weight.shape[0] // heads if heads else 0
        rows = prepared[1].shape[0]
        if (
            dim < 2
            or dim % 2
            or dim > 1024
            or q_weight.shape[0] != heads * dim
            or k_weight.shape[0] != kv_heads * dim
            or v_weight.shape[0] != kv_heads * dim
            or any(
                t.dtype != torch.float32 or not t.is_contiguous() or t.device != self.device
                for t in (cosine, sine, keys, values)
            )
            or cosine.shape != (rows, dim)
            or sine.shape != (rows, dim)
            or keys.shape != values.shape
            or keys.ndim != 3
            or keys.shape[0] != kv_heads
            or keys.shape[2] != dim
            or ranges.dtype != torch.int32
            or not ranges.is_contiguous()
            or ranges.numel() < 3 * rows
        ):
            return None
        flag = self.new_error_flag() if error_flag is None else error_flag
        raw = self._fused_group(None, weights, biases, prepared, flag, decode_target_ctas_per_sm)
        if raw is None:
            return None
        partials, ex, (eq, ek, ev), plan = raw
        has_bias = biases is not None and biases[0] is not None
        bq, bk, bv = biases if has_bias else weights
        q = torch.empty((heads, rows, dim), dtype=torch.float32, device=self.device)
        self._launch(
            self._finish_functions(plan.split_k, has_bias)["finish_qkv_rope"],
            grid=(heads + 2 * kv_heads, rows),
            block=(dim, 1),
            pointers=(partials, bq, bk, bv, ex, eq, ek, ev, cosine, sine, ranges, q, keys, values, flag),
            integers=(rows, heads, kv_heads, dim, keys.shape[1]),
        )
        self._finish(flag, error_flag)
        return q

    def _decode_plan(self, width, rows, outputs, target):
        try:
            return planning.decode_linear_plan(
                width,
                rows,
                outputs,
                self.multiprocessors,
                max_partial_bytes=self.max_partial_bytes,
                target_ctas_per_sm=target,
            )
        except ValueError as error:
            raise ReferenceArithmeticError(str(error)) from error

    @torch.inference_mode()
    def linear_many(
        self, value, weights, biases=None, *, error_flag=None, decode_target_ctas_per_sm=None, prepared=None
    ):
        """Project one activation through independent live matrices with one call-local quantization.

        No activation/content cache, concatenated weights or cross-call prepared input is retained. Validate
        every component before allocating the shared quantization; the caller's error flag stays monotonic.
        """
        if not isinstance(weights, (list, tuple)) or not weights:
            raise ReferenceArithmeticError("Integer projection group needs a nonempty list/tuple of weights")
        if biases is None:
            biases = (None,) * len(weights)
        if not isinstance(biases, (list, tuple)) or len(biases) != len(weights):
            raise ReferenceArithmeticError("Integer projection group needs matching weights and biases")
        if prepared is not None:
            value = self._prepared_shape(prepared, weights[0])
        if not isinstance(value, torch.Tensor) or value.dtype != torch.float32:
            raise ReferenceArithmeticError("Integer linear activation must be FP32")
        plans = []
        for weight, bias in zip(weights, biases):
            rows, width, outputs = sc.validate_linear(value, weight, bias, device=self.device)
            plan = (
                None
                if decode_target_ctas_per_sm is None
                else self._decode_plan(width, rows, outputs, decode_target_ctas_per_sm)
            )
            plans.append(plan)
        flag = self.new_error_flag() if error_flag is None else error_flag
        if prepared is None:
            prepared = self.quantize_input(value.reshape(rows, width), error_flag=flag, _packed=rows > 1)
        if self._group_eligible(rows, width, weights, biases, prepared[0], decode_target_ctas_per_sm):
            outputs = self._linear_group(value, rows, width, weights, biases, prepared, flag, decode_target_ctas_per_sm)
            self._finish(flag, error_flag)
            return outputs
        outputs = tuple(
            self._linear(
                value,
                weight,
                bias,
                error_flag=flag,
                prepared=prepared,
                **(
                    {}
                    if plan is None
                    else {
                        "row_tile": plan.row_tile,
                        "split_k": plan.split_k,
                        "implementation": plan.implementation,
                        "stream_columns": DECODE_STREAM_COLUMNS,
                    }
                ),
            )
            for weight, bias, plan in zip(weights, biases, plans)
        )
        self._finish(flag, error_flag)
        return outputs

    def _group_eligible(self, rows, width, weights, biases, quantized, target):
        # One streamed launch for 2-3 decode projections of one activation, all with or all without bias.
        return (
            target is not None
            and rows > 1
            and 2 <= len(weights) <= 3
            and len({bias is None for bias in biases}) == 1
            and all(self._stream_eligible(width, quantized, weight) for weight in weights)
        )

    def _linear_group(self, value, rows, width, weights, biases, prepared, flag, target, *, maxima=None, raw=False):
        """Grouped streamed projection. With raw=True (split-K plans only) return the split partials and metadata
        for a fused finish instead of encoding them; `maxima` (uint32[rows]) is cleared by the launch."""
        counts = [weight.shape[0] for weight in weights]
        total = sum(counts)
        plan = self._decode_plan(width, rows, total, target)
        has_bias = biases[0] is not None
        functions = self._integer_functions(
            width, has_bias, plan.row_tile, 4, plan.split_k, packed_input=True, columns=DECODE_STREAM_COLUMNS
        )
        quantized, ex = prepared
        exponents = [self._weight_exponents(weight, flag) for weight in weights]
        outs = [torch.empty((rows, count), dtype=torch.float32, device=self.device) for count in counts]
        partials = (
            torch.empty((plan.split_k, rows, total), dtype=torch.int64, device=self.device)
            if plan.split_k > 1
            else outs[0]
        )
        missing = 3 - len(weights)
        pad = lambda items: (*items, *(items[0],) * missing)  # noqa: E731 - unused slots have zero outputs
        bias_pointers = pad(tuple(biases) if has_bias else tuple(weights))
        self._launch(
            functions["integer_stream_group"],
            grid=(
                sum(-(-count // DECODE_STREAM_COLUMNS) for count in counts),
                min(65535, -(-rows // plan.row_tile)),
                plan.split_k,
            ),
            block=(128, 1),
            pointers=(
                quantized,
                ex,
                flag,
                partials,
                *pad(weights),
                *bias_pointers,
                *pad(exponents),
                *pad(outs),
                ex if maxima is None else maxima,
            ),
            integers=(rows, *counts, *(0,) * missing, 0 if maxima is None else rows),
        )
        if raw:
            return partials, ex, exponents, plan
        if plan.split_k > 1:
            self._launch(
                functions["integer_finish_group"],
                grid=(-(-total // 256), min(65535, rows)),
                block=(256, 1),
                pointers=(partials, ex, flag, *bias_pointers, *pad(exponents), *pad(outs)),
                integers=(rows, *counts, *(0,) * missing),
            )
        return tuple(out.reshape(*value.shape[:-1], out.shape[1]) for out in outs)

    def _linear(
        self,
        value,
        weight,
        bias=None,
        *,
        error_flag=None,
        row_tile=None,
        warps=4,
        split_k=1,
        implementation="auto",
        prepared=None,
        residual=None,
        stream_columns=STREAM_COLUMNS,
    ):
        if row_tile is not None and (type(row_tile) is not int or row_tile not in (16, 32)):
            raise ReferenceArithmeticError("Integer row tile must be 16 or 32")
        if type(warps) is not int or warps not in (4, 8):
            raise ReferenceArithmeticError("Integer warp count must be 4 or 8")
        if type(split_k) is not int or split_k not in (1, 2, 4, 8):
            raise ReferenceArithmeticError("Integer split-K count must be 1, 2, 4 or 8")
        if implementation not in ("auto", "mma", "simt"):
            raise ReferenceArithmeticError("Unknown integer execution implementation")
        if not isinstance(value, torch.Tensor) or value.dtype != torch.float32:
            raise ReferenceArithmeticError("Integer linear activation must be FP32")
        rows, width, outputs = sc.validate_linear(value, weight, bias, device=self.device)
        if residual is not None and not (
            isinstance(residual, torch.Tensor)
            and residual.dtype == torch.float32
            and residual.device == self.device
            and residual.is_contiguous()
            and residual.numel() == rows * outputs
            and residual.shape[-1] == outputs
        ):
            raise ReferenceArithmeticError("Residual must be a contiguous FP32 tensor shaped like the projection")
        if split_k > 1 and split_k * rows * outputs * 8 > self.max_partial_bytes:
            raise ReferenceArithmeticError("Integer split-K workspace budget exceeded")
        row_tile = (16 if rows <= 16 else 32) if row_tile is None else row_tile
        mode = ("simt" if rows == 1 else "mma") if implementation == "auto" else implementation
        functions = self._integer_functions(
            width, bias is not None, row_tile, warps, split_k, packed_input=mode == "mma", columns=stream_columns
        )
        flag = self.new_error_flag() if error_flag is None else error_flag
        quantized, ex = (
            self.quantize_input(
                value.reshape(rows, width), error_flag=flag, _functions=functions, _packed=mode == "mma"
            )
            if prepared is None
            else prepared
        )
        ew = self._weight_exponents(weight, flag)
        out = torch.empty((rows, outputs), dtype=torch.float32, device=self.device)
        partials = torch.empty((split_k, rows, outputs), dtype=torch.int64, device=self.device) if split_k > 1 else out
        if mode == "mma" and self._stream_eligible(width, quantized, weight):
            entry, grid, block = "integer_stream", (-(-outputs // stream_columns), -(-rows // row_tile), split_k), 128
        elif mode == "simt":
            entry, grid, block = "integer_simt", (-(-outputs // 8), rows, split_k), 256
        else:
            entry, grid, block = (
                "integer_linear",
                (-(-outputs // (warps * 8)), -(-rows // row_tile), split_k),
                32 * warps,
            )
        self._launch(
            functions[entry],
            grid=(grid[0], min(65535, grid[1]), grid[2]),
            block=(block, 1),
            pointers=(quantized, weight, weight if bias is None else bias, ex, ew, out, flag, partials),
            integers=(rows, outputs),
        )
        if split_k > 1 and residual is not None:
            # strict_add(residual, projection) fused into the split-K finish.
            out = torch.empty((rows, outputs), dtype=torch.float32, device=self.device)
            self._launch(
                self._finish_functions(split_k, bias is not None)["finish_residual"],
                grid=(-(-outputs // 256), min(65535, rows)),
                block=(256, 1),
                pointers=(partials, weight if bias is None else bias, ex, ew, residual, out, flag),
                integers=(rows, outputs),
            )
            self._finish(flag, error_flag)
            return out.reshape(*value.shape[:-1], outputs)
        if split_k > 1:
            self._launch(
                functions["integer_finish"],
                grid=(-(-outputs // 256), min(65535, rows)),
                block=(256, 1),
                pointers=(partials, weight if bias is None else bias, ex, ew, out, flag),
                integers=(rows, outputs),
            )
        if residual is not None:
            out = self.add(residual, out, error_flag=flag)
        self._finish(flag, error_flag)
        return out.reshape(*value.shape[:-1], outputs)
