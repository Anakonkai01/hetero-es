"""Vendor-FP16 fast-path decode: explicit identity, merged groups and captured determinism."""

import os

import pytest
import torch
import torch.nn.functional as F

from heteroes.eval.fp16_decoder import FP16_GRAPH_BACKEND, Fp16DecoderGraph
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.eval.strict_decoder_graph import StrictDecoderGraph
from test_strict_decoder import model_for

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(),
    reason="explicit GPU opt-in",
)


def eager_logits(model, ids):
    """One FP16 composition with per-module GEMMs, independent of the merged fast path."""
    config = model.config
    dim = getattr(config, "head_dim", None) or config.hidden_size // config.num_attention_heads
    hidden = model.model.embed_tokens.weight[ids].float()
    positions = torch.arange(ids.shape[1], device=ids.device, dtype=torch.float32)
    angles = positions[:, None] * (10000.0 ** (-torch.arange(0, dim, 2, device=ids.device) / dim))
    sine, cosine = torch.sin(angles), torch.cos(angles)
    sine, cosine = (torch.cat((part, part), dim=-1) for part in (sine, cosine))
    for layer in model.model.layers:
        attention = layer.self_attn
        normalized = torch.nn.functional.rms_norm(
            hidden, (config.hidden_size,), layer.input_layernorm.weight.float(), config.rms_norm_eps
        )
        q, k, v = (
            F.linear(normalized.half(), module.weight, module.bias).float()
            for module in (attention.q_proj, attention.k_proj, attention.v_proj)
        )
        q = q.reshape(1, -1, config.num_attention_heads, dim).transpose(1, 2)
        k = k.reshape(1, -1, config.num_key_value_heads, dim).transpose(1, 2)
        v = v.reshape(1, -1, config.num_key_value_heads, dim).transpose(1, 2)
        query = q * cosine[None, None, :, :] + torch.cat((-q[..., dim // 2 :], q[..., : dim // 2]), -1) * sine[None, None, :, :]
        key = k * cosine[None, None, :, :] + torch.cat((-k[..., dim // 2 :], k[..., : dim // 2]), -1) * sine[None, None, :, :]
        repeat = config.num_attention_heads // config.num_key_value_heads
        key = key.repeat_interleave(repeat, dim=1)
        value = v.repeat_interleave(repeat, dim=1)
        scores = (query @ key.transpose(-1, -2)) / (dim**0.5)
        mask = torch.arange(ids.shape[1], device=ids.device)[None, :] <= torch.arange(ids.shape[1], device=ids.device)[:, None]
        probabilities = torch.softmax(scores.masked_fill(~mask, float("-inf")), dim=-1)
        mixed = (probabilities @ value).transpose(1, 2).reshape(1, -1, config.hidden_size)
        hidden = hidden + F.linear(mixed.half(), attention.o_proj.weight, attention.o_proj.bias).float()
        normalized = torch.nn.functional.rms_norm(
            hidden, (config.hidden_size,), layer.post_attention_layernorm.weight.float(), config.rms_norm_eps
        )
        gate = F.linear(normalized.half(), layer.mlp.gate_proj.weight).float()
        up = F.linear(normalized.half(), layer.mlp.up_proj.weight).float()
        hidden = hidden + F.linear((gate * torch.sigmoid(gate) * up).half(), layer.mlp.down_proj.weight).float()
    final = torch.nn.functional.rms_norm(hidden, (config.hidden_size,), model.model.norm.weight.float(), config.rms_norm_eps)
    return F.linear(final.half(), model.lm_head.weight).float()


@gpu
def test_merged_fast_path_is_close_to_per_module_fp16_composition():
    model = model_for("qwen2").cuda()
    graph = Fp16DecoderGraph(model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[3, 5, 7, 11]], device="cuda")
    actual, _ = graph.forward_tokens(ids)
    expected = eager_logits(model, ids)[:, -1]
    torch.testing.assert_close(actual, expected, rtol=2e-3, atol=2e-3)


@gpu
def test_fast_path_identity_is_explicitly_not_the_exact_integer_identity():
    model = model_for("qwen2").cuda()
    fast = Fp16DecoderGraph(model, max_context=64, allow_fixture=True)
    strict = StrictDecoderGraph(model, max_context=64, allow_fixture=True)
    assert fast.identity["backend"] == FP16_GRAPH_BACKEND
    assert fast.identity["projectionImplementation"]["exactIntegerIdentity"] is False
    assert fast.identity["projectionImplementation"]["operator"] == "vendor_fp16_linear_v1_experimental"
    assert fast.identity["hardwareQualified"] is False
    assert len(fast.identity["mergedGroups"]) == 2 * len(model.model.layers)
    assert fast.fingerprint != strict.fingerprint
    heads, dim = model.config.num_attention_heads, fast.head_dim
    layer = model.model.layers[0]
    merged = fast._merged_group((layer.self_attn.q_proj, layer.self_attn.k_proj, layer.self_attn.v_proj))
    assert merged[2] == (heads * dim, model.config.num_key_value_heads * dim, model.config.num_key_value_heads * dim)
    merged = fast._merged_group((layer.mlp.gate_proj, layer.mlp.up_proj))
    assert merged[2] == (model.config.intermediate_size, model.config.intermediate_size)


@gpu
def test_captured_fast_path_is_deterministic_and_matches_the_uncaptured_path():
    model = model_for("qwen2").cuda()
    graph = Fp16DecoderGraph(model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[3, 5, 7, 11, 13]], device="cuda")
    first, _ = graph.forward_tokens(ids)
    captured = graph.generate(ids, max_new_tokens=3, use_cache=True)
    repeated = graph.generate(ids, max_new_tokens=3, use_cache=True)
    uncaptured = graph.generate(ids, max_new_tokens=3, use_cache=False)
    assert torch.equal(captured, repeated)
    assert torch.equal(captured, uncaptured)
    second, _ = graph.forward_tokens(ids)
    assert torch.equal(first, second)


@gpu
def test_fast_path_requires_an_fp16_model():
    model = model_for("qwen2").float().cuda()
    with pytest.raises(ReferenceArithmeticError, match="FP16"):
        Fp16DecoderGraph(model, max_context=64, allow_fixture=True)
