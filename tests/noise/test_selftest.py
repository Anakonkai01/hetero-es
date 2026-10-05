import hashlib
import time

import numpy as np
import pytest

from heteroes.noise import selftest
from heteroes.noise.selftest import (
    EXPECTED_NOISE_FINGERPRINT,
    GOLDEN_CHUNKS,
    compute_noise_fingerprint,
    noise_selftest,
)

# Pinned copy of what the five chunks must hash to (the same digests as GOLDEN_PRODUCTION in test_engine.py).
PINNED_DIGESTS = [
    "ebe2addd4ba90dfaebfad1582712b1660bd271f99e637c0e554caacf5fbcf87c",
    "0d1468c0d034367ccd85e3ac80b5d94d7bf37aaf3a11edb718a35cfc5195466c",
    "cd47f0154a3e8a8f2092469da29261479d115bc7db4a7794c8d59518f9a77186",
    "391a1e33d57bfe7283b4783df050ea51a751a0b61fb9d9050f5941fb40326c3f",
    "d87d01f6c48aebc7222f9bc18d1cee5981765f37363589140744b69ef6944653",
]
# Regression guard, produced by this code on 2026-10-06 (5070 Ti, NumPy 2.4.5); the 1660 SUPER computes the same value.
PINNED_FINGERPRINT = "b94575345e870b1606cb4d6a0c4aa49b054cfbfc50571d809653d01bce9184d3"


def test_this_machine_passes_the_self_test():
    assert noise_selftest() is True
    assert compute_noise_fingerprint() == EXPECTED_NOISE_FINGERPRINT


def test_the_golden_table_is_the_five_recorded_chunks():
    assert [row[3] for row in GOLDEN_CHUNKS] == PINNED_DIGESTS
    assert [(row[0], row[1], row[2]) for row in GOLDEN_CHUNKS] == [
        (0, 0, 262144), (0, 519, 81920), (1, 0, 262144), (2, 0, 896), (289, 0, 896)]


def test_the_expected_fingerprint_is_pinned():
    assert EXPECTED_NOISE_FINGERPRINT == PINNED_FINGERPRINT


def test_a_different_normal_generator_fails_the_self_test(monkeypatch):
    # What a NumPy that changed its algorithm would do: other bytes for the same address.
    def other_generator(address, n):
        return np.random.RandomState(1).standard_normal(n).astype(np.float32).astype(np.float16)

    monkeypatch.setattr(selftest, "generate_chunk_noise", other_generator)

    assert noise_selftest() is False
    assert compute_noise_fingerprint() != EXPECTED_NOISE_FINGERPRINT


@pytest.mark.parametrize("which", range(5))
def test_every_one_of_the_five_chunks_counts(monkeypatch, which):
    real = selftest.generate_chunk_noise
    calls = []

    def one_bit_off(address, n):
        noise = real(address, n).copy()
        calls.append(1)
        if len(calls) == which + 1:
            noise.view(np.int16)[0] ^= 1
        return noise

    monkeypatch.setattr(selftest, "generate_chunk_noise", one_bit_off)

    assert noise_selftest() is False


def test_the_self_test_is_fast_enough_to_run_before_every_candidate():
    start = time.perf_counter()
    noise_selftest()

    assert time.perf_counter() - start < 2.0


def test_the_fingerprint_depends_on_the_engine_version(monkeypatch):
    monkeypatch.setattr(selftest, "ENGINE_VERSION", "numpy_pcg64_normal_f32_to_f16_v2")

    assert compute_noise_fingerprint() != EXPECTED_NOISE_FINGERPRINT
