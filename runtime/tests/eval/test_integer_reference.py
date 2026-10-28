"""Independent rational oracles for a NEW integer projection contract, not the FP32 pairwise tree."""

from fractions import Fraction
import random

import pytest
import torch

from heteroes.strict.reference_ops import ReferenceArithmeticError


def reference():
    from heteroes.strict import integer_reference

    return integer_reference


def fraction_from_bits(bits):
    sign = -1 if bits >> 31 else 1
    exponent, mantissa = (bits >> 23) & 255, bits & 0x7FFFFF
    assert exponent != 255
    if exponent:
        mantissa |= 1 << 23
    power = (exponent - 127 - 23) if exponent else -149
    return sign * Fraction(mantissa) * power_two(power)


def power_two(exponent):
    return Fraction(2**exponent) if exponent >= 0 else Fraction(1, 2**-exponent)


def rational_float_bits(value):
    """Binary-search representable float values; never round through binary64."""
    if not value:
        return 0
    sign, value = (0x80000000 if value < 0 else 0), abs(value)
    overflow = power_two(128) - power_two(103)
    if value >= overflow:
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


def rational_quantize(row, magnitude_bits):
    values = [fraction_from_bits(int(u) & 0xFFFFFFFF) for u in row.contiguous().view(torch.int32)]
    values = [v if abs(v) >= power_two(-126) else Fraction(0) for v in values]
    maximum = max(map(abs, values))
    if not maximum:
        return [0] * len(values), 0
    exponent = maximum.numerator.bit_length() - maximum.denominator.bit_length()
    if maximum < power_two(exponent):
        exponent -= 1
    scale = power_two(exponent - (magnitude_bits - 1))
    return [round(v / scale) for v in values], exponent


@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_quantize_rows_matches_exact_rational_rounding_not_another_float_operation(magnitude_bits):
    gen = torch.Generator().manual_seed(729)
    values = torch.randn(7, 37, generator=gen) * torch.logspace(-37, 37, 37)
    values[1] = -0.0
    values[2, :5] = torch.tensor([1, 0x007FFFFF, 0x00800000, 0x00800001, 0x7F7FFFFF], dtype=torch.int32).view(
        torch.float32
    )
    # Halfway ties at the chosen row scale; both signs and both parity directions.
    step = 2.0 ** -(magnitude_bits - 1)
    values[3] = 0
    values[3, :7] = torch.tensor([1.0, 2.5 * step, 3.5 * step, -2.5 * step, -3.5 * step, 0.0, -0.0])
    expected = [rational_quantize(row, magnitude_bits) for row in values]
    actual, exponents = reference().quantize_rows(values, magnitude_bits=magnitude_bits)
    assert actual.dtype == torch.int32 and exponents.dtype == torch.int32
    assert actual.tolist() == [q for q, _ in expected]
    assert exponents.tolist() == [e for _, e in expected]
    assert actual.abs().max().item() <= 2**magnitude_bits


@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_signed_radix_limbs_reconstruct_endpoints_and_carries(magnitude_bits):
    edge = 2**magnitude_bits
    values = torch.tensor(
        [[-edge, -edge + 1, -32769, -32768, -129, -128, -127, -1, 0, 1, 127, 128, 129, 32767, edge - 1, edge]],
        dtype=torch.int32,
    )
    values = values.clamp(-edge, edge)
    digits = reference().balanced_digits(values, magnitude_bits=magnitude_bits)
    assert len(digits) == (2 if magnitude_bits == 14 else 3)
    assert all(t.dtype == torch.int8 for t in digits)
    reconstructed = sum(digit.to(torch.int64) * 256**i for i, digit in enumerate(digits))
    assert torch.equal(reconstructed, values.to(torch.int64))
    assert digits[-1].to(torch.int32).abs().max().item() <= 64
    with pytest.raises(ReferenceArithmeticError):
        reference().balanced_digits(torch.tensor([[-(2**31)]], dtype=torch.int32), magnitude_bits=magnitude_bits)


@pytest.mark.parametrize(
    "integer,exponent",
    [
        (0, 0),
        (0, -512),
        (1, 0),
        (-1, 0),
        (2**24 + 1, 0),
        (2**24 + 3, 0),
        (2**54 + 2**30 + 1, -30),
        (2**54 + 2**30 - 1, -30),
        (2**60 - 1, -150),
        (2**24 - 1, -150),
        (2**24 - 2, -150),
        (-(2**24 - 1), -150),
        (1, -149),
        (-1, -149),
        (1, -512),
        (-1, -512),
        (1, -126),
        (2**25 - 2, 103),
        (2**25 - 1, 103),
        (2**25, 103),
        (2**62 - 1, 512),
    ],
)
def test_scaled_integer_encoding_matches_independent_representable_value_search(integer, exponent):
    exact = Fraction(integer) * power_two(exponent)
    try:
        expected = rational_float_bits(exact)
    except ReferenceArithmeticError:
        with pytest.raises(ReferenceArithmeticError, match="[Nn]onfinite|overflow"):
            reference().scaled_integer_bits(integer, exponent)
    else:
        assert reference().scaled_integer_bits(integer, exponent) == expected


def test_scaled_encoding_random_signed_int64_values_across_normal_and_underflow_boundaries():
    gen = random.Random(9128)
    for _ in range(100):
        value = gen.randrange(-(2**62), 2**62)
        exponent = gen.randrange(-230, 60)
        exact = Fraction(value) * power_two(exponent)
        assert reference().scaled_integer_bits(value, exponent) == rational_float_bits(exact)


@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_linear_matches_rational_projection_and_is_independent_of_rows_outputs_and_tiles(magnitude_bits):
    gen = torch.Generator().manual_seed(723)
    x = torch.randn(3, 7, generator=gen)
    x[1] = -0.0
    w = torch.randn(5, 7, generator=gen).half()
    b = torch.tensor([0.25, -0.125, 1.0, -2.0, 0.5], dtype=torch.float16)
    qx = [rational_quantize(row, magnitude_bits) for row in x]
    qw = [rational_quantize(row, magnitude_bits) for row in w.float()]
    expected = []
    for row, ex in qx:
        values = []
        for j, (weights, ew) in enumerate(qw):
            dot = sum(a * b for a, b in zip(row, weights))
            bits = rational_float_bits(Fraction(dot) * power_two(ex + ew - 2 * (magnitude_bits - 1)))
            values.append(rational_float_bits(fraction_from_bits(bits) + Fraction(float(b[j]))))
        expected.append([u if u < 2**31 else u - 2**32 for u in values])
    expected = torch.tensor(expected, dtype=torch.int32)
    for tile in (1, 3, 32):
        actual = reference().linear(x, w, b, magnitude_bits=magnitude_bits, output_tile=tile)
        assert torch.equal(actual.view(torch.int32), expected)
        permuted = reference().linear(x[[2, 0]], w[[4, 1]], b[[4, 1]], magnitude_bits=magnitude_bits)
        assert torch.equal(permuted.view(torch.int32), expected[[2, 0]][:, [4, 1]])


@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_linear_zero_policy_extreme_scale_and_limb_accumulation_bound(magnitude_bits):
    x = torch.tensor([[-0.0, -0.0, -0.0], [2.0**-126, 2.0**-126, 2.0**-126]])
    w = torch.ones(2, 3, dtype=torch.float16)
    actual = reference().linear(x, w, magnitude_bits=magnitude_bits)
    assert actual.view(torch.int32)[0].tolist() == [0, 0]  # new contract explicitly uses +0 for integer zero
    assert actual[1].tolist() == [3 * 2.0**-126] * 2
    bound = 32768 * (2**magnitude_bits) ** 2
    assert bound <= 2**59 and 128**2 * 32768 == 2**29
    q = torch.full((1, 32768), 2**magnitude_bits, dtype=torch.int32)
    digits = reference().balanced_digits(q, magnitude_bits=magnitude_bits)
    reconstructed = sum(
        (a.to(torch.int64) @ b.to(torch.int64).T) * 256 ** (i + j)
        for i, a in enumerate(digits)
        for j, b in enumerate(digits)
    )
    assert reconstructed.item() == bound


@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_equal_radix_degree_products_can_share_int32_accumulators_without_overflow(magnitude_bits):
    # There are at most three products in a radix degree. This is also the bound for every partial sum,
    # regardless of input signs or integer-MMA accumulation order.
    width = reference().MAX_WIDTH
    assert 3 * 128**2 * width < 2**31
    edge = 2**magnitude_bits
    pattern = torch.tensor([-edge, -edge + 1, -129, -128, -1, 0, 127, 128, edge - 1, edge], dtype=torch.int32)
    q = pattern.repeat((width + len(pattern) - 1) // len(pattern))[:width][None]
    w = q.flip(1)
    a, b = (
        reference().balanced_digits(q, magnitude_bits=magnitude_bits),
        reference().balanced_digits(w, magnitude_bits=magnitude_bits),
    )
    coefficients = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            coefficients[i + j] += int((x.to(torch.int32) @ y.to(torch.int32).T).item())
            assert abs(coefficients[i + j]) < 2**31
    assert sum(c * 256**i for i, c in enumerate(coefficients)) == int((q.to(torch.int64) @ w.to(torch.int64).T).item())


@pytest.mark.parametrize("bits", [0, 8, 15, 23, True, 14.0])
def test_unknown_precision_refused_before_computation(bits):
    with pytest.raises(ReferenceArithmeticError):
        reference().quantize_rows(torch.ones(1, 3), magnitude_bits=bits)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_input_weight_or_bias_fails_explicitly(bad):
    module = reference()
    with pytest.raises(ReferenceArithmeticError):
        module.quantize_rows(torch.tensor([[bad, 1.0]]))
    with pytest.raises(ReferenceArithmeticError):
        module.linear(torch.ones(1, 3), torch.tensor([[1.0, bad, 1.0]], dtype=torch.float16))
    with pytest.raises(ReferenceArithmeticError):
        module.linear(torch.ones(1, 3), torch.ones(1, 3, dtype=torch.float16), torch.tensor([bad], dtype=torch.float16))


def test_new_identity_names_arithmetic_precision_and_source_and_cannot_claim_qualification():
    a, b = reference().identity(14), reference().identity(22)
    assert a["operator"] != "pairwise_f32_reference_v1_experimental"
    assert a != b and a["magnitudeBits"] == 14 and b["magnitudeBits"] == 22
    assert a["hardwareQualified"] is False and len(a["sourceSha256"]) == 64
