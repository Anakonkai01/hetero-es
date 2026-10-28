"""
SM120 B22 prefill projections whose operands arrive by TMA (the tensor memory accelerator) instead of cp.async.

Only the transport changes. The kernel body is the streamed projection of `integer_cuda._SOURCE`, derived from it
with a few checked text edits: the cp.async ring becomes bulk tensor copies that complete on shared-memory barriers.
The int8 radix-digit MMA products, the exact integer accumulation, the finish and the single final rounding are the
streamed projection's own code, so the result has the same bits (tested against the streamed route).

Tensor maps (128-byte descriptors of a tensor's address and layout, never of its values) are passed BY VALUE as kernel
parameters. `HostMapCache` keeps a few CPU templates keyed by layout; reuse only patches the address through the driver
(`cuTensorMapReplaceAddress`). cuLaunchKernel copies parameter bytes, so launches and captured graph nodes that reuse one
CPU buffer keep their own maps. A barrier that never completes within the bounded wait sets error bit 8, an
infrastructure failure (`StrictTransportError`), never an arithmetic result.

Measured gain and limits: docs/evidence/2026-10-27-strict-final-composed (whole-request ABAB on the 5070 Ti).
"""

from collections import OrderedDict
import ctypes

import numpy as np
import torch

from heteroes.strict import strict_cuda as sc

TRANSPORT_VERSION = "b22_prefill_tma_by_value_host_maps_v1"
TRANSPORT_TIMEOUT_BIT = 8
COLUMNS, STAGES, MIN_BLOCKS = 64, 2, 3  # the measured configuration (64 columns per CTA, 2 stages, 3 CTAs/SM)
MAX_ROWS = 65535 * 32

HELPERS = r"""
__device__ __forceinline__ unsigned tma_addr(const void* p) {
  unsigned long long address;
  asm volatile("cvta.to.shared.u64 %0,%1;" : "=l"(address) : "l"(p));
  return (unsigned)address;
}
__device__ __forceinline__ void tma_init(unsigned long long* barrier) {
  asm volatile("mbarrier.init.shared::cta.b64 [%0],1;" :: "r"(tma_addr(barrier)) : "memory");
}
__device__ __forceinline__ void tma_stage(unsigned char* sw,unsigned char* sa,const void* wd,const void* ad,
                                        unsigned long long* barrier,int k0,int column0,int first) {
  unsigned b=tma_addr(barrier);
  asm volatile("mbarrier.arrive.expect_tx.shared::cta.b64 _,[%0],%1;" :: "r"(b),"r"(W_STAGE+A_STAGE) : "memory");
  asm volatile("cp.async.bulk.tensor.2d.shared::cta.global.mbarrier::complete_tx::bytes [%0],[%1,{%2,%3}],[%4];"
      :: "r"(tma_addr(sw)),"l"(wd),"r"(k0),"r"(column0),"r"(b) : "memory");
  #pragma unroll
  for(int digit=0;digit<3;++digit)
    asm volatile("cp.async.bulk.tensor.3d.shared::cta.global.mbarrier::complete_tx::bytes [%0],[%1,{%2,%3,%4}],[%5];"
      :: "r"(tma_addr(sa+digit*MT*KS)),"l"(ad),"r"(k0),"r"(first),"r"(digit),"r"(b) : "memory");
}
__device__ __forceinline__ unsigned tma_wait(unsigned long long* barrier,unsigned phase) {
  unsigned ready=0,b=tma_addr(barrier);
  for(int attempt=0;attempt<100000 && !ready;++attempt)
    asm volatile("{ .reg .pred p; mbarrier.try_wait.parity.shared::cta.b64 p,[%1],%2; selp.u32 %0,1,0,p; }"
      : "=r"(ready) : "r"(b),"r"(phase) : "memory");
  return ready;
}
"""

ENTRY = r"""
#if STREAM_MIN_BLOCKS > 1
extern "C" __global__ void __launch_bounds__(128,STREAM_MIN_BLOCKS)
#else
extern "C" __global__ void __launch_bounds__(128)
#endif
tma_stream(const qi_t* x,const u16* w,const __grid_constant__ TensorMap128 wd,const __grid_constant__ TensorMap128 ad,const u16* bias,const int* ex,const int* ew,
           float* out,int* error,i64* partials,int rows,int outputs) {
  tma_stream_body(x,w,&wd,&ad,bias,ex,ew,out,error,partials,rows,outputs,blockIdx.x*NT,outputs,0);
}
"""


def _once(text, old, new):
    if text.count(old) != 1:
        raise AssertionError(f"TMA derivation expects exactly one {old[:60]!r}")
    return text.replace(old, new)


def _tma_body():
    """The streamed projection body with its cp.async transport replaced (every edit must match exactly once)."""
    from heteroes.strict import integer_cuda as ic

    start = ic._SOURCE.index("__device__ __forceinline__ void stream_body(")
    body = ic._SOURCE[start : ic._SOURCE.index("#if STREAM_MIN_BLOCKS > 1", start)]
    body = _once(body, "void stream_body(", "void tma_stream_body(")
    body = _once(
        body,
        "const qi_t* x,const u16* w,const u16* bias",
        "const qi_t* x,const u16* w,const void* wd,const void* ad,const u16* bias",
    )
    body = body.replace("__align__(16)", "__align__(1024)")  # TMA swizzled destinations need 1024-byte alignment
    body = _once(
        body,
        "  int lane=threadIdx.x&31,",
        "  __shared__ __align__(8) unsigned long long barriers[STAGES];\n  __shared__ int failed;\n  int lane=threadIdx.x&31,",
    )
    old = "    int accum[M_GROUPS][JN][2*DIGITS-1][4]={};"
    body = _once(
        body,
        old,
        old
        + r"""
    if(threadIdx.x==0) {
      failed=0;
      for(int s=0;s<STAGES;++s) tma_init(barriers+s);
      asm volatile("fence.proxy.async.shared::cta;" ::: "memory");
    }
    __syncthreads();
""",
    )
    body = _once(
        body,
        r"""    #pragma unroll
    for(int s=0;s<STAGES-1;++s) {
      if(s<count) stream_stage(weights_shared[s],inputs_shared[s],x,w,rows,outputs,first,column0,(begin+s)*KS);
      asm volatile("cp.async.commit_group;" ::: "memory");
    }""",
        r"""    if(threadIdx.x==0) for(int s=0;s<STAGES-1;++s)
      if(s<count) tma_stage(weights_shared[s],inputs_shared[s],wd,ad,barriers+s,(begin+s)*KS,column0,first);""",
    )
    body = _once(
        body,
        r"""      asm volatile("cp.async.wait_group %0;" :: "n"(STAGES-2) : "memory");
      __syncthreads();""",
        r"""      unsigned ready=tma_wait(barriers+it%STAGES,(it/STAGES)&1);
      if(!ready) atomicExch(&failed,1);
      __syncthreads();
      if(failed) {if(threadIdx.x==0) atomicOr(error,"""
        + str(TRANSPORT_TIMEOUT_BIT)
        + r""");return;}""",
    )
    body = _once(
        body,
        r"""      if(next<count) stream_stage(weights_shared[next%STAGES],inputs_shared[next%STAGES],x,w,rows,outputs,first,
                                  column0,(begin+next)*KS);
      asm volatile("cp.async.commit_group;" ::: "memory");""",
        r"""      if(threadIdx.x==0 && next<count)
        tma_stage(weights_shared[next%STAGES],inputs_shared[next%STAGES],wd,ad,barriers+next%STAGES,
                  (begin+next)*KS,column0,first);""",
    )
    body = _once(body, '    asm volatile("cp.async.wait_group 0;" ::: "memory");\n', "")
    # the hardware swizzle of the TMA copies replaces the software XOR patterns of the cp.async layout
    return body.replace("stream_weight_swizzle(r)", "(r&7)").replace("stream_input_swizzle(row)", "((row>>1)&3)")


def projection_source(width, columns, split, stages, min_blocks, has_bias):
    from heteroes.strict import integer_cuda as ic

    defines = {
        "WIDTH": width,
        "MAGNITUDE_BITS": 22,
        "DIGITS": 3,
        "HAS_BIAS": int(has_bias),
        "M_GROUPS": 2,
        "WARPS": 4,
        "SPLIT_K": split,
        "PACKED_INPUT": 1,
        "WEIGHT_READ32": 0,
        "WEIGHT_PREFETCH": 1,
        "FAST_CONVERT": 1,
        "STREAM_LDSM_INPUT": 1,
        "JN": columns // 32,
        "STAGES": stages,
        "STREAM_MIN_BLOCKS": min_blocks,
    }
    header = "".join(f"#define {k} {v}\n" for k, v in defines.items())
    return (
        "struct __align__(64) TensorMap128 { unsigned long long data[16]; };\n"
        + header
        + ic._SOURCE
        + HELPERS
        + _tma_body()
        + ENTRY
    )


def eligible(*, arch, magnitude_bits, rows, width, split_k, row_tile, implementation):
    """The route measured in the whole-request ABAB: SM120 B22 multi-row prefill, one K split, 32-row tiles."""
    return (
        arch == "sm_120"
        and magnitude_bits == 22
        and 128 < rows <= MAX_ROWS
        and width % 16 == 0
        and split_k == 1
        and row_tile in (None, 32)
        and implementation != "simt"
    )


class HostMapCache:
    """At most `capacity` CPU tensor-map templates keyed by layout; reuse patches only the address."""

    def __init__(self, kernels, capacity=16):
        self.driver, self.capacity, self.entries = kernels._driver, capacity, OrderedDict()
        self.encoded = self.patched = 0

    def get(self, value, dims, strides, box, element_bytes, swizzle):
        d, key = self.driver, (dims, strides, box, element_bytes, swizzle)
        entry = self.entries.pop(key, None)
        if entry is None:
            kind = getattr(d.CUtensorMapDataType, f"CU_TENSOR_MAP_DATA_TYPE_UINT{element_bytes * 8}")
            mode = getattr(d.CUtensorMapSwizzle, f"CU_TENSOR_MAP_SWIZZLE_{swizzle}B")
            descriptor = sc._check(
                d.cuTensorMapEncodeTiled(
                    kind,
                    len(dims),
                    value.data_ptr(),
                    tuple(d.cuuint64_t(v) for v in dims),
                    tuple(d.cuuint64_t(v) for v in strides),
                    tuple(d.cuuint32_t(v) for v in box),
                    tuple(d.cuuint32_t(1) for _ in box),
                    d.CUtensorMapInterleave.CU_TENSOR_MAP_INTERLEAVE_NONE,
                    mode,
                    d.CUtensorMapL2promotion.CU_TENSOR_MAP_L2_PROMOTION_NONE,
                    d.CUtensorMapFloatOOBfill.CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE,
                )
            )
            raw = np.empty(191, dtype=np.uint8)
            entry = descriptor, raw[(-raw.ctypes.data) % 64 :][:128]  # 64-byte aligned 128-byte parameter
            self.encoded += 1
        else:
            sc._check(d.cuTensorMapReplaceAddress(entry[0], value.data_ptr()))
            self.patched += 1
        self.entries[key] = entry
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
        descriptor, buffer = entry
        buffer[:] = np.frombuffer(ctypes.string_at(descriptor.getPtr(), 128), dtype=np.uint8)
        return buffer

    def maps(self, weight, planes, rows, width, columns):
        w = self.get(weight, (width, weight.shape[0]), (width * 2,), (64, columns), 2, 128)
        a = self.get(planes, (width, rows, 3), (width, width * rows), (64, 32, 1), 1, 64)
        return w, a


class TmaPrefill:
    """Compiled TMA projections of one `IntegerCudaKernels`, one per (K width, bias)."""

    def __init__(self, kernels):
        self.kernels, self.maps, self.functions = kernels, HostMapCache(kernels), {}

    def _compiled(self, width, has_bias):
        key = (width, has_bias)
        if key not in self.functions:
            name = f"tma-byvalue-v2-k{width}-n{COLUMNS}-s1-st{STAGES}-r{MIN_BLOCKS}-b{int(has_bias)}"
            self.functions[key] = self.kernels._compile(
                name,
                projection_source(width, COLUMNS, 1, STAGES, MIN_BLOCKS, has_bias),
                ["tma_stream"],
                sass_exact=("FENCE.VIEW.ASYNC.S",),  # the proxy fence orders barrier init before bulk copies
                integer_mma=True,
            )["tma_stream"]
        return self.functions[key]

    def project(self, prepared, weight, exponents, flag, bias=None):
        planes, ex = prepared
        rows, width, outputs = ex.numel(), weight.shape[1], weight.shape[0]
        function = self._compiled(width, bias is not None)
        wd, ad = self.maps.maps(weight, planes, rows, width, COLUMNS)
        out = torch.empty((rows, outputs), dtype=torch.float32, device=weight.device)
        b = weight if bias is None else bias
        tensors = (planes, weight, wd, ad, b, ex, exponents, out, flag, out)
        storage = [a if isinstance(a, np.ndarray) else np.array([a.data_ptr()], dtype=np.uint64) for a in tensors] + [
            np.array([rows], dtype=np.int32),
            np.array([outputs], dtype=np.int32),
        ]
        arguments = np.array([a.ctypes.data for a in storage], dtype=np.uint64)
        k = self.kernels
        with torch.cuda.device(k.device):
            sc._check(
                k._driver.cuLaunchKernel(
                    function,
                    -(-outputs // COLUMNS),
                    -(-rows // 32),
                    1,
                    128,
                    1,
                    1,
                    0,
                    torch.cuda.current_stream(k.device).cuda_stream,
                    arguments.ctypes.data,
                    0,
                )
            )
        return out
