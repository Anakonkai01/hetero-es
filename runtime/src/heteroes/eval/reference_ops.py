"""Experimental, deliberately slow FP32 operation reference for ADR-012.

Weights stay FP16; linear widens bounded tiles. Reductions are a fixed adjacent-pair tree.
Basic FP32 add/multiply calls are separate, with subnormals flushed to signed zero at each boundary.
Nonlinearities use versioned arithmetic sequences, not vendor transcendental or GEMM kernels.

This eager reference is NOT a qualified GPU backend or a throughput claim. Its arithmetic sequence is the
candidate specification; IEEE primitive/compiler assumptions still need hardware and generated-kernel checks.
Do not compile/fuse these calls under this identity: contraction/reassociation would change the algorithm.
"""

import torch

REFERENCE_OPS_VERSION = "pairwise_f32_reference_v1_experimental"


class ReferenceArithmeticError(ValueError):
    """The proposed operation contract cannot represent or support this input."""


class StrictTransportError(RuntimeError):
    """A strict kernel's data transport did not complete (error bit 8): an infrastructure failure, never a result."""


def _normal(value):
    value = value.to(dtype=torch.float32)
    if not bool(torch.isfinite(value).all()):
        raise ReferenceArithmeticError("Nonfinite reference arithmetic")
    bits = value.view(torch.int32)
    return torch.where((bits & 0x7F800000) == 0, bits & -2147483648, bits).view(torch.float32)


def _operands(a, b):
    if isinstance(a, torch.Tensor) and isinstance(b, torch.Tensor) and a.device != b.device:
        raise ReferenceArithmeticError("Reference operands must be on the same device")
    device = a.device if isinstance(a, torch.Tensor) else b.device if isinstance(b, torch.Tensor) else "cpu"
    return (
        _normal(torch.as_tensor(a, dtype=torch.float32, device=device)),
        _normal(torch.as_tensor(b, dtype=torch.float32, device=device)),
    )


def add(a, b):
    a, b = _operands(a, b)
    return _normal(torch.add(a, b))


def mul(a, b):
    a, b = _operands(a, b)
    return _normal(torch.mul(a, b))


def pairwise_sum(value):
    value = _normal(value)
    if value.ndim < 1 or value.shape[-1] < 1:
        raise ReferenceArithmeticError("A reference reduction needs a nonempty final dimension")
    while value.shape[-1] > 1:
        pairs = value.shape[-1] // 2
        summed = add(value[..., : 2 * pairs : 2], value[..., 1 : 2 * pairs : 2])
        value = torch.cat((summed, value[..., -1:]), dim=-1) if value.shape[-1] % 2 else summed
    return value.squeeze(-1)


@torch.inference_mode()
def linear(value, weight, bias=None, *, row_tile=4, output_tile=32):
    if (
        weight.dtype != torch.float16
        or weight.ndim != 2
        or value.ndim < 1
        or value.shape[-1] != weight.shape[-1]
        or value.device != weight.device
        or row_tile < 1
        or output_tile < 1
        or weight.shape[0] < 1
        or weight.shape[1] < 1
        or value.numel() == 0
    ):
        raise ReferenceArithmeticError("Unsupported linear dtype, layout, shape or tile size")
    if bias is not None and (bias.shape != (weight.shape[0],) or bias.device != value.device):
        raise ReferenceArithmeticError("Linear bias shape/device mismatch")
    flat = _normal(value).reshape(-1, value.shape[-1])
    result = torch.empty((flat.shape[0], weight.shape[0]), dtype=torch.float32, device=value.device)
    for row in range(0, flat.shape[0], row_tile):
        x = flat[row : row + row_tile]
        for column in range(0, weight.shape[0], output_tile):
            # No full-model or full-matrix FP32 copy; the widening ends with this output tile.
            w = weight[column : column + output_tile].float()
            out = pairwise_sum(mul(x[:, None, :], w[None, :, :]))
            if bias is not None:
                out = add(out, bias[column : column + output_tile])
            result[row : row + x.shape[0], column : column + w.shape[0]] = out
    return result.reshape(*value.shape[:-1], weight.shape[0])


def _positive(value):
    value = _normal(value)
    if bool(((value < 1e-30) | (value > 1e30)).any()):
        raise ReferenceArithmeticError("Reference reciprocal/root domain is [1e-30, 1e30]")
    return value


def reciprocal(value):
    value = _positive(value)
    result = (0x7EF311C3 - value.view(torch.int32)).view(torch.float32)
    for _ in range(5):
        result = mul(result, add(2.0, -mul(value, result)))
    return result


def rsqrt(value):
    value = _positive(value)
    result = (0x5F3759DF - (value.view(torch.int32) >> 1)).view(torch.float32)
    for _ in range(6):
        square = mul(result, result)
        result = mul(mul(0.5, result), add(3.0, -mul(value, square)))
    return result


def exp(value):
    value = _normal(value)
    if bool((value > 80.0).any()):
        raise ReferenceArithmeticError("Reference exp only supports inputs <= 80")
    clipped = torch.clamp(value, min=-80.0)
    power = torch.floor(add(mul(clipped, 1.4426950408889634), 0.5)).to(torch.int32)
    exponent = power.float()
    remainder = add(clipped, -mul(exponent, 0.693145751953125))
    remainder = add(remainder, -mul(exponent, 0.000001428606765330187))
    polynomial = torch.full_like(value, 1.0 / 40320.0)
    for coefficient in (1.0 / 5040.0, 1.0 / 720.0, 1.0 / 120.0, 1.0 / 24.0, 1.0 / 6.0, 0.5, 1.0, 1.0):
        polynomial = add(mul(polynomial, remainder), coefficient)
    scale = ((power + 127) << 23).view(torch.float32)
    return torch.where(value < -80.0, torch.zeros_like(value), mul(polynomial, scale))


def sin_cos(value):
    value = _normal(value)
    if bool((value.abs() > 32768.0).any()):
        raise ReferenceArithmeticError("Reference trigonometry domain is [-32768, 32768]")
    quadrant = torch.floor(add(mul(value, 0.6366197723675814), 0.5)).to(torch.int32)
    multiple = quadrant.float()
    # The first two multiples are exact for this bounded domain; the final small correction controls cancellation.
    reduced = add(value, -mul(multiple, 1.5703125))
    reduced = add(reduced, -mul(multiple, 0.00048351287841796875))
    reduced = add(reduced, -mul(multiple, 0.0000003139164786504))
    square = mul(reduced, reduced)
    sine_polynomial = torch.full_like(value, -1.0 / 39916800.0)
    for coefficient in (1.0 / 362880.0, -1.0 / 5040.0, 1.0 / 120.0, -1.0 / 6.0):
        sine_polynomial = add(mul(sine_polynomial, square), coefficient)
    sine = add(reduced, mul(mul(reduced, square), sine_polynomial))
    cosine_polynomial = torch.full_like(value, -1.0 / 3628800.0)
    for coefficient in (1.0 / 40320.0, -1.0 / 720.0, 1.0 / 24.0, -0.5):
        cosine_polynomial = add(mul(cosine_polynomial, square), coefficient)
    cosine = add(1.0, mul(square, cosine_polynomial))
    q = quadrant & 3
    result_sine = torch.where(q == 0, sine, torch.where(q == 1, cosine, torch.where(q == 2, -sine, -cosine)))
    result_cosine = torch.where(q == 0, cosine, torch.where(q == 1, -sine, torch.where(q == 2, -cosine, sine)))
    return torch.where(value == 0, value, result_sine), result_cosine


def silu(value):
    value = _normal(value)
    small_exp = exp(-value.abs())
    denominator = reciprocal(add(1.0, small_exp))
    return torch.where(value >= 0, mul(value, denominator), mul(mul(value, small_exp), denominator))


def rms_norm(value, weight, epsilon):
    if weight.dtype != torch.float16 or weight.shape != (value.shape[-1],) or epsilon <= 0:
        raise ReferenceArithmeticError("Unsupported RMSNorm weight/epsilon")
    value = _normal(value)
    mean_square = mul(pairwise_sum(mul(value, value)), 1.0 / value.shape[-1])
    inverse = rsqrt(add(mean_square, epsilon))
    return mul(mul(value, inverse[..., None]), weight)


def softmax(value, mask):
    value = _normal(value)
    if mask.dtype != torch.bool or mask.device != value.device:
        raise ReferenceArithmeticError("Softmax needs a boolean mask on the same device")
    mask = torch.broadcast_to(mask, value.shape)
    maximum = torch.where(mask, value, torch.full_like(value, -torch.finfo(torch.float32).max)).amax(-1, keepdim=True)
    maximum = torch.where(maximum == 0, torch.zeros_like(maximum), maximum)
    shifted = add(torch.where(mask, value, maximum), -maximum)
    numerators = torch.where(mask, exp(shifted), torch.zeros_like(value))
    denominator = pairwise_sum(numerators)
    inverse = reciprocal(torch.where(denominator == 0, torch.ones_like(denominator), denominator))
    return mul(numerators, inverse[..., None])
