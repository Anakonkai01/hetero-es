"""Canonical ES parameter views over serving-engine fused storage; no vLLM dependency or GPU."""

import copy

import pytest
import torch

from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.eval.candidate import model_weights_sha256
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.model.schema import build_parameter_schema
from heteroes.noise.contracts import ENGINE_V2
from test_strict_decoder import model_for


def fused_owner(model):
    owner = copy.deepcopy(model)
    for layer in owner.model.layers:
        for parent, names, packed in (
            (layer.self_attn, ("q_proj", "k_proj", "v_proj"), "qkv_proj"),
            (layer.mlp, ("gate_proj", "up_proj"), "gate_up_proj"),
        ):
            modules = [getattr(parent, name) for name in names]
            combined = torch.nn.Linear(modules[0].weight.shape[1], sum(m.weight.shape[0] for m in modules), bias=True)
            combined.weight = torch.nn.Parameter(torch.cat([m.weight for m in modules]))
            combined.bias = (
                None if modules[0].bias is None else torch.nn.Parameter(torch.cat([m.bias for m in modules]))
            )
            for name in names:
                delattr(parent, name)
            setattr(parent, packed, combined)
    return owner


@pytest.mark.parametrize("family", ["qwen2", "llama", "llama-wide", "mistral"])
def test_fused_views_keep_hf_schema_bits_and_canonical_candidate_restore(family):
    from heteroes.eval.vllm_weights import hf_parameter_view

    parent = model_for(family)
    owner = fused_owner(parent)
    view = hf_parameter_view(owner, parent.config)
    schema = build_parameter_schema(parent)
    assert build_parameter_schema(view) == schema
    assert model_weights_sha256(view, schema) == model_weights_sha256(parent, schema)
    storages = {p.untyped_storage().data_ptr() for p in owner.parameters()}
    assert all(p.untyped_storage().data_ptr() in storages for p in view.parameters())
    saved = take_snapshot(view, schema)
    original = model_weights_sha256(view, schema)
    for model in (parent, view):
        perturb_model_(model, schema, 7001, 1e-3, engine=ENGINE_V2)
    assert model_weights_sha256(view, schema) != original
    assert model_weights_sha256(view, schema) == model_weights_sha256(parent, schema)
    restore_from_snapshot_(view, schema, saved)
    assert model_weights_sha256(view, schema) == original


@pytest.mark.parametrize("defect", ["missing", "shape", "dtype", "extra"])
def test_incompatible_fused_storage_is_rejected_without_writing_owner(defect):
    from heteroes.eval.vllm_weights import hf_parameter_view

    parent = model_for("qwen2")
    owner = fused_owner(parent)
    qkv = owner.model.layers[0].self_attn.qkv_proj
    if defect == "missing":
        del qkv.weight
    elif defect == "shape":
        qkv.weight = torch.nn.Parameter(qkv.weight[:-1].detach().clone())
    elif defect == "dtype":
        qkv.weight = torch.nn.Parameter(qkv.weight.float())
    else:
        owner.register_parameter("unconsumed", torch.nn.Parameter(torch.ones(3).half()))
    before = {name: p.detach().clone() for name, p in owner.named_parameters()}
    with pytest.raises(ReferenceArithmeticError):
        hf_parameter_view(owner, parent.config)
    assert all(torch.equal(p, before[name]) for name, p in owner.named_parameters())


def test_padded_tied_vocabulary_remains_one_canonical_parameter():
    from heteroes.eval.vllm_weights import hf_parameter_view

    parent = model_for("qwen2")
    owner = fused_owner(parent)
    padded = torch.nn.Parameter(torch.cat((owner.model.embed_tokens.weight, torch.zeros(5, 24).half())))
    owner.model.embed_tokens.weight = owner.lm_head.weight = padded
    view = hf_parameter_view(owner, parent.config)
    assert view.model.embed_tokens.weight is view.lm_head.weight
    assert view.model.embed_tokens.weight.shape == parent.model.embed_tokens.weight.shape
    assert build_parameter_schema(view) == build_parameter_schema(parent)
