"""Exact CUDA projection for pinned int8 weights and B22 activations (M6 experiment).

The weight is already a signed int8 row, so a dot has three signed-byte MMA products (one per activation limb)
instead of the nine products of the B22-by-B22 path. The final ``S * signif(scale)`` product can reach 68 bits and
is kept as two 64-bit limbs; one RNE/FTZ encoding produces the FP32 output. No dequantized weight or vendor float
GEMM is used for the base projection.

This is an experimental operator, not a managed backend or a hardware qualification. Adapter deltas are outside
this module and use their own FP32 namespace.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import frozen_int8 as artifact
from heteroes.eval import integer_cuda
from heteroes.eval import integer_plan as planning
from heteroes.eval import strict_cuda as sc
from heteroes.eval.reference_ops import ReferenceArithmeticError

FROZEN_INT8_CUDA_VERSION = "frozen_int8_b22_mma_cuda_v1_experimental"
MAGNITUDE_BITS = 22
ACTIVATION_LIMBS = 3


def static_identity(max_partial_bytes=16 * 1024**2):
    if type(max_partial_bytes) is not int or max_partial_bytes < 1:
        raise ReferenceArithmeticError("Frozen int8 workspace budget must be a positive integer")
    return {
        "kernel": FROZEN_INT8_CUDA_VERSION,
        "artifact": artifact.identity(),
        "activationQuantizer": integer_cuda.static_identity(MAGNITUDE_BITS, max_partial_bytes),
        "sourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "maxPartialBytes": max_partial_bytes,
        "hardwareQualified": False,
    }


_SOURCE = (
    sc._LINEAR_SOURCE.split("// One output column")[0]
    + r"""
typedef unsigned long long u64;
typedef long long i64;

__device__ __forceinline__ void scale_parts(float value, unsigned& significand, int& exponent) {
  unsigned bits=__float_as_uint(value);
  unsigned field=(bits>>23)&0xffu;
  significand=field==0 ? (bits&0x7fffffu) : ((bits&0x7fffffu)|0x800000u);
  exponent=field==0 ? -149 : (int)field-150;
}

// Round a 128-bit unsigned value right by `shift` with ties-to-even. Only the low 69 bits of the product can be
// nonzero. A negative shift is admitted only when the high limb is zero (the subnormal branch proves it).
__device__ __forceinline__ u64 shift_round(u64 low, u64 high, int shift) {
  if(shift<=0) return low<<(-shift);
  if(shift<64) {
    u64 whole=(low>>shift)|(high<<(64-shift));
    u64 remainder=low&((1ull<<shift)-1ull), halfway=1ull<<(shift-1);
    return whole + (remainder>halfway || (remainder==halfway && (whole&1ull)));
  }
  if(shift==64) {
    u64 whole=high, remainder=low, halfway=1ull<<63;
    return whole + (remainder>halfway || (remainder==halfway && (whole&1ull)));
  }
  if(shift<128) {
    int upper=shift-64;
    u64 whole=high>>upper;
    u64 remainder=high&((1ull<<upper)-1ull), halfway=1ull<<(upper-1);
    bool above=remainder>halfway || (remainder==halfway && low!=0);
    bool tie=remainder==halfway && low==0;
    return whole + (above || (tie && (whole&1ull)));
  }
  return 0;
}

__device__ __forceinline__ float inf_with_sign(unsigned sign) {
  return __uint_as_float(sign|0x7f800000u);
}

// Exact RNE/FTZ encoding of (sum * significand) * 2**exponent. The product is formed in two limbs so that a
// 68-bit value is never rounded through FP32 or multiplied as int64 by a float.
__device__ __forceinline__ float encode_product(i64 sum, unsigned significand, int exponent, int* error) {
  if(!sum) return 0.0f;
  if(!significand) { atomicOr(error,1); return 0.0f; }
  if(exponent<-2048) { atomicOr(error,1); return 0.0f; }
  unsigned sign=sum<0 ? 0x80000000u : 0;
  u64 magnitude=sum<0 ? (u64)(-sum) : (u64)sum;
  u64 low_product=(u64)(unsigned)(magnitude&0xffffffffull)*(u64)significand;
  u64 high_product=(magnitude>>32)*(u64)significand;
  u64 low=low_product+(high_product<<32);
  u64 high=(high_product>>32)+(low<low_product ? 1ull : 0ull);
  int leading=high ? 127-__clzll((i64)high) : 63-__clzll((i64)low);
  int final_exponent=leading+exponent;
  if(final_exponent>127) { atomicOr(error,1); return inf_with_sign(sign); }
  if(final_exponent<-126) {
    int shift=-exponent-149;
    u64 rounded=shift_round(low,high,shift);
    return __uint_as_float(sign | (rounded>=0x800000ull ? 0x00800000u : 0u));
  }
  int shift=leading-23;
  u64 rounded=shift_round(low,high,shift);
  if(rounded>=0x1000000ull) { rounded>>=1; ++final_exponent; }
  if(final_exponent>127) { atomicOr(error,1); return inf_with_sign(sign); }
  return __uint_as_float(sign | ((unsigned)(final_exponent+127)<<23) | ((unsigned)rounded&0x7fffffu));
}

__device__ __forceinline__ unsigned load_weight_bytes(const signed char* w,int n,int k,int outputs) {
  if(n>=outputs) return 0;
  unsigned value=0;
  #pragma unroll
  for(int i=0;i<4;++i) {
    int p=k+i;
    if(p<WIDTH) value |= ((unsigned)(unsigned char)w[(size_t)n*WIDTH+p]) << (8*i);
  }
  return value;
}

__device__ __forceinline__ void mma_frozen(int* c,const unsigned* a,const unsigned* b) {
  asm volatile("mma.sync.aligned.m16n8k32.row.col.s32.s8.s8.s32 "
    "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};"
    : "+r"(c[0]), "+r"(c[1]), "+r"(c[2]), "+r"(c[3])
    : "r"(a[0]), "r"(a[1]), "r"(a[2]), "r"(a[3]), "r"(b[0]), "r"(b[1]));
}

extern "C" __global__ void __launch_bounds__(32*WARPS)
frozen_linear(const void* xraw,const signed char* w,const u16* bias,const int* ex,const float* scales,
              float* out,int* error,i64* partials,int rows,int outputs) {
  const unsigned* x=(const unsigned*)xraw;
  int lane=threadIdx.x&31, warp=threadIdx.x>>5, group=lane>>2, thread=lane&3;
  int column=blockIdx.x*(WARPS*8)+warp*8;
  for(int first=blockIdx.y*(M_GROUPS*16);first<rows;first+=gridDim.y*(M_GROUPS*16)) {
    int accum[M_GROUPS][3][4]={};
    for(int start=blockIdx.z*32;start<WIDTH;start+=SPLIT_K*32) {
      unsigned b[2]={};
      int source_column=column+group;
      #pragma unroll
      for(int word=0;word<2;++word)
        b[word]=load_weight_bytes(w,source_column,start+thread*4+word*16,outputs);
      #pragma unroll
      for(int m=0;m<M_GROUPS;++m) {
        unsigned a[3][4]={};
        #pragma unroll
        for(int word=0;word<4;++word) {
          int row=first+m*16+group+(word&1)*8;
          int k=start+thread*4+(word>>1)*16;
          #pragma unroll
          for(int d=0;d<3;++d)
            a[d][word]=(row<rows && k<WIDTH)
              ? x[((size_t)d*rows+row)*((WIDTH+3)/4)+k/4] : 0;
        }
        #pragma unroll
        for(int d=0;d<3;++d) mma_frozen(accum[m][d],a[d],b);
      }
    }
    #pragma unroll
    for(int m=0;m<M_GROUPS;++m) {
      #pragma unroll
      for(int d=0;d<4;++d) {
        int row=first+m*16+group+(d>>1)*8;
        int n=column+thread*2+(d&1);
        if(row<rows && n<outputs) {
          i64 sum=(i64)accum[m][0][d]+((i64)accum[m][1][d]<<8)+((i64)accum[m][2][d]<<16);
          unsigned significand;
          int scale_exponent;
          scale_parts(scales[n],significand,scale_exponent);
          i64 total=sum;
#if SPLIT_K > 1
          partials[((size_t)blockIdx.z*rows+row)*outputs+n]=total;
#else
          float value=encode_product(total,significand,ex[row]+scale_exponent-(MAGNITUDE_BITS-1),error);
          if(HAS_BIAS) value=add_rn(value,widen(bias[n]));
          out[(size_t)row*outputs+n]=value;
          if((__float_as_uint(value)&0x7f800000u)==0x7f800000u) atomicOr(error,1);
#endif
        }
      }
    }
  }
}

extern "C" __global__ void frozen_simt(const int* x,const signed char* w,const u16* bias,const int* ex,
                                       const float* scales,float* out,int* error,i64* partials,
                                       int rows,int outputs) {
  int lane=threadIdx.x&31, n=blockIdx.x*8+(threadIdx.x>>5);
  if(n>=outputs) return;
  unsigned significand;
  int scale_exponent;
  scale_parts(scales[n],significand,scale_exponent);
  for(int row=blockIdx.y;row<rows;row+=gridDim.y) {
    i64 sum=0;
    for(int k=blockIdx.z*32+lane;k<WIDTH;k+=SPLIT_K*32)
      sum+=(i64)x[(size_t)row*WIDTH+k]*(i64)w[(size_t)n*WIDTH+k];
    for(int offset=16;offset;offset>>=1) {
      i64 other=__shfl_down_sync(0xffffffffu,sum,offset);
      if(lane<offset) sum+=other;
    }
    if(lane==0) {
#if SPLIT_K > 1
      partials[((size_t)blockIdx.z*rows+row)*outputs+n]=sum;
#else
      float value=encode_product(sum,significand,ex[row]+scale_exponent-(MAGNITUDE_BITS-1),error);
      if(HAS_BIAS) value=add_rn(value,widen(bias[n]));
      out[(size_t)row*outputs+n]=value;
      if((__float_as_uint(value)&0x7f800000u)==0x7f800000u) atomicOr(error,1);
#endif
    }
  }
}

extern "C" __global__ void frozen_finish(const i64* partials,const u16* bias,const int* ex,const float* scales,
                                         float* out,int* error,int rows,int outputs) {
  int n=blockIdx.x*256+threadIdx.x;
  if(n>=outputs) return;
  unsigned significand;
  int scale_exponent;
  scale_parts(scales[n],significand,scale_exponent);
  for(int row=blockIdx.y;row<rows;row+=gridDim.y) {
    i64 sum=0;
    #pragma unroll
    for(int s=0;s<SPLIT_K;++s) sum+=partials[((size_t)s*rows+row)*outputs+n];
    float value=encode_product(sum,significand,ex[row]+scale_exponent-(MAGNITUDE_BITS-1),error);
    if(HAS_BIAS) value=add_rn(value,widen(bias[n]));
    out[(size_t)row*outputs+n]=value;
    if((__float_as_uint(value)&0x7f800000u)==0x7f800000u) atomicOr(error,1);
  }
}

// Direct encoder entry for boundary tests; it uses the same function as both projections.
extern "C" __global__ void frozen_encode(const i64* sums,const int* significands,const int* exponents,
                                         float* out,int* error,int count) {
  int i=blockIdx.x*256+threadIdx.x;
  if(i<count) out[i]=encode_product(sums[i],(unsigned)significands[i],exponents[i],error);
}
"""
)


class FrozenInt8CudaKernels(integer_cuda.IntegerCudaKernels):
    """One CUDA device: exact frozen-int8 projection plus the inherited B22 activation quantizer."""

    def __init__(self, device, *, max_partial_bytes=16 * 1024**2):
        super().__init__(device, magnitude_bits=MAGNITUDE_BITS, max_partial_bytes=max_partial_bytes)
        self._frozen_specs = {}

    def identity(self):
        identity = {
            **super().identity(),
            "frozenKernel": FROZEN_INT8_CUDA_VERSION,
            "frozenArtifact": artifact.identity(),
            "frozenSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        identity["fingerprint"] = canonical_json_hash({k: v for k, v in identity.items() if k != "fingerprint"})
        return identity

    def _frozen_functions(self, width, has_bias=False, row_tile=16, warps=4, split_k=1):
        name = f"frozen-{width}-bias{int(has_bias)}-m{row_tile}-w{warps}-s{split_k}"
        if name not in self._functions:
            defines = dict(
                WIDTH=width,
                HAS_BIAS=int(has_bias),
                M_GROUPS=row_tile // 16,
                WARPS=warps,
                SPLIT_K=split_k,
                MAGNITUDE_BITS=MAGNITUDE_BITS,
            )
            header = "".join(f"#define {k} {v}\n" for k, v in defines.items())
            self._functions[name] = self._compile(
                name,
                header + _SOURCE,
                ["frozen_linear", "frozen_simt", "frozen_finish", "frozen_encode"],
                integer_mma=True,
            )
        return self._functions[name]

    def _validate_weights(self, weight_q, weight_scale, bias, width, outputs):
        if (
            not isinstance(weight_q, torch.Tensor)
            or not isinstance(weight_scale, torch.Tensor)
            or weight_q.dtype != torch.int8
            or weight_scale.dtype != torch.float32
            or weight_q.device != self.device
            or weight_scale.device != self.device
            or weight_q.ndim != 2
            or weight_q.shape != (outputs, width)
            or weight_scale.shape != (outputs,)
            or not weight_q.is_contiguous()
            or not weight_scale.is_contiguous()
            or not 1 <= width <= artifact.MAX_WIDTH
            or outputs < 1
        ):
            raise ReferenceArithmeticError("Unsupported frozen int8 weight storage for this kernel")
        if bias is not None and (
            not isinstance(bias, torch.Tensor)
            or bias.dtype != torch.float16
            or bias.shape != (outputs,)
            or bias.device != self.device
            or not bias.is_contiguous()
        ):
            raise ReferenceArithmeticError("Frozen int8 bias must be contiguous FP16 on the kernel device")

    @torch.inference_mode()
    def encode_products(self, sums, significands, exponents, *, error_flag=None):
        """Test/reference entry for the exact two-limb encoder."""
        if (
            not isinstance(sums, torch.Tensor)
            or sums.dtype != torch.int64
            or sums.device != self.device
            or not sums.is_contiguous()
            or not isinstance(significands, torch.Tensor)
            or significands.dtype != torch.int32
            or significands.shape != sums.shape
            or significands.device != self.device
            or not isinstance(exponents, torch.Tensor)
            or exponents.dtype != torch.int32
            or exponents.shape != sums.shape
            or exponents.device != self.device
            or not sums.numel()
        ):
            raise ReferenceArithmeticError("Frozen encoder needs matching contiguous int64/int32 device vectors")
        functions = self._frozen_functions(1)
        flag = self.new_error_flag() if error_flag is None else error_flag
        out = torch.empty_like(sums, dtype=torch.float32)
        count = sums.numel()
        self._launch(
            functions["frozen_encode"],
            grid=(-(-count // 256),),
            block=(256, 1),
            pointers=(sums, significands.contiguous(), exponents.contiguous(), out, flag),
            integers=(count,),
        )
        self._finish(flag, error_flag)
        return out

    @torch.inference_mode()
    def linear(
        self,
        value,
        weight_q,
        weight_scale,
        bias=None,
        *,
        error_flag=None,
        row_tile=None,
        warps=4,
        split_k=1,
        implementation="auto",
        prepared=None,
    ):
        """Exact frozen-int8 projection. ``weight_q``/``weight_scale`` must come from a verified artifact payload.

        The operator does not rescan a large weight matrix for range or provenance on every call; typed storage
        and the artifact reader enforce those invariants once. Everything else (shape, dtype, device, layout,
        liveness) is checked here before any launch.
        """
        if row_tile is not None and (type(row_tile) is not int or row_tile not in (16, 32)):
            raise ReferenceArithmeticError("Frozen int8 row tile must be 16 or 32")
        if type(warps) is not int or warps not in (4, 8):
            raise ReferenceArithmeticError("Frozen int8 warp count must be 4 or 8")
        if type(split_k) is not int or split_k not in (1, 2, 4, 8):
            raise ReferenceArithmeticError("Frozen int8 split-K count must be 1, 2, 4 or 8")
        if implementation not in ("auto", "mma", "simt"):
            raise ReferenceArithmeticError("Unknown frozen int8 execution implementation")
        if (
            not isinstance(value, torch.Tensor)
            or value.dtype != torch.float32
            or value.device != self.device
            or value.ndim < 1
            or not value.numel()
        ):
            raise ReferenceArithmeticError("Frozen int8 activation must be nonempty FP32 on the kernel device")
        width = value.shape[-1]
        if (
            not isinstance(weight_q, torch.Tensor)
            or weight_q.ndim != 2
            or weight_q.shape[1] != width
            or not weight_q.shape[0]
            or width < 1
            or width > artifact.MAX_WIDTH
        ):
            raise ReferenceArithmeticError("Frozen int8 linear width mismatch")
        outputs = int(weight_q.shape[0])
        self._validate_weights(weight_q, weight_scale, bias, width, outputs)
        rows = value.numel() // width
        if split_k > 1 and split_k * rows * outputs * 8 > self.max_partial_bytes:
            raise ReferenceArithmeticError("Frozen int8 split-K workspace budget exceeded")
        row_tile = (16 if rows <= 16 else 32) if row_tile is None else row_tile
        mode = ("simt" if rows == 1 else "mma") if implementation == "auto" else implementation
        functions = self._frozen_functions(width, bias is not None, row_tile, warps, split_k)
        flag = self.new_error_flag() if error_flag is None else error_flag
        quantized, ex = (
            self.quantize_input(value.reshape(rows, width), error_flag=flag, _packed=mode == "mma")
            if prepared is None
            else prepared
        )
        out = torch.empty((rows, outputs), dtype=torch.float32, device=self.device)
        partials = torch.empty((split_k, rows, outputs), dtype=torch.int64, device=self.device) if split_k > 1 else out
        self._launch(
            functions["frozen_simt" if mode == "simt" else "frozen_linear"],
            grid=(
                -(-outputs // (8 if mode == "simt" else warps * 8)),
                min(65535, rows if mode == "simt" else -(-rows // row_tile)),
                split_k,
            ),
            block=(256 if mode == "simt" else 32 * warps, 1),
            pointers=(quantized, weight_q, weight_q if bias is None else bias, ex, weight_scale, out, flag, partials),
            integers=(rows, outputs),
        )
        if split_k > 1:
            self._launch(
                functions["frozen_finish"],
                grid=(-(-outputs // 256), min(65535, rows)),
                block=(256, 1),
                pointers=(partials, weight_q if bias is None else bias, ex, weight_scale, out, flag),
                integers=(rows, outputs),
            )
        self._finish(flag, error_flag)
        return out.reshape(*value.shape[:-1], outputs)

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
    def linear_decode(self, value, weight_q, weight_scale, bias=None, *, error_flag=None, target_ctas_per_sm=8):
        rows = value.numel() // value.shape[-1]
        plan = self._decode_plan(value.shape[-1], rows, weight_q.shape[0], target_ctas_per_sm)
        return self.linear(
            value,
            weight_q,
            weight_scale,
            bias,
            error_flag=error_flag,
            row_tile=plan.row_tile,
            split_k=plan.split_k,
            implementation=plan.implementation,
        )

    @torch.inference_mode()
    def linear_many(
        self,
        value,
        weights,
        biases=None,
        *,
        error_flag=None,
        decode_target_ctas_per_sm=None,
    ):
        """Project one activation through independent frozen matrices with one call-local quantization."""
        if not isinstance(weights, (list, tuple)) or not weights:
            raise ReferenceArithmeticError("Frozen projection group needs a nonempty list/tuple of weights")
        if biases is None:
            biases = (None,) * len(weights)
        if not isinstance(biases, (list, tuple)) or len(biases) != len(weights):
            raise ReferenceArithmeticError("Frozen projection group needs matching weights and biases")
        if not isinstance(value, torch.Tensor) or value.dtype != torch.float32:
            raise ReferenceArithmeticError("Frozen linear activation must be FP32")
        if value.ndim < 1 or not value.numel():
            raise ReferenceArithmeticError("Frozen linear activation must be nonempty")
        width = value.shape[-1]
        rows = value.numel() // width
        plans = []
        for (weight_q, weight_scale), bias in zip(weights, biases):
            if (
                not isinstance(weight_q, torch.Tensor)
                or weight_q.ndim != 2
                or weight_q.shape[1] != width
                or not weight_q.shape[0]
            ):
                raise ReferenceArithmeticError("Frozen int8 linear width mismatch")
            outputs = int(weight_q.shape[0])
            self._validate_weights(weight_q, weight_scale, bias, width, outputs)
            plans.append(
                None
                if decode_target_ctas_per_sm is None
                else self._decode_plan(width, rows, outputs, decode_target_ctas_per_sm)
            )
        flag = self.new_error_flag() if error_flag is None else error_flag
        mode = "simt" if rows == 1 and all(plan is None or plan.implementation == "simt" for plan in plans) else "mma"
        prepared = self.quantize_input(value.reshape(rows, width), error_flag=flag, _packed=mode == "mma")
        outputs = tuple(
            self.linear(
                value,
                weight_q,
                weight_scale,
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
                    }
                ),
            )
            for (weight_q, weight_scale), bias, plan in zip(weights, biases, plans)
        )
        self._finish(flag, error_flag)
        return outputs
