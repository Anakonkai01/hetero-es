from dataclasses import dataclass


ENGINE_VERSION = "numpy_pcg64_normal_f32_to_f16_v1"
# contract value, part of every chunk address, so changing it changes all noise
DEFAULT_CHUNK_ELEMENTS = 2**18


@dataclass(frozen=True)
class ChunkNoiseAddress:
    """
    Storing Noise Address for generate seed (chunk level) 
        - must frozen 
        - to avoid add/remove or modify attribute 
        - does not has worker_id, attempt_id because noise does not depend on runtime
        - must be reproducible from these five fields alone(for regenerate)
    """
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

