"""
Subset weight spaces (ADR-008 section 4): a trainable schema that selects some parameters of a full schema. The frozen
perturbation, restore and update code runs over it unchanged; unselected tensors never move, and a FULL schema must still
match its model exactly.
"""

import numpy as np
import pytest
import torch
import torch.nn as nn

from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.es.update import apply_coefficients_
from heteroes.model.schema import (
    SUBSET_SCHEMA_VERSION,
    ParameterSchema,
    SchemaMismatchError,
    build_parameter_schema,
    resolve_tensors,
    select_parameters,
)
from heteroes.noise.contracts import ParameterNoiseAddress
from heteroes.noise.engine import iter_parameter_noise_chunks

CHUNK = 32


class Tied(nn.Module):
    def __init__(self, extra=False):
        super().__init__()
        torch.manual_seed(1)
        self.embed = nn.Embedding(10, 6)
        self.layers = nn.ModuleList(nn.Linear(6, 6) for _ in range(3))
        self.head = nn.Linear(6, 10, bias=False)
        self.head.weight = self.embed.weight
        if extra:  # a module registered last, so the earlier parameters keep their index
            self.tail = nn.Linear(6, 1)
        self.half()


def bits(model):
    return {name: p.detach().clone().view(torch.int16) for name, p in model.named_parameters()}


def test_a_subset_keeps_full_entries_in_order_and_follows_aliases():
    full = build_parameter_schema(Tied())
    subset = select_parameters(full, [r"layers\.[02]\.weight", r"^head\."])
    assert subset.schema_version == SUBSET_SCHEMA_VERSION and subset.hash != full.hash
    names = [entry.canonical_name for entry in subset.entries]
    assert names == ["embed.weight", "layers.0.weight", "layers.2.weight"]  # head.weight is an alias of embed.weight
    assert all(entry in full.entries for entry in subset.entries)
    model = Tied()
    parameters = dict(model.named_parameters())
    assert [t.data_ptr() for t in resolve_tensors(model, subset)] == [parameters[name].data_ptr() for name in names]


@pytest.mark.parametrize("include", [[], [""], ["nothing-matches"], ["("]])
def test_a_subset_that_selects_nothing_or_is_malformed_is_refused(include):
    import re

    with pytest.raises((ValueError, re.error)):
        select_parameters(build_parameter_schema(Tied()), include)


def test_a_subset_cannot_be_narrowed_again():
    subset = select_parameters(build_parameter_schema(Tied()), ["layers"])
    with pytest.raises(ValueError, match="full schema"):
        select_parameters(subset, ["layers.0"])


def test_a_full_schema_still_refuses_a_model_with_an_extra_parameter():
    with pytest.raises(SchemaMismatchError):
        resolve_tensors(Tied(extra=True), build_parameter_schema(Tied()))
    # a subset does not pin the parameters it leaves out: the recipe pins the model files instead (ADR-008 section 4)
    subset = select_parameters(build_parameter_schema(Tied()), ["layers.1"])
    assert len(resolve_tensors(Tied(extra=True), subset)) == 2


def test_a_subset_refuses_a_model_whose_parameter_indices_moved():
    class Shifted(Tied):
        def __init__(self):
            super().__init__()
            self.first = nn.Parameter(
                torch.zeros(3, dtype=torch.float16)
            )  # root parameters come first: every index moves

    subset = select_parameters(build_parameter_schema(Tied()), ["layers.1"])
    with pytest.raises(SchemaMismatchError):
        resolve_tensors(Shifted(), subset)


def test_a_subset_that_is_not_an_ordered_selection_of_the_model_is_refused():
    full = build_parameter_schema(Tied())
    subset = select_parameters(full, ["layers"])
    reordered = ParameterSchema(SUBSET_SCHEMA_VERSION, tuple(reversed(subset.entries)))
    changed = ParameterSchema(
        SUBSET_SCHEMA_VERSION, (subset.entries[0].__class__(**{**subset.entries[0].__dict__, "shape": (7, 6)}),)
    )
    renumbered = ParameterSchema(
        SUBSET_SCHEMA_VERSION, (subset.entries[0].__class__(**{**subset.entries[0].__dict__, "index": 0}),)
    )
    empty = ParameterSchema(SUBSET_SCHEMA_VERSION, ())
    for bad in (reordered, changed, renumbered, empty):
        with pytest.raises(SchemaMismatchError):
            resolve_tensors(Tied(), bad)


def test_perturb_restore_and_update_touch_only_the_subset():
    model = Tied()
    full = build_parameter_schema(model)
    subset = select_parameters(full, [r"layers\.1\."])
    selected = {entry.canonical_name for entry in subset.entries}
    before = bits(model)
    snapshot = take_snapshot(model, subset)
    perturb_model_(model, subset, 77, 5e-2, CHUNK)
    after = bits(model)
    assert all(torch.equal(before[n], after[n]) != (n in selected) for n in before)  # exactly the subset moved
    restore_from_snapshot_(model, subset, snapshot)
    assert all(torch.equal(before[n], bits(model)[n]) for n in before)
    apply_coefficients_(model, subset, [5, 6], np.array([1.0, -1.0], dtype=np.float32), 0.5, CHUNK)
    updated = bits(model)
    assert all(torch.equal(before[n], updated[n]) != (n in selected) for n in before)


def test_subset_noise_is_addressed_by_the_subset_hash_and_original_index():
    model = Tied()
    subset = select_parameters(build_parameter_schema(model), [r"layers\.2\.bias"])
    (entry,) = subset.entries
    old = dict(model.named_parameters())["layers.2.bias"].detach().clone()
    perturb_model_(model, subset, 5, 1e-2, CHUNK)
    address = ParameterNoiseAddress(5, subset.hash, entry.index, CHUNK)
    eps = np.concatenate([n for _, _, n in iter_parameter_noise_chunks(address, old.numel())]).astype(np.float32)
    expected = (old.float().numpy() + eps * np.float32(1e-2)).astype(np.float16)
    assert entry.index == 6  # embed 0, three layers x (weight, bias) 1..6
    assert np.array_equal(
        dict(model.named_parameters())["layers.2.bias"].detach().numpy().view(np.int16), expected.view(np.int16)
    )


def test_a_pattern_may_match_anywhere_in_a_name():
    subset = select_parameters(build_parameter_schema(Tied()), [r"\.bias$"])
    assert [entry.canonical_name for entry in subset.entries] == ["layers.0.bias", "layers.1.bias", "layers.2.bias"]
