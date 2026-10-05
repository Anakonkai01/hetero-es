from heteroes.es.perturb import perturb_model_, resolve_tensors
from heteroes.es.snapshot import take_snapshot, diff_from_snapshot, restore_from_snapshot_
from heteroes.model.schema import ParameterSchema
from heteroes.es.checks import _check_param, _check_sigma
from heteroes.noise.engine import iter_parameter_noise_chunks
from heteroes.noise.contracts import ParameterNoiseAddress

from dataclasses import dataclass
import math
import torch 
import torch.nn as nn 
import numpy as np


DEFAULT_ETA = 1e-9
DEFAULT_CHUNK_ELEMENTS = 2**18


@dataclass(frozen=True)
class UpdateReport: 
    noop: bool


def standardize_rewards(rewards, eta=DEFAULT_ETA) -> np.ndarray: 
    # calculate in float64 then cast to float32 
    rewards = np.array(rewards, dtype=np.float64)
    # z = (r - mean(r)) / (std(r) + eta)
    mean_r = rewards.mean(dtype=np.float64)
    std_r = rewards.std(ddof=0, dtype=np.float64)

    z = (rewards - mean_r) / (std_r + np.float64(eta))
    
    return z.astype(np.float32)



# agentic esopt update style
def apply_es_update_(model: nn.Module, schema: ParameterSchema, candidate_seeds: list[int], rewards, alpha: float, chunk_elements: int=DEFAULT_CHUNK_ELEMENTS, eta=DEFAULT_ETA) -> UpdateReport: 
    # check 
    # resolve tensor
    tensors = resolve_tensors(model, schema)
    # check param 
    for tensor in tensors: 
        _check_param(tensor)
    # check eta 
    if math.isinf(eta): 
        raise ValueError("Eta being Nan/Inf")

    z_rewards = standardize_rewards(rewards, eta)
    
    # TODO: need more info for this case
    if np.all(z_rewards != 0):
        return UpdateReport(
            noop=True
        )

    with torch.no_grad(): 
        for entry, tensor in zip(schema.entries, tensors): 
            numel = tensor.numel()
            parameter_noise_address = ParameterNoiseAddress(
                candidate_seed=
            )



    
        
    
        
    