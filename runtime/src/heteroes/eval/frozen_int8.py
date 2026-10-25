"""Versioned frozen-int8 base artifact and exact CPU projection for the M6 experiment.

The frozen base weight is signed int8 with one FP32 scale per output row. A pinned artifact is written once on the
host from an exact rational quantizer; this runtime only reads and verifies it and never re-quantizes or materializes
a dequantized weight. Activations use the existing B22 integer reference, so each dot is three limb products
instead of the nine products of the B22-by-B22 path.

This module is a CPU oracle, not a CUDA backend, a managed recipe or an accepted model path. Its arithmetic is
separate from `pairwise_f32_reference_v1` and from `row_scaled_signed_integer_dot_v1`.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile

import numpy as np
import torch

from heteroes.eval import integer_reference
from heteroes.eval import reference_ops as ops
from heteroes.eval.reference_ops import ReferenceArithmeticError

ARTIFACT_FORMAT = "heteroes.frozen-int8-b22"
ARTIFACT_FORMAT_VERSION = 1
QUANTIZER_VERSION = "per_output_channel_int8_ceil_absmax_over_127_rne_v1_experimental"
OPERATOR_VERSION = "frozen_int8_b22_exact_reference_v1_experimental"
ADAPTER_STORAGE_VERSION = "frozen_int8_fp16_lora_storage_v1_experimental"
ADAPTER_ARITHMETIC_VERSION = "pairwise_f32_fp16_factors_scale_add_zero_delta_preserves_base_v1_experimental"
MAGNITUDE_BITS = 22
ACTIVATION_LIMBS = 3
MAX_WIDTH = integer_reference.MAX_WIDTH
WEIGHT_MIN, WEIGHT_MAX = -127, 127
MAGIC = b"HESFINT8"
MAX_HEADER_BYTES = 1 << 20
# Encoder accepts the full B22 projection range and the independent 2**68 boundary tests. Values with an exponent
# above the FP32 range fail the exact overflow check, not an arbitrary upper bound.
MIN_ENCODING_EXPONENT = -2048

_HEADER_KEYS = {
    "activationLimbs",
    "format",
    "formatVersion",
    "magnitudeBits",
    "maxWidth",
    "metadata",
    "operator",
    "quantizer",
    "shape",
    "tensors",
    "weightLayout",
    "weightRange",
}
_TENSOR_KEYS = {"weight_q", "weight_scale"}


def _power_two(exponent):
    return Fraction(1 << exponent) if exponent >= 0 else Fraction(1, 1 << -exponent)


def _fraction_from_bits(bits):
    """Decode a finite positive FP32 bit pattern to an exact rational."""
    bits &= 0xFFFFFFFF
    exponent, mantissa = (bits >> 23) & 0xFF, bits & 0x7FFFFF
    if exponent == 0xFF:
        raise ReferenceArithmeticError("Nonfinite FP32 value")
    if exponent:
        return (mantissa | 0x800000) * _power_two(exponent - 150)
    return mantissa * _power_two(-149)


def _ceil_fp32_bits(value):
    """Least positive finite FP32 bit pattern greater than or equal to an exact nonnegative rational."""
    if value < 0:
        raise ReferenceArithmeticError("A frozen int8 scale cannot be negative")
    if not value:
        return 0
    estimate = struct.unpack("<f", struct.pack("<f", float(value)))[0]
    bits = struct.unpack("<I", struct.pack("<f", estimate))[0]
    if bits >= 0x7F800000:
        raise ReferenceArithmeticError("Frozen int8 scale overflow")
    while _fraction_from_bits(bits) < value:
        bits += 1
        if bits >= 0x7F800000:
            raise ReferenceArithmeticError("Frozen int8 scale overflow")
    while bits and _fraction_from_bits(bits - 1) >= value:
        bits -= 1
    return bits


def _weight_matrix(weight):
    if (
        not isinstance(weight, torch.Tensor)
        or weight.device.type != "cpu"
        or weight.dtype not in (torch.float16, torch.float32)
        or weight.ndim != 2
        or not weight.numel()
        or weight.shape[0] < 1
        or not 1 <= weight.shape[1] <= MAX_WIDTH
    ):
        raise ReferenceArithmeticError("Frozen int8 needs a nonempty CPU FP16/FP32 [N,K] weight with 1 <= K <= 32768")
    return weight


def quantize_weight(weight):
    """Return signed int8 rows and FP32 per-row scales using the exact ceiling rule.

    The stored scale is the least FP32 value `s >= absmax/127`. Quantization is RNE against that exact scale, so no
    value is clipped and `-128` is never emitted. The binary64 division is exact enough by proof: a non-tie exact
    quotient is at least about `2^-26` from a half-integer while binary64 division error is below `2^-53`, and an
    exact tie is representable in binary64 and `torch.round` rounds ties to even. A program assertion checks the
    integer range instead of silently clipping.
    """
    _weight_matrix(weight)
    source = weight.detach().to(device="cpu", dtype=torch.float32).contiguous()
    absolute = source.view(torch.int32) & 0x7FFFFFFF
    if bool((absolute >= 0x7F800000).any()):
        raise ReferenceArithmeticError("Nonfinite frozen int8 weight")
    maximum = absolute.amax(dim=1)
    scale_bits = torch.zeros(source.shape[0], dtype=torch.int64)
    minimum_row = _power_two(-149) * 127
    for row, row_maximum in enumerate(maximum.tolist()):
        if row_maximum:
            exact_maximum = _fraction_from_bits(row_maximum)
            if exact_maximum < minimum_row:
                raise ReferenceArithmeticError("Frozen int8 weight row is too small for a scale")
            scale_bits[row] = _ceil_fp32_bits(exact_maximum / 127)
    scale = scale_bits.to(torch.int32).view(torch.float32)
    quantized = torch.empty_like(source, dtype=torch.int8)
    # A full FP64 copy of a model would be large; each block is bounded independently of the model.
    row_block = max(1, (4 * 1024 * 1024) // source.shape[1])
    for first in range(0, source.shape[0], row_block):
        block = source[first : first + row_block]
        block_scale = scale[first : first + row_block]
        active = block_scale > 0
        values = torch.zeros_like(block)
        if bool(active.any()):
            quotient = block[active].double() / block_scale[active, None].double()
            rounded = torch.round(quotient)
            if not bool(torch.isfinite(rounded).all()):
                raise ReferenceArithmeticError("Frozen int8 quantizer produced a nonfinite value")
            if bool((rounded.abs() > WEIGHT_MAX).any()):
                raise ReferenceArithmeticError("Frozen int8 quantizer escaped [-127, 127]")
            values[active] = rounded.to(block.dtype)
        quantized[first : first + block.shape[0]] = values.to(torch.int8)
    return quantized, scale


def _scale_components(scale):
    bits = scale.contiguous().view(torch.int32).to(torch.int64) & 0xFFFFFFFF
    exponent_field = (bits >> 23) & 0xFF
    significand = torch.where(exponent_field == 0, bits & 0x7FFFFF, (bits & 0x7FFFFF) | 0x800000)
    exponent = torch.where(exponent_field == 0, torch.full_like(exponent_field, -149), exponent_field - 150)
    return significand, exponent


def _round_shift(value, shift):
    if shift <= 0:
        return value << -shift
    whole, remainder = divmod(value, 1 << shift)
    halfway = 1 << (shift - 1)
    return whole + (remainder > halfway or (remainder == halfway and whole & 1))


def encode_scaled_integer_bits(value, exponent):
    """Encode exact `value * 2**exponent` to FP32 RNE, then signed-zero FTZ.

    `value` may exceed int64 (the B22 projection product can reach just under 2**68), so the CPU oracle keeps it as a
    Python integer. A future CUDA operator must use a two-limb 96-bit product and this same one-rounding contract.
    """
    if type(value) is not int or abs(value) >= 2**96 or type(exponent) is not int:
        raise ReferenceArithmeticError("Unsupported scaled integer range")
    if value == 0:
        return 0
    if not MIN_ENCODING_EXPONENT <= exponent:
        raise ReferenceArithmeticError("Unsupported scaled integer range")
    sign, magnitude = (0x80000000 if value < 0 else 0), abs(value)
    leading = magnitude.bit_length() - 1
    final_exponent = leading + exponent
    if final_exponent > 127:
        raise ReferenceArithmeticError("Nonfinite scaled integer output overflow")
    if final_exponent < -126:
        # Round in units of 2**-149 before flushing; a round up to the smallest normal survives.
        rounded = _round_shift(magnitude, -exponent - 149)
        return sign | (0x00800000 if rounded >= 2**23 else 0)
    rounded = _round_shift(magnitude, leading - 23)
    if rounded >= 2**24:
        rounded >>= 1
        final_exponent += 1
    if final_exponent > 127:
        # RNE overflow midpoint: max-finite + 2**103 rounds to infinity; below it rounds down to max-finite.
        raise ReferenceArithmeticError("Nonfinite scaled integer output overflow")
    return sign | ((final_exponent + 127) << 23) | (rounded & 0x7FFFFF)


@dataclass(frozen=True)
class FrozenInt8Artifact:
    """Verified immutable artifact payload. There is deliberately no dequantized weight tensor.

    Construction re-derives the content address from the payload, so a forged version, dtype, out-of-range
    scale or mismatched hash is rejected before arithmetic. The payload tensors are still backed by mutable
    torch storage: any versioned in-place write invalidates the seal, and ``verify`` re-hashes the payload for
    explicit lifecycle checks. ``.data`` writes bypass the autograd version counter, so callers that use that
    escape hatch must call ``verify`` at the next admission boundary.
    """

    weight_q: torch.Tensor
    weight_scale: torch.Tensor
    metadata: dict
    sha256: str
    format_version: int

    def __post_init__(self):
        _validate_payload(self.weight_q, self.weight_scale)
        if type(self.format_version) is not int or self.format_version != ARTIFACT_FORMAT_VERSION:
            raise ReferenceArithmeticError("Unsupported frozen int8 artifact format version")
        if not isinstance(self.metadata, dict):
            raise ReferenceArithmeticError("Frozen int8 artifact metadata must be an object")
        if not _valid_digest(self.sha256):
            raise ReferenceArithmeticError("Frozen int8 artifact needs one lowercase SHA-256 digest")
        digest = artifact_digest(self.weight_q, self.weight_scale, metadata=self.metadata)
        if digest != self.sha256:
            raise ReferenceArithmeticError("Frozen int8 artifact digest does not match its payload")
        object.__setattr__(self, "_sealed_versions", self._versions())
        object.__setattr__(self, "_sealed_metadata", metadata_digest(self.metadata))

    def _versions(self):
        return (self.weight_q._version, self.weight_scale._version)

    def _seal(self):
        if self._versions() != self._sealed_versions or metadata_digest(self.metadata) != self._sealed_metadata:
            raise ReferenceArithmeticError("Frozen int8 artifact storage or metadata changed after verification")

    @torch.inference_mode()
    def verify(self):
        """Re-check the seal and the full content address at an admission boundary."""
        self._seal()
        if artifact_digest(self.weight_q, self.weight_scale, metadata=self.metadata) != self.sha256:
            raise ReferenceArithmeticError("Frozen int8 artifact payload no longer matches its digest")


def _valid_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def metadata_digest(metadata):
    """Canonical SHA-256 of artifact metadata, used by the seal and the module cache key."""
    if not isinstance(metadata, dict):
        raise ReferenceArithmeticError("Artifact metadata must be an object")
    return hashlib.sha256(_canonical_json(metadata)).hexdigest()


@torch.inference_mode()
def verify_payload(weight_q, weight_scale, metadata, sha256):
    """Admit a payload that may live on another device by re-hashing a bounded CPU copy."""
    if (
        not isinstance(weight_q, torch.Tensor)
        or not isinstance(weight_scale, torch.Tensor)
        or weight_q.device != weight_scale.device
        or not isinstance(metadata, dict)
        or not _valid_digest(sha256)
    ):
        raise ReferenceArithmeticError("Unsupported frozen int8 artifact storage or admission input")
    host_q = weight_q.detach().to(device="cpu", dtype=torch.int8).contiguous()
    host_scale = weight_scale.detach().to(device="cpu", dtype=torch.float32).contiguous()
    _validate_payload(host_q, host_scale)
    if artifact_digest(host_q, host_scale, metadata=metadata) != sha256:
        raise ReferenceArithmeticError("Frozen int8 artifact payload no longer matches its digest")
    return True


def _validate_payload(weight_q, weight_scale):
    if (
        not isinstance(weight_q, torch.Tensor)
        or not isinstance(weight_scale, torch.Tensor)
        or weight_q.device.type != "cpu"
        or weight_scale.device.type != "cpu"
        or weight_q.dtype != torch.int8
        or weight_scale.dtype != torch.float32
        or weight_q.ndim != 2
        or weight_scale.ndim != 1
        or weight_q.shape[1] < 1
        or weight_q.shape[1] > MAX_WIDTH
        or weight_q.shape[0] < 1
        or weight_scale.shape != (weight_q.shape[0],)
    ):
        raise ReferenceArithmeticError("Unsupported frozen int8 payload shape or dtype")
    if bool((weight_q == -128).any()):
        raise ReferenceArithmeticError("Frozen int8 weights must stay in [-127, 127]")
    scale_bits = weight_scale.contiguous().view(torch.int32)
    if bool((scale_bits < 0).any()):
        raise ReferenceArithmeticError("Frozen int8 scales must be nonnegative and not negative zero")
    if bool(((scale_bits & 0x7F800000) == 0x7F800000).any()):
        raise ReferenceArithmeticError("Frozen int8 scales must be finite")
    zero_scale = scale_bits == 0
    zero_row = (weight_q == 0).all(dim=1)
    if not torch.equal(zero_scale, zero_row):
        raise ReferenceArithmeticError("A zero weight row and a zero scale must coincide")


def _canonical_json(value):
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        # Integer/float object keys can collide after JSON string conversion; reject that ambiguity.
        json.loads(text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)
    except (TypeError, ValueError) as exc:
        raise ReferenceArithmeticError("Artifact metadata is not canonical JSON") from exc
    return text.encode("utf-8")


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReferenceArithmeticError("Duplicate artifact header key")
        result[key] = value
    return result


def _reject_constant(_token):
    raise ReferenceArithmeticError("Nonstandard artifact header number")


def _decode_canonical_json(raw):
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ReferenceArithmeticError("Invalid artifact header") from exc
    if not isinstance(value, dict) or _canonical_json(value) != raw:
        raise ReferenceArithmeticError("Noncanonical artifact header")
    return value


def _payload_bytes(weight_q, weight_scale):
    weight = np.asarray(weight_q.contiguous(), dtype=np.int8)
    scales = np.asarray(weight_scale.contiguous(), dtype="<f4")
    return weight.tobytes(), scales.tobytes()


@torch.inference_mode()
def artifact_bytes(weight_q, weight_scale, *, metadata=None):
    """Return the canonical artifact bytes without writing them."""
    _validate_payload(weight_q, weight_scale)
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ReferenceArithmeticError("Artifact metadata must be an object")
    weight_bytes, scale_bytes = _payload_bytes(weight_q, weight_scale)
    outputs, width = weight_q.shape
    header = {
        "activationLimbs": ACTIVATION_LIMBS,
        "format": ARTIFACT_FORMAT,
        "formatVersion": ARTIFACT_FORMAT_VERSION,
        "magnitudeBits": MAGNITUDE_BITS,
        "maxWidth": MAX_WIDTH,
        "metadata": metadata,
        "operator": OPERATOR_VERSION,
        "quantizer": QUANTIZER_VERSION,
        "shape": [outputs, width],
        "tensors": {
            "weight_q": {
                "dtype": "int8",
                "shape": [outputs, width],
                "sha256": hashlib.sha256(weight_bytes).hexdigest(),
            },
            "weight_scale": {
                "dtype": "float32",
                "shape": [outputs],
                "sha256": hashlib.sha256(scale_bytes).hexdigest(),
            },
        },
        "weightLayout": "output-major-k-contiguous",
        "weightRange": [WEIGHT_MIN, WEIGHT_MAX],
    }
    header_bytes = _canonical_json(header)
    if len(header_bytes) > MAX_HEADER_BYTES:
        raise ReferenceArithmeticError("Artifact header is too large")
    return MAGIC + struct.pack("<Q", len(header_bytes)) + header_bytes + weight_bytes + scale_bytes


@torch.inference_mode()
def artifact_digest(weight_q, weight_scale, *, metadata=None):
    """Content address for the exact canonical bytes the writer would emit."""
    return hashlib.sha256(artifact_bytes(weight_q, weight_scale, metadata=metadata)).hexdigest()


@torch.inference_mode()
def write_artifact(path, weight_q, weight_scale, *, metadata=None):
    """Write one canonical artifact and return the SHA-256 of the whole file."""
    path = Path(path)
    if not path.parent.is_dir():
        raise ReferenceArithmeticError("Artifact parent directory does not exist")
    data = artifact_bytes(weight_q, weight_scale, metadata=metadata)
    digest = hashlib.sha256(data).hexdigest()
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return digest


def _tensor_descriptor(header, name, shape, dtype):
    descriptor = header["tensors"].get(name) if isinstance(header.get("tensors"), dict) else None
    if (
        not isinstance(descriptor, dict)
        or set(descriptor) != {"dtype", "shape", "sha256"}
        or descriptor["dtype"] != dtype
        or not isinstance(descriptor["shape"], list)
        or len(descriptor["shape"]) != len(shape)
        or any(type(entry) is not int for entry in descriptor["shape"])
        or descriptor["shape"] != shape
        or type(descriptor["sha256"]) is not str
        or len(descriptor["sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in descriptor["sha256"])
    ):
        raise ReferenceArithmeticError(f"Invalid artifact descriptor for {name}")
    return descriptor


def _validate_header(header):
    if set(header) != _HEADER_KEYS:
        raise ReferenceArithmeticError("Artifact header keys do not match version 1")
    weight_range = header["weightRange"]
    if (
        type(header["formatVersion"]) is not int
        or type(header["magnitudeBits"]) is not int
        or type(header["activationLimbs"]) is not int
        or type(header["maxWidth"]) is not int
        or not isinstance(weight_range, list)
        or len(weight_range) != 2
        or any(type(entry) is not int for entry in weight_range)
        or header["format"] != ARTIFACT_FORMAT
        or header["formatVersion"] != ARTIFACT_FORMAT_VERSION
        or header["operator"] != OPERATOR_VERSION
        or header["quantizer"] != QUANTIZER_VERSION
        or header["magnitudeBits"] != MAGNITUDE_BITS
        or header["activationLimbs"] != ACTIVATION_LIMBS
        or header["maxWidth"] != MAX_WIDTH
        or header["weightLayout"] != "output-major-k-contiguous"
        or weight_range != [WEIGHT_MIN, WEIGHT_MAX]
    ):
        raise ReferenceArithmeticError("Artifact identity does not match version 1")
    shape = header["shape"]
    if (
        not isinstance(shape, list)
        or len(shape) != 2
        or type(shape[0]) is not int
        or type(shape[1]) is not int
        or shape[0] < 1
        or not 1 <= shape[1] <= MAX_WIDTH
    ):
        raise ReferenceArithmeticError("Invalid artifact shape")
    if not isinstance(header["metadata"], dict):
        raise ReferenceArithmeticError("Artifact metadata must be an object")
    if not isinstance(header["tensors"], dict) or set(header["tensors"]) != _TENSOR_KEYS:
        raise ReferenceArithmeticError("Artifact tensor set does not match version 1")
    _tensor_descriptor(header, "weight_q", [shape[0], shape[1]], "int8")
    _tensor_descriptor(header, "weight_scale", [shape[0]], "float32")
    return shape


def read_artifact(path, *, expected_sha256=None):
    """Read and verify one artifact. Supplying `expected_sha256` pins the whole file.

    The payload is a normal (not inference-mode) tensor so its storage stamp tracks in-place writes for the seal.
    """
    if expected_sha256 is not None and (
        type(expected_sha256) is not str
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise ReferenceArithmeticError("Expected artifact hash must be 64 lowercase hex characters")
    if sys.byteorder != "little":
        raise ReferenceArithmeticError("Frozen int8 artifacts require a little-endian host")
    data = Path(path).read_bytes()
    if len(data) < 16:
        raise ReferenceArithmeticError("Truncated frozen int8 artifact")
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ReferenceArithmeticError("Artifact hash mismatch")
    if data[:8] != MAGIC:
        raise ReferenceArithmeticError("Bad frozen int8 artifact magic")
    header_length = struct.unpack("<Q", data[8:16])[0]
    if header_length > MAX_HEADER_BYTES or 16 + header_length > len(data):
        raise ReferenceArithmeticError("Invalid frozen int8 header length")
    header = _decode_canonical_json(data[16 : 16 + header_length])
    outputs, width = _validate_header(header)
    weight_bytes = outputs * width
    scale_bytes = outputs * 4
    if len(data) != 16 + header_length + weight_bytes + scale_bytes:
        raise ReferenceArithmeticError("Frozen int8 artifact size mismatch")
    weight_start = 16 + header_length
    scale_start = weight_start + weight_bytes
    raw_weight = data[weight_start:scale_start]
    raw_scale = data[scale_start:]
    if hashlib.sha256(raw_weight).hexdigest() != header["tensors"]["weight_q"]["sha256"]:
        raise ReferenceArithmeticError("Weight payload hash mismatch")
    if hashlib.sha256(raw_scale).hexdigest() != header["tensors"]["weight_scale"]["sha256"]:
        raise ReferenceArithmeticError("Scale payload hash mismatch")
    weight_q = torch.frombuffer(bytearray(raw_weight), dtype=torch.int8).reshape(outputs, width)
    weight_scale = torch.frombuffer(bytearray(raw_scale), dtype=torch.float32)
    _validate_payload(weight_q, weight_scale)
    return FrozenInt8Artifact(
        weight_q=weight_q,
        weight_scale=weight_scale,
        metadata=header["metadata"],
        sha256=digest,
        format_version=ARTIFACT_FORMAT_VERSION,
    )


@torch.inference_mode()
def linear(value, artifact, bias=None, *, output_tile=32):
    """Exact CPU projection with B22 activations, one final encoding, then the reference bias add."""
    if not isinstance(artifact, FrozenInt8Artifact):
        raise ReferenceArithmeticError("Frozen int8 linear needs a verified artifact")
    artifact._seal()
    if (
        not isinstance(value, torch.Tensor)
        or value.dtype != torch.float32
        or value.device.type != "cpu"
        or value.ndim < 1
        or not value.numel()
        or type(output_tile) is not int
        or output_tile < 1
    ):
        raise ReferenceArithmeticError("Unsupported frozen int8 CPU linear activation or tile")
    outputs, width = artifact.weight_q.shape
    if value.shape[-1] != width:
        raise ReferenceArithmeticError("Frozen int8 linear width mismatch")
    if bias is not None:
        if (
            not isinstance(bias, torch.Tensor)
            or bias.shape != (outputs,)
            or bias.dtype != torch.float16
            or bias.device.type != "cpu"
        ):
            raise ReferenceArithmeticError("Unsupported frozen int8 linear bias")
        if not bool(torch.isfinite(bias).all()):
            raise ReferenceArithmeticError("Nonfinite frozen int8 linear bias")
    flat = value.reshape(-1, width)
    quantized_input, input_exponent = integer_reference.quantize_rows(flat, magnitude_bits=MAGNITUDE_BITS)
    integer_input = quantized_input.to(torch.int64)
    scale_significand, scale_exponent = _scale_components(artifact.weight_scale)
    result = torch.empty((flat.shape[0], outputs), dtype=torch.float32)
    for first in range(0, outputs, output_tile):
        stop = min(first + output_tile, outputs)
        integer_weight = artifact.weight_q[first:stop].to(torch.int64)
        # Every partial sum is below 127 * 2**22 * 2**15 < 2**44, so int64 accumulation is exact.
        integer = integer_input @ integer_weight.T
        exponents = input_exponent[:, None] + scale_exponent[None, first:stop] - (MAGNITUDE_BITS - 1)
        significands = scale_significand[first:stop].tolist()
        encoded = []
        for sums, row_exponents in zip(integer.tolist(), exponents.tolist()):
            row = []
            for total, exponent, significand in zip(sums, row_exponents, significands):
                bits = encode_scaled_integer_bits(total * significand, exponent)
                row.append(bits if bits < 2**31 else bits - 2**32)
            encoded.append(row)
        tile = torch.tensor(encoded, dtype=torch.int32).view(torch.float32)
        if bias is not None:
            tile = ops.add(tile, bias[first:stop].float())
        result[:, first:stop] = tile
    return result.reshape(*value.shape[:-1], outputs)


def combine_adapter(base, delta):
    """Combine the exact base output with the strict FP32 adapter delta.

    A zero delta preserves the base bit pattern, including a signed zero. A nonzero delta is the strict
    ``reference_ops.add``: separate FP32 add, subnormals flushed to signed zero, nonfinite values rejected.
    The zero-delta select is part of the adapter contract and is not an IEEE add with a signed-zero rounding
    choice.
    """
    if (
        not isinstance(base, torch.Tensor)
        or not isinstance(delta, torch.Tensor)
        or base.dtype != torch.float32
        or delta.dtype != torch.float32
        or base.shape != delta.shape
        or base.device != delta.device
    ):
        raise ReferenceArithmeticError("Unsupported frozen adapter delta")
    added = ops.add(base, delta)
    return torch.where(delta == 0, base, added)


def identity():
    source = b"".join(Path(module).read_bytes() for module in (__file__, integer_reference.__file__, ops.__file__))
    return {
        "format": ARTIFACT_FORMAT,
        "formatVersion": ARTIFACT_FORMAT_VERSION,
        "operator": OPERATOR_VERSION,
        "quantizer": QUANTIZER_VERSION,
        "magnitudeBits": MAGNITUDE_BITS,
        "activationLimbs": ACTIVATION_LIMBS,
        "maxWidth": MAX_WIDTH,
        "weightLayout": "output-major-k-contiguous",
        "weightRange": [WEIGHT_MIN, WEIGHT_MAX],
        "rounding": "exact_scaled_integer_rne_then_signed_ftz",
        "bias": ops.REFERENCE_OPS_VERSION,
        "sourceSha256": hashlib.sha256(source).hexdigest(),
        "hardwareQualified": False,
    }
