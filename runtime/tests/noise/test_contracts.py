import dataclasses

import pytest

from heteroes.noise.contracts import (
    DEFAULT_CHUNK_ELEMENTS,
    ENGINE_VERSION,
    ChunkNoiseAddress,
)


def make_address():
    return ChunkNoiseAddress(
        candidate_seed=0,
        schema_hash="h" * 64,
        parameter_index=0,
        chunk_index=0,
        chunk_elements=DEFAULT_CHUNK_ELEMENTS,
    )


def test_engine_version_is_the_contract_string():
    # The string is part of every chunk seed: any change is a new engine version.
    assert ENGINE_VERSION == "numpy_pcg64_normal_f32_to_f16_v1"


def test_default_chunk_elements_is_2_pow_18():
    assert DEFAULT_CHUNK_ELEMENTS == 262_144
    assert isinstance(DEFAULT_CHUNK_ELEMENTS, int)


def test_n_m_address_has_exactly_the_five_contract_fields():
    names = [f.name for f in dataclasses.fields(ChunkNoiseAddress)]

    assert names == [
        "candidate_seed",
        "schema_hash",
        "parameter_index",
        "chunk_index",
        "chunk_elements",
    ]


@pytest.mark.parametrize(
    "operational_field", ["worker_id", "attempt_id", "lease_token", "retry", "reward"]
)
def test_n_m_address_rejects_operational_metadata(operational_field):
    # Noise identity must not depend on worker/attempt/lease/retry/reward.
    with pytest.raises(TypeError):
        ChunkNoiseAddress(0, "h" * 64, 0, 0, DEFAULT_CHUNK_ELEMENTS, **{operational_field: 1})


def test_address_is_frozen():
    address = make_address()

    with pytest.raises(dataclasses.FrozenInstanceError):
        address.chunk_index = 5


def test_address_requires_chunk_elements_explicitly():
    with pytest.raises(TypeError):
        ChunkNoiseAddress(0, "h" * 64, 0, 0)


# ---------------------------------------------------------------------------
# ParameterNoiseAddress
# ---------------------------------------------------------------------------

from heteroes.noise.contracts import ParameterNoiseAddress  # noqa: E402


def make_parameter_address():
    return ParameterNoiseAddress(
        candidate_seed=11, schema_hash="hh", parameter_index=22, chunk_elements=33
    )


def test_parameter_address_has_exactly_four_fields_and_no_chunk_index():
    names = [f.name for f in dataclasses.fields(ParameterNoiseAddress)]

    assert names == ["candidate_seed", "schema_hash", "parameter_index", "chunk_elements"]


@pytest.mark.parametrize("extra_field", ["worker_id", "attempt_id", "chunk_index", "numel"])
def test_parameter_address_rejects_extra_fields(extra_field):
    # chunk_index belongs to the chunk address; numel is not part of noise identity.
    with pytest.raises(TypeError):
        ParameterNoiseAddress(0, "h", 0, 4, **{extra_field: 1})


def test_parameter_address_is_frozen_and_hashable():
    address = make_parameter_address()

    with pytest.raises(dataclasses.FrozenInstanceError):
        address.chunk_elements = 5
    assert {address: 1}[make_parameter_address()] == 1


def test_parameter_address_requires_chunk_elements_explicitly():
    with pytest.raises(TypeError):
        ParameterNoiseAddress(0, "h", 0)


def test_chunk_copies_every_field_and_adds_chunk_index():
    # distinct values so that a swapped field would be noticed
    chunk = make_parameter_address().chunk(44)

    assert isinstance(chunk, ChunkNoiseAddress)
    assert chunk == ChunkNoiseAddress(
        candidate_seed=11, schema_hash="hh", parameter_index=22, chunk_index=44, chunk_elements=33
    )


def test_chunk_zero_is_valid():
    # Regression: an early version rejected chunk_index 0 (chunks are numbered from 0).
    assert make_parameter_address().chunk(0).chunk_index == 0


@pytest.mark.parametrize("bad_index", [-1, -100])
def test_chunk_rejects_negative_index(bad_index):
    with pytest.raises(ValueError):
        make_parameter_address().chunk(bad_index)
