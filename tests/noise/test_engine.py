import dataclasses
import hashlib
import json
import random
from pathlib import Path

import numpy as np
import pytest

from heteroes.noise import engine
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, NoiseAddress
from heteroes.noise.engine import (
    chunk_length,
    derive_chunk_seed,
    generate_chunk,
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

PROBE_FULL_JSON = (
    Path(__file__).resolve().parents[2]
    / "artifacts" / "probes" / "2026-09-29" / "noiseengine_5070ti_full.json"
)


def address(seed=0, schema=PROBE_SCHEMA_HASH, param=0, chunk=0, chunk_elements=C):
    return NoiseAddress(seed, schema, param, chunk, chunk_elements)


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
# generate_chunk
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("param, chunk, n, digest", GOLDEN)
def test_n_g_golden_vectors_from_physical_probe(param, chunk, n, digest):
    noise = generate_chunk(address(param=param, chunk=chunk), n)

    assert hashlib.sha256(noise.tobytes()).hexdigest() == digest


def test_generated_chunk_is_float16_array_of_length_n():
    noise = generate_chunk(address(), 1000)

    assert isinstance(noise, np.ndarray)
    assert noise.dtype == np.float16
    assert noise.shape == (1000,)


def test_n_o_generation_order_does_not_change_the_bytes():
    keys = [(p, c) for p in range(3) for c in range(4)]
    in_order = {k: generate_chunk(address(param=k[0], chunk=k[1]), 64).tobytes() for k in keys}

    shuffled = keys[:]
    random.Random(0).shuffle(shuffled)
    out_of_order = {k: generate_chunk(address(param=k[0], chunk=k[1]), 64).tobytes() for k in shuffled}

    assert in_order == out_of_order


def test_shorter_chunk_is_a_prefix_of_the_full_chunk():
    # The last (short) chunk uses the FIRST n values of its own stream.
    short = generate_chunk(address(chunk=3), 10)
    longer = generate_chunk(address(chunk=3), 20)

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
    base = generate_chunk(address(), 256)
    other = generate_chunk(dataclasses.replace(address(), **{field: value}), 256)

    assert not np.array_equal(base, other)


def test_noise_looks_standard_normal():
    # Sanity check of the distribution, not a statistical proof.
    noise = generate_chunk(address(), C).astype(np.float32)

    assert abs(float(noise.mean())) < 0.02
    assert abs(float(noise.std()) - 1.0) < 0.02


@pytest.mark.parametrize("bad_n", [0, -1, C + 1])
def test_generate_rejects_n_outside_1_to_chunk_elements(bad_n):
    with pytest.raises(ValueError):
        generate_chunk(address(), bad_n)


def test_generate_accepts_the_boundary_values_of_n():
    assert generate_chunk(address(), 1).shape == (1,)
    assert generate_chunk(address(), C).shape == (C,)


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
