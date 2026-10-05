from heteroes.model.schema import ParameterSchema, resolve_tensors
from heteroes.es.perturb import _check_param
from heteroes.model.schema import SchemaMismatchError

from dataclasses import dataclass
import torch 
import torch.nn as nn


DEFAULT_SLAB = 2**24

@dataclass(frozen=True, eq=False)
class Snapshot: 
    """
    Storing snapshot tensor and it schema hash 
    - not allow this to do it own compare
    """
    schema_hash: str
    tensors: tuple[torch.Tensor, ...]

    
class RestoreError(Exception):
    pass



# copy model from gpu to cpu 
def take_snapshot(model: nn.Module, schema: ParameterSchema) -> Snapshot: 
    # resolved tensor 
    tensors = resolve_tensors(model, schema)
    for tensor in tensors: 
        _check_param(tensor)
    
    schema_hash = schema.hash
    tensors_cpu: list[torch.Tensor]= []
    with torch.no_grad():
        for tensor in tensors: 
            # copy = true because if tensor already in cpu, it does not copy, so must explicitly copy=true
            # TODO: consider using non-blocking 
            tensors_cpu.append(tensor
                               .detach()
                               .to(device="cpu", copy=True))

    return Snapshot(schema_hash=schema_hash, tensors=tuple(tensors_cpu)) 



# compare bit by bit with snapshot (using int16)
def diff_from_snapshot(model: nn.Module, schema: ParameterSchema, snapshot: Snapshot, slab_elements=DEFAULT_SLAB) -> list[str]: 
    if not slab_elements >= 1: 
        raise ValueError("slab_elements must be >= 1")

    # resolve tensor
    tensors = resolve_tensors(model, schema)

    # check contiguous and dtype
    for tensor in tensors: 
        _check_param(tensor)

    # check snapshot hash with current model 
    schema_hash = schema.hash 
    if snapshot.schema_hash != schema_hash: 
        raise SchemaMismatchError("current model schema hash!= snapshot schema hash")
    
    # using Slab technique: 
    # move a slab (slab_elements) from cpu to gpu then compare it
    # using bit compare int16
    diff: list[str] = []
    with torch.no_grad():
        for entry, live_tensor, saved_tensor in zip(schema.entries, tensors, snapshot.tensors, strict=True):
             
            numel = live_tensor.numel()
            # flatten the tensor and reinterpretate from float16 to int16 to compare (compare raw bits: as numbers NaN != NaN and +0.0 == -0.0)
            live_tensor_flat = live_tensor.view(-1)
            saved_tensor_flat = saved_tensor.view(-1)
             
            
            for start in range(0, numel, slab_elements): 
                end = min(numel, start + slab_elements)

                # slab
                saved_slab = saved_tensor_flat[start : end]
                live_slab = live_tensor_flat[start : end]
                # move save slab to same device as live (move to gpu)
                saved_slab = saved_slab.to(device=live_tensor.device)

                # compare int 16 bit
                saved_slab_int16 = saved_slab.view(torch.int16)
                live_slab_int16 = live_slab.view(torch.int16)

                compared = torch.equal(saved_slab_int16, live_slab_int16)
                if not compared: 
                    diff.append(entry.canonical_name)
                    # stop this loop (slab loop) to move to another tensor
                    break
    
    return diff
                
# restore model from snapshot 
def restore_from_snapshot_(model: nn.Module, schema: ParameterSchema, snapshot: Snapshot, slab_elements: int=DEFAULT_SLAB) -> None: 
    if not slab_elements >= 1: 
        raise ValueError("slab_elements must be >= 1")

    # resolved 
    tensors = resolve_tensors(model, schema) 

    # check snapshot hash 
    schema_hash = schema.hash
    if snapshot.schema_hash != schema_hash: 
        raise SchemaMismatchError("current model schema hash != snapshot schema hash")

    # check contiguous and dtype
    for tensor in tensors: 
        _check_param(tensor)

    with torch.no_grad():
        # restore, using copy inplace 
        for live_tensor, saved_tensor in zip(tensors, snapshot.tensors, strict=True):
            live_tensor.copy_(saved_tensor)

    # check after restore 
    bad = diff_from_snapshot(model, schema, snapshot, slab_elements)
    if len(bad) > 0: 
        raise RestoreError(
            f"Restore left {len(bad)} tensor(s) different from snapshot:\n"
            f"{bad}"
        )

    