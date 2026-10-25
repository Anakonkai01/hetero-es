"""GPU frozen-int8 decoder must match the CPU oracle, keep tied storage and survive captured decode."""

import os

import pytest
import torch

from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.eval import frozen_int8
from heteroes.eval.frozen_int8_decoder import (
    GRAPH_BACKEND,
    FrozenInt8DecoderGraph,
    FrozenInt8DecoderReference,
)
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.model.frozen_int8 import freeze_projections, frozen_modules
from heteroes.model.lora import trainable_schema
from test_strict_decoder import bits, model_for

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(),
    reason="explicit GPU opt-in",
)

TARGETS = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")


def frozen_model(seed, targets=TARGETS):
    model = model_for("qwen2")
    freeze_projections(model, rank=2, alpha=4, seed=seed, target_modules=targets)
    return model


def backends(seed, **kwargs):
    reference = FrozenInt8DecoderReference(frozen_model(seed), max_context=64, allow_fixture=True)
    graph = FrozenInt8DecoderGraph(frozen_model(seed).cuda(), max_context=64, allow_fixture=True, **kwargs)
    return reference, graph


@gpu
def test_serial_packed_and_incremental_logits_match_the_cpu_oracle_bits():
    reference, graph = backends(31)
    ids = torch.tensor([[3, 5, 7, 11, 13]])
    expected, _ = reference.forward_tokens(ids)
    actual, cache = graph.forward_tokens(ids.cuda())
    assert torch.equal(bits(actual.cpu()), bits(expected))
    packed, packed_cache = graph.forward_batch([ids.cuda()])
    assert torch.equal(bits(packed.cpu()), bits(expected))
    assert len(cache) == 2
    assert len(packed_cache) == 1 and len(packed_cache[0]) == 2

    _, prefix = reference.forward_tokens(ids[:, :2])
    incremental, _ = reference.forward_tokens(ids[:, 2:], prefix)
    _, gpu_prefix = graph.forward_tokens(ids[:, :2].cuda())
    gpu_incremental, _ = graph.forward_tokens(ids[:, 2:].cuda(), gpu_prefix)
    assert torch.equal(bits(gpu_incremental.cpu()), bits(incremental))


@gpu
def test_zero_adapter_captured_generate_matches_cpu_tokens_and_uncaptured_path():
    reference, graph = backends(37)
    ids = torch.tensor([[3, 5, 7, 11, 13, 17]])
    expected = reference.generate(ids, max_new_tokens=4, use_cache=True)
    captured = graph.generate(ids.cuda(), max_new_tokens=4, use_cache=True)
    assert torch.equal(captured.cpu(), expected)
    uncaptured = graph.generate(ids.cuda(), max_new_tokens=4, use_cache=False)
    assert torch.equal(uncaptured.cpu(), expected)


@gpu
def test_adapter_perturbation_changes_captured_tokens_and_restore_is_exact():
    _, graph = backends(41)
    ids = torch.tensor([[3, 5, 7, 11, 13]])
    before_logits, _ = graph.forward_tokens(ids.cuda())
    before_tokens = graph.generate(ids.cuda(), max_new_tokens=3, use_cache=True)
    base_before = [
        (module.weight_q.clone(), module.weight_scale.clone(), None if module.bias is None else module.bias.clone())
        for _, module in frozen_modules(graph.model)
    ]
    schema = trainable_schema(graph.model)
    snapshot = take_snapshot(graph.model, schema)
    perturb_model_(graph.model, schema, 43, 5e-2, 64)
    for (weight_q, weight_scale, bias), (_, module) in zip(base_before, frozen_modules(graph.model), strict=True):
        assert torch.equal(module.weight_q, weight_q)
        assert torch.equal(module.weight_scale, weight_scale)
        assert (module.bias is None) is (bias is None)
        if bias is not None:
            assert torch.equal(module.bias, bias)
    changed_logits, _ = graph.forward_tokens(ids.cuda())
    assert not torch.equal(bits(changed_logits.cpu()), bits(before_logits.cpu()))
    changed_tokens = graph.generate(ids.cuda(), max_new_tokens=3, use_cache=True)
    assert changed_tokens.shape == before_tokens.shape
    restore_from_snapshot_(graph.model, schema, snapshot)
    restored_logits, _ = graph.forward_tokens(ids.cuda())
    assert torch.equal(bits(restored_logits.cpu()), bits(before_logits.cpu()))
    restored_tokens = graph.generate(ids.cuda(), max_new_tokens=3, use_cache=True)
    assert torch.equal(restored_tokens, before_tokens)


@gpu
def test_partial_freeze_mixes_frozen_and_strict_fp16_projection_paths():
    targets = ("q_proj", "down_proj")
    reference = FrozenInt8DecoderReference(frozen_model(61, targets), max_context=64, allow_fixture=True)
    graph = FrozenInt8DecoderGraph(frozen_model(61, targets).cuda(), max_context=64, allow_fixture=True)
    ids = torch.tensor([[1, 4, 9, 16, 25, 36]])
    expected, _ = reference.forward_tokens(ids)
    actual, _ = graph.forward_tokens(ids.cuda())
    assert torch.equal(bits(actual.cpu()), bits(expected))
    packed, _ = graph.forward_batch([ids.cuda()])
    assert torch.equal(bits(packed.cpu()), bits(expected))


@gpu
def test_frozen_graph_keeps_tied_embedding_and_lm_head_in_fp16_storage():
    model = frozen_model(29).cuda()
    embed, head = model.model.embed_tokens.weight, model.lm_head.weight
    assert embed is head and embed.dtype == torch.float16
    graph = FrozenInt8DecoderGraph(model, max_context=64, allow_fixture=True)
    graph.forward_tokens(torch.tensor([[1, 2, 3]], device="cuda"))
    assert graph.identity["backend"] == GRAPH_BACKEND
    assert graph.identity["graph"]["tiedHead"] is True
    assert "lm_head" not in graph.identity["graph"]["frozenProjections"]
    assert graph.identity["frozenKernels"]["kernel"] == "frozen_int8_b22_mma_cuda_v1_experimental"
    assert graph.identity["hardwareQualified"] is False
    assert graph.kernel_identity()["frozen"]["builds"]


@gpu
def test_frozen_graph_identity_covers_live_artifacts_and_nonzero_adapter_roundtrip():
    reference, graph = backends(47)
    descriptors = graph.identity["graph"]["frozenProjections"]
    for name, module in frozen_modules(graph.model):
        assert descriptors[name]["artifactSha256"] == module.artifact_sha256
    with torch.no_grad():
        module = graph.model.model.layers[0].self_attn.q_proj
        weight = module.lora_B["default"].weight
        replacement = torch.randn(weight.shape, generator=torch.Generator().manual_seed(53), dtype=torch.float16)
        weight.copy_(replacement * 0.05)
    ids = torch.tensor([[1, 4, 9, 16, 25]])
    output, _ = graph.forward_tokens(ids.cuda())
    assert output.shape == (1, graph.config.vocab_size)
    assert torch.isfinite(output).all()
    zero = reference.forward_tokens(ids)[0]
    assert not torch.equal(bits(output.cpu()), bits(zero))


@gpu
def test_capture_refuses_a_moved_frozen_buffer_and_recovers_after_release():
    _, graph = backends(59, max_graph_bytes=2**30)
    ids = torch.tensor([[3, 5, 7, 11]])
    graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    module = graph.model.model.layers[0].self_attn.q_proj
    original = module.weight_q
    module.weight_q = original.cpu()
    with pytest.raises(ReferenceArithmeticError, match="storage"):
        graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    graph.release_graph()
    module.weight_q = original
    tokens = graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    assert tokens.shape[0] == 1


@gpu
def test_replacing_a_frozen_buffer_forces_a_fresh_capture_session():
    _, graph = backends(67, max_graph_bytes=2**30)
    ids = torch.tensor([[3, 5, 7, 11]])
    graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    previous = graph._session
    module = graph.model.model.layers[0].self_attn.q_proj
    original = module.weight_q
    module.weight_q = original.clone()
    graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    assert graph._session is not None and graph._session is not previous
    module.weight_q = original


@gpu
def test_adapter_combine_is_capture_safe_with_signed_zero_base():
    base = torch.tensor([-0.0, 0.0, -1.0], device="cuda", dtype=torch.float32)
    delta = torch.zeros(3, device="cuda", dtype=torch.float32)
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        combined = frozen_int8.combine_adapter(base, delta)
    graph.replay()
    assert torch.equal(bits(combined.cpu()), bits(base.cpu()))
