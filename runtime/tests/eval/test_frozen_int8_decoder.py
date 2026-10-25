"""Frozen-int8 decoder composition: independent eager oracle, graph admission and adapter isolation."""

import pytest
import torch

from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.eval import frozen_int8
from heteroes.eval import reference_ops as ops
from heteroes.eval.frozen_int8_decoder import (
    REFERENCE_BACKEND,
    FrozenInt8DecoderReference,
)
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.eval.strict_decoder import describe_graph
from heteroes.model.frozen_int8 import freeze_projections, freeze_tied_head, frozen_modules
from heteroes.model.lora import trainable_schema
from test_strict_decoder import bits, model_for

TARGETS = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")


def project(value, module):
    if getattr(module, "is_frozen_int8_head", False):
        artifact = frozen_int8.FrozenInt8Artifact(
            weight_q=module.frozen_weight_q,
            weight_scale=module.frozen_weight_scale,
            metadata=dict(module.frozen_head_metadata),
            sha256=module.frozen_head_sha256,
            format_version=frozen_int8.ARTIFACT_FORMAT_VERSION,
        )
        return frozen_int8.linear(value, artifact, getattr(module, "bias", None))
    if getattr(module, "is_frozen_int8_linear", False):
        return frozen_int8.combine_adapter(module.base_linear_cpu(value), module.lora_delta(value))
    return ops.linear(value, module.weight, getattr(module, "bias", None))


def rotate(value, cosine, sine, head_dim):
    half = head_dim // 2
    rotated = torch.cat((-value[..., half:], value[..., :half]), dim=-1)
    return ops.add(ops.mul(value, cosine), ops.mul(rotated, sine))


def eager_forward(backend, input_ids, cache=None):
    """Test-local projection composition, independent of the decoder's ``_linear`` dispatch."""
    config, model = backend.config, backend.model
    past = 0 if cache is None else cache[0][0].shape[2]
    length = input_ids.shape[1]
    hidden = model.model.embed_tokens.weight[input_ids].float()
    positions = torch.arange(past, past + length, device=backend.device, dtype=torch.float32)
    angles = ops.mul(positions[:, None], backend._inverse_frequency[None, :])
    sine, cosine = ops.sin_cos(angles)
    sine, cosine = (torch.cat((part, part), dim=-1)[None, None, :, :] for part in (sine, cosine))
    new_cache = []
    for number, layer in enumerate(model.model.layers):
        residual = hidden
        normalized = ops.rms_norm(hidden, layer.input_layernorm.weight, config.rms_norm_eps)
        attention = layer.self_attn
        q = (
            project(normalized, attention.q_proj)
            .reshape(1, length, config.num_attention_heads, backend.head_dim)
            .transpose(1, 2)
        )
        k = (
            project(normalized, attention.k_proj)
            .reshape(1, length, config.num_key_value_heads, backend.head_dim)
            .transpose(1, 2)
        )
        v = (
            project(normalized, attention.v_proj)
            .reshape(1, length, config.num_key_value_heads, backend.head_dim)
            .transpose(1, 2)
        )
        q, k = rotate(q, cosine, sine, backend.head_dim), rotate(k, cosine, sine, backend.head_dim)
        if cache is not None:
            k, v = (torch.cat((old, current), dim=2) for old, current in zip(cache[number], (k, v)))
        new_cache.append((k, v))
        hidden = ops.add(residual, project(backend._attention(q, k, v, past), attention.o_proj))
        residual = hidden
        normalized = ops.rms_norm(hidden, layer.post_attention_layernorm.weight, config.rms_norm_eps)
        gated = ops.mul(
            ops.silu(project(normalized, layer.mlp.gate_proj)),
            project(normalized, layer.mlp.up_proj),
        )
        hidden = ops.add(residual, project(gated, layer.mlp.down_proj))
    hidden = ops.rms_norm(hidden[:, -1], model.model.norm.weight, config.rms_norm_eps)
    return project(hidden, model.lm_head), tuple(new_cache)


def frozen_model(seed=7, targets=TARGETS):
    model = model_for("qwen2")
    freeze_projections(model, rank=2, alpha=4, seed=seed, target_modules=targets)
    return model


def test_cuda_rank_admission_precedes_cuda_allocation_and_keeps_the_cpu_reference(monkeypatch):
    from heteroes.eval.frozen_int8_decoder import FrozenInt8DecoderGraph
    from heteroes.eval.strict_decoder_graph import StrictDecoderGraph

    model = model_for("qwen2")
    freeze_projections(model, rank=33, alpha=66, seed=19, target_modules=("q_proj",))
    # The eager oracle supports this rank. CUDA's fused product currently supports only rank <= 32.
    reference = FrozenInt8DecoderReference(model, max_context=64, allow_fixture=True)
    assert all(item["rank"] == 33 for item in reference.identity["graph"]["frozenProjections"].values())
    monkeypatch.setattr(StrictDecoderGraph, "__init__", lambda *a, **k: pytest.fail("must reject before CUDA setup"))
    with pytest.raises(ReferenceArithmeticError, match="rank.*32"):
        FrozenInt8DecoderGraph(model, max_context=64, allow_fixture=True)


def test_cuda_rank_32_reaches_cuda_setup(monkeypatch):
    from heteroes.eval.frozen_int8_decoder import FrozenInt8DecoderGraph
    from heteroes.eval.strict_decoder_graph import StrictDecoderGraph

    model = model_for("qwen2")
    freeze_projections(model, rank=32, alpha=64, seed=23, target_modules=("q_proj",))

    def admitted(*args, **kwargs):
        raise RuntimeError("admitted to CUDA setup")

    monkeypatch.setattr(StrictDecoderGraph, "__init__", admitted)
    with pytest.raises(RuntimeError, match="admitted to CUDA setup"):
        FrozenInt8DecoderGraph(model, max_context=64, allow_fixture=True)


@pytest.mark.parametrize("rank,execution", [(8, "output"), (16, "output"), (17, "warp"), (32, "warp")])
def test_adapter_finish_uses_the_measured_rank_policy_and_retains_a_strict_control(rank, execution):
    from types import SimpleNamespace

    from heteroes.eval.frozen_int8_decoder import FrozenInt8DecoderGraph

    captured = {}

    def finish(*args, **kwargs):
        captured.update(kwargs)
        return args[2]

    decoder = object.__new__(FrozenInt8DecoderGraph)
    decoder.kernels = SimpleNamespace(lora_finish=finish)
    module = SimpleNamespace(
        rank=rank, adapter_name="default", lora_B={"default": SimpleNamespace(weight=None)}, scaling=2.0
    )
    base = object()
    assert decoder._adapter_finish(None, base, module, None) is base
    assert captured["execution"] == execution


def test_cpu_reference_projects_a_pinned_tied_head_and_changes_only_the_head_arithmetic():
    strict_model = frozen_model()
    pinned_model = frozen_model()
    digest = freeze_tied_head(pinned_model)
    strict = FrozenInt8DecoderReference(strict_model, max_context=64, allow_fixture=True)
    pinned = FrozenInt8DecoderReference(pinned_model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[3, 5, 7, 11, 13]])
    expected, _ = eager_forward(pinned, ids)
    actual, _ = pinned.forward_tokens(ids)
    assert torch.equal(bits(actual), bits(expected))
    strict_head, _ = strict.forward_tokens(ids)
    assert not torch.equal(bits(actual), bits(strict_head))
    assert pinned.identity["graph"]["frozenTiedHead"] == {
        "lm_head": {
            "artifactSha256": digest,
            "storageTied": True,
            "numericalWeight": "int8_approximation_of_storage_tied_fp16_embedding",
            "inFeatures": pinned.config.hidden_size,
            "outFeatures": pinned.config.vocab_size,
            "bias": False,
            "rank": 0,
        }
    }


def test_cpu_reference_matches_independent_eager_projection_composition():
    model = frozen_model()
    backend = FrozenInt8DecoderReference(model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[3, 5, 7, 11, 13]])
    expected, _ = eager_forward(backend, ids)
    actual, cache = backend.forward_tokens(ids)
    assert torch.equal(bits(actual), bits(expected))
    assert len(cache) == model.config.num_hidden_layers

    _, prefix = backend.forward_tokens(ids[:, :2])
    incremental, _ = backend.forward_tokens(ids[:, 2:], prefix)
    assert torch.equal(bits(incremental), bits(actual))

    descriptors = backend.identity["graph"]["frozenProjections"]
    assert len(descriptors) == 2 * len(TARGETS)
    for name, module in frozen_modules(model):
        assert descriptors[name]["artifactSha256"] == module.artifact_sha256
        assert descriptors[name]["rank"] == module.rank
        assert descriptors[name]["bias"] is (module.bias is not None)


def test_partial_freeze_mixes_frozen_and_fp16_projections():
    model = frozen_model(seed=9, targets=("q_proj", "down_proj"))
    backend = FrozenInt8DecoderReference(model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[1, 4, 9, 16]])
    expected, _ = eager_forward(backend, ids)
    actual, _ = backend.forward_tokens(ids)
    assert torch.equal(bits(actual), bits(expected))
    descriptors = backend.identity["graph"]["frozenProjections"]
    assert set(descriptors) == {
        "model.layers.0.self_attn.q_proj",
        "model.layers.0.mlp.down_proj",
        "model.layers.1.self_attn.q_proj",
        "model.layers.1.mlp.down_proj",
    }


def test_graph_admission_requires_the_explicit_frozen_mode():
    model = frozen_model(seed=11, targets=("q_proj",))
    with pytest.raises(ReferenceArithmeticError, match="explicit frozen"):
        describe_graph(model, 64)
    graph = describe_graph(model, 64, frozen_int8=True)
    assert set(graph["frozenProjections"]) == {
        "model.layers.0.self_attn.q_proj",
        "model.layers.1.self_attn.q_proj",
    }
    with pytest.raises(ReferenceArithmeticError, match="selects no typed"):
        describe_graph(model_for("qwen2"), 64, frozen_int8=True)
    with pytest.raises(ReferenceArithmeticError, match="boolean"):
        describe_graph(model, 64, frozen_int8=1)


@pytest.mark.parametrize(
    "defect",
    [
        "weight_dtype",
        "weight_shape",
        "scale_shape",
        "weight_attribute",
        "digest_type",
        "digest_chars",
        "adapter_set",
        "adapter_dtype",
        "adapter_grad",
        "bias_dtype",
    ],
)
def test_frozen_graph_rejects_changed_storage(defect):
    model = frozen_model(seed=13, targets=("q_proj",))
    module = model.model.layers[0].self_attn.q_proj
    if defect == "weight_dtype":
        module.weight_q = module.weight_q.float()
    elif defect == "weight_shape":
        module.weight_q = torch.zeros((module.out_features + 1, module.in_features), dtype=torch.int8)
    elif defect == "scale_shape":
        module.weight_scale = module.weight_scale[:1]
    elif defect == "weight_attribute":
        module.weight = torch.nn.Parameter(torch.zeros((module.out_features, module.in_features), dtype=torch.float16))
    elif defect == "digest_type":
        module.artifact_sha256 = None
    elif defect == "digest_chars":
        module.artifact_sha256 = "z" * 64
    elif defect == "adapter_set":
        module.lora_A["other"] = torch.nn.Linear(module.in_features, 1, bias=False)
    elif defect == "adapter_dtype":
        module.lora_A["default"].weight.data = module.lora_A["default"].weight.data.float()
    elif defect == "adapter_grad":
        module.lora_A["default"].weight.requires_grad_(False)
    else:
        module.bias = module.bias.float()
    with pytest.raises(ReferenceArithmeticError):
        describe_graph(model, 64, frozen_int8=True)


def test_zero_adapter_delta_preserves_signed_zero_base_bits():
    base = torch.tensor([-0.0, 0.0, -1.0, 2.0], dtype=torch.float32)
    delta = torch.zeros(4, dtype=torch.float32)
    combined = frozen_int8.combine_adapter(base, delta)
    assert torch.equal(bits(combined), bits(base))
    delta = torch.tensor([-0.0, 0.0, 0.5, -0.0], dtype=torch.float32)
    combined = frozen_int8.combine_adapter(base, delta)
    assert torch.equal(bits(combined)[[0, 1, 3]], bits(base)[[0, 1, 3]])
    assert torch.equal(bits(combined)[2], bits(torch.tensor([-0.5], dtype=torch.float32))[0])
    with pytest.raises(ReferenceArithmeticError, match="adapter delta"):
        frozen_int8.combine_adapter(torch.zeros(1), torch.zeros(2))


def test_nonzero_adapter_delta_uses_the_strict_flushed_add_and_rejects_nonfinite():
    # An ordinary FP32 add would keep the subnormal delta; the strict adapter contract flushes it to signed zero.
    base = torch.zeros(3, dtype=torch.float32)
    delta = torch.tensor([2.0**-149, -(2.0**-149), 1.0], dtype=torch.float32)
    combined = frozen_int8.combine_adapter(base, delta)
    assert bits(combined).tolist() == [0, 0, 0x3F800000]
    assert bits(torch.add(base, delta)).tolist() != bits(combined).tolist()
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        frozen_int8.combine_adapter(torch.zeros(1), torch.tensor([float("nan")]))
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        frozen_int8.combine_adapter(torch.tensor([float("inf")]), torch.zeros(1))


def test_es_moves_only_adapters_and_restore_is_exact():
    model = frozen_model(seed=17)
    backend = FrozenInt8DecoderReference(model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[3, 5, 7, 11, 13]])
    before, _ = backend.forward_tokens(ids)
    frozen_before = [
        (module.weight_q.clone(), module.weight_scale.clone(), None if module.bias is None else module.bias.clone())
        for _, module in frozen_modules(model)
    ]
    schema = trainable_schema(model)
    snapshot = take_snapshot(model, schema)
    perturb_model_(model, schema, 19, 1e-1, 64)
    for (weight_q, weight_scale, bias), (_, module) in zip(frozen_before, frozen_modules(model), strict=True):
        assert torch.equal(module.weight_q, weight_q)
        assert torch.equal(module.weight_scale, weight_scale)
        assert (module.bias is None) is (bias is None)
        if bias is not None:
            assert torch.equal(module.bias, bias)
    changed, _ = backend.forward_tokens(ids)
    assert not torch.equal(bits(changed), bits(before))
    restore_from_snapshot_(model, schema, snapshot)
    restored, _ = backend.forward_tokens(ids)
    assert torch.equal(bits(restored), bits(before))


def test_identity_is_separate_and_not_hardware_qualified():
    model = frozen_model(seed=23, targets=("q_proj",))
    backend = FrozenInt8DecoderReference(model, max_context=64, allow_fixture=True)
    identity = backend.identity
    assert identity["backend"] == REFERENCE_BACKEND
    assert identity["adapterStorage"] == "frozen_int8_fp16_lora_storage_v1_experimental"
    assert identity["adapterArithmetic"].startswith("pairwise_f32_fp16_factors")
    assert identity["operators"]["linear"]["format"] == frozen_int8.ARTIFACT_FORMAT
    assert identity["hardwareQualified"] is False
    assert backend.fingerprint
