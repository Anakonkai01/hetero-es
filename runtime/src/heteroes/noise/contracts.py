from dataclasses import dataclass


ENGINE_VERSION = "numpy_pcg64_normal_f32_to_f16_v1"
# contract value, part of every chunk address, so changing it changes all noise
DEFAULT_CHUNK_ELEMENTS = 2**18

# The second engine, made on the GPU (`cuda_engine.py`, numerical contract section 16). Here, without torch, so that the manifest can name it.
# 22,528 = 88 blocks of 256 threads: the largest call of the random kernel that the RTX 5070 Ti and the GTX 1660 SUPER serve with the same thread mapping.
CUDA_ENGINE_VERSION = "torch_cuda_philox_chunked_f32_to_f16_v1"
CUDA_CALL_ELEMENTS = 22_528
# equal on the two GPUs (artifacts/experiments/2026-10-07-g7-restore-tradeoff/cudaengine-*.json); a worker whose GPU makes other numbers must not take part
EXPECTED_CUDA_NOISE_FINGERPRINT = "9492a49ab70efe98e2b710e9a9e927f54be658489eae4b549c0cbf7340b9ffaf"
ENGINE_V2 = "pcg64_u32_to_f16_normal_quantile_v2"
EXPECTED_V2_TABLE_SHA256 = "e15f542c139cfd415ca9c19805535a64d8666f7d2e584429ac6e278bf9a32e2d"
EXPECTED_V2_NOISE_FINGERPRINT = "e80f079ca06fd3e2fcae7b41583aedd8b407e65c196677d5da54c1dc6de02bb4"
CPU_ENGINES = (ENGINE_VERSION, ENGINE_V2)
CPU_NOISE_FINGERPRINTS = {
    ENGINE_VERSION: "b94575345e870b1606cb4d6a0c4aa49b054cfbfc50571d809653d01bce9184d3",
    ENGINE_V2: EXPECTED_V2_NOISE_FINGERPRINT,
}
KNOWN_ENGINES = (*CPU_ENGINES, CUDA_ENGINE_VERSION)


@dataclass(frozen=True)
class ChunkNoiseAddress:
    # fmt: off
    """
    Storing Noise Address for generate seed (chunk level) 
        - must frozen 
        - to avoid add/remove or modify attribute 
        - does not has worker_id, attempt_id because noise does not depend on runtime
        - must be reproducible from these five fields alone(for regenerate)
    """
    # fmt: on

    candidate_seed: int
    schema_hash: str
    parameter_index: int
    chunk_index: int
    chunk_elements: int


@dataclass(frozen=True)
class ParameterNoiseAddress:
    """
    Storing address describe NOISE OF SPECIFIC TENSOR (parameter level)
    - must frozen to avoid add/remove or modify attribute
    """

    candidate_seed: int
    schema_hash: str
    parameter_index: int
    chunk_elements: int

    def chunk(self, chunk_index: int) -> ChunkNoiseAddress:
        if not chunk_index >= 0:
            raise ValueError("chunk_index must >= 0")

        return ChunkNoiseAddress(
            candidate_seed=self.candidate_seed,
            schema_hash=self.schema_hash,
            parameter_index=self.parameter_index,
            chunk_elements=self.chunk_elements,
            chunk_index=chunk_index,
        )
