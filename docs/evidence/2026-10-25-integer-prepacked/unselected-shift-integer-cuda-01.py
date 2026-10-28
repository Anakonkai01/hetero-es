"""Experimental NVRTC signed-integer MMA for the separately versioned row-scaled reference.

No quantized weight matrix is materialized. Live FP16 weights are quantized inside each MMA tile. Input
quantization is per call. Weight exponents are per call unless the locked graph adapter explicitly refreshes
them at request entry; retained buffers are cleared at exit. It is NOT the prior FP32-tree arithmetic.
"""

import hashlib
from pathlib import Path
import weakref

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_reference as reference
from heteroes.eval import integer_plan as planning
from heteroes.eval import strict_cuda as sc
from heteroes.eval.reference_ops import ReferenceArithmeticError

INTEGER_CUDA_VERSION = "row_scaled_integer_mma_cuda_v1_experimental"


def static_identity(magnitude_bits=14, max_partial_bytes=16 * 1024**2):
    reference._precision(magnitude_bits)
    if type(max_partial_bytes) is not int or max_partial_bytes < 1:
        raise ReferenceArithmeticError("Integer workspace budget must be a positive integer")
    return {
        "kernel": INTEGER_CUDA_VERSION,
        "linear": reference.identity(magnitude_bits),
        "nonlinear": sc.static_identity(),
        "integerSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "maxPartialBytes": max_partial_bytes,
        "activationPacking": "radix_planes_once_v1_experimental",
        "decodePlanning": planning.identity(),
        "hardwareQualified": False,
    }


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

__device__ __forceinline__ unsigned rne_shift(unsigned value, int shift) {
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
__device__ __forceinline__ int quant_half(u16 u, int exponent) {
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
__device__ __forceinline__ void pack_digits(unsigned* words, int q, int element) {
  #pragma unroll
  for(int d=0;d<DIGITS;++d) {
    words[d] |= ((unsigned)q&255u) << (8*element);
    // Balanced digit d=(q+128 mod 256)-128, so next=floor((q+128)/256).
    // q+128 is in int32 range; PTX signed shift defines floor for negatives without C++ shift assumptions.
    int next=q+128;
    asm("shr.s32 %0, %1, 8;" : "=r"(q) : "r"(next));
  }
}

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

__device__ __forceinline__ u64 rne64(u64 value, int shift) {
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

__device__ __forceinline__ void mma(int* c,const unsigned* a,const unsigned* b) {
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
  for(int first=blockIdx.y*(M_GROUPS*16);first<rows;first+=gridDim.y*(M_GROUPS*16)) {
    // Equal radix degrees share an int32 accumulator. At most three limb products contribute to a
    // degree: 3*128^2*32768 < 2^31, including every possible signed partial sum.
    int accum[M_GROUPS][2*DIGITS-1][4]={};
    for(int start=blockIdx.z*32;start<WIDTH;start+=SPLIT_K*32) {
      unsigned b[DIGITS][2]={};
      int n=column+group;
      int exponent=n<outputs ? ew[n] : 0;
      #pragma unroll
      for(int word=0;word<2;++word) {
        unsigned packed[DIGITS]={};
        #pragma unroll
        for(int i=0;i<4;++i) {
          int k=start+thread*4+word*16+i;
          int q=(n<outputs && k<WIDTH) ? quant_half(w[(size_t)n*WIDTH+k],exponent) : 0;
          pack_digits(packed,q,i);
        }
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
"""
)


class IntegerCudaKernels(sc.StrictCudaKernels):
    def __init__(self, device, *, magnitude_bits=14, max_partial_bytes=16 * 1024**2):
        reference._precision(magnitude_bits)
        if type(max_partial_bytes) is not int or max_partial_bytes < 1:
            raise ReferenceArithmeticError("Integer workspace budget must be a positive integer")
        super().__init__(device)
        if int(self.arch[3:]) < 80:
            raise ReferenceArithmeticError("Integer MMA prototype currently requires sm80 or newer")
        self.magnitude_bits = magnitude_bits
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
        for key, (target, _, exponents) in retained.items():
            self._refresh_weight_exponents(target(), exponents, flag)
        self.raise_if_error(flag)  # a bad scale may never be hidden by resetting a later decode flag
        self._request_active = True

    @torch.inference_mode()
    def _end_request(self):
        self._request_active = False
        for tensor in self.weight_metadata_buffers():
            tensor.zero_()

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
            **static_identity(self.magnitude_bits, self.max_partial_bytes),
            "integerKernel": INTEGER_CUDA_VERSION,
            "integerReference": reference.identity(self.magnitude_bits),
            "integerSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "maxPartialBytes": self.max_partial_bytes,
            "multiprocessors": self.multiprocessors,
            "hardwareQualified": False,
        }
        identity["fingerprint"] = canonical_json_hash({k: v for k, v in identity.items() if k != "fingerprint"})
        return identity

    def _integer_functions(self, width, has_bias=False, row_tile=16, warps=4, split_k=1, *, packed_input=False):
        name = f"integer-{self.magnitude_bits}-{width}-bias{int(has_bias)}-m{row_tile}-w{warps}-s{split_k}-p{int(packed_input)}"
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
            )
            header = "".join(f"#define {k} {v}\n" for k, v in defines.items())
            self._functions[name] = self._compile(
                name,
                header + _SOURCE,
                ["integer_input", "integer_weights", "integer_linear", "integer_simt", "integer_finish"],
                integer_mma=True,
            )
        return self._functions[name]

    @torch.inference_mode()
    def quantize_input(self, value, *, error_flag=None, _functions=None, _packed=False):
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
            torch.empty((2 if self.magnitude_bits == 14 else 3, value.shape[0], (value.shape[1]+3)//4), dtype=torch.int32, device=self.device)
            if _packed else torch.empty_like(value, dtype=torch.int16 if self.magnitude_bits == 14 else torch.int32)
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
    def linear_decode(self, value, weight, bias=None, *, error_flag=None, target_ctas_per_sm=8):
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
        )

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
    def linear_many(self, value, weights, biases=None, *, error_flag=None, decode_target_ctas_per_sm=None):
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
        prepared = self.quantize_input(value.reshape(rows, width), error_flag=flag, _packed=rows > 1)
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
                    }
                ),
            )
            for weight, bias, plan in zip(weights, biases, plans)
        )
        self._finish(flag, error_flag)
        return outputs

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
        if split_k > 1 and split_k * rows * outputs * 8 > self.max_partial_bytes:
            raise ReferenceArithmeticError("Integer split-K workspace budget exceeded")
        row_tile = (16 if rows <= 16 else 32) if row_tile is None else row_tile
        mode = ("simt" if rows == 1 else "mma") if implementation == "auto" else implementation
        functions = self._integer_functions(width, bias is not None, row_tile, warps, split_k, packed_input=mode == "mma")
        flag = self.new_error_flag() if error_flag is None else error_flag
        quantized, ex = (
            self.quantize_input(value.reshape(rows, width), error_flag=flag, _functions=functions, _packed=mode == "mma")
            if prepared is None
            else prepared
        )
        ew = self._weight_exponents(weight, flag)
        out = torch.empty((rows, outputs), dtype=torch.float32, device=self.device)
        partials = torch.empty((split_k, rows, outputs), dtype=torch.int64, device=self.device) if split_k > 1 else out
        self._launch(
            functions["integer_simt" if mode == "simt" else "integer_linear"],
            grid=(
                -(-outputs // (8 if mode == "simt" else warps * 8)),
                min(65535, rows if mode == "simt" else -(-rows // row_tile)),
                split_k,
            ),
            block=(256 if mode == "simt" else 32 * warps, 1),
            pointers=(quantized, weight, weight if bias is None else bias, ex, ew, out, flag, partials),
            integers=(rows, outputs),
        )
        if split_k > 1:
            self._launch(
                functions["integer_finish"],
                grid=(-(-outputs // 256), min(65535, rows)),
                block=(256, 1),
                pointers=(partials, weight if bias is None else bias, ex, ew, out, flag),
                integers=(rows, outputs),
            )
        self._finish(flag, error_flag)
        return out.reshape(*value.shape[:-1], outputs)
