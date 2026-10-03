from heteroes.noise.contracts import NoiseAddress, ENGINE_VERSION
import numpy as np 
import hashlib
import math


def derive_chunk_seed(noise_address: NoiseAddress) -> int:
    """
    generate from noise_address to int to become seed 
    - input: NoiseAddress
    - output: int 128 bit (16 bytes) (seed for PCG64)  
    """

    # do not sort, to keep the position info
    string_address = f"{ENGINE_VERSION}|candidate_seed={noise_address.candidate_seed}|schema={noise_address.schema_hash}|param={noise_address.parameter_index}|chunk={noise_address.chunk_index}|chunk_elements={noise_address.chunk_elements}"

    # sha to byte, only take first 16 bytes (sha256 auto mix with each byte), 
    hash_to_byte = hashlib.sha256(string_address.encode("utf-8")).digest()[:16]
    
    # use little endian 
    seed = int.from_bytes(hash_to_byte, "little")
    
    return seed
    
def generate_chunk(noise_address: NoiseAddress, n: int) -> np.ndarray :
    """
    generate chunk noise 
    - input: Noise Address, n (number of elements per chunks) 
    - output: numpy array float 16, len = n
    """

    # chunk_elements is MAXIMUM ELEMENTS OF EACH CHUNKS (const)
    # n is the real number of elements of each chunks, ex: normal n = C, but last in last chunk, n can < C
    if not (1 <= n <= noise_address.chunk_elements): 
        raise ValueError("n must in range 1 <= n <= chunk_elements")

    seed = derive_chunk_seed(noise_address)

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


        
    
    