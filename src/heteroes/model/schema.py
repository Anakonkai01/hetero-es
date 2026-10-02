from collections import defaultdict
from dataclasses import dataclass, asdict

import torch.nn as nn 
import json 
import hashlib


SCHEMA_VERSION = "heteroes.parameter_schema.v1"

def find_alias_groups(model: nn.Module) -> list[list[str]]:
    """
    Return groups of parameter names that refer to the same tensor. (weight tying) 
    
        - id: id of a object store in mem in runtime (process)
        - must using remove_duplicate=False because default pytorch auto hide it (=True)
        - each group and the list of groups are sorted
    """

    groups = defaultdict(list)
    for name, param in model.named_parameters(remove_duplicate=False): 
        groups[id(param)].append(name)

    # find alias
    list_alias_groups = []
    for value in groups.values():  
        if len(value) > 1: 
            list_alias_groups.append(sorted(value))
    
    # sort
    list_alias_groups.sort()

    return list_alias_groups

@dataclass(frozen=True)
class SchemaEntry:
    """
    Schema for 
        One tensor in the parameter schema. 
        Immutable; collection fields are tuples so the entry (and its hash) cannot change after creation.
        - tuple anything that the object itself can mutable
    """
    # TODO(schema-validation): add __post_init__ that rejects invalid entries:
    #   - shape and aliases must be tuples (frozen alone leaves lists mutable)
    #   - numel must equal math.prod(shape)
    #   - aliases must be sorted (hash must not depend on discovery order)
    #   - canonical_name must not appear in aliases
    #   Raise instead of silently converting. Cover each check with a test.

    index: int 
    canonical_name: str 
    aliases: tuple[str, ...]
    shape: tuple[int, ...]
    dtype: str 
    numel: int
    
@dataclass(frozen=True)
class ParameterSchema: 
    """
    
    """
    # TODO(schema-polish): after the end-to-end path works
    #   - extract canonical_json_bytes(obj) as the ONE place that serializes for hashing
    #     (needed before adding to_json / manifest, so no second json.dumps call appears)
    #   - replace the "what" comments in hash with a "why" comment
    #   - add docstrings to ParameterSchema and hash (hash = layout fingerprint, not weights)
    #   - remove the stale line in the SchemaEntry docstring
    #   - add return type hints (to_dict -> dict, hash -> str)
    #   - build_parameter_schema: raise instead of silently skipping an alias group
    #     that has no canonical name (should be impossible; a loud failure beats lost aliases)

    schema_version: str 
    entries: tuple[SchemaEntry, ...]

    def to_dict(self) -> dict: 
        # asdict will keep the value data type, tuple still tuple 
        # asdict can recursive to subdataclass 
        return asdict(self)
    
    @property
    def hash(self) -> str:
        # sort key 
        # seperator 
        # ensure_ascii 
        raw_dict = self.to_dict()

        to_json = json.dumps(
            raw_dict,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")

        hashed = hashlib.sha256(to_json).hexdigest()
        return hashed


def build_parameter_schema(model: nn.Module) -> ParameterSchema: 
    # build a parameter schema for a model
    
    alias_groups = find_alias_groups(model) # list(list of alias name)
    canonical_name_model = [name for name, _ in model.named_parameters()]
    dict_alias_groups = {}
    for group in alias_groups: 
        # get the first met name found in group
        canonical = next((name for name in canonical_name_model if name in group), None)

        # canonical != None
        if canonical: 
            dict_alias_groups[canonical] = tuple(another_name for another_name in group if another_name != canonical)
            
        
    
    list_schema_entry = []
    for index, (name, param) in enumerate(model.named_parameters()): 
        if not param.is_floating_point(): 
            raise ValueError(f"{name} is not a floating point")
            

        schema_entry = SchemaEntry(
            index=index,
            canonical_name=name,
            aliases=dict_alias_groups.get(name, tuple()),
            dtype=str(param.dtype),
            shape=tuple(param.shape),
            numel=param.numel(),
        )

        list_schema_entry.append(schema_entry)

    param_schema = ParameterSchema(
        schema_version=SCHEMA_VERSION,
        entries=tuple(list_schema_entry),
    )

    return param_schema
    

        

