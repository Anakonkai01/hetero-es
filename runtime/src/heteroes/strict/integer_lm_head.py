"""Exact B22 greedy selection with integer intervals and sparse recomputation of surviving vocab tiles.

For t=floor(qw/32768), P=sum(qa*t), Q=sum(qa), L=sum(abs(qa)), the exact dot S satisfies
abs(S-(32768*P+16384*Q)) <= 16384*L. Monotone RNE/FTZ encoding bounds every score. A tile can
be skipped only when its upper bound is strictly below the largest lower bound and all its bounds are
finite. Thus ties and every potentially overflowing logit are recomputed with the original arithmetic.
Only the greedy token is materialized; forward/logit APIs and repetition penalties use the full projection.
"""

import hashlib
from pathlib import Path
import weakref

import torch

from heteroes.strict.reference_ops import ReferenceArithmeticError

SELECT_PARTITIONS = 8

_SOURCE = r"""
__device__ __forceinline__ i64 bound_floor(i64 q,int shift) {
  return q>=0 ? q>>shift : -(i64)(((u64)(-q)+((1ull<<shift)-1ull))>>shift);
}
// IEEE encodings ordered as unsigned integers: comparisons add no floating arithmetic and keep -0/+0 adjacent.
__device__ __forceinline__ float bound_max(float a,float b) {
  unsigned ua=__float_as_uint(a),ub=__float_as_uint(b);
  unsigned ka=ua^((ua>>31) ? 0xffffffffu : 0x80000000u);
  unsigned kb=ub^((ub>>31) ? 0xffffffffu : 0x80000000u);
  return __uint_as_float(ka>kb ? ua : ub);
}
__device__ __forceinline__ void bound_mma(int* c,const unsigned* a,const unsigned* b) {
  asm volatile("mma.sync.aligned.m16n8k32.row.col.s32.s8.s8.s32 "
    "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};"
    : "+r"(c[0]), "+r"(c[1]), "+r"(c[2]), "+r"(c[3])
    : "r"(a[0]), "r"(a[1]), "r"(a[2]), "r"(a[3]), "r"(b[0]), "r"(b[1]));
}
__device__ __forceinline__ int bound_q(const unsigned* x,int rows,int row,int k) {
  int q=0;
#pragma unroll
  for(int d=0;d<3;++d) {
    unsigned word=x[((size_t)d*rows+row)*(WIDTH/4)+k/4];
    int byte=(int)((word>>(8*(k&3)))&255u);
    if(byte>=128) byte-=256;
    q+=byte*(1<<(8*d));
  }
  return q;
}
extern "C" __global__ void bound_weights(const u16* w,const int* ew,signed char* coarse,int outputs) {
  int v=blockIdx.x;
  for(int k=threadIdx.x;k<WIDTH;k+=128) {
    int q=quant_half(w[(size_t)v*WIDTH+k],ew[v]);
    int t=q/32768;
    t-=q<0 && (q&32767)!=0; // mathematical floor, including negative nonmultiples
    coarse[(size_t)v*WIDTH+k]=(signed char)t;
  }
}
extern "C" __global__ void bound_rows(const unsigned* x,i64* summary,int rows) {
  int row=blockIdx.x,t=threadIdx.x;
  i64 sum=0,absolute=0;
  for(int k=t;k<WIDTH;k+=256) {
    int q=bound_q(x,rows,row,k);
    sum+=q;absolute+=q<0 ? -(i64)q : (i64)q;
  }
  for(int m=16;m;m>>=1) {
    sum+=__shfl_xor_sync(0xffffffffu,sum,m);
    absolute+=__shfl_xor_sync(0xffffffffu,absolute,m);
  }
  __shared__ i64 totals[8],absolutes[8];
  if((t&31)==0) {totals[t>>5]=sum;absolutes[t>>5]=absolute;}
  __syncthreads();
  if(t==0) {
    sum=0;absolute=0;
    for(int w=0;w<8;++w) {sum+=totals[w];absolute+=absolutes[w];}
    summary[row*2]=sum;summary[row*2+1]=absolute;
  }
}
__device__ __forceinline__ void bound_cp16(void* dest,const void* source,int bytes) {
  unsigned long long address;
  asm volatile("cvta.to.shared.u64 %0, %1;" : "=l"(address) : "l"(dest));
  asm volatile("cp.async.cg.shared.global [%0], [%1], 16, %2;" ::
               "r"((unsigned)address),"l"(source),"r"(bytes) : "memory");
}
__device__ __forceinline__ void bound_stage(unsigned char* sw,unsigned char* sa,const unsigned* x,
                                           const signed char* w,int rows,int outputs,int first,int column0,int k0) {
  int t=threadIdx.x,r=t>>2,chunk=t&3,n=column0+r,k=k0+chunk*16;
  int valid=n<outputs && k<WIDTH ? min(16,WIDTH-k) : 0;
  bound_cp16(sw+r*64+((chunk^((r&1)<<1))<<4),valid ? (const void*)(w+(size_t)n*WIDTH+k) : (const void*)w,valid);
  for(int c=t;c<3*MT*4;c+=128) {
    int d=c/(MT*4),rr=(c>>2)%MT,ch=c&3,row=first+rr,kk=k0+ch*16;
    int bytes=row<rows && kk<WIDTH ? min(16,WIDTH-kk) : 0;
    const unsigned* source=x+((size_t)d*rows+row)*(WIDTH/4)+kk/4;
    bound_cp16(sa+(d*MT+rr)*64+((ch^(((rr>>1)&1)<<1))<<4),bytes ? (const void*)source : (const void*)x,bytes);
  }
}
extern "C" __global__ void __launch_bounds__(128) bound_scores(const unsigned* x,const signed char* w,
    const int* ex,const int* ew,const i64* summary,float* tile_hi,float* tile_lo,int rows,int outputs) {
  __shared__ __align__(16) unsigned char ws[3][32*64],as[3][3*MT*64];
  // The staged weights are dead after the final wait/barrier. Reuse that aligned storage for row
  // maxima so the int64 bounds do not reduce the number of resident CTAs.
  i64 (*highs)[4]=reinterpret_cast<i64 (*)[4]>(ws);
  i64 (*lows)[4]=highs+MT;
  int lane=threadIdx.x&31,warp=threadIdx.x>>5,group=lane>>2,thread=lane&3;
  int first=blockIdx.y*MT,column0=blockIdx.x*32,tiles=(outputs+31)/32;
  const int count=(WIDTH+63)/64;
  int accum[MT/16][3][4]={};
#pragma unroll
  for(int s=0;s<2;++s) {
    if(s<count) bound_stage(ws[s],as[s],x,w,rows,outputs,first,column0,s*64);
    asm volatile("cp.async.commit_group;" ::: "memory");
  }
  for(int it=0;it<count;++it) {
    asm volatile("cp.async.wait_group 1;" ::: "memory");
    __syncthreads();
    int next=it+2;
    if(next<count) bound_stage(ws[next%3],as[next%3],x,w,rows,outputs,first,column0,next*64);
    asm volatile("cp.async.commit_group;" ::: "memory");
    const unsigned char* sw=ws[it%3];
    const unsigned char* sa=as[it%3];
#pragma unroll
    for(int step=0;step<2;++step) {
      int wr=warp*8+group;
      int off=(((step*2+(thread>>1))^((wr&1)<<1))<<4)+(thread&1)*8;
      uint2 h=*(const uint2*)(sw+wr*64+off);
      unsigned b[2]={h.x,h.y};
#pragma unroll
      for(int m=0;m<MT/16;++m) {
        int row=m*16+group;
        int offset=(((step*2+(thread>>1))^(((row>>1)&1)<<1))<<4)+(thread&1)*8;
#pragma unroll
        for(int d=0;d<3;++d) {
          uint2 top=*(const uint2*)(sa+(d*MT+row)*64+offset);
          uint2 bot=*(const uint2*)(sa+(d*MT+row+8)*64+offset);
          unsigned a[4]={top.x,bot.x,top.y,bot.y};
          bound_mma(accum[m][d],a,b);
        }
      }
    }
  }
  asm volatile("cp.async.wait_group 0;" ::: "memory");
  __syncthreads();
#pragma unroll
  for(int m=0;m<MT/16;++m) {
#pragma unroll
    for(int half=0;half<2;++half) {
      int rr=m*16+group+half*8,row=first+rr;
      i64 hi=-(1ll<<62),lo=hi;
#pragma unroll
      for(int j=0;j<2;++j) {
        int v=column0+warp*8+thread*2+j,index=half*2+j;
        if(row<rows && v<outputs) {
          i64 p=0;
#pragma unroll
          for(int d=0;d<3;++d) p+=(i64)accum[m][d][index]*(1ll<<(8*d));
          i64 center=32768ll*p+16384ll*summary[row*2],radius=16384ll*summary[row*2+1];
          // Every finite FP16 weight row has exponent <=15. Put the integer intervals on that
          // common scale with outward rounding; monotonicity then permits encoding only tile maxima.
          int shift=15-ew[v],scale=ex[row]-27;
          i64 upper=-bound_floor(-(center+radius),shift),lower=bound_floor(center-radius,shift);
          // RNE overflows exactly at |q| >= (2^128-2^103)/2^scale. For scale<66 the entire int64
          // domain is finite. Mark even a negative nonwinning overflow before reducing the maxima.
          u64 limit=scale>=66 ? (1ull<<(128-scale))-(1ull<<(103-scale)) : 0x8000000000000000ull;
          if((u64)(upper<0 ? -upper : upper)>=limit || (u64)(lower<0 ? -lower : lower)>=limit)
            upper=1ll<<62; // impossible for an admitted exact bound (<2^60), denotes a nonfinite interval
          hi=upper>hi ? upper : hi;lo=lower>lo ? lower : lo;
        }
      }
#pragma unroll
      for(int mask=1;mask<=2;mask<<=1) {
        i64 h=__shfl_xor_sync(0xffffffffu,hi,mask),l=__shfl_xor_sync(0xffffffffu,lo,mask);
        hi=h>hi ? h : hi;lo=l>lo ? l : lo;
      }
      if(thread==0) {highs[rr][warp]=hi;lows[rr][warp]=lo;}
    }
  }
  __syncthreads();
  if(threadIdx.x<MT && first+threadIdx.x<rows) {
    int rr=threadIdx.x;
    i64 hi=highs[rr][0],lo=lows[rr][0];
    for(int warp=1;warp<4;++warp) {
      hi=highs[rr][warp]>hi ? highs[rr][warp] : hi;
      lo=lows[rr][warp]>lo ? lows[rr][warp] : lo;
    }
    tile_hi[(size_t)(first+rr)*tiles+blockIdx.x]=hi==(1ll<<62) ? __uint_as_float(0x7f800000u) : bound_encode(hi,ex[first+rr]-27);
    tile_lo[(size_t)(first+rr)*tiles+blockIdx.x]=bound_encode(lo,ex[first+rr]-27);
  }
}
// Recompute a surviving tile with the same nine digit-pair IMMAs as the full projection. Replicate the
// one live activation across the sixteen tensor rows, then consume only row zero. This avoids the long
// dependent per-column SIMT quantization/dot loop while retaining the exact int64 reconstruction.
__device__ __forceinline__ void bound_exact_stage(unsigned char* sw,const u16* w,int outputs,int column0,int k0) {
  int t=threadIdx.x,r=t>>3,chunk=t&7,n=column0+r,k=k0+chunk*8;
  for(int i=0;i<2;++i) {
    int rr=r+i*16,v=n+i*16;
    int bytes=v<outputs && k<WIDTH ? 16 : 0;
    bound_cp16(sw+rr*128+((chunk^((rr&1)<<2))<<4),bytes ? (const void*)(w+(size_t)v*WIDTH+k) : (const void*)w,bytes);
  }
}
__device__ __forceinline__ void bound_exact(const unsigned* x,const u16* w,const int* ex,const int* ew,
    unsigned char* shared,int rows,int row,int outputs,int column0,float& best,int& index,int* error) {
  int lane=threadIdx.x&31,warp=threadIdx.x>>5,group=lane>>2,thread=lane&3;
  int n=column0+warp*8+group;
  unsigned scale=(unsigned)((21-(n<outputs ? ew[n] : 0))*0x800000);
  int accum[5][4]={};
  const int count=(WIDTH+63)/64;
#pragma unroll
  for(int s=0;s<2;++s) {
    if(s<count) bound_exact_stage(shared+s*4096,w,outputs,column0,s*64);
    asm volatile("cp.async.commit_group;" ::: "memory");
  }
  for(int it=0;it<count;++it) {
    asm volatile("cp.async.wait_group 1;" ::: "memory");
    __syncthreads();
    int next=it+2;
    if(next<count) bound_exact_stage(shared+(next%3)*4096,w,outputs,column0,next*64);
    asm volatile("cp.async.commit_group;" ::: "memory");
#pragma unroll
    for(int step=0;step<2;++step) {
      int r=warp*8+group,k=it*64+step*32+thread*8;
      uint4 h=*(const uint4*)(shared+(it%3)*4096+r*128+(((step*4+thread)^((r&1)<<2))<<4));
      unsigned lo[3],hi[3],b[3][2],a[3][4];
      convert4(lo,h.x,h.y,scale);convert4(hi,h.z,h.w,scale);
#pragma unroll
      for(int d=0;d<3;++d) {
        b[d][0]=lo[d];b[d][1]=hi[d];
        uint2 q={0,0};
        if(k<WIDTH) q=*(const uint2*)(x+((size_t)d*rows+row)*(WIDTH/4)+k/4);
        a[d][0]=a[d][1]=q.x;a[d][2]=a[d][3]=q.y;
      }
#pragma unroll
      for(int i=0;i<3;++i) {
#pragma unroll
        for(int j=0;j<3;++j) bound_mma(accum[i+j],a[i],b[j]);
      }
    }
  }
  asm volatile("cp.async.wait_group 0;" ::: "memory");
  __syncthreads();
  if(group==0) {
#pragma unroll
    for(int j=0;j<2;++j) {
      int v=column0+warp*8+thread*2+j;
      if(v<outputs) {
        i64 sum=0;
#pragma unroll
        for(int d=0;d<5;++d) sum+=(i64)accum[d][j]*(1ll<<(8*d));
        float s=flush(encode(sum,ex[row]+ew[v]-42,error));
        if((__float_as_uint(s)&0x7f800000u)==0x7f800000u) atomicOr(error,1);
        if(s>best || (s==best && v<index)) {best=s;index=v;}
      }
    }
  }
}
extern "C" __global__ void bound_select(const unsigned* x,const u16* w,const int* ex,const int* ew,
    const float* tile_hi,const float* tile_lo,float* best_scores,int* best_indices,int* error,int rows,int outputs) {
  int row=blockIdx.y,t=threadIdx.x,lane=t&31,warp=t>>5,tiles=(outputs+31)/32;
  float global_lo=__uint_as_float(0xff800000u);
#pragma unroll 1
  for(int tile=t;tile<tiles;tile+=128) {
    float lo=tile_lo[(size_t)row*tiles+tile];
    global_lo=bound_max(lo,global_lo);
  }
  for(int m=16;m;m>>=1) {
    float other=__shfl_xor_sync(0xffffffffu,global_lo,m);
    global_lo=bound_max(other,global_lo);
  }
  __shared__ float maxima[4];
  __shared__ int indices[4];
  __shared__ unsigned masks[4];
  __shared__ __align__(16) unsigned char exact_shared[3*4096];
  if(lane==0) maxima[warp]=global_lo;
  __syncthreads();
  for(int j=0;j<4;++j) global_lo=bound_max(maxima[j],global_lo);
  __syncthreads(); // every warp must read global bounds before maxima is reused for exact winners
  float best=__uint_as_float(0xff7fffffu);
  int index=outputs;
#pragma unroll 1
  for(int base=blockIdx.x*128;base<tiles;base+=gridDim.x*128) {
    int candidate=base+t;
    bool survives=candidate<tiles && tile_hi[(size_t)row*tiles+candidate]>=global_lo;
    unsigned mask=__ballot_sync(0xffffffffu,survives);
    if(lane==0) masks[warp]=mask;
    __syncthreads();
    // One coalesced read of 128 tile bounds, then visit only the surviving bits. Scanning one scalar
    // bound per CTA per iteration would serialize hundreds of independent global loads.
    for(int source=0;source<4;++source) {
      unsigned pending=masks[source];
#pragma unroll 1
      while(pending) {
        int bit=__ffs(pending)-1,tile=base+source*32+bit;
        pending&=pending-1;
        bound_exact(x,w,ex,ew,exact_shared,rows,row,outputs,tile*32,best,index,error);
      }
    }
    __syncthreads();
  }
  for(int mask=16;mask;mask>>=1) {
    float s=__shfl_xor_sync(0xffffffffu,best,mask);
    int v=__shfl_xor_sync(0xffffffffu,index,mask);
    if(s>best || (s==best && v<index)) {best=s;index=v;}
  }
  if(lane==0) {maxima[warp]=best;indices[warp]=index;}
  __syncthreads();
  if(t==0) {
    for(int j=0;j<4;++j) {
      float s=maxima[j];int v=indices[j];
      if(s>best || (s==best && v<index)) {best=s;index=v;}
    }
    best_scores[row*gridDim.x+blockIdx.x]=best;
    best_indices[row*gridDim.x+blockIdx.x]=index;
  }
}
"""


def source(width, row_tile=32):
    from heteroes.strict import integer_cuda as ic

    # Reuse the admitted quantizer and encoder verbatim. The interval encoder suppresses only the flag;
    # nonfinite intervals survive and the exact recomputation below raises the original flag if needed.
    helpers = ic._SOURCE.split('extern "C" __global__ void integer_input')[0]
    unchecked = ic._ENCODE.split("__device__ __forceinline__ float encode")[1]
    unchecked = "__device__ __forceinline__ float bound_encode" + unchecked
    unchecked = unchecked.replace("int scale,int* error", "int scale").replace("atomicOr(error,1);", "")
    conversion = ic._SOURCE[
        ic._SOURCE.index("#if FAST_CONVERT\n#if MAGNITUDE_BITS") : ic._SOURCE.index(
            "// Split partials of matrix columns"
        )
    ]
    return (
        f"#define WIDTH {width}\n#define MAGNITUDE_BITS 22\n#define DIGITS 3\n#define MT {row_tile}\n#define FAST_CONVERT 1\n"
        + helpers
        + ic._ENCODE
        + unchecked
        + conversion
        + _SOURCE
    )


def source_sha256():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class BoundedLmHead:
    def __init__(self, kernels):
        self.kernels = kernels
        self.buffer = None
        self._weight = None
        self._binding = None
        self._active = False

    def eligible(self, weight):
        return (
            self.kernels.magnitude_bits == 22
            and weight.ndim == 2
            and weight.shape[0] >= 4096
            and weight.shape[1] % 16 == 0
            and weight.is_contiguous()
            and weight.data_ptr() % 16 == 0
            and self.kernels.mma_schedule != "tile"
        )

    def _functions(self, width, row_tile=32):
        name = f"integer-bound-{width}-m{row_tile}"
        kernels = self.kernels
        if name not in kernels._functions:
            kernels._functions[name] = kernels._compile(
                name,
                source(width, row_tile),
                ["bound_weights", "bound_rows", "bound_scores", "bound_select"],
                integer_mma=True,
            )
        return kernels._functions[name]

    @torch.inference_mode()
    def prepare(self, weight):
        kernels = self.kernels
        if (
            kernels.magnitude_bits != 22
            or not kernels._request_active
            or weight.ndim != 2
            or weight.shape[1] % 16
            or not weight.is_contiguous()
            or weight.data_ptr() % 16
        ):
            raise ReferenceArithmeticError("Bounded lm_head needs an active B22 request with aligned FP16 weights")
        binding = kernels._weight_binding(weight)
        ew = kernels._weight_exponents(weight, None)
        if self.buffer is None or self._weight() is not weight or self._binding != binding:
            self.buffer = torch.empty_like(weight, dtype=torch.int8)
        self._weight, self._binding = weakref.ref(weight), binding
        kernels._launch(
            self._functions(weight.shape[1])["bound_weights"],
            grid=weight.shape[0],
            block=(128, 1),
            pointers=(weight, ew, self.buffer),
            integers=(weight.shape[0],),
        )
        self._active = True

    @torch.inference_mode()
    def clear(self):
        self._active = False
        if self.buffer is not None:
            self.buffer.zero_()

    def _validate(self, prepared, weight):
        if (
            not self._active
            or not self.kernels._request_active
            or self._weight() is not weight
            or self._binding != self.kernels._weight_binding(weight)
        ):
            raise ReferenceArithmeticError("Bounded lm_head weight binding changed or request is inactive")
        rows, width = self.kernels._prepared_shape(prepared, weight).shape
        if rows < 2 or width % 16:
            raise ReferenceArithmeticError("Bounded lm_head needs at least two packed activation rows")
        return rows, width

    @torch.inference_mode()
    def bounds(self, prepared, weight):
        rows, width = self._validate(prepared, weight)
        kernels, (planes, ex) = self.kernels, prepared
        ew = kernels._weight_exponents(weight, None)
        summary = torch.empty((rows, 2), dtype=torch.int64, device=kernels.device)
        tiles = -(-weight.shape[0] // 32)
        hi = torch.empty((rows, tiles), dtype=torch.float32, device=kernels.device)
        lo = torch.empty_like(hi)
        row_tile = 16 if rows <= 16 else 32
        functions = self._functions(width, row_tile)
        kernels._launch(
            functions["bound_rows"], grid=rows, block=(256, 1), pointers=(planes, summary), integers=(rows,)
        )
        kernels._launch(
            functions["bound_scores"],
            grid=(tiles, -(-rows // row_tile)),
            block=(128, 1),
            pointers=(planes, self.buffer, ex, ew, summary, hi, lo),
            integers=(rows, weight.shape[0]),
        )
        return hi, lo

    @torch.inference_mode()
    def select(self, prepared, weight, decode, seen, owners, tokens, result, flag):
        rows, width = self._validate(prepared, weight)
        kernels, (planes, ex) = self.kernels, prepared
        hi, lo = self.bounds(prepared, weight)
        ew = kernels._weight_exponents(weight, flag)
        parts = SELECT_PARTITIONS
        best = torch.empty((rows, parts), dtype=torch.float32, device=kernels.device)
        indices = torch.empty((rows, parts), dtype=torch.int32, device=kernels.device)
        kernels._launch(
            self._functions(width, 16 if rows <= 16 else 32)["bound_select"],
            grid=(parts, rows),
            block=(128, 1),
            pointers=(planes, weight, ex, ew, hi, lo, best, indices, flag),
            integers=(rows, weight.shape[0]),
        )
        kernels._launch(
            decode.functions["decode_greedy_select"],
            grid=rows,
            block=(32, 1),
            pointers=(best, indices, seen, owners, tokens, result, flag),
            integers=(weight.shape[0], parts),
        )
