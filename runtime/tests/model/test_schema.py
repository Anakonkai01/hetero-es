import dataclasses
import hashlib
import os

import pytest
import torch
import torch.nn as nn

from heteroes.model.schema import (
    SCHEMA_VERSION,
    ParameterSchema,
    SchemaEntry,
    build_parameter_schema,
    find_alias_groups,
)


class TiedToy(nn.Module):
    def __init__(self):
        super().__init__()

        self.embed = nn.Embedding(10, 4)
        self.linear = nn.Linear(4, 10, bias=False)

        self.embed.weight = self.linear.weight


class ReverseOrderToy(nn.Module):
    # Registration order (zeta, alpha) is the opposite of alphabetical order,
    # so the names inside the group only come out sorted if the code sorts them.
    def __init__(self):
        super().__init__()

        self.zeta = nn.Linear(4, 4, bias=False)
        self.alpha = nn.Linear(4, 4, bias=False)

        self.alpha.weight = self.zeta.weight


class TripleTiedToy(nn.Module):
    def __init__(self):
        super().__init__()

        self.a = nn.Linear(4, 4, bias=False)
        self.b = nn.Linear(4, 4, bias=False)
        self.c = nn.Linear(4, 4, bias=False)

        self.b.weight = self.a.weight
        self.c.weight = self.a.weight


class TwoGroupsReverseOrderToy(nn.Module):
    # Two tied groups, registered in reverse alphabetical order (y-group first),
    # so the groups only come out sorted if the code sorts the list of groups.
    def __init__(self):
        super().__init__()

        self.y1 = nn.Linear(4, 4, bias=False)
        self.y2 = nn.Linear(4, 4, bias=False)
        self.a1 = nn.Linear(2, 2, bias=False)
        self.a2 = nn.Linear(2, 2, bias=False)

        self.y2.weight = self.y1.weight
        self.a2.weight = self.a1.weight


class SameShapeToy(nn.Module):
    def __init__(self):
        super().__init__()

        self.linear1 = nn.Linear(2, 2)
        self.linear2 = nn.Linear(2, 2)


def test_s2_tied_weights_form_one_group():
    model = TiedToy()
    groups = find_alias_groups(model)

    assert groups == [["embed.weight", "linear.weight"]]


def test_s3_names_within_group_are_sorted():
    model = ReverseOrderToy()

    # sanity check: PyTorch really does report the names in the "wrong" order
    names = [n for n, _ in model.named_parameters(remove_duplicate=False)]
    assert names == ["zeta.weight", "alpha.weight"]

    assert find_alias_groups(model) == [["alpha.weight", "zeta.weight"]]


def test_s3b_group_of_three_names_is_one_group():
    model = TripleTiedToy()
    groups = find_alias_groups(model)

    assert groups == [["a.weight", "b.weight", "c.weight"]]


def test_s3c_groups_are_sorted():
    model = TwoGroupsReverseOrderToy()
    groups = find_alias_groups(model)

    assert groups == [["a1.weight", "a2.weight"], ["y1.weight", "y2.weight"]]


def test_s4_different_tensors_same_shape_are_not_grouped():
    model = SameShapeToy()
    groups = find_alias_groups(model)

    assert len(groups) == 0


# ---------------------------------------------------------------------------
# ParameterSchema: hash
# ---------------------------------------------------------------------------

def make_small_schema():
    e0 = SchemaEntry(0, "w", ("b",), (2, 3), "torch.float16", 6)
    e1 = SchemaEntry(1, "x", (), (4,), "torch.float16", 4)
    return ParameterSchema(SCHEMA_VERSION, (e0, e1))


def test_hash_matches_hand_written_canonical_json():
    # Independent oracle: the canonical JSON written by hand (keys sorted,
    # no whitespace). If code and hand-written string agree, the serialization
    # follows the contract.
    manual = (
        '{"entries":['
        '{"aliases":["b"],"canonical_name":"w","dtype":"torch.float16",'
        '"index":0,"numel":6,"shape":[2,3]},'
        '{"aliases":[],"canonical_name":"x","dtype":"torch.float16",'
        '"index":1,"numel":4,"shape":[4]}],'
        '"schema_version":"heteroes.parameter_schema.v1"}'
    )
    expected = hashlib.sha256(manual.encode("utf-8")).hexdigest()

    assert make_small_schema().hash == expected


def test_hash_escapes_non_ascii_names():
    # ensure_ascii=True makes the bytes independent of any text-encoding choice.
    entry = SchemaEntry(0, "café", (), (1,), "torch.float16", 1)
    manual = (
        '{"entries":[{"aliases":[],"canonical_name":"caf\\u00e9","dtype":"torch.float16",'
        '"index":0,"numel":1,"shape":[1]}],"schema_version":"heteroes.parameter_schema.v1"}'
    )
    expected = hashlib.sha256(manual.encode("utf-8")).hexdigest()

    assert ParameterSchema(SCHEMA_VERSION, (entry,)).hash == expected


def test_s1_hash_is_deterministic():
    assert make_small_schema().hash == make_small_schema().hash


def test_s5_hash_changes_when_entry_order_changes():
    schema = make_small_schema()
    swapped = dataclasses.replace(schema, entries=tuple(reversed(schema.entries)))

    assert swapped.hash != schema.hash


def test_s5_hash_changes_when_aliases_change():
    schema = make_small_schema()
    no_alias = dataclasses.replace(schema.entries[0], aliases=())
    changed = dataclasses.replace(schema, entries=(no_alias, schema.entries[1]))

    assert changed.hash != schema.hash


def test_s5_hash_changes_when_version_changes():
    schema = make_small_schema()

    assert dataclasses.replace(schema, schema_version="other").hash != schema.hash


@pytest.mark.parametrize(
    "field, value",
    [("shape", (9, 9)), ("dtype", "torch.float32"), ("numel", 7), ("canonical_name", "z")],
)
def test_s5_hash_changes_when_entry_field_changes(field, value):
    schema = make_small_schema()
    changed_entry = dataclasses.replace(schema.entries[0], **{field: value})
    changed = dataclasses.replace(schema, entries=(changed_entry, schema.entries[1]))

    assert changed.hash != schema.hash


def test_s6_serialized_keys_are_exactly_the_contract_fields():
    data = make_small_schema().to_dict()

    assert set(data) == {"schema_version", "entries"}
    for entry in data["entries"]:
        assert set(entry) == {"index", "canonical_name", "aliases", "shape", "dtype", "numel"}


def test_schema_entry_is_frozen():
    entry = make_small_schema().entries[0]

    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.index = 5


# ---------------------------------------------------------------------------
# build_parameter_schema
# ---------------------------------------------------------------------------

class NoAliasToy(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Linear(2, 2)


class TiedThenPlainToy(nn.Module):
    # Like Qwen: the tied tensor comes first, plain tensors afterwards.
    def __init__(self):
        super().__init__()
        self.embed = nn.Embedding(10, 4)
        self.head = nn.Linear(4, 10, bias=False)
        self.head.weight = self.embed.weight
        self.fc = nn.Linear(4, 4)


class IntParamToy(nn.Module):
    def __init__(self):
        super().__init__()
        self.p = nn.Parameter(torch.zeros(3, dtype=torch.int64), requires_grad=False)


def test_build_model_without_aliases():
    schema = build_parameter_schema(NoAliasToy())

    assert [e.canonical_name for e in schema.entries] == ["fc.weight", "fc.bias"]
    assert all(e.aliases == () for e in schema.entries)


def test_build_records_alias_on_canonical_entry_only():
    schema = build_parameter_schema(TiedThenPlainToy())
    by_name = {e.canonical_name: e for e in schema.entries}

    assert by_name["embed.weight"].aliases == ("head.weight",)
    assert by_name["fc.weight"].aliases == ()
    assert by_name["fc.bias"].aliases == ()
    # the tied tensor is ONE entry, the alias name has no entry of its own
    assert "head.weight" not in by_name


def test_build_canonical_name_is_first_registered_not_first_alphabetical():
    # ReverseOrderToy: "zeta" registered first, "alpha" second.
    # PyTorch reports "zeta.weight", so that is the canonical name even
    # though "alpha.weight" sorts first.
    schema = build_parameter_schema(ReverseOrderToy())

    assert len(schema.entries) == 1
    assert schema.entries[0].canonical_name == "zeta.weight"
    assert schema.entries[0].aliases == ("alpha.weight",)


def test_build_triple_tied_has_two_aliases_sorted():
    schema = build_parameter_schema(TripleTiedToy())

    assert len(schema.entries) == 1
    assert schema.entries[0].aliases == ("b.weight", "c.weight")


def test_build_entry_fields_and_index_follow_model_order():
    schema = build_parameter_schema(TiedThenPlainToy())

    assert [e.index for e in schema.entries] == [0, 1, 2]
    assert schema.entries[0].shape == (10, 4)
    assert schema.entries[0].numel == 40
    assert schema.entries[0].dtype == "torch.float32"


def test_build_uses_plain_tuples_everywhere():
    schema = build_parameter_schema(TiedThenPlainToy())

    assert type(schema.entries) is tuple
    for e in schema.entries:
        assert type(e.aliases) is tuple
        assert type(e.shape) is tuple  # not torch.Size


def test_build_rejects_non_floating_parameter():
    with pytest.raises(ValueError):
        build_parameter_schema(IntParamToy())


def test_build_is_deterministic_and_leaves_model_untouched():
    model = TiedThenPlainToy()
    groups_before = find_alias_groups(model)

    first = build_parameter_schema(model)
    second = build_parameter_schema(model)

    assert first.hash == second.hash
    assert find_alias_groups(model) == groups_before


def test_build_hash_depends_on_alias_structure():
    tied = TiedThenPlainToy()
    untied = TiedThenPlainToy()
    untied.head.weight = nn.Parameter(untied.head.weight.detach().clone())  # break the tie

    assert build_parameter_schema(tied).hash != build_parameter_schema(untied).hash


# ---------------------------------------------------------------------------
# S9: real Qwen2.5-0.5B layout. Skipped unless a checkpoint directory is given:
#   HETEROES_QWEN_PATH=/path/to/qwen_checkpoint pytest tests/model/test_schema.py
# The schema depends only on layout, so any checkpoint of this architecture works.
# ---------------------------------------------------------------------------

QWEN_PATH = os.environ.get("HETEROES_QWEN_PATH")

# Hash of the probe-style schema (no aliases, no version) recorded by the physical
# probes on both machines (artifacts/probes/2026-09-29).
PROBE_SCHEMA_HASH = "152e9d82e61d6610a414466026ac60a13e718924dfdf0416809686adcf4188e1"
# Production hash (aliases + schema_version), first computed 2026-10-02.
PRODUCTION_SCHEMA_HASH = "0b21250e331398a266785dc473da3a8b8f5e8f98fa15e9044637d742eb7845ec"


@pytest.mark.skipif(QWEN_PATH is None, reason="set HETEROES_QWEN_PATH to run the Qwen layout test")
def test_s9_qwen_layout_matches_probe_evidence():
    import json

    from transformers import AutoModelForCausalLM

    model = AutoModelForCausalLM.from_pretrained(QWEN_PATH, dtype=torch.float16)
    schema = build_parameter_schema(model)

    assert len(schema.entries) == 290
    assert sum(e.numel for e in schema.entries) == 494_032_768
    assert [(e.canonical_name, e.aliases) for e in schema.entries if e.aliases] == [
        ("model.embed_tokens.weight", ("lm_head.weight",))
    ]
    assert schema.entries[0].numel == 136_134_656
    assert schema.entries[-1].canonical_name == "model.norm.weight"

    # Rebuild the probe's schema from our entries: it must hash exactly like the probe did.
    probe_style = [
        {"index": e.index, "name": e.canonical_name, "shape": list(e.shape),
         "dtype": e.dtype, "numel": e.numel}
        for e in schema.entries
    ]
    raw = json.dumps(probe_style, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert hashlib.sha256(raw.encode("utf-8")).hexdigest() == PROBE_SCHEMA_HASH

    assert schema.hash == PRODUCTION_SCHEMA_HASH
