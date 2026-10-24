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
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import reference_ops as ops
from heteroes.eval.reference_ops import ReferenceArithmeticError

KERNEL_VERSION = "pairwise_f32_cuda_linear_v1_experimental"
MAX_LINEAR_WIDTH = 32768
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
  __shared__ float partial[GROUPS][PADDED_WARPS];
  float weight[PER];
#pragma unroll
  for (int i = 0; i < PER; ++i) {
    const int k = start + i;
    weight[i] = (live && k < WIDTH) ? widen(w[(size_t)o * WIDTH + k]) : 0.0f;
  }
  float b = 0.0f;
  if (HAS_BIAS && live) b = widen(bias[o]);
  for (int m = 0; m < rows; ++m) {
    const float* row = x + (size_t)m * WIDTH;
    float stack[LOG_PER + 1];
#pragma unroll
    for (int i = 0; i < PER; ++i) {
      const int k = start + i;
      float v = (live && k < WIDTH) ? mul_rn(flush(row[k]), weight[i]) : -0.0f;
      int level = 0;
#pragma unroll
      for (; level < LOG_PER && ((i >> level) & 1); ++level) v = add_rn(stack[level], v);
      stack[level] = v;
    }
    float v = stack[LOG_PER];
#pragma unroll
    for (int offset = 1; offset < 32; offset <<= 1) v = add_rn(v, __shfl_xor_sync(0xffffffffu, v, offset));
    if (PADDED_WARPS > 1) {
      if (lane == 0) partial[threadIdx.y][warp] = v;
      __syncthreads();
      if (t == 0) {
        float s[LOG_WARPS + 1];
#pragma unroll
        for (int i = 0; i < PADDED_WARPS; ++i) {
          float u = i < WARPS ? partial[threadIdx.y][i] : -0.0f;
          int level = 0;
#pragma unroll
          for (; level < LOG_WARPS && ((i >> level) & 1); ++level) u = add_rn(s[level], u);
          s[level] = u;
        }
        v = s[LOG_WARPS];
      }
      __syncthreads();
    }
    if (t == 0 && live) {
      if (HAS_BIAS) v = add_rn(v, b);
      out[(size_t)m * outputs + o] = v;
      if ((__float_as_uint(v) & 0x7f800000u) == 0x7f800000u) atomicOr(error, 1);
    }
  }
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


def linear_plan(width):
    if type(width) is not int or not 1 <= width <= MAX_LINEAR_WIDTH:
        raise ReferenceArithmeticError(f"Strict CUDA linear supports input widths 1..{MAX_LINEAR_WIDTH}")
    padded = 1 << (width - 1).bit_length()
    per_thread = max(1, min(32, padded // 32))
    padded_warps = max(1, padded // (32 * per_thread))
    warps = -(-width // (32 * per_thread))
    return LinearPlan(width, padded, per_thread, warps, padded_warps, max(1, 8 // warps))


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


def audit_ptx(text):
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
            opcode in _PTX_EXACT or opcode.startswith(_PTX_EXACT_PREFIX) or _PTX_COMPARE.match(opcode)
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


def audit_sass(text):
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
        elif not (opcode in _SASS_EXACT or _SASS_COMPARE.match(opcode) or _SASS_CONSTANT.match(line)):
            violations.append(line)
    return {"floatOps": counts, "violations": violations}


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

    def _compile(self, name, source, entry):
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
        ptx_audit = audit_ptx(ptx_text)
        sass_audit = self._audit_cubin(cubin)
        violations = ptx_audit["violations"] + ([] if sass_audit == "unavailable" else sass_audit["violations"])
        if violations:
            raise ReferenceArithmeticError(f"Compiled strict kernel failed its instruction audit: {violations[:5]}")
        with torch.cuda.device(self.device):
            torch.cuda.init()
            module = _check(self._driver.cuModuleLoadData(cubin))
            function = _check(self._driver.cuModuleGetFunction(module, entry.encode()))
        self._modules.append(module)
        self._builds[name] = {
            "sourceSha256": hashlib.sha256(source.encode()).hexdigest(),
            "ptxSha256": hashlib.sha256(ptx_text.encode()).hexdigest(),
            "cubinSha256": hashlib.sha256(cubin).hexdigest(),
            "ptxAudit": ptx_audit,
            "sassAudit": sass_audit,
        }
        return function

    def _audit_cubin(self, cubin):
        if not self._nvdisasm:
            return "unavailable"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel.cubin"
            path.write_bytes(cubin)
            result = subprocess.run([self._nvdisasm, str(path)], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return "unavailable"
        return audit_sass(result.stdout)

    def _linear_function(self, plan, has_bias):
        name = f"linear-{plan.width}-{'bias' if has_bias else 'nobias'}"
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
            }
            header = "".join(f"#define {k} {v}\n" for k, v in defines.items())
            self._functions[name] = self._compile(name, header + _LINEAR_SOURCE, "strict_linear")
        return self._functions[name]

    def new_error_flag(self):
        return torch.zeros(1, dtype=torch.int32, device=self.device)

    @staticmethod
    def raise_if_error(flag):
        if int(flag.item()):
            raise ReferenceArithmeticError("Nonfinite reference arithmetic")

    @torch.inference_mode()
    def linear(self, value, weight, bias=None, *, error_flag=None):
        """Bitwise ``reference_ops.linear`` with FP16 weights read in place; FP32 output only.

        With ``error_flag`` the nonfinite check is deferred to ``raise_if_error`` (no host sync here).
        """
        rows, width, outputs = validate_linear(value, weight, bias, device=self.device)
        plan = linear_plan(width)
        function = self._linear_function(plan, bias is not None)
        flat = value.to(torch.float32).reshape(rows, width).contiguous()
        result = torch.empty((rows, outputs), dtype=torch.float32, device=self.device)
        flag = self.new_error_flag() if error_flag is None else error_flag
        self._launch(
            function,
            grid=-(-outputs // plan.outputs_per_block),
            block=(32 * plan.warps, plan.outputs_per_block),
            pointers=(flat, weight, weight if bias is None else bias, result, flag),
            integers=(rows, outputs),
        )
        if error_flag is None:
            self.raise_if_error(flag)
        return result.reshape(*value.shape[:-1], outputs)

    def _launch(self, function, *, grid, block, pointers, integers):
        import numpy as np

        storage = [np.array([p.data_ptr()], dtype=np.uint64) for p in pointers]
        storage += [np.array([i], dtype=np.int32) for i in integers]
        arguments = np.array([s.ctypes.data for s in storage], dtype=np.uint64)
        stream = torch.cuda.current_stream(self.device).cuda_stream
        with torch.cuda.device(self.device):
            _check(
                self._driver.cuLaunchKernel(
                    function, grid, 1, 1, block[0], block[1], 1, 0, stream, arguments.ctypes.data, 0
                )
            )
