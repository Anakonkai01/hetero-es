import dataclasses
import hashlib
import json
import random
from pathlib import Path

import numpy as np
import pytest

from heteroes.noise import engine
from heteroes.noise.contracts import (
    DEFAULT_CHUNK_ELEMENTS,
    ChunkNoiseAddress,
    ParameterNoiseAddress,
)
from heteroes.noise.engine import (
    chunk_length,
    derive_chunk_seed,
    generate_chunk_noise,
    generate_parameter_noise,
    iter_parameter_noise_chunks,
    num_chunks,
)

C = DEFAULT_CHUNK_ELEMENTS

# Schema hash of the physical probes (no aliases). The engine takes the hash as a
# plain string, so the probe's golden vectors can be checked without loading a model.
PROBE_SCHEMA_HASH = "152e9d82e61d6610a414466026ac60a13e718924dfdf0416809686adcf4188e1"

# (parameter_index, chunk_index, n, sha256 of the FP16 bytes), candidate_seed=0.
# Recorded on both machines (5070 Ti, 1660S) by the 2026-09-29 full probe.
GOLDEN = [
    (0, 0, 262144, "1c7a5a141fb785001881807b2bf0c9f81a1f2acf61877b1d2b2e4d029cfb8a35"),
    (0, 519, 81920, "8f57f603def436e1a642e71988b80a39331efaf9273e32634fe9f305f48ec405"),
    (1, 0, 262144, "34cc1872a32730731bb5b753277885281dd31aa0c27fdfbdcdd09c001a23eda8"),
    (2, 0, 896, "56d3f8f512beadbebf9cbf0b1e6fda5143f7940375fc4af99a3437943af12602"),
    (289, 0, 896, "3ed137fd746d5f0655e81731e39e80df6857404c5644dad5dd40b6a6767a25ae"),
]

# Schema hash of the PRODUCTION schema (aliases + schema_version), see test_schema.py (S9).
PRODUCTION_SCHEMA_HASH = "0b21250e331398a266785dc473da3a8b8f5e8f98fa15e9044637d742eb7845ec"

# Same chunks as GOLDEN, but addressed with the production schema hash (candidate_seed=0).
#
# These digests were produced by this very engine on 2026-10-03 (5070 Ti host, NumPy 2.4.5), so
# on their own they only prove that the bytes have not changed since then (regression guard).
# They are also cross-machine evidence because the same test (117 tests) passed on the
# GTX 1660 SUPER at commit 7b73e03 (NumPy 2.5.2, Python 3.14); the standalone script also
# reproduced them on Colab and Kaggle T4 (NumPy 2.1.3). See
# artifacts/regression/2026-10-03-o2-perturbation/.
GOLDEN_PRODUCTION = [
    (0, 0, 262144, "ebe2addd4ba90dfaebfad1582712b1660bd271f99e637c0e554caacf5fbcf87c"),
    (0, 519, 81920, "0d1468c0d034367ccd85e3ac80b5d94d7bf37aaf3a11edb718a35cfc5195466c"),
    (1, 0, 262144, "cd47f0154a3e8a8f2092469da29261479d115bc7db4a7794c8d59518f9a77186"),
    (2, 0, 896, "391a1e33d57bfe7283b4783df050ea51a751a0b61fb9d9050f5941fb40326c3f"),
    (289, 0, 896, "d87d01f6c48aebc7222f9bc18d1cee5981765f37363589140744b69ef6944653"),
]

PROBE_FULL_JSON = (
    Path(__file__).resolve().parents[2]
    / "artifacts" / "probes" / "2026-09-29" / "noiseengine_5070ti_full.json"
)


def address(seed=0, schema=PROBE_SCHEMA_HASH, param=0, chunk=0, chunk_elements=C):
    return ChunkNoiseAddress(seed, schema, param, chunk, chunk_elements)


# ---------------------------------------------------------------------------
# derive_chunk_seed
# ---------------------------------------------------------------------------

def test_seed_matches_hand_written_contract_string():
    # Independent oracle: the address string written out by hand, exactly as in the contract.
    text = (
        "numpy_pcg64_normal_f32_to_f16_v1|candidate_seed=0|schema="
        + PROBE_SCHEMA_HASH
        + "|param=0|chunk=0|chunk_elements=262144"
    )
    expected = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:16], "little")

    assert derive_chunk_seed(address()) == expected
    assert expected == 309890476452062159403129943193007553436


def test_seed_is_a_128_bit_unsigned_int():
    seed = derive_chunk_seed(address(seed=12345, param=17, chunk=3))

    assert isinstance(seed, int)
    assert 0 <= seed < 2**128


def test_seed_uses_little_endian_byte_order():
    text = (
        "numpy_pcg64_normal_f32_to_f16_v1|candidate_seed=0|schema="
        + PROBE_SCHEMA_HASH
        + "|param=0|chunk=0|chunk_elements=262144"
    )
    digest16 = hashlib.sha256(text.encode("utf-8")).digest()[:16]

    assert derive_chunk_seed(address()) != int.from_bytes(digest16, "big")


@pytest.mark.parametrize(
    "field, value",
    [
        ("candidate_seed", 1),
        ("schema_hash", "y" * 64),
        ("parameter_index", 1),
        ("chunk_index", 1),
        ("chunk_elements", 524_288),
    ],
)
def test_n_d_changing_any_address_part_changes_the_seed(field, value):
    base = address()

    assert derive_chunk_seed(dataclasses.replace(base, **{field: value})) != derive_chunk_seed(base)


def test_n_d_changing_engine_version_changes_the_seed(monkeypatch):
    before = derive_chunk_seed(address())
    monkeypatch.setattr(engine, "ENGINE_VERSION", "some_other_engine_v2")

    assert derive_chunk_seed(address()) != before


def test_position_matters_swapped_values_do_not_collide():
    # Regression: an early version sorted the values, so swapping two fields collided.
    assert derive_chunk_seed(address(seed=1, param=2)) != derive_chunk_seed(address(seed=2, param=1))
    assert derive_chunk_seed(address(param=0, chunk=1)) != derive_chunk_seed(address(param=1, chunk=0))


def test_seed_is_deterministic():
    assert derive_chunk_seed(address(seed=7)) == derive_chunk_seed(address(seed=7))


# ---------------------------------------------------------------------------
# generate_chunk_noise
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("param, chunk, n, digest", GOLDEN)
def test_n_g_golden_vectors_from_physical_probe(param, chunk, n, digest):
    noise = generate_chunk_noise(address(param=param, chunk=chunk), n)

    assert hashlib.sha256(noise.tobytes()).hexdigest() == digest


@pytest.mark.parametrize("param, chunk, n, digest", GOLDEN_PRODUCTION)
def test_n_g_production_golden_vectors_regression_guard(param, chunk, n, digest):
    noise = generate_chunk_noise(
        address(schema=PRODUCTION_SCHEMA_HASH, param=param, chunk=chunk), n
    )

    assert hashlib.sha256(noise.tobytes()).hexdigest() == digest


def test_production_golden_differs_from_probe_golden():
    # The schema hash is part of the address, so production noise is a different byte stream
    # from the probe's. If these tables ever became equal, the schema hash would be ignored.
    probe = {(param, chunk): digest for param, chunk, _, digest in GOLDEN}
    production = {(param, chunk): digest for param, chunk, _, digest in GOLDEN_PRODUCTION}

    assert probe.keys() == production.keys()
    assert all(probe[key] != production[key] for key in probe)


def test_generated_chunk_is_float16_array_of_length_n():
    noise = generate_chunk_noise(address(), 1000)

    assert isinstance(noise, np.ndarray)
    assert noise.dtype == np.float16
    assert noise.shape == (1000,)


def test_n_o_generation_order_does_not_change_the_bytes():
    keys = [(p, c) for p in range(3) for c in range(4)]
    in_order = {k: generate_chunk_noise(address(param=k[0], chunk=k[1]), 64).tobytes() for k in keys}

    shuffled = keys[:]
    random.Random(0).shuffle(shuffled)
    out_of_order = {k: generate_chunk_noise(address(param=k[0], chunk=k[1]), 64).tobytes() for k in shuffled}

    assert in_order == out_of_order


def test_shorter_chunk_is_a_prefix_of_the_full_chunk():
    # The last (short) chunk uses the FIRST n values of its own stream.
    short = generate_chunk_noise(address(chunk=3), 10)
    longer = generate_chunk_noise(address(chunk=3), 20)

    assert np.array_equal(short, longer[:10])


@pytest.mark.parametrize(
    "field, value",
    [
        ("candidate_seed", 1),
        ("schema_hash", "y" * 64),
        ("parameter_index", 1),
        ("chunk_index", 1),
        ("chunk_elements", 524_288),
    ],
)
def test_n_d_changing_any_address_part_changes_the_noise(field, value):
    base = generate_chunk_noise(address(), 256)
    other = generate_chunk_noise(dataclasses.replace(address(), **{field: value}), 256)

    assert not np.array_equal(base, other)


def test_noise_looks_standard_normal():
    # Sanity check of the distribution, not a statistical proof.
    noise = generate_chunk_noise(address(), C).astype(np.float32)

    assert abs(float(noise.mean())) < 0.02
    assert abs(float(noise.std()) - 1.0) < 0.02


@pytest.mark.parametrize("bad_n", [0, -1, C + 1])
def test_generate_rejects_n_outside_1_to_chunk_elements(bad_n):
    with pytest.raises(ValueError):
        generate_chunk_noise(address(), bad_n)


def test_generate_accepts_the_boundary_values_of_n():
    assert generate_chunk_noise(address(), 1).shape == (1,)
    assert generate_chunk_noise(address(), C).shape == (C,)


# ---------------------------------------------------------------------------
# chunk geometry: num_chunks, chunk_length
# ---------------------------------------------------------------------------

def test_geometry_hand_computed_examples():
    assert num_chunks(600_000, C) == 3
    assert [chunk_length(600_000, j, C) for j in range(3)] == [262_144, 262_144, 75_712]

    assert num_chunks(136_134_656, C) == 520          # embedding tensor
    assert chunk_length(136_134_656, 519, C) == 81_920

    assert num_chunks(896, C) == 1                    # tensor smaller than one chunk
    assert chunk_length(896, 0, C) == 896


def test_geometry_exact_multiple_has_no_short_last_chunk():
    assert num_chunks(2 * C, C) == 2
    assert [chunk_length(2 * C, j, C) for j in range(2)] == [C, C]


@pytest.mark.parametrize("chunk_elements", [1, 3, 4, 5, C])
def test_geometry_chunks_exactly_tile_the_tensor(chunk_elements):
    # Property: the chunks together cover numel exactly; only the last one may be short.
    for numel in list(range(1, 40)) + [C - 1, C, C + 1, 2 * C, 600_000]:
        lengths = [chunk_length(numel, j, chunk_elements) for j in range(num_chunks(numel, chunk_elements))]

        assert sum(lengths) == numel
        assert all(1 <= length <= chunk_elements for length in lengths)
        assert all(length == chunk_elements for length in lengths[:-1])


@pytest.mark.parametrize("numel, chunk_elements", [(0, C), (-5, C), (10, 0), (10, -1)])
def test_geometry_rejects_non_positive_sizes(numel, chunk_elements):
    with pytest.raises(ValueError):
        num_chunks(numel, chunk_elements)
    with pytest.raises(ValueError):
        chunk_length(numel, 0, chunk_elements)


@pytest.mark.parametrize("numel, bad_index", [(896, 1), (896, 5), (600_000, 3), (600_000, -1), (10, 10)])
def test_chunk_length_rejects_index_outside_the_tensor(numel, bad_index):
    # A tensor has chunk indexes 0 .. num_chunks-1 only (not 0 .. chunk_elements-1).
    with pytest.raises(ValueError):
        chunk_length(numel, bad_index, C)


@pytest.mark.skipif(not PROBE_FULL_JSON.exists(), reason="probe evidence file not found")
def test_geometry_matches_probe_chunk_counts_for_all_qwen_tensors():
    results = json.loads(PROBE_FULL_JSON.read_text(encoding="utf-8"))["target_results"]

    assert all(num_chunks(t["numel"], C) == t["total_chunks"] for t in results)
    assert sum(num_chunks(t["numel"], C) for t in results) == 2105


# ---------------------------------------------------------------------------
# whole-parameter noise: iter_parameter_noise_chunks, generate_parameter_noise
# ---------------------------------------------------------------------------

def parameter_address(seed=0, schema=PROBE_SCHEMA_HASH, param=0, chunk_elements=C):
    return ParameterNoiseAddress(seed, schema, param, chunk_elements)


def test_iter_yields_chunks_in_order_with_start_positions():
    # numel=10, C=4 -> chunks of 4, 4, 2 starting at 0, 4, 8
    items = list(iter_parameter_noise_chunks(parameter_address(chunk_elements=4), 10))

    assert [(index, start, len(noise)) for index, start, noise in items] == [
        (0, 0, 4),
        (1, 4, 4),
        (2, 8, 2),
    ]


def test_iter_chunks_are_exactly_what_generate_chunk_noise_returns():
    address_ = parameter_address(seed=3, param=5, chunk_elements=4)

    for index, _, noise in iter_parameter_noise_chunks(address_, 10):
        expected = generate_chunk_noise(address_.chunk(index), len(noise))

        assert noise.dtype == np.float16
        assert np.array_equal(noise, expected)


def test_iter_is_lazy(monkeypatch):
    # Only one chunk may be generated per step (this is what keeps memory low).
    calls = []
    real = engine.generate_chunk_noise
    monkeypatch.setattr(engine, "generate_chunk_noise", lambda *a, **k: calls.append(1) or real(*a, **k))

    stream = iter_parameter_noise_chunks(parameter_address(chunk_elements=4), 10)
    assert calls == []
    next(stream)
    assert len(calls) == 1
    next(stream)
    assert len(calls) == 2


def test_generate_parameter_noise_dtype_and_shape():
    noise = generate_parameter_noise(parameter_address(chunk_elements=4), 10)

    assert isinstance(noise, np.ndarray)
    assert noise.dtype == np.float16
    assert noise.shape == (10,)


@pytest.mark.parametrize(
    "numel, chunk_elements",
    [(10, 4), (8, 4), (3, 4), (5, 1), (1, 4), (1, 1), (600, 256)],
)
def test_generate_parameter_noise_equals_concatenated_chunks(numel, chunk_elements):
    # Independent oracle: build each chunk directly and concatenate.
    address_ = parameter_address(seed=2, param=7, chunk_elements=chunk_elements)
    pieces = [
        generate_chunk_noise(address_.chunk(j), chunk_length(numel, j, chunk_elements))
        for j in range(num_chunks(numel, chunk_elements))
    ]

    assert np.array_equal(generate_parameter_noise(address_, numel), np.concatenate(pieces))


def test_generate_parameter_noise_of_a_small_real_tensor_matches_golden():
    # Qwen parameter 2 (a bias, 896 elements) is a single chunk: same bytes as the probe golden.
    noise = generate_parameter_noise(parameter_address(param=2), 896)
    golden = next(digest for param, chunk, n, digest in GOLDEN if (param, chunk, n) == (2, 0, 896))

    assert hashlib.sha256(noise.tobytes()).hexdigest() == golden


def test_existing_elements_do_not_depend_on_numel_when_chunking_is_the_same():
    # numel only decides how many values the last chunk takes (a prefix of its own stream).
    address_ = parameter_address(chunk_elements=4)
    shorter = generate_parameter_noise(address_, 10)
    longer = generate_parameter_noise(address_, 11)

    assert np.array_equal(shorter, longer[:10])


def test_different_chunk_elements_give_different_parameter_noise():
    a = generate_parameter_noise(parameter_address(chunk_elements=4), 10)
    b = generate_parameter_noise(parameter_address(chunk_elements=5), 10)

    assert not np.array_equal(a, b)


@pytest.mark.parametrize("bad_numel", [0, -1])
def test_parameter_noise_rejects_non_positive_numel(bad_numel):
    with pytest.raises(ValueError):
        generate_parameter_noise(parameter_address(chunk_elements=4), bad_numel)
    with pytest.raises(ValueError):
        list(iter_parameter_noise_chunks(parameter_address(chunk_elements=4), bad_numel))


def test_real_embedding_first_and_last_chunk_match_probe_golden():
    # Streams all 520 chunks of the real embedding (136,134,656 elements) without ever
    # holding more than one chunk in memory, and checks the two golden chunks.
    numel = 136_134_656
    golden = {chunk: digest for param, chunk, n, digest in GOLDEN if param == 0}
    seen = 0
    covered = 0

    for index, start, noise in iter_parameter_noise_chunks(parameter_address(param=0), numel):
        assert start == covered
        covered += len(noise)
        seen += 1
        if index in golden:
            assert hashlib.sha256(noise.tobytes()).hexdigest() == golden[index]

    assert seen == 520
    assert covered == numel
