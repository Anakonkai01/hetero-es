from heteroes.model.schema import ParameterSchema, resolve_tensors
from heteroes.es.checks import _check_param
from heteroes.noise.engine import num_chunks, generate_chunk_noise, chunk_length
from heteroes.noise.contracts import ParameterNoiseAddress, DEFAULT_CHUNK_ELEMENTS
from heteroes.noise.parallel import ordered_map

from dataclasses import dataclass
import math
import torch 
import torch.nn as nn 
import numpy as np
import numbers


DEFAULT_ETA = 1e-9


@dataclass(frozen=True)
class UpdateReport: 
    noop: bool # no operations 
    coefficients: tuple[float, ...]
    requested_l2: float
    applied_l2: float
    changed: int
    numel: int
    
    


def standardize_rewards(rewards, eta=DEFAULT_ETA) -> np.ndarray: 
    if not (math.isfinite(eta) and eta > 0): 
        raise ValueError("eta must finite and > 0") 
    
    # calculate in float64 then cast to float32 
    rewards = np.asarray(rewards, dtype=np.float64)
    if rewards.ndim != 1: 
        raise ValueError("rewards must be 1d-array")
    if not rewards.size > 0: 
        raise ValueError("rewards size must > 0")
    if not np.isfinite(rewards).all(): 
        raise ValueError("rewards has value being Nan/Inf") 

    # z = (r - mean(r)) / (std(r) + eta)
    mean_r = rewards.mean(dtype=np.float64)
    std_r = rewards.std(ddof=0, dtype=np.float64)
    
    # no signal
    if std_r < eta: 
        return np.zeros(rewards.size, dtype=np.float32)

    z = (rewards - mean_r) / (std_r + np.float64(eta))
    
    return z.astype(np.float32)



def _check_coefficients(coefficients) -> np.ndarray:
    # the coefficients of a generation record: a vector of finite numbers that are exactly float32 values
    array = np.asarray(coefficients)
    if array.dtype.kind not in "iuf":
        raise TypeError(f"coefficients must be real numbers, got {array.dtype}")
    if array.ndim != 1:
        raise ValueError("coefficients must be a 1-d vector")
    if array.size == 0:
        raise ValueError("coefficients must not be empty")
    array = array.astype(np.float64)
    if not np.isfinite(array).all():
        raise ValueError("coefficients has a value that is Nan/Inf")
    with np.errstate(over="ignore"):
        as_float32 = array.astype(np.float32)
    if not np.array_equal(as_float32.astype(np.float64), array):
        raise ValueError("every coefficient must be exactly a float32 value (it would be rounded in silence)")
    return as_float32


def apply_coefficients_(model: nn.Module, schema: ParameterSchema, candidate_seeds: list[int], coefficients, alpha: float, chunk_elements: int=DEFAULT_CHUNK_ELEMENTS) -> UpdateReport:
    """
    The update of one ES generation with the coefficients GIVEN (no standardization here): what a worker applies when it
    replays a generation record. `apply_es_update_` is this with the coefficients computed from the rewards.
    """
    tensors = resolve_tensors(model, schema)
    for tensor in tensors:
        _check_param(tensor)
    return _apply_coefficients(schema, tensors, candidate_seeds, _check_coefficients(coefficients), alpha, chunk_elements)


# agentic esopt update style
def apply_es_update_(model: nn.Module, schema: ParameterSchema, candidate_seeds: list[int], rewards, alpha: float, chunk_elements: int=DEFAULT_CHUNK_ELEMENTS, eta=DEFAULT_ETA) -> UpdateReport: 
    # resolve tensor
    tensors = resolve_tensors(model, schema)
    # check param 
    for tensor in tensors: 
        _check_param(tensor)
    
    # z already check eta and rewards
    z_rewards = standardize_rewards(rewards, eta)
    return _apply_coefficients(schema, tensors, candidate_seeds, z_rewards, alpha, chunk_elements)


def _apply_coefficients(schema: ParameterSchema, tensors, candidate_seeds, z_rewards, alpha: float, chunk_elements: int) -> UpdateReport:
    total_numel = sum(t.numel() for t in tensors) 
    
    # check alpha 
    if not math.isfinite(alpha): 
        raise ValueError("alpha must not be Nan/Inf")
    
    # check chunks 
    if not chunk_elements >= 1: 
        raise ValueError("chunk_elements must be >=1") 

    # check len candidate 
    if len(candidate_seeds) != len(z_rewards):
        raise ValueError("length candidate_seeds != lenght rewards")
    
    # check seed 
    for seed in candidate_seeds: 
        # check if seed is int or np.int 
        if not (isinstance(seed, numbers.Integral) and not isinstance(seed, bool)): 
            raise TypeError("seed must be in int or np.int")
    
    # check duplicated seed 
    if len(set(candidate_seeds)) != len(candidate_seeds): 
        raise ValueError("seed being duplicated") 
       
    # check zero array, mean no signal
    if not z_rewards.any():
        return UpdateReport(
            noop=True,
            coefficients=(0.0,) * len(z_rewards),
            requested_l2=0.0,
            applied_l2=0.0,
            changed=0,
            numel=total_numel
        ) 
    
    schema_hash = schema.hash
    n_seeds = len(candidate_seeds)

    # Every (tensor, chunk, candidate) noise block, in the exact order the sum needs them. They are
    # generated on a thread pool but come back in this order, so the sum over candidates (the only
    # floating-point order that matters) is the same as with one thread.
    def tasks():
        for entry, tensor in zip(schema.entries, tensors):
            numel = tensor.numel()
            for chunk_index in range(num_chunks(numel=numel, chunk_elements=chunk_elements)):
                n = chunk_length(numel, chunk_index, chunk_elements)
                for seed in candidate_seeds:
                    address = ParameterNoiseAddress(
                        candidate_seed=seed,
                        schema_hash=schema_hash,
                        parameter_index=entry.index,
                        chunk_elements=chunk_elements,
                    ).chunk(chunk_index)
                    yield address, n

    noise_stream = ordered_map(lambda task: generate_chunk_noise(*task), tasks())

    # The three statistics of a chunk stay on the device and are read once at the end (one sync
    # instead of three per chunk); they are then added in chunk order exactly as before.
    changed_parts, requested_parts, applied_parts = [], [], []
    with torch.no_grad(): 
        for entry, tensor in zip(schema.entries, tensors): 
            numel = tensor.numel()
            n_chunks = num_chunks(numel=numel, chunk_elements=chunk_elements)
            for chunk_index in range(n_chunks): 
                start = chunk_index * chunk_elements
                n = chunk_length(numel, chunk_index, chunk_elements)
                chunk = tensor.view(-1)[start: start + n]
                acc = torch.zeros(n, dtype=torch.float32, device=tensor.device)
                
                for zi in z_rewards:
                    eps = torch.from_numpy(next(noise_stream)).to(device=tensor.device, dtype=torch.float32)

                    term = eps * float(zi)
                    acc = acc + term 
                
                direction = acc / n_seeds
                update = direction * float(np.float32(alpha))
                new = (chunk.to(torch.float32) + update).to(torch.float16)
                # compare 
                
                changed_parts.append((new.view(torch.int16) != chunk.view(torch.int16)).sum())
                requested_parts.append((update.double() ** 2).sum())
                applied_parts.append(((new.double() - chunk.double())**2).sum())
                 
                chunk.copy_(new)

        changed = 0
        requested_l2 = 0.0
        applied_l2 = 0.0
        if changed_parts:
            for value in torch.stack(changed_parts).tolist():
                changed += int(value)
            for value in torch.stack(requested_parts).tolist():
                requested_l2 += float(value)
            for value in torch.stack(applied_parts).tolist():
                applied_l2 += float(value)


    requested_l2 = math.sqrt(requested_l2)
    applied_l2 = math.sqrt(applied_l2)
    coefficients = tuple(float(v) for v in z_rewards)

    return UpdateReport(
        noop=False,
        coefficients=coefficients,
        requested_l2=requested_l2,
        applied_l2=applied_l2,
        changed=changed,
        numel=total_numel,
    )
        
    
        
    