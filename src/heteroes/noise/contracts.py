from dataclasses import dataclass


ENGINE_VERSION = "numpy_pcg64_normal_f32_to_f16_v1"
# contract value, part of every chunk address, so changing it changes all noise
DEFAULT_CHUNK_ELEMENTS = 2**18


@dataclass(frozen=True)
class NoiseAddress:
    """
    Storing Noise Address for generate seed 
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