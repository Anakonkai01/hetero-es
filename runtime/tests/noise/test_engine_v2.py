"""V2 byte contract, independent scalar oracle and numerical integration."""

import bisect
import hashlib
import struct

import numpy as np
import pytest
import torch

from heteroes.noise import engine_v2
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, ENGINE_V2, ChunkNoiseAddress, ParameterNoiseAddress
from heteroes.noise.engine import generate_chunk_noise as v1_chunk, generate_parameter_noise
from heteroes.noise.selftest import SELFTEST_SCHEMA_HASH
from heteroes.model.schema import build_parameter_schema
from heteroes.es.perturb import perturb_model_
from heteroes.es.update import apply_coefficients_


def address():
    return ChunkNoiseAddress(17, SELFTEST_SCHEMA_HASH, 2, 3, DEFAULT_CHUNK_ELEMENTS)


def reference_words(words):
    # Python bisect and explicit struct serialization, independent of the bucket fast path.
    return b"".join(
        struct.pack("<H", bisect.bisect_right(engine_v2.THRESHOLDS, int(w) & 0x7FFFFFFF) | (int(w) >> 31) << 15)
        for w in words
    )


def test_table_contract_and_digest():
    assert engine_v2.TABLE_SHA256 == "e15f542c139cfd415ca9c19805535a64d8666f7d2e584429ac6e278bf9a32e2d"
    assert len(engine_v2.THRESHOLDS) == 17980
    assert all(a <= b for a, b in zip(engine_v2.THRESHOLDS, engine_v2.THRESHOLDS[1:]))
    assert engine_v2.THRESHOLDS[-1] == 2**31 - 1
    assert hashlib.sha256(struct.pack(f"<{len(engine_v2.THRESHOLDS)}I", *engine_v2.THRESHOLDS)).hexdigest() == (
        engine_v2.TABLE_SHA256
    )


def test_boundary_words_both_signs_match_scalar_oracle():
    thresholds = [int(t) + d for t in engine_v2.THRESHOLDS for d in (-1, 0, 1)]
    edges = [i * 32768 + d for i in range(65536) for d in (-1, 0, 32767)]
    positive = sorted({0, 2**31 - 1} | {w for w in thresholds + edges if 0 <= w < 2**31})
    words = np.array(positive + [w | 2**31 for w in positive], dtype="<u4")
    assert engine_v2.transform_words(words).tobytes() == reference_words(words)


def test_signed_zero_and_tail_endpoints():
    words = np.array([0, 2**31, 2**31 - 1, 2**32 - 1], dtype="<u4")
    actual = engine_v2.transform_words(words)
    assert actual.view("<u2").tolist() == [0, 0x8000, 17980, 0x8000 | 17980]
    assert actual.tolist() == [0.0, -0.0, 6.234375, -6.234375]


@pytest.mark.parametrize("n", [1, 3, 896, 81921, 262144])
def test_chunk_seed_raw_stream_and_odd_prefix(n):
    a = address()
    material = f"{ENGINE_V2}|candidate_seed=17|schema={SELFTEST_SCHEMA_HASH}|param=2|chunk=3|chunk_elements=262144"
    seed = int.from_bytes(hashlib.sha256(material.encode()).digest()[:16], "little")
    raw = np.random.PCG64(seed).random_raw((n + 1) // 2)
    words = [w for r in raw for w in (int(r) & 0xFFFFFFFF, int(r) >> 32)][:n]
    actual = engine_v2.generate_chunk_noise(a, n)
    assert actual.dtype == np.dtype("<f2")
    assert actual.tobytes() == reference_words(words)
    assert actual.tobytes() == engine_v2.generate_chunk_noise(a, DEFAULT_CHUNK_ELEMENTS)[:n].tobytes()


@pytest.mark.parametrize("n", [0, -1, DEFAULT_CHUNK_ELEMENTS + 1])
def test_bad_chunk_length(n):
    with pytest.raises(ValueError):
        engine_v2.generate_chunk_noise(address(), n)


def test_parameter_parallelism_preserves_bytes(monkeypatch):
    a = ParameterNoiseAddress(17, SELFTEST_SCHEMA_HASH, 2, 37)
    results = []
    for threads in (1, 4, 8, 16):
        monkeypatch.setenv("HETEROES_NOISE_THREADS", str(threads))
        results.append(generate_parameter_noise(a, 503, engine=ENGINE_V2).tobytes())
    assert len(set(results)) == 1
    assert results[0] != generate_parameter_noise(a, 503).tobytes()


def test_perturb_and_update_use_v2_in_canonical_order():
    model = torch.nn.Linear(13, 3, bias=False).half()
    with torch.no_grad():
        model.weight.zero_()
    schema = build_parameter_schema(model)
    a = ParameterNoiseAddress(17, schema.hash, 0, 37)
    eps = torch.from_numpy(generate_parameter_noise(a, 39, engine=ENGINE_V2)).float().reshape(3, 13)
    perturb_model_(model, schema, 17, 0.125, 37, engine=ENGINE_V2)
    assert torch.equal(model.weight, (eps * 0.125).half())
    with torch.no_grad():
        model.weight.zero_()
    seeds, coefficients = [17, 9, 5], [1.0, -0.5, 0.25]
    acc = torch.zeros(39)
    for seed, coefficient in zip(seeds, coefficients):
        a = ParameterNoiseAddress(seed, schema.hash, 0, 37)
        acc = acc + torch.from_numpy(generate_parameter_noise(a, 39, engine=ENGINE_V2)).float() * coefficient
    expected = (acc * float(np.float32(1) / np.float32(3)) * 0.125).half().reshape(3, 13)
    apply_coefficients_(model, schema, seeds, coefficients, 0.125, 37, engine=ENGINE_V2)
    assert torch.equal(model.weight, expected)


def test_unknown_engine_rejected_before_parameter_write():
    model = torch.nn.Linear(3, 2, bias=False).half()
    schema = build_parameter_schema(model)
    before = model.weight.detach().clone()
    with pytest.raises(ValueError, match="engine"):
        perturb_model_(model, schema, 0, 0.1, engine="unknown")
    assert torch.equal(model.weight, before)


def test_v2_golden_fingerprint_and_one_bit_refusal(monkeypatch):
    from heteroes.noise import selftest_v2

    assert selftest_v2.compute_noise_fingerprint() == "e80f079ca06fd3e2fcae7b41583aedd8b407e65c196677d5da54c1dc6de02bb4"
    real = selftest_v2.generate_chunk_noise

    def changed(address, n):
        value = real(address, n).copy()
        value.view("<u2")[0] ^= 1
        return value

    monkeypatch.setattr(selftest_v2, "generate_chunk_noise", changed)
    assert not selftest_v2.noise_selftest()


def test_table_selftest_refuses_a_different_self_consistent_table(monkeypatch):
    changed = engine_v2._TABLE.copy()
    changed[-1] -= 1
    monkeypatch.setattr(engine_v2, "_TABLE", changed)
    monkeypatch.setattr(engine_v2, "TABLE_SHA256", hashlib.sha256(changed.tobytes()).hexdigest())
    assert not engine_v2.table_selftest()
