"""CUDA frozen-int8 projection must match the independent exact CPU oracle bit for bit."""

import os
import random

import pytest
import torch

from heteroes.strict import frozen_int8
from heteroes.strict.reference_ops import ReferenceArithmeticError

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(),
    reason="explicit GPU opt-in",
)

pytestmark = gpu


def kernels():
    from heteroes.strict.frozen_int8_cuda import FrozenInt8CudaKernels

    return FrozenInt8CudaKernels("cuda", max_partial_bytes=32 * 1024**2)


def bits(value):
    return value.contiguous().view(torch.int32)


def artifact_for(weight_q, weight_scale, metadata=None):
    metadata = {} if metadata is None else metadata
    digest = frozen_int8.artifact_digest(weight_q, weight_scale, metadata=metadata)
    return frozen_int8.FrozenInt8Artifact(
        weight_q=weight_q,
        weight_scale=weight_scale,
        metadata=metadata,
        sha256=digest,
        format_version=frozen_int8.ARTIFACT_FORMAT_VERSION,
    )


def random_case(rows, width, outputs, seed, *, bias=True, zeros=False):
    generator = torch.Generator().manual_seed(seed)
    weight = torch.randn((outputs, width), generator=generator, dtype=torch.float32).half()
    if zeros:
        weight[0, 0] = 0.0
    quantized, scale = frozen_int8.quantize_weight(weight)
    source_bias = None
    if bias:
        source_bias = torch.randn((outputs,), generator=generator, dtype=torch.float32).half()
    value = torch.randn((rows, width), generator=generator, dtype=torch.float32) * 0.37
    if zeros:
        value[0, 0] = 0.0
    return weight, quantized, scale, source_bias, value


@torch.inference_mode()
def compare(kernel, value, weight_q, weight_scale, bias, *, output_tile=32, **options):
    artifact = artifact_for(weight_q, weight_scale)
    expected = frozen_int8.linear(value, artifact, bias, output_tile=output_tile)
    actual = kernel.linear(
        value.cuda(),
        weight_q.cuda(),
        weight_scale.cuda(),
        None if bias is None else bias.cuda(),
        **options,
    )
    assert actual.shape == expected.shape
    assert torch.equal(bits(actual.cpu()), bits(expected))


def test_encoder_matches_the_python_big_integer_oracle():
    kernel = kernels()
    cases = [
        (0, 1, 0),
        (0, 0, -2048),
        ((1 << 24) - 1, 1, 104),
        ((1 << 24) - 2, 1, 104),
        (-((1 << 24) - 1), 1, 104),
        (1 << 23, 1, -149),
        (1 << 23, 1, -150),
        ((1 << 24) - 2, 1, -150),
        ((1 << 44) - 1, (1 << 24) - 1, -44),
        (-((1 << 44) - 1), (1 << 24) - 1, -44),
        ((1 << 44) - 1, 1, -44),
        (127 * (1 << 22), 0x800000, -149),
        # Exact RNE ties: subnormal zero/minimum, and normals rounding down/up on odd and even wholes.
        (1, 1, -150),
        (3, 1, -150),
        ((1 << 24) + 1, 1, -24),
        ((1 << 24) + 3, 1, -24),
        (-((1 << 24) + 1), 1, -24),
        (-((1 << 24) + 3), 1, -24),
        # The high limb addition carries: low32(magnitude)=all ones and the product below the split is all ones.
        (0x00010001FFFFFFFF, 0xFFFF, -40),
        (-0x00010001FFFFFFFF, 0xFFFF, -40),
        # Just above max-finite but below the RNE overflow midpoint: rounds down to max-finite.
        ((((1 << 24) - 1) << 2) + 1, 1, 102),
        (-((((1 << 24) - 1) << 2) + 1), 1, 102),
    ]
    generator = random.Random(20261025)
    for _ in range(300):
        cases.append(
            (
                generator.randrange(-(1 << 44), 1 << 44),
                generator.randrange(1, 1 << 24),
                generator.randrange(-2048, 128),
            )
        )
    for _ in range(80):
        cases.append(
            (
                generator.randrange(-(1 << 63), 1 << 63),
                generator.randrange(1, 1 << 24),
                generator.randrange(-2048, 128),
            )
        )
    sums, significands, exponents, expected = [], [], [], []
    for total, significand, exponent in cases:
        try:
            exact = frozen_int8.encode_scaled_integer_bits(total * significand, exponent)
        except ReferenceArithmeticError:
            continue
        sums.append(total)
        significands.append(significand)
        exponents.append(exponent)
        expected.append(exact)
    actual = kernel.encode_products(
        torch.tensor(sums, dtype=torch.int64, device="cuda"),
        torch.tensor(significands, dtype=torch.int32, device="cuda"),
        torch.tensor(exponents, dtype=torch.int32, device="cuda"),
    )
    expected_bits = torch.tensor(expected, dtype=torch.uint32).view(torch.int32)
    assert torch.equal(bits(actual.cpu()), expected_bits)


def test_encoder_flags_overflow_and_unsupported_exponent():
    kernel = kernels()
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        kernel.encode_products(
            torch.tensor([1 << 44, 1 << 44], dtype=torch.int64, device="cuda"),
            torch.tensor([(1 << 24) - 1, (1 << 24) - 1], dtype=torch.int32, device="cuda"),
            torch.tensor([61, 61], dtype=torch.int32, device="cuda"),
        )
    with pytest.raises(ReferenceArithmeticError):
        kernel.encode_products(
            torch.tensor([1], dtype=torch.int64, device="cuda"),
            torch.tensor([1], dtype=torch.int32, device="cuda"),
            torch.tensor([-2049], dtype=torch.int32, device="cuda"),
        )


def test_encoder_matches_the_rne_overflow_midpoint_and_below_it():
    kernel = kernels()
    below = (((1 << 24) - 1) << 2) + 1
    actual = kernel.encode_products(
        torch.tensor([below, -below], dtype=torch.int64, device="cuda"),
        torch.tensor([1, 1], dtype=torch.int32, device="cuda"),
        torch.tensor([102, 102], dtype=torch.int32, device="cuda"),
    )
    assert bits(actual.cpu()).tolist() == [0x7F7FFFFF, -8388609]
    for integer in ((((1 << 24) - 1) << 2) + 2, ((((1 << 24) - 1) << 2) + 3)):
        with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
            kernel.encode_products(
                torch.tensor([integer], dtype=torch.int64, device="cuda"),
                torch.tensor([1], dtype=torch.int32, device="cuda"),
                torch.tensor([102], dtype=torch.int32, device="cuda"),
            )


def test_negative_limbs_reconstruct_an_exact_signed_projection():
    kernel = kernels()
    generator = torch.Generator().manual_seed(89)
    weight = (-torch.rand((5, 257), generator=generator, dtype=torch.float32)).half()
    value = -torch.rand((3, 257), generator=generator, dtype=torch.float32) * 0.5
    quantized, scale = frozen_int8.quantize_weight(weight)
    compare(kernel, value, quantized, scale, None)


def test_linear_consumes_the_audit_artifact_at_the_max_finite_rounding_boundary():
    kernel = kernels()
    source = torch.tensor([[1.0, 2.0**-6, 127.0 / 64.0 - 2.0**-23]], dtype=torch.float32)
    quantized, scale = frozen_int8.quantize_weight(source)
    value = torch.tensor([[3.4028234663852886e38, 2.0**106, 0.0]], dtype=torch.float32)
    compare(kernel, value, quantized, scale, None)


@pytest.mark.parametrize(
    "rows,width,outputs,bias",
    [
        (1, 1, 1, False),
        (1, 7, 9, True),
        (3, 31, 17, True),
        (17, 33, 7, False),
        (32, 129, 33, True),
        (5, 64, 16, True),
        (2, 257, 3, True),
        (4, 1024, 5, True),
    ],
)
def test_linear_matches_cpu_oracle_for_tails_rows_and_bias(rows, width, outputs, bias):
    kernel = kernels()
    _, quantized, scale, source_bias, value = random_case(rows, width, outputs, rows * 1000 + width, bias=bias)
    compare(kernel, value, quantized, scale, source_bias)


@pytest.mark.parametrize("implementation", ["mma", "simt"])
@pytest.mark.parametrize("split_k", [1, 2, 4, 8])
def test_explicit_schedules_keep_exact_arithmetic(implementation, split_k):
    kernel = kernels()
    _, quantized, scale, source_bias, value = random_case(
        3 if implementation == "mma" else 1,
        257,
        17,
        71,
        bias=True,
    )
    compare(
        kernel,
        value,
        quantized,
        scale,
        source_bias,
        implementation=implementation,
        split_k=split_k,
        row_tile=16,
    )


def test_zero_row_with_zero_scale_and_subnormal_scales():
    kernel = kernels()
    quantized = torch.zeros((3, 5), dtype=torch.int8)
    largest_subnormal = 2.0**-126 * (1.0 - 2.0**-23)
    scale = torch.tensor([0.0, 2.0**-149, largest_subnormal], dtype=torch.float32)
    quantized[1, :] = torch.tensor([127, -127, 1, -1, 0], dtype=torch.int8)
    quantized[2, :] = torch.tensor([127, -127, 1, -1, 0], dtype=torch.int8)
    value = torch.tensor([[1.0, -2.0, 0.0, 3.0, 4.0]], dtype=torch.float32)
    compare(kernel, value, quantized, scale, None)


def test_linear_flags_nonfinite_input_and_output_overflow():
    kernel = kernels()
    quantized = torch.tensor([[127]], dtype=torch.int8)
    scale = torch.tensor([3.0e38], dtype=torch.float32)
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        kernel.linear(torch.tensor([[float("nan")]], device="cuda"), quantized.cuda(), scale.cuda())
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        kernel.linear(torch.tensor([[3.0e38]], device="cuda"), quantized.cuda(), scale.cuda())


def test_linear_many_shares_activation_quantization_and_matches_individual_calls():
    kernel = kernels()
    cases = []
    for index in range(3):
        _, quantized, scale, source_bias, value = random_case(7, 65, 13 + index * 3, 300 + index, bias=True)
        cases.append((quantized, scale, source_bias, value))
    value = cases[0][3]
    calls = []
    quantize = kernel.quantize_input

    def counted(*args, **kwargs):
        calls.append(1)
        return quantize(*args, **kwargs)

    kernel.quantize_input = counted
    outputs = kernel.linear_many(
        value.cuda(),
        tuple((q.cuda(), s.cuda()) for q, s, _, _ in cases),
        tuple(b.cuda() for _, _, b, _ in cases),
    )
    assert calls == [1]
    for (q, s, b, _), actual in zip(cases, outputs, strict=True):
        expected = frozen_int8.linear(value, artifact_for(q, s), b)
        assert torch.equal(bits(actual.cpu()), bits(expected))


def test_identity_names_the_separate_frozen_operator():
    kernel = kernels()
    _, quantized, scale, source_bias, value = random_case(2, 33, 7, 401, bias=True)
    compare(kernel, value, quantized, scale, source_bias)
    identity = kernel.identity()
    assert identity["frozenKernel"] == "frozen_int8_b22_mma_cuda_v1_experimental"
    assert identity["frozenArtifact"]["format"] == frozen_int8.ARTIFACT_FORMAT
    assert identity["hardwareQualified"] is False
    assert identity["arch"].startswith("sm_")
    assert identity["builds"]
