"""One batched launch must produce every request weight exponent and flag of the per-weight kernel."""

import os

import pytest
import torch

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@pytest.fixture(scope="module")
def kernels():
    from heteroes.strict.integer_cuda import IntegerCudaKernels

    return IntegerCudaKernels("cuda", magnitude_bits=22)


def weights(seed):
    gen = torch.Generator(device="cuda").manual_seed(seed)
    shapes = [(896, 896, 0.02), (128, 896, 1e-6), (4864, 896, 3.0), (896, 4864, 0.001), (37, 64, 1e3), (9, 8, 1.0)]
    shapes += [(int(r), 16 * int(c), 0.5) for r, c in torch.randint(1, 70, (30, 2), generator=gen, device="cuda")]
    made = [(torch.randn(r, c, device="cuda", generator=gen) * s).half() for r, c, s in shapes]
    made[1][3] = 0  # an all-zero row has exponent zero
    made[1][7, 5] = 6e-8  # a subnormal-only row
    made[1][7, 6] = -6e-8
    made[2][4, 0] = 65504.0  # the largest finite half
    made[5][2] = -0.0
    return made


def per_weight(kernels, matrices):
    flag = kernels.new_error_flag()
    out = [torch.empty(w.shape[0], dtype=torch.int32, device="cuda") for w in matrices]
    for weight, exponents in zip(matrices, out):
        kernels._refresh_weight_exponents(weight, exponents, flag)
    return out, int(flag.item())


def batched(kernels, matrices):
    flag = kernels.new_error_flag()
    out = [torch.full((w.shape[0],), 77, dtype=torch.int32, device="cuda") for w in matrices]
    kernels._refresh_exponents_batched(list(zip(matrices, out)), flag)
    return out, int(flag.item())


@gpu
@pytest.mark.parametrize("seed", [1, 2])
def test_batched_exponents_equal_the_per_weight_kernel(kernels, seed):
    matrices = weights(seed)
    expected, expected_flag = per_weight(kernels, matrices)
    actual, actual_flag = batched(kernels, matrices)
    assert expected_flag == actual_flag == 0
    assert all(torch.equal(a, e) for a, e in zip(actual, expected))
    assert int(expected[1][3]) == 0 and int(expected[1][7]) < -14  # the premise: zero and subnormal rows


@gpu
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
@pytest.mark.parametrize("where", [0, 4, 35])
def test_batched_exponents_flag_nonfinite_weights_like_the_per_weight_kernel(kernels, value, where):
    matrices = weights(3)
    matrices[where][matrices[where].shape[0] - 1, 7] = value
    expected, expected_flag = per_weight(kernels, matrices)
    actual, actual_flag = batched(kernels, matrices)
    assert expected_flag == actual_flag == 1
    assert all(torch.equal(a, e) for a, e in zip(actual, expected))


@gpu
def test_request_routes_unaligned_or_narrow_rows_to_the_per_weight_kernel(kernels, monkeypatch):
    base = torch.randn(64, 897, device="cuda").half()
    narrow = torch.randn(5, 12, device="cuda").half()  # 24-byte rows: no 16-byte loads
    unaligned = base[:, 1:].contiguous()[:, :888]  # contiguous copy, then a view offset by 8 bytes below
    storage = torch.empty(64 * 888 + 4, device="cuda", dtype=torch.float16)
    offset = storage[4:].view(64, 888)
    offset.copy_(unaligned)
    assert offset.data_ptr() % 16 == 8
    aligned = torch.randn(40, 896, device="cuda").half()
    single, batch = [], []
    original_single, original_batch = kernels._refresh_weight_exponents, kernels._refresh_exponents_batched

    def record_single(weight, exponents, flag):
        single.append(weight.data_ptr())
        return original_single(weight, exponents, flag)

    def record_batch(entries, flag):
        batch.extend(weight.data_ptr() for weight, _ in entries)
        return original_batch(entries, flag)

    monkeypatch.setattr(kernels, "_refresh_weight_exponents", record_single)
    monkeypatch.setattr(kernels, "_refresh_exponents_batched", record_batch)
    kernels._begin_request([narrow, offset, aligned])
    try:
        assert sorted(single) == sorted([narrow.data_ptr(), offset.data_ptr()])
        assert batch == [aligned.data_ptr()]
        for weight in (narrow, offset, aligned):
            expected = torch.empty(weight.shape[0], dtype=torch.int32, device="cuda")
            original_single(weight, expected, kernels.new_error_flag())
            assert torch.equal(kernels._weight_exponents(weight, kernels.new_error_flag()), expected)
    finally:
        kernels._end_request()
    assert all(not bool(t.any()) for t in kernels.weight_metadata_buffers())
