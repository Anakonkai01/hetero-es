"""
Tests of the CUDA noise engine (G7). They need a CUDA device (the engine needs one); without it the whole file is skipped.

The oracle is plain torch written in the test: a fresh generator seeded with the documented seed and a loop of `torch.randn` calls of CUDA_CALL_ELEMENTS
elements. It does not use `TensorNoise`, so the tests check that the class does what the documentation says. What the tests CANNOT show
is that two different GPUs give the same numbers: that is the cross-GPU evidence (`artifacts/experiments/2026-10-07-g7-restore-tradeoff/`).
"""
import hashlib

import pytest
import torch

import heteroes.noise.cuda_engine as engine
from heteroes.noise.cuda_engine import (CUDA_CALL_ELEMENTS, CUDA_ENGINE_VERSION, EXPECTED_CUDA_NOISE_FINGERPRINT, TensorNoise, check_cuda_noise_selftest,
                                        check_device, compute_noise_fingerprint, derive_tensor_seed, generate_tensor_noise)

pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="the CUDA noise engine needs a CUDA device")

SCHEMA = "ab" * 32
K = CUDA_CALL_ELEMENTS                       # the size of a call: the tests are written in multiples of it


def oracle(schema_hash, seed, index, numel):
    """Written from the documentation: seed from the address, then calls of K elements (the last one shorter), float32 -> float16."""
    address = f"{CUDA_ENGINE_VERSION}|candidate_seed={seed}|schema={schema_hash}|param={index}|call_elements={K}"
    gen = torch.Generator(device="cuda")
    gen.manual_seed(int.from_bytes(hashlib.sha256(address.encode()).digest()[:8], "little") & ((1 << 63) - 1))
    parts, left = [], numel
    while left > 0:
        size = min(K, left)
        parts.append(torch.randn((size,), generator=gen, dtype=torch.float32, device="cuda"))
        left -= size
    return (torch.cat(parts) if parts else torch.empty(0, device="cuda")).to(torch.float16)


# ---- the noise is what the documentation says ------------------------------------------------------------------------------------

@pytest.mark.parametrize("numel", [1, 100, K - 1, K, K + 1, 2 * K, 2 * K + 1000, 5 * K + 3, 100_003])
def test_the_noise_of_a_tensor_is_the_documented_sequence_of_calls_of_k_elements(numel):
    assert torch.equal(generate_tensor_noise(SCHEMA, 7, 3, numel, "cuda"), oracle(SCHEMA, 7, 3, numel))


def test_the_noise_is_float16_on_the_device_asked_for():
    noise = generate_tensor_noise(SCHEMA, 7, 3, 1000, "cuda")
    assert noise.dtype == torch.float16 and noise.device.type == "cuda"


def test_an_empty_tensor_has_empty_noise():
    assert generate_tensor_noise(SCHEMA, 7, 3, 0, "cuda").numel() == 0


# ---- the bytes do not depend on how the tensor is cut into pieces ----------------------------------------------------------------

@pytest.mark.parametrize("pieces", [[K] * 6 + [1000], [2 * K, K, 3 * K, 2000], [6 * K + 1000], [K, K * 5, 1000]])
def test_the_bytes_do_not_depend_on_the_size_of_the_pieces(pieces):
    numel = sum(pieces)
    stream = TensorNoise(SCHEMA, 11, 5, numel, "cuda")
    got = torch.cat([stream.next(count) for count in pieces])
    assert torch.equal(got, oracle(SCHEMA, 11, 5, numel))


def test_the_first_elements_of_a_tensor_are_the_noise_of_a_shorter_tensor_of_the_same_address():
    assert torch.equal(generate_tensor_noise(SCHEMA, 11, 5, 3 * K + 100, "cuda")[:K], generate_tensor_noise(SCHEMA, 11, 5, K, "cuda"))


# ---- identity ------------------------------------------------------------------------------------------------------------------------

def test_the_same_address_gives_the_same_noise_twice_and_in_any_order_of_tensors():
    a1 = generate_tensor_noise(SCHEMA, 1, 0, 3 * K, "cuda")
    b1 = generate_tensor_noise(SCHEMA, 1, 1, 3 * K, "cuda")
    b2 = generate_tensor_noise(SCHEMA, 1, 1, 3 * K, "cuda")           # the other tensor first this time
    a2 = generate_tensor_noise(SCHEMA, 1, 0, 3 * K, "cuda")
    assert torch.equal(a1, a2) and torch.equal(b1, b2)


@pytest.mark.parametrize("other", [dict(seed=2), dict(index=1), dict(schema="cd" * 32)])
def test_every_field_of_the_address_changes_the_noise(other):
    base = dict(schema=SCHEMA, seed=1, index=0)
    changed = {**base, **other}
    a = generate_tensor_noise(base["schema"], base["seed"], base["index"], 3 * K, "cuda")
    b = generate_tensor_noise(changed["schema"], changed["seed"], changed["index"], 3 * K, "cuda")
    assert not torch.equal(a, b)


def test_two_chunks_of_one_tensor_are_not_the_same_numbers():
    noise = generate_tensor_noise(SCHEMA, 3, 0, 2 * K, "cuda")
    assert not torch.equal(noise[:K], noise[K:])            # one generator advancing, not a generator restarted per call


def test_the_noise_is_standard_normal_enough_for_es():
    noise = generate_tensor_noise(SCHEMA, 3, 0, 1_000_000, "cuda").float()
    assert abs(float(noise.mean())) < 0.01 and abs(float(noise.std()) - 1.0) < 0.01
    assert float(noise.abs().max()) > 4.0                           # the tails exist (a table of 1000 levels would not have them)


# ---- the seed of a tensor ---------------------------------------------------------------------------------------------------------

def test_the_tensor_seed_is_a_pure_function_of_the_address_below_2_pow_63():
    seed = derive_tensor_seed(SCHEMA, 5, 2)
    assert seed == derive_tensor_seed(SCHEMA, 5, 2) and 0 <= seed < 2**63
    assert len({derive_tensor_seed(SCHEMA, s, i) for s in range(20) for i in range(20)}) == 400


def test_the_tensor_seed_of_an_address_is_pinned():
    # a regression guard produced by this code (not independent evidence): the string that is hashed is part of the contract
    assert derive_tensor_seed(SCHEMA, 5, 2) == 3803758128943327799


@pytest.mark.parametrize("seed", [-1, 1.0, "1", True, None])
def test_a_bad_candidate_seed_is_refused(seed):
    with pytest.raises(ValueError):
        derive_tensor_seed(SCHEMA, seed, 0)


@pytest.mark.parametrize("index", [-1, 1.5, "0", False, None])
def test_a_bad_parameter_index_is_refused(index):
    with pytest.raises(ValueError):
        derive_tensor_seed(SCHEMA, 1, index)


# ---- the stream refuses what would break the sequence of calls -----------------------------------------------------------------------

def test_a_piece_that_is_not_a_multiple_of_the_call_size_is_refused_unless_it_is_the_rest():
    stream = TensorNoise(SCHEMA, 1, 0, 2 * K + 1000, "cuda")
    with pytest.raises(ValueError, match="multiple"):
        stream.next(100)                                          # would make a call of 100 followed by more calls: another sequence
    assert stream.done == 0                                       # a refused request consumes nothing
    stream.next(2 * K)
    assert stream.next(1000).numel() == 1000                      # the rest may be any length


@pytest.mark.parametrize("count", [0, -K, K * 5, True, float(K)])
def test_a_piece_of_a_bad_size_is_refused(count):
    stream = TensorNoise(SCHEMA, 1, 0, 2 * K + 1000, "cuda")
    with pytest.raises(ValueError):
        stream.next(count)


def test_asking_for_more_than_is_left_is_refused():
    stream = TensorNoise(SCHEMA, 1, 0, K, "cuda")
    stream.next(K)
    with pytest.raises(ValueError):
        stream.next(1)


def test_a_piece_bigger_than_the_buffer_is_refused(monkeypatch):
    monkeypatch.setattr(engine, "PIECE_ELEMENTS", 2 * K)
    stream = TensorNoise(SCHEMA, 1, 0, 10 * K, "cuda")
    with pytest.raises(ValueError, match="at most"):
        stream.next(4 * K)


def test_a_negative_or_non_integer_numel_is_refused():
    for bad in (-1, 1.5, True, None):
        with pytest.raises(ValueError):
            TensorNoise(SCHEMA, 1, 0, bad, "cuda")


# ---- the guard on the device -----------------------------------------------------------------------------------------------------------

def test_a_cpu_device_is_refused():
    with pytest.raises(RuntimeError, match="CUDA device"):
        check_device("cpu")


def test_a_gpu_with_too_few_blocks_for_a_call_is_refused(monkeypatch):
    class Small:
        name, multi_processor_count, max_threads_per_multi_processor = "tiny", 3, 2048     # 3 * 8 blocks * 256 = 6144 threads: far below K

    monkeypatch.setattr(torch.cuda, "get_device_properties", lambda device: Small)
    with pytest.raises(RuntimeError, match="too few"):
        check_device("cuda")


def test_the_gpu_of_the_tests_passes_the_guard():
    check_device("cuda")


# ---- the fingerprint -----------------------------------------------------------------------------------------------------------------------

def test_the_fingerprint_is_stable_and_sees_a_change_of_the_noise(monkeypatch):
    first = compute_noise_fingerprint()
    assert first == compute_noise_fingerprint() and len(first) == 64
    monkeypatch.setattr(engine, "CUDA_ENGINE_VERSION", "another_engine")
    assert compute_noise_fingerprint() != first


def test_the_fingerprint_of_this_gpu_is_the_one_measured_on_the_rtx_5070_ti_and_the_gtx_1660_super():
    # the value was produced on the two GPUs by cuda_engine_crossgpu.py and found equal: this test fails on a GPU or a torch that makes other numbers
    assert compute_noise_fingerprint() == EXPECTED_CUDA_NOISE_FINGERPRINT
    check_cuda_noise_selftest()


def test_the_self_test_refuses_a_gpu_that_makes_other_numbers(monkeypatch):
    monkeypatch.setattr(engine, "EXPECTED_CUDA_NOISE_FINGERPRINT", "0" * 64)
    with pytest.raises(RuntimeError, match="self-test failed"):
        check_cuda_noise_selftest()
