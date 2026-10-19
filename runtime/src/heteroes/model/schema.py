from collections import defaultdict
from dataclasses import dataclass, asdict

import torch
import torch.nn as nn

from heteroes.canonical import canonical_json_hash


SCHEMA_VERSION = "heteroes.parameter_schema.v1"
# A trainable subset of a full schema (ADR-008 section 4): its entries are entries of the full schema, unchanged (original
# index included) and in the same order. The version says so, so that a FULL schema still has to match the model exactly.
SUBSET_SCHEMA_VERSION = "heteroes.parameter_schema.v1.subset"


def find_alias_groups(model: nn.Module) -> list[list[str]]:
    # fmt: off
    """
    Return groups of parameter names that refer to the same tensor. (weight tying) 
    
        - id: id of a object store in mem in runtime (process)
        - must using remove_duplicate=False because default pytorch auto hide it (=True)
        - each group and the list of groups are sorted
    """
    # fmt: on

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
    # fmt: off
    """
    Schema for 
        One tensor in the parameter schema. 
        Immutable; collection fields are tuples so the entry (and its hash) cannot change after creation.
        - tuple anything that the object itself can mutable
    """
    # fmt: on

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
    # fmt: off
    """
    
    """
    # fmt: on

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
        # the layout fingerprint: the shared canonical serialization of the schema document, hashed
        return canonical_json_hash(self.to_dict())


def build_parameter_schema(model: nn.Module) -> ParameterSchema:
    # build a parameter schema for a model

    alias_groups = find_alias_groups(model)  # list(list of alias name)
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


# check exception schema mismatch
class SchemaMismatchError(Exception):
    pass


def select_parameters(schema: ParameterSchema, include: list[str]) -> ParameterSchema:
    """
    The trainable schema of a subset weight space: the entries of a full schema whose canonical name or one of its aliases
    matches one of the `include` patterns (`re.search`), unchanged and in schema order. A tied tensor is selected when any
    of its names matches. Noise, perturbation, restore and update then touch only these tensors; the subset's own hash
    addresses its noise.
    """
    import re

    if schema.schema_version != SCHEMA_VERSION:
        raise ValueError("a subset is selected from a full schema")
    if not include or not all(isinstance(pattern, str) and pattern for pattern in include):
        raise ValueError("a subset needs at least one nonempty pattern")
    patterns = [re.compile(pattern) for pattern in include]
    entries = tuple(
        entry
        for entry in schema.entries
        if any(pattern.search(name) for pattern in patterns for name in (entry.canonical_name, *entry.aliases))
    )
    if not entries:
        raise ValueError("the subset selects no parameter")
    return ParameterSchema(schema_version=SUBSET_SCHEMA_VERSION, entries=entries)


def _ordered_selection(entries, full_entries) -> bool:
    remaining = iter(full_entries)
    return bool(entries) and all(any(entry == candidate for candidate in remaining) for entry in entries)


def resolve_tensors(model: nn.Module, schema: ParameterSchema) -> list[torch.Tensor]:
    current_model_schema = build_parameter_schema(model)

    if schema.schema_version == SUBSET_SCHEMA_VERSION:
        # a subset is checked entry by entry against the model's full schema (its hash differs by construction)
        if not _ordered_selection(schema.entries, current_model_schema.entries):
            raise SchemaMismatchError(
                f"the subset schema {schema.hash} is not an ordered selection of this model's parameters "
                f"(model schema {current_model_schema.hash})"
            )
    # fast check, using hash
    elif current_model_schema.hash != schema.hash:
        mismatch_info = []

        # check version schema
        if current_model_schema.schema_version != schema.schema_version:
            mismatch_info.append(
                f"Version mismatch: expected {schema.schema_version}, got: {current_model_schema.schema_version}"
            )
        # check len entry
        if len(current_model_schema.entries) != len(schema.entries):
            mismatch_info.append(
                f"Length entries mismatch: expected {len(schema.entries)}, got: {len(current_model_schema.entries)}"
            )
        # detail check
        else:
            for expected, actual in zip(schema.entries, current_model_schema.entries, strict=True):
                if expected != actual:
                    mismatch_info.append(
                        f"Mismatch at index {expected.index} (canonical: '{expected.canonical_name}'):\n"
                        f"  Expected: name='{expected.canonical_name}', shape={expected.shape}, dtype={expected.dtype}, aliases={expected.aliases}\n"
                        f"  Actual: name='{actual.canonical_name}', shape={actual.shape}, dtype={actual.dtype}, aliases={actual.aliases}"
                    )

        # join to string
        detail_msg = "\n".join(mismatch_info)
        # raise SchemaMismatchError
        raise SchemaMismatchError(
            f"Model parameter schema does not match expected schema.\n"
            f"Expected Hash: {schema.hash}\n"
            f"Actual Hash: {current_model_schema.hash}\n"
            f"Details:\n{detail_msg}"
        )

    # pass all check -> return list of tensor
    resolved_tensor: list[torch.Tensor] = []

    param_dict = dict(model.named_parameters(remove_duplicate=True))
    for entry in schema.entries:
        tensor = param_dict[entry.canonical_name]
        resolved_tensor.append(tensor)

    return resolved_tensor
