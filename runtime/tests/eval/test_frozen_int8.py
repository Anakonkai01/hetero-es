"""Independent rational tests for the proposed frozen-int8-base artifact and projection.

The oracle below decodes FP32 bits to exact Fractions, searches the float bit space for the required
representable value, and rounds rationals by integer division. It does not call the production quantizer or
encoder except through the public functions under test.
"""

from fractions import Fraction
import json
import math
import random
import struct

import pytest
import torch

from heteroes.strict import frozen_int8
from heteroes.strict.reference_ops import ReferenceArithmeticError


def power_two(exponent):
    return Fraction(2**exponent) if exponent >= 0 else Fraction(1, 2**-exponent)


def fraction_from_bits(bits):
    bits &= 0xFFFFFFFF
    sign = -1 if bits >> 31 else 1
    exponent, mantissa = (bits >> 23) & 255, bits & 0x7FFFFF
    assert exponent != 255
    if exponent:
        return sign * (mantissa | (1 << 23)) * power_two(exponent - 150)
    return sign * mantissa * power_two(-149)


def float_bits(value):
    """Nearest FP32 (ties-even), with signed-zero FTZ. Exact rational input, no binary64.

    Values above max-finite but below the RNE overflow midpoint still round DOWN to max-finite. Only the
    midpoint itself and values above it round to infinity.
    """
    if not value:
        return 0
    sign, value = (0x80000000 if value < 0 else 0), abs(value)
    maximum = Fraction((1 << 24) - 1) * power_two(104)
    if value >= maximum + power_two(103):
        raise ReferenceArithmeticError("overflow")
    lo, hi = 0, 0x7F7FFFFF
    while lo < hi:
        middle = (lo + hi + 1) // 2
        if fraction_from_bits(middle) <= value:
            lo = middle
        else:
            hi = middle - 1
    lower = fraction_from_bits(lo)
    if lower != value and lo < 0x7F7FFFFF:
        upper = fraction_from_bits(lo + 1)
        if upper - value < value - lower or (upper - value == value - lower and lo & 1):
            lo += 1
    return sign | (lo if lo & 0x7F800000 else 0)


def ceil_bits(value):
    """Least positive FP32 greater than or equal to an exact positive rational."""
    if value < 0:
        raise ValueError("ceil_bits needs a nonnegative value")
    if not value:
        return 0
    if value > Fraction((1 << 24) - 1) * power_two(104):
        raise ReferenceArithmeticError("overflow")
    lo, hi = 0, 0x7F7FFFFF
    while lo < hi:
        middle = (lo + hi) // 2
        if fraction_from_bits(middle) >= value:
            hi = middle
        else:
            lo = middle + 1
    return lo


def round_half_even(value):
    sign = -1 if value < 0 else 1
    value = abs(value)
    whole, remainder = divmod(value.numerator, value.denominator)
    if 2 * remainder > value.denominator or (2 * remainder == value.denominator and whole & 1):
        whole += 1
    return sign * whole


def decode_scale(bits):
    bits &= 0xFFFFFFFF
    exponent, mantissa = (bits >> 23) & 255, bits & 0x7FFFFF
    assert exponent != 255
    if exponent:
        return mantissa | (1 << 23), exponent - 150
    return mantissa, -149


def activation_oracle(value):
    """B22 exact row quantization over normal FP32 values, returning ints and row exponents."""
    rows = value.reshape(-1, value.shape[-1])
    quantized, exponents = [], []
    for row in rows:
        values = [fraction_from_bits(int(bits) & 0xFFFFFFFF) for bits in row.contiguous().view(torch.int32)]
        maximum = max(map(abs, values))
        if not maximum:
            quantized.append([0] * len(values))
            exponents.append(0)
            continue
        exponent = maximum.numerator.bit_length() - maximum.denominator.bit_length()
        if maximum < power_two(exponent):
            exponent -= 1
        scale = power_two(exponent - 21)
        quantized.append([round_half_even(v / scale) for v in values])
        exponents.append(exponent)
    return quantized, exponents


def projection_oracle(value, quantized_weight, scale, bias=None):
    flat = value.reshape(-1, value.shape[-1])
    quantized_activation, exponents = activation_oracle(flat)
    outputs = []
    for row, exponent in zip(quantized_activation, exponents):
        output = []
        for column, weight_scale in enumerate(scale.view(torch.int32).tolist()):
            integer = sum(a * int(b) for a, b in zip(row, quantized_weight[column].tolist()))
            significand, scale_exponent = decode_scale(weight_scale)
            bits = float_bits(Fraction(integer * significand) * power_two(scale_exponent + exponent - 21))
            if bias is not None:
                bias_bits = int(bias[column].float().view(torch.int32)) & 0xFFFFFFFF
                bits = float_bits(fraction_from_bits(bits) + fraction_from_bits(bias_bits))
                bits = bits if bits & 0x7F800000 else bits & 0x80000000
            output.append(bits)
        outputs.append(output)
    encoded = [[int(value) if int(value) < 2**31 else int(value) - 2**32 for value in row] for row in outputs]
    return torch.tensor(encoded, dtype=torch.int32).view(torch.float32)


def artifact_file(tmp_path, weight_q, weight_scale, metadata=None, name="weights.fint8"):
    path = tmp_path / name
    digest = frozen_int8.write_artifact(
        path, weight_q, weight_scale, metadata={"purpose": "test"} if metadata is None else metadata
    )
    return path, digest


def test_weight_quantizer_matches_exact_ceiling_and_rne_oracle():
    for dtype in (torch.float16, torch.float32):
        generator = torch.Generator().manual_seed(413)
        weight = torch.randn((6, 37), generator=generator, dtype=torch.float32).to(dtype) * 3.25
        quantized, scale = frozen_int8.quantize_weight(weight)
        assert quantized.dtype == torch.int8 and quantized.shape == weight.shape
        assert scale.dtype == torch.float32 and scale.shape == (weight.shape[0],)
        for row in range(weight.shape[0]):
            values = [fraction_from_bits(int(bits) & 0xFFFFFFFF) for bits in weight[row].float().view(torch.int32)]
            maximum = max(map(abs, values))
            expected_scale = ceil_bits(maximum / 127) if maximum else 0
            assert int(scale[row].view(torch.int32)) == expected_scale
            exact_scale = fraction_from_bits(expected_scale)
            expected = [0 if not exact_scale else round_half_even(value / exact_scale) for value in values]
            assert quantized[row].tolist() == expected
            assert all(-127 <= value <= 127 for value in expected)


@pytest.mark.parametrize(
    "row,scale,expected",
    [
        ([127.0, -127.0, 0.0], 1.0, [127, -127, 0]),
        ([127.0, 63.5, -63.5], 1.0, [127, 64, -64]),
        ([127.0, 0.5, 1.5, 2.5, -0.5, -1.5], 1.0, [127, 0, 2, 2, 0, -2]),
        ([2.0**-20 * 127, 2.0**-21 * 127], 2.0**-20, [127, 64]),
    ],
)
def test_quantizer_uses_round_to_nearest_even_and_never_clips(row, scale, expected):
    weight = torch.tensor([row], dtype=torch.float32)
    quantized, stored = frozen_int8.quantize_weight(weight)
    assert int(stored[0].view(torch.int32)) == int(torch.tensor([scale], dtype=torch.float32).view(torch.int32))
    assert quantized[0].tolist() == expected


def test_scale_ceiling_is_never_below_the_exact_absmax_over_127():
    for numerator in (1, 2, 127, 128, 255, 32767, 32768):
        for exponent in (-30, -1, 0, 1, 20):
            maximum = Fraction(numerator) * power_two(exponent)
            bits = ceil_bits(maximum / 127)
            assert fraction_from_bits(bits) >= maximum / 127
            if bits:
                previous = fraction_from_bits(bits - 1)
                assert previous < maximum / 127 or bits == 0


@pytest.mark.parametrize(
    "bits",
    [127, 128, 0x007FFFFF, 0x00800000, 0x00800001, 0x3F800000, 0x3F800001, 0x7F7FFFFF],
)
def test_weight_scale_ceiling_matches_oracle_at_fp32_boundaries(bits):
    negative = (bits | 0x80000000) - (1 << 32)
    weight = torch.tensor([bits, negative], dtype=torch.int32).view(torch.float32).reshape(1, 2)
    quantized, scale = frozen_int8.quantize_weight(weight)
    maximum = fraction_from_bits(bits)
    expected_scale = ceil_bits(maximum / 127)
    assert int(scale[0].view(torch.int32)) == expected_scale
    exact_scale = fraction_from_bits(expected_scale)
    assert quantized[0].tolist() == [
        round_half_even(maximum / exact_scale),
        -round_half_even(maximum / exact_scale),
    ]


def test_quantizer_accepts_the_minimum_supported_row_scale():
    exact_minimum = power_two(-149) * 127
    weight = torch.tensor([float(exact_minimum), -float(exact_minimum)], dtype=torch.float32).reshape(1, 2)
    quantized, scale = frozen_int8.quantize_weight(weight)
    assert int(scale[0].view(torch.int32)) == 1
    assert quantized[0].tolist() == [127, -127]


def test_zero_and_fp16_subnormal_rows_are_explicit():
    weight = torch.tensor(
        [[0.0, -0.0, 0.0], [2.0**-24, -(2.0**-24), 2.0**-25], [2.0**-14, 0.0, 2.0**-15]],
        dtype=torch.float16,
    )
    quantized, scale = frozen_int8.quantize_weight(weight)
    assert int(scale[0].view(torch.int32)) == 0
    assert quantized[0].tolist() == [0, 0, 0]
    for row in (1, 2):
        assert scale[row] > 0
        assert max(abs(value) for value in quantized[row].tolist()) == 127


@pytest.mark.parametrize(
    "weight",
    [
        torch.tensor([[0.0, 0.0]], dtype=torch.float32).reshape(1, 1, 2),
        torch.tensor([], dtype=torch.float32).reshape(0, 2),
        torch.tensor([[0.0]], dtype=torch.float32).repeat(1, 32769),
        torch.tensor([[float("inf")]], dtype=torch.float32),
        torch.tensor([[float("nan")]], dtype=torch.float32),
    ],
)
def test_quantizer_rejects_unsupported_matrices(weight):
    with pytest.raises(ReferenceArithmeticError):
        frozen_int8.quantize_weight(weight)


def test_quantizer_rejects_a_nonzero_fp32_row_below_the_smallest_supported_scale():
    with pytest.raises(ReferenceArithmeticError, match="small"):
        frozen_int8.quantize_weight(torch.tensor([[2.0**-149]], dtype=torch.float32))


def test_artifact_roundtrip_is_byte_deterministic_and_row_major(tmp_path):
    quantized = torch.tensor([[1, 2, 3], [4, 5, 6]], dtype=torch.int8)
    scale = torch.tensor([1.0, 0.5], dtype=torch.float32)
    first, first_digest = artifact_file(tmp_path, quantized, scale, {"note": "first"}, "first.fint8")
    second, second_digest = artifact_file(tmp_path, quantized, scale, {"note": "first"}, "second.fint8")
    assert first_digest == second_digest
    assert first.read_bytes() == second.read_bytes()
    assert frozen_int8.artifact_digest(quantized, scale, metadata={"note": "first"}) == first_digest
    assert frozen_int8.artifact_bytes(quantized, scale, metadata={"note": "first"}) == first.read_bytes()
    reordered, reordered_digest = artifact_file(tmp_path, quantized, scale, {"b": 2, "a": 1}, "reordered.fint8")
    canonical, canonical_digest = artifact_file(tmp_path, quantized, scale, {"a": 1, "b": 2}, "canonical.fint8")
    assert reordered_digest == canonical_digest
    assert reordered.read_bytes() == canonical.read_bytes()

    header_length = int.from_bytes(first.read_bytes()[8:16], "little")
    payload = first.read_bytes()[16 + header_length : 16 + header_length + 6]
    assert payload == bytes([1, 2, 3, 4, 5, 6])
    loaded = frozen_int8.read_artifact(first, expected_sha256=first_digest)
    assert loaded.weight_q.tolist() == quantized.tolist()
    assert loaded.weight_scale.tolist() == scale.tolist()
    assert loaded.sha256 == first_digest


def test_artifact_hash_covers_metadata_and_payload(tmp_path):
    quantized = torch.tensor([[7, 8]], dtype=torch.int8)
    scale = torch.tensor([1.0], dtype=torch.float32)
    _, first = artifact_file(tmp_path, quantized, scale, {"note": "a"}, "a.fint8")
    _, second = artifact_file(tmp_path, quantized, scale, {"note": "b"}, "b.fint8")
    assert first != second
    changed = quantized.clone()
    changed[0, 0] = 9
    _, third = artifact_file(tmp_path, changed, scale, {"note": "a"}, "c.fint8")
    assert first != third


def test_artifact_admission_recomputes_the_content_address_and_seals_live_storage():
    quantized = torch.tensor([[1, 2], [3, 4]], dtype=torch.int8)
    scale = torch.tensor([1.0, 2.0], dtype=torch.float32)
    digest = frozen_int8.artifact_digest(quantized, scale)
    artifact = frozen_int8.FrozenInt8Artifact(quantized, scale, {}, digest, frozen_int8.ARTIFACT_FORMAT_VERSION)
    artifact.verify()
    with pytest.raises(ReferenceArithmeticError, match="version"):
        frozen_int8.FrozenInt8Artifact(quantized, scale, {}, digest, frozen_int8.ARTIFACT_FORMAT_VERSION + 1)
    with pytest.raises(ReferenceArithmeticError, match="digest"):
        frozen_int8.FrozenInt8Artifact(quantized, scale, {"forged": True}, digest, frozen_int8.ARTIFACT_FORMAT_VERSION)
    with pytest.raises(ReferenceArithmeticError, match="digest"):
        frozen_int8.FrozenInt8Artifact(quantized, scale, {}, "0" * 64, frozen_int8.ARTIFACT_FORMAT_VERSION)
    with pytest.raises(ReferenceArithmeticError, match="digest"):
        frozen_int8.verify_payload(quantized, scale, {}, "0" * 64)

    quantized[0, 0] = 9
    with pytest.raises(ReferenceArithmeticError, match="changed after verification"):
        artifact.verify()
    with pytest.raises(ReferenceArithmeticError, match="changed after verification"):
        frozen_int8.linear(torch.ones((1, 2), dtype=torch.float32), artifact)


def test_artifact_verify_rehashes_a_storage_write_that_bypasses_the_version_counter():
    quantized = torch.tensor([[1, 2], [3, 4]], dtype=torch.int8)
    scale = torch.tensor([1.0, 2.0], dtype=torch.float32)
    digest = frozen_int8.artifact_digest(quantized, scale)
    artifact = frozen_int8.FrozenInt8Artifact(quantized, scale, {}, digest, frozen_int8.ARTIFACT_FORMAT_VERSION)
    with torch.no_grad():
        quantized.data[0, 0] = 7
    with pytest.raises(ReferenceArithmeticError, match="no longer matches"):
        artifact.verify()


def test_artifact_metadata_mutation_breaks_the_seal_before_arithmetic():
    quantized = torch.tensor([[1, 2], [3, 4]], dtype=torch.int8)
    scale = torch.tensor([1.0, 2.0], dtype=torch.float32)
    digest = frozen_int8.artifact_digest(quantized, scale, metadata={"module": "q"})
    artifact = frozen_int8.FrozenInt8Artifact(
        quantized, scale, {"module": "q"}, digest, frozen_int8.ARTIFACT_FORMAT_VERSION
    )
    artifact.metadata["module"] = "forged"
    with pytest.raises(ReferenceArithmeticError, match="metadata changed"):
        artifact.verify()
    with pytest.raises(ReferenceArithmeticError, match="metadata changed"):
        frozen_int8.linear(torch.ones((1, 2), dtype=torch.float32), artifact)


def test_linear_consumes_the_audit_artifact_at_the_max_finite_rounding_boundary():
    source = torch.tensor([[1.0, 2.0**-6, 127.0 / 64.0 - 2.0**-23]], dtype=torch.float32)
    quantized, scale = frozen_int8.quantize_weight(source)
    assert quantized.tolist() == [[64, 1, 127]]
    assert int(scale.view(torch.int32)[0]) & 0xFFFFFFFF == 0x3C7FFFFF
    value = torch.tensor([[3.4028234663852886e38, 2.0**106, 0.0]], dtype=torch.float32)
    artifact = frozen_int8.FrozenInt8Artifact(
        quantized,
        scale,
        {},
        frozen_int8.artifact_digest(quantized, scale),
        frozen_int8.ARTIFACT_FORMAT_VERSION,
    )
    output = frozen_int8.linear(value, artifact)
    assert int(output.view(torch.int32)[0]) & 0xFFFFFFFF == 0x7F7FFFFF


def test_reader_rejects_payload_header_and_expected_hash_tampering(tmp_path):
    quantized = torch.tensor([[1, 2], [3, 4]], dtype=torch.int8)
    scale = torch.tensor([1.0, 2.0], dtype=torch.float32)
    path, digest = artifact_file(tmp_path, quantized, scale)
    original = path.read_bytes()
    header_length = int.from_bytes(original[8:16], "little")

    payload = bytearray(original)
    payload[16 + header_length] ^= 1
    path.write_bytes(payload)
    with pytest.raises(ReferenceArithmeticError, match="[Hh]ash"):
        frozen_int8.read_artifact(path)

    header = bytearray(original)
    header[20] ^= 1
    path.write_bytes(header)
    with pytest.raises(ReferenceArithmeticError):
        frozen_int8.read_artifact(path)

    path.write_bytes(original)
    with pytest.raises(ReferenceArithmeticError, match="[Hh]ash"):
        frozen_int8.read_artifact(path, expected_sha256="0" * 64)

    path.write_bytes(b"BADMAGIC" + original[8:])
    with pytest.raises(ReferenceArithmeticError):
        frozen_int8.read_artifact(path)
    assert digest != "0" * 64


def replace_header(path, mutate):
    data = path.read_bytes()
    length = int.from_bytes(data[8:16], "little")
    header = json.loads(data[16 : 16 + length])
    mutate(header)
    raw = json.dumps(header, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    path.write_bytes(data[:8] + len(raw).to_bytes(8, "little") + raw + data[16 + length :])


def splice_header(path, raw):
    data = path.read_bytes()
    length = int.from_bytes(data[8:16], "little")
    path.write_bytes(data[:8] + len(raw).to_bytes(8, "little") + raw + data[16 + length :])


def test_reader_rejects_descriptor_dtype_and_noninteger_header_identity(tmp_path):
    path, _ = artifact_file(
        tmp_path,
        torch.tensor([[1, 2], [3, 4]], dtype=torch.int8),
        torch.tensor([1.0, 2.0], dtype=torch.float32),
    )
    original = path.read_bytes()

    def wrong_dtype(header):
        header["tensors"]["weight_q"]["dtype"] = "float32"

    replace_header(path, wrong_dtype)
    with pytest.raises(ReferenceArithmeticError, match="descriptor"):
        frozen_int8.read_artifact(path)

    path.write_bytes(original)

    def boolean_version(header):
        header["formatVersion"] = True

    replace_header(path, boolean_version)
    with pytest.raises(ReferenceArithmeticError, match="identity"):
        frozen_int8.read_artifact(path)


def test_reader_rejects_duplicate_keys_noncanonical_json_and_trailing_bytes(tmp_path):
    path, _ = artifact_file(
        tmp_path,
        torch.tensor([[1, 2]], dtype=torch.int8),
        torch.tensor([1.0], dtype=torch.float32),
    )
    original = path.read_bytes()
    header_length = int.from_bytes(original[8:16], "little")
    header = original[16 : 16 + header_length]

    duplicate = header[:-1] + b',"format":"' + frozen_int8.ARTIFACT_FORMAT.encode("ascii") + b'"}'
    splice_header(path, duplicate)
    with pytest.raises(ReferenceArithmeticError, match="header"):
        frozen_int8.read_artifact(path)

    path.write_bytes(original)
    splice_header(path, header.replace(b",", b", ", 1))
    with pytest.raises(ReferenceArithmeticError, match="[Nn]oncanonical|Invalid"):
        frozen_int8.read_artifact(path)

    path.write_bytes(original + b"\0")
    with pytest.raises(ReferenceArithmeticError, match="size"):
        frozen_int8.read_artifact(path)


def test_writer_rejects_zero_scale_on_a_zero_row_and_noncanonical_metadata(tmp_path):
    with pytest.raises(ReferenceArithmeticError, match="zero"):
        frozen_int8.write_artifact(
            tmp_path / "bad.fint8",
            torch.tensor([[0, 0]], dtype=torch.int8),
            torch.tensor([1.0], dtype=torch.float32),
            metadata={},
        )
    with pytest.raises(ReferenceArithmeticError):
        frozen_int8.write_artifact(
            tmp_path / "bad.fint8",
            torch.tensor([[1, 2]], dtype=torch.int8),
            torch.tensor([1.0], dtype=torch.float32),
            metadata={"not": float("nan")},
        )


@pytest.mark.parametrize("scale", [-1.0, -0.0, float("inf"), float("nan")])
def test_writer_rejects_negative_zero_negative_and_nonfinite_scales(tmp_path, scale):
    with pytest.raises(ReferenceArithmeticError):
        frozen_int8.write_artifact(
            tmp_path / "bad.fint8",
            torch.tensor([[1, 2]], dtype=torch.int8),
            torch.tensor([scale], dtype=torch.float32),
            metadata={},
        )


def test_writer_rejects_minus_128_and_scale_relationship_errors(tmp_path):
    with pytest.raises(ReferenceArithmeticError, match="126|range|127"):
        frozen_int8.write_artifact(
            tmp_path / "bad.fint8",
            torch.tensor([[-128, 0]], dtype=torch.int8),
            torch.tensor([1.0], dtype=torch.float32),
            metadata={},
        )
    with pytest.raises(ReferenceArithmeticError):
        frozen_int8.write_artifact(
            tmp_path / "bad.fint8",
            torch.tensor([[1, 2]], dtype=torch.int8),
            torch.tensor([0.0], dtype=torch.float32),
            metadata={},
        )


@pytest.mark.parametrize(
    "value,exponent",
    [
        (0, 0),
        (1, -149),
        (1, -150),
        (3, -151),
        (3, -150),
        ((1 << 23) - 1, -149),
        ((1 << 63) - 1, -44),
        (1 << 63, -44),
        (1 << 68, -44),
        (-(1 << 68), -44),
        (1 << 68, -100),
        (1 << 68, -200),
    ],
)
def test_scaled_integer_encoder_matches_independent_representable_search(value, exponent):
    exact = Fraction(value) * power_two(exponent)
    try:
        expected = float_bits(exact)
    except ReferenceArithmeticError:
        with pytest.raises(ReferenceArithmeticError, match="[Oo]verflow|Nonfinite"):
            frozen_int8.encode_scaled_integer_bits(value, exponent)
    else:
        assert frozen_int8.encode_scaled_integer_bits(value, exponent) == expected


def test_scaled_integer_encoder_random_boundaries_and_overflow():
    generator = random.Random(99)
    for _ in range(300):
        value = generator.randint(-(1 << 68), 1 << 68)
        exponent = generator.randint(-260, 120)
        exact = Fraction(value) * power_two(exponent)
        try:
            expected = float_bits(exact)
        except ReferenceArithmeticError:
            with pytest.raises(ReferenceArithmeticError):
                frozen_int8.encode_scaled_integer_bits(value, exponent)
        else:
            assert frozen_int8.encode_scaled_integer_bits(value, exponent) == expected
    with pytest.raises(ReferenceArithmeticError):
        frozen_int8.encode_scaled_integer_bits(1, 128)
    with pytest.raises(ReferenceArithmeticError):
        frozen_int8.encode_scaled_integer_bits(1, -2049)


def test_scaled_integer_encoder_exact_max_and_smallest_normal_boundaries():
    maximum = 0x7F7FFFFF
    assert frozen_int8.encode_scaled_integer_bits((1 << 24) - 1, 104) == maximum
    assert frozen_int8.encode_scaled_integer_bits(((1 << 24) - 1) << 1, 103) == maximum
    with pytest.raises(ReferenceArithmeticError, match="[Oo]verflow|Nonfinite"):
        frozen_int8.encode_scaled_integer_bits(1 << 24, 104)
    with pytest.raises(ReferenceArithmeticError, match="[Oo]verflow|Nonfinite"):
        frozen_int8.encode_scaled_integer_bits((((1 << 24) - 1) << 1) + 1, 103)
    assert frozen_int8.encode_scaled_integer_bits(1 << 23, -149) == 0x00800000
    assert frozen_int8.encode_scaled_integer_bits((1 << 24) - 1, -150) == 0x00800000
    assert frozen_int8.encode_scaled_integer_bits((1 << 24) - 2, -150) == 0
    assert frozen_int8.encode_scaled_integer_bits(-((1 << 24) - 2), -150) == 0x80000000


def test_encoder_rounds_down_to_max_finite_above_max_finite_below_the_overflow_midpoint():
    # 2**102 above max-finite and 2**102 below the RNE overflow midpoint. IEEE RNE still returns max-finite.
    integer = (((1 << 24) - 1) << 2) + 1
    exact = Fraction(integer) * power_two(102)
    assert Fraction((1 << 24) - 1) * power_two(104) < exact < Fraction(2**128) - power_two(103)
    assert float_bits(exact) == 0x7F7FFFFF
    assert float_bits(-exact) == 0xFF7FFFFF
    assert frozen_int8.encode_scaled_integer_bits(integer, 102) == 0x7F7FFFFF
    assert frozen_int8.encode_scaled_integer_bits(-integer, 102) == 0xFF7FFFFF


@pytest.mark.parametrize("integer", [((((1 << 24) - 1) << 2) + 2), ((((1 << 24) - 1) << 2) + 3)])
def test_encoder_overflows_at_or_above_the_rne_overflow_midpoint(integer):
    exact = Fraction(integer) * power_two(102)
    assert exact >= Fraction(2**128) - power_two(103)
    with pytest.raises(ReferenceArithmeticError):
        float_bits(exact)
    with pytest.raises(ReferenceArithmeticError, match="[Oo]verflow|Nonfinite"):
        frozen_int8.encode_scaled_integer_bits(integer, 102)
    with pytest.raises(ReferenceArithmeticError, match="[Oo]verflow|Nonfinite"):
        frozen_int8.encode_scaled_integer_bits(-integer, 102)


def test_scaled_integer_encoder_rounds_normal_ties_to_even():
    for value in (2**24 + 1, 2**24 + 3, 2**25 + 2):
        expected = float_bits(Fraction(value))
        assert frozen_int8.encode_scaled_integer_bits(value, 0) == expected


def test_linear_matches_independent_rational_projection_and_bias(tmp_path):
    generator = torch.Generator().manual_seed(1207)
    weight = torch.randn((5, 33), generator=generator, dtype=torch.float32).to(torch.float16)
    value = torch.randn((3, 33), generator=generator, dtype=torch.float32)
    bias = torch.randn((5,), generator=generator, dtype=torch.float16)
    quantized, scale = frozen_int8.quantize_weight(weight)
    path, digest = artifact_file(tmp_path, quantized, scale)
    artifact = frozen_int8.read_artifact(path, expected_sha256=digest)
    expected = projection_oracle(value, quantized, scale, bias)
    for output_tile in (1, 2, 32):
        actual = frozen_int8.linear(value, artifact, bias, output_tile=output_tile)
        assert actual.dtype == torch.float32 and actual.shape == (3, 5)
        assert torch.equal(actual.view(torch.int32), expected.view(torch.int32))


def test_linear_is_independent_of_row_order_and_output_tile(tmp_path):
    generator = torch.Generator().manual_seed(88)
    weight = torch.randn((4, 19), generator=generator, dtype=torch.float16)
    value = torch.randn((3, 19), generator=generator, dtype=torch.float32)
    quantized, scale = frozen_int8.quantize_weight(weight)
    path, _ = artifact_file(tmp_path, quantized, scale)
    artifact = frozen_int8.read_artifact(path)
    first = frozen_int8.linear(value, artifact, output_tile=7)
    second = frozen_int8.linear(value[[2, 0, 1]], artifact, output_tile=1)
    assert torch.equal(first.view(torch.int32)[[2, 0, 1]], second.view(torch.int32))
    assert torch.equal(first, frozen_int8.linear(value, artifact, output_tile=32))


def test_linear_supports_1d_width_one_input(tmp_path):
    weight = torch.tensor([[0.75]], dtype=torch.float16)
    value = torch.tensor([1.25], dtype=torch.float32)
    quantized, scale = frozen_int8.quantize_weight(weight)
    path, _ = artifact_file(tmp_path, quantized, scale)
    artifact = frozen_int8.read_artifact(path)
    expected = projection_oracle(value, quantized, scale).reshape(-1)
    actual = frozen_int8.linear(value, artifact)
    assert actual.shape == (1,)
    assert torch.equal(actual.view(torch.int32), expected.view(torch.int32))


def test_identity_names_the_format_and_is_not_a_qualification():
    identity = frozen_int8.identity()
    assert identity["format"] == "heteroes.frozen-int8-b22"
    assert identity["formatVersion"] == 1
    assert identity["magnitudeBits"] == 22
    assert identity["activationLimbs"] == 3
    assert identity["maxWidth"] == 32768
    assert identity["hardwareQualified"] is False
    assert len(identity["sourceSha256"]) == 64


def test_artifact_exposes_no_dequantized_weight_tensor(tmp_path):
    quantized = torch.tensor([[1, 2, 3]], dtype=torch.int8)
    scale = torch.tensor([1.0], dtype=torch.float32)
    path, _ = artifact_file(tmp_path, quantized, scale)
    artifact = frozen_int8.read_artifact(path)
    assert artifact.weight_q.dtype == torch.int8
    assert artifact.weight_scale.dtype == torch.float32
    assert not any(
        isinstance(getattr(artifact, field.name), torch.Tensor)
        and getattr(artifact, field.name).dtype == torch.float32
        and tuple(getattr(artifact, field.name).shape) == tuple(quantized.shape)
        for field in __import__("dataclasses").fields(artifact)
    )
