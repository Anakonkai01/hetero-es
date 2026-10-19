import numpy as np
import pytest
import torch

from heteroes.es.perturb import perturb_parameter_
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, ParameterNoiseAddress
from heteroes.noise.engine import generate_parameter_noise

SCHEMA_HASH = "h" * 64
DEVICES = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])


def make_theta(numel, seed=1):
    return (np.random.default_rng(seed).standard_normal(numel) * 0.02).astype(np.float16)


def make_address(chunk_elements=4, seed=7, param=3):
    return ParameterNoiseAddress(seed, SCHEMA_HASH, param, chunk_elements)


def oracle(theta, eps, sigma):
    # Independent oracle, written straight from contract O2 = (c) with NumPy:
    # multiply in FP32, then add in FP32, then one cast to FP16.
    sigma32 = np.float32(sigma)
    scaled = sigma32 * eps.astype(np.float32)
    return (theta.astype(np.float32) + scaled).astype(np.float16)


def fused_fma_emulation(theta, eps, sigma):
    # What a fused multiply-add (option a, add_(alpha)) computes: one rounding step instead of two.
    exact = theta.astype(np.float64) + np.float64(np.float32(sigma)) * eps.astype(np.float64)
    return exact.astype(np.float32).astype(np.float16)


def bits(array):
    return np.asarray(array).view(np.int16)


def perturbed_copy(theta, address, sigma, device):
    tensor = torch.from_numpy(theta.copy()).to(device)
    perturb_parameter_(tensor, address, sigma)
    return tensor.cpu().numpy()


# ---------------------------------------------------------------------------
# bitwise agreement with the NumPy oracle
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("device", DEVICES)
@pytest.mark.parametrize("sigma", [1e-3, 0.0123456789, 0.0])
@pytest.mark.parametrize(
    "numel, chunk_elements",
    [(10, 4), (8, 4), (3, 4), (1, 4), (1000, 256), (600_000, DEFAULT_CHUNK_ELEMENTS)],
)
def test_result_is_bit_identical_to_the_numpy_oracle(numel, chunk_elements, sigma, device):
    theta = make_theta(numel)
    address = make_address(chunk_elements)
    eps = generate_parameter_noise(address, numel)

    result = perturbed_copy(theta, address, sigma, device)

    assert np.array_equal(bits(result), bits(oracle(theta, eps, sigma)))


@pytest.mark.skipif("cuda" not in DEVICES, reason="needs a CUDA GPU")
def test_cpu_and_gpu_give_the_same_bits():
    theta = make_theta(50_000)
    address = make_address(1024)

    on_cpu = perturbed_copy(theta, address, 1e-3, "cpu")
    on_gpu = perturbed_copy(theta, address, 1e-3, "cuda")

    assert np.array_equal(bits(on_cpu), bits(on_gpu))


def test_multidimensional_parameter_is_perturbed_like_its_flat_version():
    theta = make_theta(12)
    address = make_address(5)
    expected = oracle(theta, generate_parameter_noise(address, 12), 1e-3)
    tensor = torch.from_numpy(theta.copy()).reshape(3, 4)

    perturb_parameter_(tensor, address, 1e-3)

    assert tensor.shape == (3, 4)
    assert np.array_equal(bits(tensor.reshape(-1).numpy()), bits(expected))


# ---------------------------------------------------------------------------
# the test data must be able to tell option (c) from the fused option (a)
# ---------------------------------------------------------------------------

LARGE = 2_000_000


def test_large_case_data_can_distinguish_unfused_from_fused():
    # Fused and unfused arithmetic differ in only a few elements per million, so the small cases
    # above cannot catch a fused implementation. This data set is big enough to contain some.
    theta = make_theta(LARGE)
    eps = generate_parameter_noise(make_address(DEFAULT_CHUNK_ELEMENTS), LARGE)

    unfused = oracle(theta, eps, 1e-3)
    fused = fused_fma_emulation(theta, eps, 1e-3)

    assert np.count_nonzero(bits(unfused) != bits(fused)) > 0


@pytest.mark.parametrize("device", DEVICES)
def test_large_case_matches_unfused_oracle_and_not_the_fused_one(device):
    theta = make_theta(LARGE)
    address = make_address(DEFAULT_CHUNK_ELEMENTS)
    eps = generate_parameter_noise(address, LARGE)

    result = perturbed_copy(theta, address, 1e-3, device)

    assert np.array_equal(bits(result), bits(oracle(theta, eps, 1e-3)))
    assert not np.array_equal(bits(result), bits(fused_fma_emulation(theta, eps, 1e-3)))


def test_does_not_use_fused_in_place_add(monkeypatch):
    # Option (a) is add_(eps, alpha=sigma). The contract forbids it (numerical-contract.md section 5).
    def forbidden(*args, **kwargs):
        raise AssertionError("fused in-place arithmetic is forbidden by contract O2")

    monkeypatch.setattr(torch.Tensor, "add_", forbidden)
    monkeypatch.setattr(torch.Tensor, "addcmul_", forbidden)
    tensor = torch.from_numpy(make_theta(10))

    perturb_parameter_(tensor, make_address(4), 1e-3)  # must not raise


# ---------------------------------------------------------------------------
# in-place behaviour
# ---------------------------------------------------------------------------

def test_perturbs_in_place_and_returns_none():
    tensor = torch.from_numpy(make_theta(10).copy())
    pointer = tensor.data_ptr()
    before = tensor.clone()

    returned = perturb_parameter_(tensor, make_address(4), 1e-3)

    assert returned is None
    assert tensor.data_ptr() == pointer
    assert not torch.equal(tensor, before)


def test_only_the_given_view_changes_not_its_neighbours():
    # A contiguous slice of a bigger tensor is a valid parameter; elements outside must stay put.
    big = torch.from_numpy(make_theta(30).copy())
    before = big.clone()
    middle = big[10:20]

    perturb_parameter_(middle, make_address(4), 1e-2)

    assert torch.equal(big[:10], before[:10])
    assert torch.equal(big[20:], before[20:])
    assert not torch.equal(big[10:20], before[10:20])


def test_is_deterministic():
    theta = make_theta(1000)
    address = make_address(256)

    first = perturbed_copy(theta, address, 1e-3, "cpu")
    second = perturbed_copy(theta, address, 1e-3, "cpu")

    assert np.array_equal(bits(first), bits(second))


def test_result_depends_on_address_and_sigma():
    theta = make_theta(1000)
    base = perturbed_copy(theta, make_address(256), 1e-3, "cpu")

    other_seed = perturbed_copy(theta, make_address(256, seed=8), 1e-3, "cpu")
    other_param = perturbed_copy(theta, make_address(256, param=4), 1e-3, "cpu")
    other_sigma = perturbed_copy(theta, make_address(256), 2e-3, "cpu")

    assert not np.array_equal(bits(base), bits(other_seed))
    assert not np.array_equal(bits(base), bits(other_param))
    assert not np.array_equal(bits(base), bits(other_sigma))


def test_gradient_tracking_parameter_can_be_perturbed():
    # Model parameters have requires_grad=True; in-place writes need torch.no_grad inside the function.
    param = torch.nn.Parameter(torch.from_numpy(make_theta(10).copy()))
    expected = oracle(make_theta(10), generate_parameter_noise(make_address(4), 10), 1e-3)

    perturb_parameter_(param, make_address(4), 1e-3)

    assert np.array_equal(bits(param.detach().numpy()), bits(expected))
    assert param.requires_grad


# ---------------------------------------------------------------------------
# input validation: wrong input is rejected loudly and nothing is modified
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dtype", [torch.float32, torch.float64, torch.bfloat16, torch.int64])
def test_rejects_other_dtypes_and_leaves_param_untouched(dtype):
    tensor = torch.zeros(10, dtype=dtype)
    before = tensor.clone()

    with pytest.raises(TypeError):
        perturb_parameter_(tensor, make_address(4), 1e-3)

    assert torch.equal(tensor, before)


def test_rejects_non_contiguous_param_and_leaves_it_untouched():
    tensor = torch.from_numpy(make_theta(12).copy()).reshape(3, 4).t()
    before = tensor.clone()

    with pytest.raises(ValueError):
        perturb_parameter_(tensor, make_address(4), 1e-3)

    assert torch.equal(tensor, before)


@pytest.mark.parametrize("bad_sigma", [float("nan"), float("inf"), float("-inf")])
def test_rejects_non_finite_sigma_and_leaves_param_untouched(bad_sigma):
    tensor = torch.from_numpy(make_theta(10).copy())
    before = tensor.clone()

    with pytest.raises(ValueError):
        perturb_parameter_(tensor, make_address(4), bad_sigma)

    assert torch.equal(tensor, before)
