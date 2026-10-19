from heteroes.noise.contracts import ChunkNoiseAddress, ParameterNoiseAddress, ENGINE_VERSION
from heteroes.noise.parallel import ordered_map

from collections.abc import Iterator
import numpy as np 
import hashlib
import math


def derive_chunk_seed(chunk_noise_address: ChunkNoiseAddress) -> int:
    """
    generate from chunk_noise_address to int to become seed 
    - input: ChunkNoiseAddress (address of ONE chunk of one tensor)
    - output: int 128 bit (16 bytes) (seed for PCG64)  
    """

    # do not sort, to keep the position info
    string_address = f"{ENGINE_VERSION}|candidate_seed={chunk_noise_address.candidate_seed}|schema={chunk_noise_address.schema_hash}|param={chunk_noise_address.parameter_index}|chunk={chunk_noise_address.chunk_index}|chunk_elements={chunk_noise_address.chunk_elements}"

    # sha to byte, only take first 16 bytes (sha256 auto mix with each byte), 
    hash_to_byte = hashlib.sha256(string_address.encode("utf-8")).digest()[:16]
    
    # use little endian 
    seed = int.from_bytes(hash_to_byte, "little")
    
    return seed
    
def generate_chunk_noise(chunk_noise_address: ChunkNoiseAddress, n: int) -> np.ndarray :
    """
    generate a chunk noise 
    - input: ChunkNoiseAddress, n (chunk_length ,number of elements of this chunk)
    - output: numpy array float 16, len = n
    """

    # chunk_elements is MAXIMUM ELEMENTS OF EACH CHUNKS (const)
    # n is the real number of elements of each chunks, ex: normal n = C, but last in last chunk, n can < C
    if not (1 <= n <= chunk_noise_address.chunk_elements):
        raise ValueError("n must in range 1 <= n <= chunk_elements")

    seed = derive_chunk_seed(chunk_noise_address)

    generator = np.random.Generator(np.random.PCG64(seed=seed))

    # generate n random number with standard normal distribution with float32
    random_numbers = generator.standard_normal(n,dtype=np.float32)

    return random_numbers.astype(np.float16, copy=False)

def num_chunks(numel: int, chunk_elements: int) -> int: 
    """
    calculate number of chunks for a tensor: 
    - numel: total parameters of a tensor  
    - chunk_elements: number of parameter of each chunk
    return: number of chunks of each tensor 
    """
    if not (numel >= 1 and chunk_elements >=1): 
        raise ValueError("numel and chunk_elements must >= 1")


    return math.ceil(numel / chunk_elements)

def chunk_length(numel: int, chunk_index: int, chunk_elements: int) -> int: 
    """
    find the length, number of elements of a specific chunk at current index 
    """
    chunks = num_chunks(numel, chunk_elements)
    if not (0 <= chunk_index < chunks): 
        raise ValueError("chunk index must be in 0<= chunk_index < num_chunks")
    
    # chunk_index * chunk_elements = real index of a tensor (like steps) 
    return min(chunk_elements, numel - chunk_index * chunk_elements) 


def iter_parameter_noise_chunks(parameter_noise_address: ParameterNoiseAddress, numel: int) -> Iterator[tuple[int, int, np.ndarray]]:
    """
    create iterator for generate parameter noise, return chunk noise one by one
    to avoid create all at one which could lead to out of memory 

    The chunks are generated on a thread pool a few chunks ahead (see noise/parallel.py) but are
    ALWAYS yielded in chunk order, and each chunk is the same bytes as when generated alone.
    """
    number_of_chunks = num_chunks(numel, parameter_noise_address.chunk_elements)

    def make(chunk_index: int) -> tuple[int, int, np.ndarray]:
        start_index_pos_of_tensor = chunk_index * parameter_noise_address.chunk_elements
        len_of_chunk = chunk_length(numel, chunk_index, parameter_noise_address.chunk_elements)
        chunk_noise_address = parameter_noise_address.chunk(chunk_index)
        return (chunk_index, start_index_pos_of_tensor, generate_chunk_noise(chunk_noise_address=chunk_noise_address, n=len_of_chunk))

    yield from ordered_map(make, range(number_of_chunks))

    
def generate_parameter_noise(parameter_noise_address: ParameterNoiseAddress, numel: int) -> np.ndarray: 
    """
    generate full noise of a tensor:
        - generate noise per chunk then combine it and return
    input:
        - parameter_noise_address: (address of one tensor, no chunk_index)
        - numel: number of elements of the tensor (not part of the noise identity)
    return:
        - a flat array (float16, length = numel)
    """

    # do not use list then append then concate because it will create new and then copy -> overhead compute and memory
    # using np.empty not (np.zeros or np.ones because this use calloc/memset -> allocate then write value), because only allocation, no write value
    parameter_noise = np.empty(numel, dtype=np.float16)

    # reuse logic in iter_parameter_noise_chunks
    for _, start_index_pos_of_tensor, chunk_noise in iter_parameter_noise_chunks(parameter_noise_address, numel):
        parameter_noise[start_index_pos_of_tensor: start_index_pos_of_tensor + len(chunk_noise)] = chunk_noise
    
    return parameter_noise

    

    
    
