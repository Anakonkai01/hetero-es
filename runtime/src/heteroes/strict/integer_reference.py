"""Independent CPU reference for experimental row-scaled integer projections (ADR-012).

This is DIFFERENT arithmetic from pairwise_f32_reference_v1. FP16 weights remain the live parameters;
only bounded CPU oracle tiles are widened. Each row has its own power-of-two scale. Quantization, exact
nonoverflowing integer dot and one final RNE/FTZ encoding are fully specified without vendor float GEMM.
No managed recipe or hardware qualification is implied.
"""

import hashlib
from pathlib import Path

import torch

from heteroes.strict import reference_ops as ops
from heteroes.strict.reference_ops import ReferenceArithmeticError

INTEGER_REFERENCE_VERSION = "row_scaled_signed_integer_dot_v1_experimental"
MAX_WIDTH = 32768
PRECISIONS = (14, 22)


def _precision(magnitude_bits):
    if type(magnitude_bits) is not int or magnitude_bits not in PRECISIONS:
        raise ReferenceArithmeticError("Integer projection magnitude bits must be 14 or 22")


def _matrix(value, dtype):
    if (
        not isinstance(value, torch.Tensor)
        or value.device.type != "cpu"
        or value.dtype != dtype
        or value.ndim != 2
        or not value.numel()
        or not 1 <= value.shape[1] <= MAX_WIDTH
    ):
        raise ReferenceArithmeticError("Integer CPU reference needs a nonempty declared-dtype CPU matrix")


def quantize_rows(value, *, magnitude_bits=14):
    """Return signed int32 quantized rows and floor-log2 row maxima, using integer RNE only.

    Input FP32 subnormals map to zero; integer zero has no sign. All-zero rows use exponent zero.
    Scale for each row is 2**(exponent-(magnitude_bits-1)); both signed endpoints +/-2**bits are admitted.
    """
    _precision(magnitude_bits)
    _matrix(value, torch.float32)
    bits = value.contiguous().view(torch.int32)
    absolute = bits & 0x7FFFFFFF
    if bool((absolute >= 0x7F800000).any()):
        raise ReferenceArithmeticError("Nonfinite integer reference input")
    absolute = torch.where((absolute & 0x7F800000) == 0, 0, absolute)
    maximum = absolute.amax(dim=1)
    exponent = torch.where(maximum == 0, 0, (maximum >> 23) - 127).to(torch.int32)
    shift = exponent[:, None] - ((absolute >> 23) - 127) + 24 - magnitude_bits
    safe = shift.clamp(max=31).to(torch.int64)
    mantissa = ((absolute & 0x7FFFFF) | 0x800000).to(torch.int64)
    whole = mantissa >> safe
    remainder = mantissa & ((1 << safe) - 1)
    halfway = 1 << (safe - 1)
    increment = (remainder > halfway) | ((remainder == halfway) & ((whole & 1) != 0))
    quantized = whole + increment.to(torch.int64)
    quantized = torch.where((absolute == 0) | (shift > 31), 0, quantized)
    quantized = torch.where(bits < 0, -quantized, quantized).to(torch.int32)
    return quantized, exponent


def balanced_digits(value, *, magnitude_bits=14):
    """Signed radix-256 limbs; the highest limb is bounded by 64 in magnitude for both precisions."""
    _precision(magnitude_bits)
    _matrix(value, torch.int32)
    if bool((value.to(torch.int64).abs() > 2**magnitude_bits).any()):
        raise ReferenceArithmeticError("Integer projection operand outside its magnitude bound")
    remaining, digits = value, []
    for _ in range(2 if magnitude_bits == 14 else 3):
        digit = (((remaining + 128) & 255) - 128).to(torch.int8)
        digits.append(digit)
        remaining = (remaining - digit.to(torch.int32)) >> 8
    return tuple(digits)


def _round_shift(value, shift):
    if shift <= 0:
        return value << -shift
    whole, remainder = divmod(value, 1 << shift)
    halfway = 1 << (shift - 1)
    return whole + (remainder > halfway or (remainder == halfway and whole & 1))


def scaled_integer_bits(value, exponent):
    """Encode exact value*2**exponent directly to FP32 RNE, then signed-zero FTZ; integer zero is +0.

    No intermediate FP32 scale can underflow prematurely, and no binary64 conversion can double-round.
    The admitted reference range also covers all linear dots and their integer reconstruction bounds.
    """
    if type(value) is not int or abs(value) >= 2**63 or type(exponent) is not int or not -512 <= exponent <= 512:
        raise ReferenceArithmeticError("Unsupported scaled integer range")
    if value == 0:
        return 0
    sign, magnitude = (0x80000000 if value < 0 else 0), abs(value)
    leading = magnitude.bit_length() - 1
    final_exponent = leading + exponent
    if final_exponent < -126:
        # Round the exact subnormal in units of 2^-149 BEFORE flushing. A round up to min-normal survives.
        rounded = _round_shift(magnitude, -exponent - 149)
        return sign | (0x00800000 if rounded >= 2**23 else 0)
    rounded = _round_shift(magnitude, leading - 23)
    if rounded >= 2**24:
        rounded >>= 1
        final_exponent += 1
    if final_exponent > 127:
        raise ReferenceArithmeticError("Nonfinite integer reference output overflow")
    return sign | ((final_exponent + 127) << 23) | (rounded & 0x7FFFFF)


@torch.inference_mode()
def linear(value, weight, bias=None, *, magnitude_bits=14, output_tile=32):
    """Exact nonoverflowing CPU integer matmul plus specified FP32 encoding and the existing RNE/FTZ bias add."""
    _precision(magnitude_bits)
    if (
        not isinstance(value, torch.Tensor)
        or value.dtype != torch.float32
        or value.device.type != "cpu"
        or value.ndim < 1
        or not value.numel()
        or type(output_tile) is not int
        or output_tile < 1
    ):
        raise ReferenceArithmeticError("Unsupported integer CPU linear activation or tile")
    _matrix(weight, torch.float16)
    if value.shape[-1] != weight.shape[1]:
        raise ReferenceArithmeticError("Integer linear width mismatch")
    if bias is not None and (
        not isinstance(bias, torch.Tensor)
        or bias.shape != (weight.shape[0],)
        or bias.dtype != torch.float16
        or bias.device.type != "cpu"
    ):
        raise ReferenceArithmeticError("Unsupported integer linear bias")
    if bias is not None:
        ops._normal(bias.float())
    width, outputs = weight.shape[1], weight.shape[0]
    flat = value.reshape(-1, width)
    qx, ex = quantize_rows(flat, magnitude_bits=magnitude_bits)
    result = torch.empty((flat.shape[0], outputs), dtype=torch.float32)
    for first in range(0, outputs, output_tile):
        qw, ew = quantize_rows(weight[first : first + output_tile].float(), magnitude_bits=magnitude_bits)
        # Every individual product and every possible partial sum is bounded by K*2**(2B)<=2**59.
        integer = qx.to(torch.int64) @ qw.to(torch.int64).T
        scale = ex[:, None] + ew[None, :] - 2 * (magnitude_bits - 1)
        encoded = []
        for sums, scales in zip(integer.tolist(), scale.tolist()):
            row = [scaled_integer_bits(s, e) for s, e in zip(sums, scales)]
            encoded.append([u if u < 2**31 else u - 2**32 for u in row])
        tile = torch.tensor(encoded, dtype=torch.int32).view(torch.float32)
        if bias is not None:
            tile = ops.add(tile, bias[first : first + tile.shape[1]].float())
        result[:, first : first + tile.shape[1]] = tile
    return result.reshape(*value.shape[:-1], outputs)


def identity(magnitude_bits=14):
    _precision(magnitude_bits)
    return {
        "operator": INTEGER_REFERENCE_VERSION,
        "magnitudeBits": magnitude_bits,
        "limbs": 2 if magnitude_bits == 14 else 3,
        "maxWidth": MAX_WIDTH,
        "zeroIntegerOutput": "+0",
        "rounding": "exact_scaled_integer_rne_then_signed_ftz",
        "bias": ops.REFERENCE_OPS_VERSION,
        "sourceSha256": hashlib.sha256(Path(__file__).read_bytes() + Path(ops.__file__).read_bytes()).hexdigest(),
        "hardwareQualified": False,
    }
