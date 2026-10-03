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
