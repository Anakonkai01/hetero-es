"""Experimental NVRTC kernels that execute the ADR-012 reference arithmetic faster (linear projection first).

The kernel must produce the same bits as ``reference_ops.linear``: FP16 weights widened exactly, separate
round-to-nearest FP32 multiply and add (inline PTX ``mul.rn.f32``/``add.rn.f32``, which the PTX ISA excludes
from multiply-add contraction), subnormal results flushed to signed zero by integer bit selection (no ``.ftz``),
and the reference adjacent-pair tree with odd-tail carry. That tree equals an aligned power-of-two tree padded
with -0.0, because x + (-0) == x for every finite x under round-to-nearest; +0 padding would turn -0 into +0.
Each thread reduces one aligned block, a warp combines lanes with an xor butterfly (adjacent aligned pairs,
addition is commutative), and warps combine through shared memory with the same padded tree.

Nonfinite inputs or intermediates always reach the corresponding output (inf/NaN propagate through products,
sums and the bias), so a device flag set from outputs reports the same failure the reference raises.

Every build records NVRTC version, options, architecture and binary hashes, and audits the PTX (and SASS when
Triton's ``nvdisasm`` is available) for contraction, flush modes and vendor arithmetic. This is NOT hardware
qualification; ``hardwareQualified`` stays false.
"""

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import reference_ops as ops
from heteroes.eval.reference_ops import ReferenceArithmeticError

KERNEL_VERSION = "pairwise_f32_cuda_linear_v3_experimental"
MAX_LINEAR_WIDTH = 32768
MAX_ATTENTION_KEYS = 4096
MAX_NORM_WIDTH = 8192
NVRTC_OPTIONS = ("--fmad=false", "--ftz=false", "--prec-div=true", "--prec-sqrt=true", "--std=c++17")

_LINEAR_SOURCE = r"""
typedef unsigned short u16;

__device__ __forceinline__ float flush(float v) {
  unsigned u = __float_as_uint(v);
  return (u & 0x7f800000u) == 0u ? __uint_as_float(u & 0x80000000u) : v;
}
__device__ __forceinline__ float add_rn(float a, float b) {
  float r;
  asm volatile("add.rn.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
  return flush(r);
}
__device__ __forceinline__ float mul_rn(float a, float b) {
  float r;
  asm volatile("mul.rn.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
  return flush(r);
}
__device__ __forceinline__ float widen(u16 h) {
  float r;
  asm("cvt.f32.f16 %0, %1;" : "=f"(r) : "h"(h));
  return r;
}

// One output column per group of 32*WARPS threads; thread t reduces elements [t*PER, (t+1)*PER).
extern "C" __global__ void __launch_bounds__(32 * WARPS * GROUPS)
strict_linear(const float* __restrict__ x, const u16* __restrict__ w, const u16* __restrict__ bias,
              float* __restrict__ out, int* __restrict__ error, int rows, int outputs) {
  const int t = threadIdx.x, lane = t & 31, warp = t >> 5;
  const int o = blockIdx.x * GROUPS + threadIdx.y;
  const bool live = o < outputs;
  const int start = t * PER;
  __shared__ float partial[GROUPS][ROW_TILE][PADDED_WARPS];
  float weight[PER];
#if STAGE_WEIGHTS
  // Global reads are consecutive across lanes; padding removes shared-memory bank conflicts on blocked reads.
  __shared__ float staged[GROUPS][32 * WARPS][PER + 1];
  for (int p = t; p < WIDTH; p += 32 * WARPS)
    staged[threadIdx.y][p / PER][p % PER] = live ? widen(w[(size_t)o * WIDTH + p]) : 0.0f;
  __syncthreads();
#endif
#pragma unroll
  for (int i = 0; i < PER; ++i) {
    const int k = start + i;
#if STAGE_WEIGHTS
    weight[i] = (live && k < WIDTH) ? staged[threadIdx.y][t][i] : 0.0f;
#else
    weight[i] = (live && k < WIDTH) ? widen(w[(size_t)o * WIDTH + k]) : 0.0f;
#endif
  }
  float b = 0.0f;
  if (HAS_BIAS && live) b = widen(bias[o]);
  // Independent row trees share the same widened weights. Blocks run row tiles concurrently; the grid-stride
  // loop also supports more tiles than CUDA's y dimension. No reduction ever combines different rows.
  for (int first = blockIdx.y * ROW_TILE; first < rows; first += gridDim.y * ROW_TILE) {
    float stack[ROW_TILE][LOG_PER + 1];
#if STAGE_WEIGHTS
    __syncthreads();  // all widened weights are now in registers; reuse the first shared plane for activations
#pragma unroll
    for (int r = 0; r < ROW_TILE; ++r) {
      const int m = first + r;
      if (threadIdx.y == 0) {
        for (int p = t; p < WIDTH; p += 32 * WARPS)
          staged[0][p / PER][p % PER] = m < rows ? x[(size_t)m * WIDTH + p] : -0.0f;
      }
      __syncthreads();
#pragma unroll
      for (int i = 0; i < PER; ++i) {
        const int k = start + i;
        float v = (live && m < rows && k < WIDTH) ? mul_rn(flush(staged[0][t][i]), weight[i]) : -0.0f;
        int level = 0;
#pragma unroll
        for (; level < LOG_PER && ((i >> level) & 1); ++level) v = add_rn(stack[r][level], v);
        stack[r][level] = v;
      }
      __syncthreads();
    }
#else
#pragma unroll
    for (int i = 0; i < PER; ++i) {
      const int k = start + i;
#pragma unroll
      for (int r = 0; r < ROW_TILE; ++r) {
        const int m = first + r;
        float v = (live && m < rows && k < WIDTH) ? mul_rn(flush(x[(size_t)m * WIDTH + k]), weight[i]) : -0.0f;
        int level = 0;
#pragma unroll
        for (; level < LOG_PER && ((i >> level) & 1); ++level) v = add_rn(stack[r][level], v);
        stack[r][level] = v;
      }
    }
#endif
    float v[ROW_TILE];
#pragma unroll
    for (int r = 0; r < ROW_TILE; ++r) {
      v[r] = stack[r][LOG_PER];
#pragma unroll
      for (int offset = 1; offset < 32; offset <<= 1) v[r] = add_rn(v[r], __shfl_xor_sync(0xffffffffu, v[r], offset));
    }
    if (PADDED_WARPS > 1) {
#pragma unroll
      for (int r = 0; r < ROW_TILE; ++r) {
        if (lane == 0) partial[threadIdx.y][r][warp] = v[r];
      }
      __syncthreads();
      if (t == 0) {
#pragma unroll
        for (int r = 0; r < ROW_TILE; ++r) {
          float s[LOG_WARPS + 1];
#pragma unroll
          for (int i = 0; i < PADDED_WARPS; ++i) {
            float u = i < WARPS ? partial[threadIdx.y][r][i] : -0.0f;
            int level = 0;
#pragma unroll
            for (; level < LOG_WARPS && ((i >> level) & 1); ++level) u = add_rn(s[level], u);
            s[level] = u;
          }
          v[r] = s[LOG_WARPS];
        }
      }
      __syncthreads();
    }
    if (t == 0 && live) {
#pragma unroll
      for (int r = 0; r < ROW_TILE; ++r) {
        const int m = first + r;
        if (m < rows) {
          if (HAS_BIAS) v[r] = add_rn(v[r], b);
          out[(size_t)m * outputs + o] = v[r];
          if ((__float_as_uint(v[r]) & 0x7f800000u) == 0x7f800000u) atomicOr(error, 1);
        }
      }
    }
  }
}
"""

_OPS_SOURCE = r"""
typedef unsigned short u16;
#define FLT_BIG 3.4028234663852886e+38f

__device__ __forceinline__ float flush(float v) {
  unsigned u = __float_as_uint(v);
  return (u & 0x7f800000u) == 0u ? __uint_as_float(u & 0x80000000u) : v;
}
__device__ __forceinline__ void note(float v, unsigned& bad) {
  if ((__float_as_uint(v) & 0x7f800000u) == 0x7f800000u) bad |= 1u;
}
__device__ __forceinline__ float add_(float a, float b, unsigned& bad) {
  float r;
  asm volatile("add.rn.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
  r = flush(r);
  note(r, bad);
  return r;
}
__device__ __forceinline__ float mul_(float a, float b, unsigned& bad) {
  float r;
  asm volatile("mul.rn.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
  r = flush(r);
  note(r, bad);
  return r;
}
__device__ __forceinline__ float load(const float* p, unsigned& bad) {
  float v = flush(*p);
  note(v, bad);
  return v;
}
__device__ __forceinline__ float widen(u16 h) {
  float r;
  asm("cvt.f32.f16 %0, %1;" : "=f"(r) : "h"(h));
  return r;
}
__device__ __forceinline__ float k(unsigned bits) { return __uint_as_float(bits); }

// Domain [1e-30, 1e30]; outside it the reference raises, here bit 2 is set.
__device__ __forceinline__ void domain(float v, unsigned& bad) {
  if (!(v >= k(DOMAIN_LOW) && v <= k(DOMAIN_HIGH))) bad |= 2u;
}
__device__ float reciprocal_(float x, unsigned& bad) {
  domain(x, bad);
  float r = __int_as_float(0x7EF311C3 - __float_as_int(x));
#pragma unroll
  for (int i = 0; i < 5; ++i) r = mul_(r, add_(2.0f, -mul_(x, r, bad), bad), bad);
  return r;
}
__device__ float rsqrt_(float x, unsigned& bad) {
  domain(x, bad);
  float r = __int_as_float(0x5F3759DF - (__float_as_int(x) >> 1));
#pragma unroll
  for (int i = 0; i < 6; ++i) {
    float square = mul_(r, r, bad);
    r = mul_(mul_(0.5f, r, bad), add_(3.0f, -mul_(x, square, bad), bad), bad);
  }
  return r;
}
__device__ float exp_(float x, unsigned& bad) {
  if (x > 80.0f) bad |= 2u;
  float clipped = x < -80.0f ? -80.0f : x;
  int power = (int)floorf(add_(mul_(clipped, k(LOG2E), bad), 0.5f, bad));
  float exponent = (float)power;
  float remainder = add_(clipped, -mul_(exponent, k(LN2_HI), bad), bad);
  remainder = add_(remainder, -mul_(exponent, k(LN2_LO), bad), bad);
  float p = k(EXP_C0);
  p = add_(mul_(p, remainder, bad), k(EXP_C1), bad);
  p = add_(mul_(p, remainder, bad), k(EXP_C2), bad);
  p = add_(mul_(p, remainder, bad), k(EXP_C3), bad);
  p = add_(mul_(p, remainder, bad), k(EXP_C4), bad);
  p = add_(mul_(p, remainder, bad), k(EXP_C5), bad);
  p = add_(mul_(p, remainder, bad), k(EXP_C6), bad);
  p = add_(mul_(p, remainder, bad), k(EXP_C7), bad);
  p = add_(mul_(p, remainder, bad), k(EXP_C8), bad);
  float result = mul_(p, __int_as_float((power + 127) << 23), bad);
  return x < -80.0f ? 0.0f : result;
}
__device__ float silu_(float x, unsigned& bad) {
  float small = exp_(-fabsf(x), bad);
  float denominator = reciprocal_(add_(1.0f, small, bad), bad);
  float positive = mul_(x, denominator, bad);
  float negative = mul_(mul_(x, small, bad), denominator, bad);
  return x >= 0.0f ? positive : negative;
}

// Binary-counter reduction in input order; finish() folds pending nodes from the lowest set bit upward.
struct Tree {
  float s[17];
  unsigned n;
};
__device__ __forceinline__ void push(Tree& t, float v, unsigned& bad) {
  unsigned i = t.n++;
  int level = 0;
  while ((i >> level) & 1u) {
    v = add_(t.s[level], v, bad);
    ++level;
  }
  t.s[level] = v;
}
__device__ __forceinline__ float finish(const Tree& t, unsigned& bad) {
  float acc = 0.0f;
  bool any = false;
  for (int level = 0; level < 17; ++level) {
    if ((t.n >> level) & 1u) {
      acc = any ? add_(t.s[level], acc, bad) : t.s[level];
      any = true;
    }
  }
  return acc;
}
// In-place aligned tree over a[0..n): level stride s adds a[i+s] into a[i] for i a multiple of 2s.
// Within a level no slot is both written and read by different threads; levels are barrier-separated.
__device__ void block_tree(float* a, int n, unsigned& bad) {
  for (int stride = 1; stride < n; stride <<= 1) {
    for (int i = threadIdx.x * 2 * stride; i < n; i += blockDim.x * 2 * stride)
      if (i + stride < n) a[i] = add_(a[i], a[i + stride], bad);
    __syncthreads();
  }
}
__device__ __forceinline__ void report(int* error, unsigned bad) {
  if (bad) atomicOr(error, (int)bad);
}

extern "C" __global__ void strict_rms_norm(const float* x, const u16* w, float* out, int* error, int rows, int n,
                                           float inv_n, float eps) {
  extern __shared__ float a[];
  unsigned bad = 0;
  const float* row = x + (size_t)blockIdx.x * n;
  for (int i = threadIdx.x; i < n; i += blockDim.x) {
    float v = load(row + i, bad);
    a[i] = mul_(v, v, bad);
  }
  __syncthreads();
  block_tree(a, n, bad);
  float inverse = rsqrt_(add_(mul_(a[0], inv_n, bad), eps, bad), bad);
  for (int i = threadIdx.x; i < n; i += blockDim.x)
    out[(size_t)blockIdx.x * n + i] = mul_(mul_(load(row + i, bad), inverse, bad), widen(w[i]), bad);
  report(error, bad);
}

extern "C" __global__ void strict_add(const float* a, const float* b, float* out, int* error, int count) {
  unsigned bad = 0;
  int i = blockIdx.x * blockDim.x + threadIdx.x;
  if (i < count) out[i] = add_(load(a + i, bad), load(b + i, bad), bad);
  report(error, bad);
}

extern "C" __global__ void strict_silu_mul(const float* gate, const float* up, float* out, int* error, int count) {
  unsigned bad = 0;
  int i = blockIdx.x * blockDim.x + threadIdx.x;
  if (i < count) out[i] = mul_(silu_(load(gate + i, bad), bad), load(up + i, bad), bad);
  report(error, bad);
}

// x: [length, heads*dim] projection output; out: [heads, length, dim]; cos/sin: [length, dim].
// Grid (length, heads), one thread per channel: no runtime integer division (ptxas lowers it with MUFU.RCP).
extern "C" __global__ void strict_rope(const float* x, const float* cosine, const float* sine, float* out, int* error,
                                       int length, int heads, int dim) {
  unsigned bad = 0;
  const int l = blockIdx.x, h = blockIdx.y, d = threadIdx.x, half = dim >> 1;
  if (d < dim) {
    const float* row = x + (size_t)l * heads * dim + h * dim;
    float value = load(row + d, bad);
    float rotated = d < half ? -load(row + d + half, bad) : load(row + d - half, bad);
    float c = load(cosine + l * dim + d, bad), s = load(sine + l * dim + d, bad);
    out[((size_t)h * length + l) * dim + d] = add_(mul_(value, c, bad), mul_(rotated, s, bad), bad);
  }
  report(error, bad);
}

// Grid (query, kv head, repeat). q: [heads, length, dim]; k/v: [kv_heads, keys, dim]; out: [length, heads*dim].
extern "C" __global__ void strict_attention(const float* q, const float* key, const float* value, float* out,
                                            int* error, const int* ranges, int heads, int length, int total_keys,
                                            int past, int repeats, int dim, int packed, float scale) {
  const int i = blockIdx.x, kv = blockIdx.y, h = kv * repeats + blockIdx.z;
  const int start = packed ? ranges[3 * i] : 0;
  const int keys = packed ? ranges[3 * i + 1] : total_keys;
  const int limit = packed ? ranges[3 * i + 2] : past + i;
  extern __shared__ float shared[];
  float* query = shared;
  float* numerators = shared + dim;
  float* tree = numerators + keys;
  __shared__ float maxima[32];
  unsigned bad = 0;
  for (int d = threadIdx.x; d < dim; d += blockDim.x) query[d] = load(q + ((size_t)h * length + i) * dim + d, bad);
  __syncthreads();
  float local = -FLT_BIG;
  for (int j = threadIdx.x; j < keys; j += blockDim.x) {
    const float* row = key + ((size_t)kv * total_keys + start + j) * dim;
    Tree t;
    t.n = 0;
    for (int d = 0; d < dim; ++d) push(t, mul_(query[d], load(row + d, bad), bad), bad);
    float score = mul_(finish(t, bad), scale, bad);
    numerators[j] = score;
    if (j <= limit && score > local) local = score;
  }
  for (int offset = 16; offset >= 1; offset >>= 1) {
    float other = __shfl_xor_sync(0xffffffffu, local, offset);
    local = other > local ? other : local;
  }
  if ((threadIdx.x & 31) == 0) maxima[threadIdx.x >> 5] = local;
  __syncthreads();
  float maximum = -FLT_BIG;
  for (int w = 0; w < (int)(blockDim.x + 31) / 32; ++w) maximum = maxima[w] > maximum ? maxima[w] : maximum;
  if (__float_as_uint(maximum) == 0x80000000u) maximum = 0.0f;  // the reference maps a -0 maximum to +0
  for (int j = threadIdx.x; j < keys; j += blockDim.x) {
    bool allowed = j <= limit;
    float shifted = add_(allowed ? numerators[j] : maximum, -maximum, bad);
    float e = exp_(shifted, bad);
    float n = allowed ? e : 0.0f;
    numerators[j] = n;
    tree[j] = n;
  }
  __syncthreads();
  block_tree(tree, keys, bad);
  float denominator = tree[0];
  float inverse = reciprocal_(denominator == 0.0f ? 1.0f : denominator, bad);
  for (int j = threadIdx.x; j < keys; j += blockDim.x) numerators[j] = mul_(numerators[j], inverse, bad);
  __syncthreads();
  for (int d = threadIdx.x; d < dim; d += blockDim.x) {
    Tree t;
    t.n = 0;
    for (int j = 0; j < keys; ++j) push(t, mul_(numerators[j], load(value + ((size_t)kv * total_keys + start + j) * dim + d, bad), bad), bad);
    out[(size_t)i * heads * dim + h * dim + d] = finish(t, bad);
  }
  report(error, bad);
}
"""


@dataclass(frozen=True)
class LinearPlan:
    width: int
    padded: int
    per_thread: int
    warps: int
    padded_warps: int
    outputs_per_block: int


@dataclass(frozen=True)
class _PackedAttentionLayout:
    ranges: torch.Tensor
    queries: int
    keys: int
    max_keys: int


def linear_plan(width):
    if type(width) is not int or not 1 <= width <= MAX_LINEAR_WIDTH:
        raise ReferenceArithmeticError(f"Strict CUDA linear supports input widths 1..{MAX_LINEAR_WIDTH}")
    padded = 1 << (width - 1).bit_length()
    per_thread = max(1, min(32, padded // 32))
    padded_warps = max(1, padded // (32 * per_thread))
    warps = -(-width // (32 * per_thread))
    return LinearPlan(width, padded, per_thread, warps, padded_warps, max(1, 8 // warps))


def linear_execution_plan(width, rows):
    """Select independent work decomposition by matrix dimensions; the arithmetic tree stays fixed.

    Smaller per-thread subtrees expose more K parallelism and reduce shared memory per output group.
    Keep the original wide path. Both decompositions use the same signed-zero padding and rounded
    primitives; this selects no model-specific arithmetic or checkpoint identity.
    """
    plan = linear_plan(width)
    if type(rows) is not int or rows < 1:
        raise ReferenceArithmeticError("Strict linear needs a positive integer row count")
    if 512 <= width <= 8192:
        per_thread = 8 if rows > 1 and width <= 1024 else 16
        warps = -(-width // (32 * per_thread))
        padded_warps = 1 << (warps - 1).bit_length()
        plan = LinearPlan(width, plan.padded, per_thread, warps, padded_warps, max(1, 8 // warps))
    return plan, 1 if rows == 1 else 4 if rows < 8 else 8


def _binary_counter_tree(blocks):
    """Reduce the last dimension (a power of two) in input order exactly as the kernel's register stack does."""
    count = blocks.shape[-1]
    stack = [None] * count.bit_length()
    for i in range(count):
        value = blocks[..., i]
        level = 0
        while (i >> level) & 1:
            value = ops.add(stack[level], value)
            level += 1
        stack[level] = value
    return stack[count.bit_length() - 1]


def emulate_running_sum(values):
    """CPU emulation of the kernels' runtime-length reduction: binary-counter stack, then fold low to high."""
    values = ops._normal(values)
    count = values.shape[-1]
    stack = [None] * (count.bit_length() + 1)
    for i in range(count):
        value, level = values[..., i], 0
        while (i >> level) & 1:
            value = ops.add(stack[level], value)
            level += 1
        stack[level] = value
    total = None
    for level in range(count.bit_length()):
        if (count >> level) & 1:
            total = stack[level] if total is None else ops.add(stack[level], total)
    return total


def _f32_bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def reference_constants():
    """Float32 bit patterns of the Python constants that reference_ops rounds when it builds tensors."""
    coefficients = (1.0 / 40320.0, 1.0 / 5040.0, 1.0 / 720.0, 1.0 / 120.0, 1.0 / 24.0, 1.0 / 6.0, 0.5, 1.0, 1.0)
    constants = {
        "LOG2E": _f32_bits(1.4426950408889634),
        "LN2_HI": _f32_bits(0.693145751953125),
        "LN2_LO": _f32_bits(0.000001428606765330187),
        "DOMAIN_LOW": _f32_bits(1e-30),
        "DOMAIN_HIGH": _f32_bits(1e30),
    }
    constants.update({f"EXP_C{i}": _f32_bits(c) for i, c in enumerate(coefficients)})
    return constants


def emulate_blocked_sum(rows, plan):
    """CPU emulation of the kernel decomposition: thread blocks, xor butterfly, padded warp tree."""
    rows = ops._normal(rows)
    lanes = 32 * plan.padded_warps
    padded = torch.full((*rows.shape[:-1], lanes * plan.per_thread), -0.0)
    padded[..., : plan.width] = rows
    blocks = padded.reshape(*rows.shape[:-1], plan.padded_warps, 32, plan.per_thread)
    value = _binary_counter_tree(blocks)
    lane = torch.arange(32)
    offset = 1
    while offset < 32:
        value = ops.add(value, value[..., lane ^ offset])
        offset <<= 1
    warp_values = value[..., 0]
    warp_values[..., plan.warps :] = -0.0  # never launched; the kernel substitutes -0.0
    return _binary_counter_tree(warp_values)


_FLOAT_TYPE = re.compile(r"\.(?:f16|f16x2|bf16|bf16x2|tf32|f32|f64|e4m3x2|e5m2x2)\b")
_PTX_COUNTED = ("add.rn.f32", "mul.rn.f32")
_PTX_EXACT = ("cvt.f32.f16", "neg.f32", "abs.f32", "selp.f32")
_PTX_EXACT_PREFIX = ("ld.", "st.", "mov.", "shfl.")
# Ordered/unordered comparisons are exact; the compiler rewrites integer exponent tests into them.
_PTX_COMPARE = re.compile(r"^setp\.(?:eq|ne|lt|le|gt|ge|equ|neu|ltu|leu|gtu|geu|num|nan)\.f32$")


# Exact on the domains the fused operations admit: floor, truncation of an integral value, int->float for
# |n| < 2^24 (exponents/positions) and comparisons/selection used by max and clamp.
OPS_PTX_EXACT = ("cvt.rmi.f32.f32", "cvt.rzi.s32.f32", "cvt.rn.f32.s32", "max.f32", "min.f32")
OPS_SASS_EXACT = ("FRND.FLOOR", "F2I.FLOOR.NTZ", "F2I.TRUNC.NTZ", "I2FP.F32.S32", "I2F", "FMNMX", "FMNMX.NAN")


def audit_ptx(text, exact=()):
    """Every floating instruction must be a counted rounded add/mul or an exact data movement/conversion."""
    counts, violations = {}, []
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line or line.startswith((".", "{", "}", "$")):
            continue
        tokens = line.split()
        if tokens[0].startswith("@"):
            tokens = tokens[1:]
        opcode = tokens[0] if tokens else ""
        if not _FLOAT_TYPE.search(opcode):
            continue
        if opcode in _PTX_COUNTED:
            counts[opcode] = counts.get(opcode, 0) + 1
        elif ".ftz" in opcode or not (
            opcode in _PTX_EXACT
            or opcode in exact
            or opcode.startswith(_PTX_EXACT_PREFIX)
            or _PTX_COMPARE.match(opcode)
        ):
            violations.append(line)
    return {"floatOps": counts, "violations": violations}


_SASS_FLOAT = re.compile(r"^(?:F[A-Z0-9]*|H[A-Z0-9]+|D(?:ADD|MUL|FMA|MNMX|SET|SETP)|MUFU|I2F|I2FP|F2I|F2F|F2FP)$")
_SASS_COUNTED = {"FADD": "FADD", "FADD32I": "FADD", "FMUL": "FMUL", "FMUL32I": "FMUL"}
_SASS_EXACT = ("HADD2.F32", "FSEL")
_SASS_NOT_FLOAT = ("FLO",)  # find-leading-one is an integer instruction
_SASS_COMPARE = re.compile(r"^FSETP\.(?:EQ|NE|LT|LE|GT|GE|EQU|NEU|LTU|LEU|GTU|GEU|NUM|NAN)\.(?:AND|OR|XOR)$")
# ptxas materializes immediates as (-0)*(+0) + constant, which returns the constant bits exactly.
_SASS_CONSTANT = re.compile(r"^HFMA2(?:\.MMA)? R\d+, -RZ, RZ, [^,]+, [^,;]+ ;?$")


def audit_sass(text, exact=()):
    counts, violations = {}, []
    for raw in text.splitlines():
        line = raw.split("*/", 1)[1].strip() if "*/" in raw else raw.strip()
        tokens = line.split()
        if tokens and tokens[0].startswith("@"):
            tokens = tokens[1:]
        if not tokens:
            continue
        opcode = tokens[0]
        base = opcode.split(".", 1)[0]
        if base in _SASS_NOT_FLOAT or not _SASS_FLOAT.match(base):
            continue
        if opcode in _SASS_COUNTED:
            counts[_SASS_COUNTED[opcode]] = counts.get(_SASS_COUNTED[opcode], 0) + 1
        elif not (
            opcode in _SASS_EXACT or opcode in exact or _SASS_COMPARE.match(opcode) or _SASS_CONSTANT.match(line)
        ):
            violations.append(line)
    return {"floatOps": counts, "violations": violations}


def audit_integer_ptx(text):
    """Integer projections admit signed int8 MMA and rounded bias add, never floating dot/multiply."""
    result = audit_ptx(text, exact=("cvt.rni.s32.f32",))
    result["integerMmaOps"] = len(re.findall(r"\bmma\.sync\.aligned\.m16n8k32\.row\.col\.s32\.s8\.s8\.s32\s", text))
    if not result["integerMmaOps"]:
        result["violations"].append("Missing signed integer m16n8k32 MMA")
    if result["floatOps"].get("mul.rn.f32", 0):
        result["violations"].append("Floating multiply in integer projection")
    return result


def audit_integer_sass(text):
    result = audit_sass(text, exact=("F2I.NTZ", "F2I.RN.NTZ", "F2I.RN"))
    result["integerMmaOps"] = len(re.findall(r"\bIMMA(?:\.[A-Z0-9_]+)*\s", text))
    if not result["integerMmaOps"]:
        result["violations"].append("Missing integer IMMA")
    if result["floatOps"].get("FMUL", 0):
        result["violations"].append("Floating multiply in integer projection")
    return result


def static_identity():
    source = Path(__file__).read_bytes() + Path(ops.__file__).read_bytes()
    return {
        "kernel": KERNEL_VERSION,
        "operators": ops.REFERENCE_OPS_VERSION,
        "sourceSha256": hashlib.sha256(source).hexdigest(),
        "nvrtcOptions": list(NVRTC_OPTIONS),
        "hardwareQualified": False,
    }


def validate_linear(value, weight, bias, *, device):
    """Shape/dtype/device checks, mirrored from the reference; returns (rows, width, outputs) without CUDA access."""
    if (
        not isinstance(value, torch.Tensor)
        or not isinstance(weight, torch.Tensor)
        or not value.is_floating_point()
        or weight.dtype != torch.float16
        or weight.ndim != 2
        or not weight.is_contiguous()
        or value.ndim < 1
        or value.shape[-1] != weight.shape[-1]
        or weight.shape[0] < 1
        or weight.shape[1] < 1
        or value.numel() == 0
    ):
        raise ReferenceArithmeticError("Unsupported strict linear dtype, layout or shape")
    if bias is not None and (
        not isinstance(bias, torch.Tensor)
        or bias.dtype != torch.float16
        or bias.shape != (weight.shape[0],)
        or not bias.is_contiguous()
    ):
        raise ReferenceArithmeticError("Strict linear bias must be contiguous FP16 with one value per output")
    if any(t.device != device for t in (value, weight, *(() if bias is None else (bias,)))):
        raise ReferenceArithmeticError("Strict linear tensors must be on the kernel device")
    linear_plan(weight.shape[1])
    return value.numel() // value.shape[-1], weight.shape[1], weight.shape[0]


def _check(result):
    status, *values = result
    if int(status) != 0:
        raise ReferenceArithmeticError(f"CUDA/NVRTC call failed: {status!r}")
    return values[0] if len(values) == 1 else values


def _find_nvdisasm():
    found = shutil.which("nvdisasm")
    if found:
        return found
    try:
        import triton

        candidate = Path(triton.__file__).parent / "backends" / "nvidia" / "bin" / "nvdisasm"
        return str(candidate) if candidate.is_file() else None
    except Exception:
        return None


class StrictCudaKernels:
    """Compiles and launches audited kernels on ONE CUDA device; the acceptance guard runs first."""

    def __init__(self, device):
        if os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
            raise ReferenceArithmeticError("Strict CUDA kernels need HETEROES_GPU_ACCEPTANCE=1")
        device = torch.device(device)
        if device.type != "cuda":
            raise ReferenceArithmeticError("Strict CUDA kernels need a CUDA device")
        from cuda.bindings import driver, nvrtc

        self._driver, self._nvrtc = driver, nvrtc
        self.device = torch.device("cuda", device.index if device.index is not None else torch.cuda.current_device())
        major, minor = torch.cuda.get_device_capability(self.device)
        self.arch = f"sm_{major}{minor}"
        self.nvrtc_version = list(_check(nvrtc.nvrtcVersion()))
        self._nvdisasm = _find_nvdisasm()
        self._functions, self._modules, self._builds = {}, [], {}

    def identity(self):
        identity = {
            **static_identity(),
            "arch": self.arch,
            "gpu": torch.cuda.get_device_name(self.device),
            "nvrtcVersion": self.nvrtc_version,
            "builds": dict(sorted(self._builds.items())),
        }
        identity["fingerprint"] = canonical_json_hash(identity)
        return identity

    def _compile(self, name, source, entries, *, ptx_exact=(), sass_exact=(), integer_mma=False):
        nvrtc = self._nvrtc
        program = _check(nvrtc.nvrtcCreateProgram(source.encode(), f"{name}.cu".encode(), 0, [], []))
        options = [f"--gpu-architecture={self.arch}".encode(), *(o.encode() for o in NVRTC_OPTIONS)]
        try:
            status = nvrtc.nvrtcCompileProgram(program, len(options), options)[0]
            if int(status) != 0:
                size = _check(nvrtc.nvrtcGetProgramLogSize(program))
                log = b" " * size
                nvrtc.nvrtcGetProgramLog(program, log)
                raise ReferenceArithmeticError(f"Strict kernel compilation failed: {log.decode(errors='replace')}")
            ptx = b" " * _check(nvrtc.nvrtcGetPTXSize(program))
            _check(nvrtc.nvrtcGetPTX(program, ptx))
            cubin = b" " * _check(nvrtc.nvrtcGetCUBINSize(program))
            _check(nvrtc.nvrtcGetCUBIN(program, cubin))
        finally:
            nvrtc.nvrtcDestroyProgram(program)
        ptx_text = ptx.rstrip(b"\0").decode()
        ptx_audit = audit_integer_ptx(ptx_text) if integer_mma else audit_ptx(ptx_text, ptx_exact)
        sass_audit = self._audit_cubin(cubin, sass_exact, integer_mma=integer_mma)
        violations = ptx_audit["violations"] + ([] if sass_audit == "unavailable" else sass_audit["violations"])
        if violations:
            raise ReferenceArithmeticError(f"Compiled strict kernel failed its instruction audit: {violations[:5]}")
        with torch.cuda.device(self.device):
            torch.cuda.init()
            module = _check(self._driver.cuModuleLoadData(cubin))
            functions = {e: _check(self._driver.cuModuleGetFunction(module, e.encode())) for e in entries}
        self._modules.append(module)
        self._builds[name] = {
            "sourceSha256": hashlib.sha256(source.encode()).hexdigest(),
            "ptxSha256": hashlib.sha256(ptx_text.encode()).hexdigest(),
            "cubinSha256": hashlib.sha256(cubin).hexdigest(),
            "ptxAudit": ptx_audit,
            "sassAudit": sass_audit,
        }
        return functions

    def _audit_cubin(self, cubin, exact=(), *, integer_mma=False):
        if not self._nvdisasm:
            return "unavailable"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel.cubin"
            path.write_bytes(cubin)
            result = subprocess.run([self._nvdisasm, str(path)], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return "unavailable"
        return audit_integer_sass(result.stdout) if integer_mma else audit_sass(result.stdout, exact)

    def _linear_function(self, plan, has_bias, row_tile):
        name = f"linear-{plan.width}-{'bias' if has_bias else 'nobias'}"
        if plan.per_thread != linear_plan(plan.width).per_thread:
            name += f"-per{plan.per_thread}"
        if row_tile != 1:
            name += f"-rows{row_tile}"
        if name not in self._functions:
            defines = {
                "WIDTH": plan.width,
                "PER": plan.per_thread,
                "LOG_PER": plan.per_thread.bit_length() - 1,
                "WARPS": plan.warps,
                "PADDED_WARPS": plan.padded_warps,
                "LOG_WARPS": plan.padded_warps.bit_length() - 1,
                "GROUPS": plan.outputs_per_block,
                "HAS_BIAS": int(has_bias),
                "ROW_TILE": row_tile,
                "STAGE_WEIGHTS": int(plan.outputs_per_block * 32 * plan.warps * (plan.per_thread + 1) * 4 <= 40 * 1024),
            }
            header = "".join(f"#define {k} {v}\n" for k, v in defines.items())
            self._functions[name] = self._compile(name, header + _LINEAR_SOURCE, ["strict_linear"])["strict_linear"]
        return self._functions[name]

    def new_error_flag(self):
        return torch.zeros(1, dtype=torch.int32, device=self.device)

    @staticmethod
    def raise_if_error(flag):
        status = int(flag.item())
        if status & 1:
            raise ReferenceArithmeticError("Nonfinite reference arithmetic")
        if status:
            raise ReferenceArithmeticError("Reference reciprocal/root/exp domain failure")

    def _ops(self, entry):
        if "ops" not in self._functions:
            header = "".join(f"#define {k} 0x{v:08x}u\n" for k, v in reference_constants().items())
            self._functions["ops"] = self._compile(
                "ops",
                header + _OPS_SOURCE,
                ["strict_rms_norm", "strict_add", "strict_silu_mul", "strict_rope", "strict_attention"],
                ptx_exact=OPS_PTX_EXACT,
                sass_exact=OPS_SASS_EXACT,
            )
        return self._functions["ops"][entry]

    def _float32(self, *tensors):
        for t in tensors:
            if not isinstance(t, torch.Tensor) or t.dtype != torch.float32 or t.device != self.device or not t.numel():
                raise ReferenceArithmeticError(
                    "Strict fused operations take nonempty FP32 tensors on the kernel device"
                )
        return [t.contiguous() for t in tensors]

    def _finish(self, flag, error_flag):
        if error_flag is None:
            self.raise_if_error(flag)

    @torch.inference_mode()
    def rms_norm(self, value, weight, epsilon, *, error_flag=None):
        (value,) = self._float32(value)
        width = value.shape[-1]
        if (
            not isinstance(weight, torch.Tensor)
            or weight.dtype != torch.float16
            or weight.shape != (width,)
            or weight.device != self.device
            or not weight.is_contiguous()
            or not 1 <= width <= MAX_NORM_WIDTH
            or not (isinstance(epsilon, float) and math.isfinite(epsilon) and epsilon > 0)
        ):
            raise ReferenceArithmeticError("Unsupported strict RMSNorm weight, width or epsilon")
        rows = value.numel() // width
        result = torch.empty_like(value)
        flag = self.new_error_flag() if error_flag is None else error_flag
        self._launch(
            self._ops("strict_rms_norm"),
            grid=rows,
            block=(256, 1),
            pointers=(value, weight, result, flag),
            integers=(rows, width),
            floats=(1.0 / width, epsilon),
            shared=4 * width,
        )
        self._finish(flag, error_flag)
        return result

    def _elementwise(self, entry, a, b, error_flag):
        a, b = self._float32(a, b)
        if a.shape != b.shape:
            raise ReferenceArithmeticError("Strict elementwise operands must have the same shape")
        result = torch.empty_like(a)
        flag = self.new_error_flag() if error_flag is None else error_flag
        count = a.numel()
        self._launch(
            self._ops(entry), grid=-(-count // 256), block=(256, 1), pointers=(a, b, result, flag), integers=(count,)
        )
        self._finish(flag, error_flag)
        return result

    @torch.inference_mode()
    def add(self, a, b, *, error_flag=None):
        return self._elementwise("strict_add", a, b, error_flag)

    @torch.inference_mode()
    def silu_mul(self, gate, up, *, error_flag=None):
        """``mul(silu(gate), up)`` of the reference, elementwise."""
        return self._elementwise("strict_silu_mul", gate, up, error_flag)

    @torch.inference_mode()
    def rope(self, value, cosine, sine, heads, *, error_flag=None):
        """[length, heads*dim] projection -> rotated [heads, length, dim]; cos/sin are [length, dim]."""
        value, cosine, sine = self._float32(value, cosine, sine)
        if value.ndim != 2 or type(heads) is not int or heads < 1 or value.shape[1] % heads:
            raise ReferenceArithmeticError("Unsupported strict RoPE layout")
        length, dim = value.shape[0], value.shape[1] // heads
        if dim % 2 or cosine.shape != (length, dim) or sine.shape != (length, dim):
            raise ReferenceArithmeticError("Strict RoPE needs an even head dimension and [length, dim] tables")
        result = torch.empty((heads, length, dim), dtype=torch.float32, device=self.device)
        flag = self.new_error_flag() if error_flag is None else error_flag
        self._launch(
            self._ops("strict_rope"),
            grid=(length, heads),
            block=(32 * -(-dim // 32), 1),
            pointers=(value, cosine, sine, result, flag),
            integers=(length, heads, dim),
        )
        self._finish(flag, error_flag)
        return result

    @torch.inference_mode()
    def attention(self, query, key, value, past, repeats, scale, *, error_flag=None):
        """Causal GQA attention of the reference: q [heads, length, dim], k/v [kv_heads, past+length, dim]."""
        query, key, value = self._float32(query, key, value)
        if (
            query.ndim != 3
            or key.ndim != 3
            or key.shape != value.shape
            or type(past) is not int
            or type(repeats) is not int
            or past < 0
            or repeats < 1
            or query.shape[0] != key.shape[0] * repeats
            or query.shape[2] != key.shape[2]
            or key.shape[1] != past + query.shape[1]
            or not 1 <= key.shape[1] <= MAX_ATTENTION_KEYS
            or query.shape[2] > 256
            or not (isinstance(scale, float) and math.isfinite(scale))
        ):
            raise ReferenceArithmeticError("Unsupported strict attention shapes, context or scale")
        heads, length, dim = query.shape
        keys = key.shape[1]
        result = torch.empty((length, heads * dim), dtype=torch.float32, device=self.device)
        flag = self.new_error_flag() if error_flag is None else error_flag
        self._launch(
            self._ops("strict_attention"),
            grid=(length, key.shape[0], repeats),
            block=(128, 1),
            pointers=(query, key, value, result, flag, flag),
            integers=(heads, length, keys, past, repeats, dim, 0),
            floats=(scale,),
            shared=4 * (dim + 2 * keys),
        )
        self._finish(flag, error_flag)
        return result

    def attention_layout(self, spans):
        """One call-local range table shared by all layers; each span is (queries, keys, cached prefix)."""
        if not isinstance(spans, (list, tuple)) or not 1 <= len(spans) <= 128:
            raise ReferenceArithmeticError("Spans need 1..128 independent sequences")
        ranges, offset, queries, maximum = [], 0, 0, 0
        for span in spans:
            if (
                not isinstance(span, (tuple, list))
                or len(span) != 3
                or any(type(n) is not int for n in span)
                or not 1 <= span[0] <= span[1] <= MAX_ATTENTION_KEYS
                or span[2] != span[1] - span[0]
            ):
                raise ReferenceArithmeticError("Span needs positive query/key counts and the exact cached prefix")
            length, keys, past = span
            ranges.extend((offset, keys, past + i) for i in range(length))
            offset += keys
            queries += length
            maximum = max(maximum, keys)
        return _PackedAttentionLayout(
            torch.tensor(ranges, dtype=torch.int32, device=self.device), queries, offset, maximum
        )

    @torch.inference_mode()
    def attention_packed(self, query, key, value, spans, repeats, scale, *, error_flag=None):
        """Ragged sequences share a launch, with a separate causal mask and reduction tree for every query."""
        layout = spans if isinstance(spans, _PackedAttentionLayout) else self.attention_layout(spans)
        query, key, value = self._float32(query, key, value)
        if (
            query.ndim != 3
            or key.ndim != 3
            or key.shape != value.shape
            or query.shape[1] != layout.queries
            or key.shape[1] != layout.keys
            or layout.ranges.device != self.device
            or type(repeats) is not int
            or repeats < 1
            or query.shape[0] != key.shape[0] * repeats
            or query.shape[2] != key.shape[2]
            or not 1 <= query.shape[2] <= 256
            or not (isinstance(scale, float) and math.isfinite(scale))
        ):
            raise ReferenceArithmeticError("Packed attention shape/device/scale does not match its spans")
        heads, length, dim = query.shape
        result = torch.empty((length, heads * dim), dtype=torch.float32, device=self.device)
        flag = self.new_error_flag() if error_flag is None else error_flag
        self._launch(
            self._ops("strict_attention"),
            grid=(length, key.shape[0], repeats),
            block=(128, 1),
            pointers=(query, key, value, result, flag, layout.ranges),
            integers=(heads, length, key.shape[1], 0, repeats, dim, 1),
            floats=(scale,),
            shared=4 * (dim + 2 * layout.max_keys),
        )
        self._finish(flag, error_flag)
        return result

    @torch.inference_mode()
    def linear(self, value, weight, bias=None, *, error_flag=None, row_tile=None):
        """Bitwise ``reference_ops.linear`` with FP16 weights read in place; FP32 output only.

        With ``error_flag`` the nonfinite check is deferred to ``raise_if_error`` (no host sync here).
        """
        if row_tile is not None and (type(row_tile) is not int or row_tile not in (1, 2, 4, 8)):
            raise ReferenceArithmeticError("Strict linear row tile must be 1, 2, 4 or 8")
        rows, width, outputs = validate_linear(value, weight, bias, device=self.device)
        plan, selected_tile = linear_execution_plan(width, rows)
        row_tile = selected_tile if row_tile is None else 1 if rows == 1 else row_tile
        function = self._linear_function(plan, bias is not None, row_tile)
        flat = value.to(torch.float32).reshape(rows, width).contiguous()
        result = torch.empty((rows, outputs), dtype=torch.float32, device=self.device)
        flag = self.new_error_flag() if error_flag is None else error_flag
        self._launch(
            function,
            grid=(-(-outputs // plan.outputs_per_block), min(65535, -(-rows // row_tile))),
            block=(32 * plan.warps, plan.outputs_per_block),
            pointers=(flat, weight, weight if bias is None else bias, result, flag),
            integers=(rows, outputs),
        )
        if error_flag is None:
            self.raise_if_error(flag)
        return result.reshape(*value.shape[:-1], outputs)

    def _launch(self, function, *, grid, block, pointers, integers, floats=(), shared=0):
        import numpy as np

        storage = [np.array([p.data_ptr()], dtype=np.uint64) for p in pointers]
        storage += [np.array([i], dtype=np.int32) for i in integers]
        storage += [np.array([f], dtype=np.float32) for f in floats]  # Python float -> FP32, round to nearest
        arguments = np.array([s.ctypes.data for s in storage], dtype=np.uint64)
        grid = (*((grid,) if isinstance(grid, int) else grid), 1, 1)[:3]
        stream = torch.cuda.current_stream(self.device).cuda_stream
        with torch.cuda.device(self.device):
            _check(
                self._driver.cuLaunchKernel(
                    function, grid[0], grid[1], grid[2], block[0], block[1], 1, shared, stream, arguments.ctypes.data, 0
                )
            )
