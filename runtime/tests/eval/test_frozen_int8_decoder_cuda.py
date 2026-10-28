"""GPU frozen-int8 decoder must match the CPU oracle, keep tied storage and survive captured decode."""

import os

import pytest
import torch

from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.strict.frozen_int8_decoder import (
    GRAPH_BACKEND,
    FrozenInt8DecoderGraph,
    FrozenInt8DecoderReference,
)
from heteroes.strict.reference_ops import ReferenceArithmeticError
from heteroes.model.frozen_int8 import freeze_projections, freeze_tied_head, frozen_modules
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


def frozen_model_with_head(seed):
    model = frozen_model(seed)
    freeze_tied_head(model)
    return model


@gpu
def test_pinned_tied_head_matches_the_cpu_oracle_in_captured_decode():
    reference = FrozenInt8DecoderReference(frozen_model_with_head(71), max_context=64, allow_fixture=True)
    graph = FrozenInt8DecoderGraph(frozen_model_with_head(71).cuda(), max_context=64, allow_fixture=True)
    model = graph.model
    assert model.lm_head.weight is model.model.embed_tokens.weight
    assert model.lm_head.weight.dtype == torch.float16
    assert graph.identity["graph"]["frozenTiedHead"]["lm_head"]["artifactSha256"] == (model.lm_head.frozen_head_sha256)
    ids = torch.tensor([[3, 5, 7, 11, 13]])
    expected, _ = reference.forward_tokens(ids)
    actual, _ = graph.forward_tokens(ids.cuda())
    assert torch.equal(bits(actual.cpu()), bits(expected))
    captured = graph.generate(ids.cuda(), max_new_tokens=4, use_cache=True)
    assert torch.equal(captured.cpu(), reference.generate(ids, max_new_tokens=4, use_cache=True))


@gpu
def test_replacing_a_head_sidecar_buffer_forces_a_fresh_capture_session():
    model = frozen_model(73).cuda()
    freeze_tied_head(model)
    graph = FrozenInt8DecoderGraph(model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[3, 5, 7, 11]])
    graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    previous = graph._session
    original = graph.model.lm_head.frozen_weight_q
    graph.model.lm_head.frozen_weight_q = original.clone()
    graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    assert graph._session is not None and graph._session is not previous
    graph.model.lm_head.frozen_weight_q = original


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
def test_nonzero_signed_adapters_match_the_cpu_strict_oracle_in_capture():
    reference, graph = backends(79)
    shape = reference.model.model.layers[0].self_attn.q_proj.lora_B["default"].weight.shape
    replacement = torch.randn(shape, generator=torch.Generator().manual_seed(83), dtype=torch.float16) * 0.2
    replacement[0, 0], replacement[0, 1] = 1.0, -1.0
    for model in (reference.model, graph.model):
        with torch.no_grad():
            model.model.layers[0].self_attn.q_proj.lora_B["default"].weight.copy_(replacement)
    ids = torch.tensor([[1, 4, 9, 16, 25, 36]])
    expected, _ = reference.forward_tokens(ids)
    actual, _ = graph.forward_tokens(ids.cuda())
    assert torch.equal(bits(actual.cpu()), bits(expected))
    expected_tokens = reference.generate(ids, max_new_tokens=3, use_cache=True)
    actual_tokens = graph.generate(ids.cuda(), max_new_tokens=3, use_cache=True)
    assert torch.equal(actual_tokens.cpu(), expected_tokens)


@gpu
def test_in_place_frozen_storage_mutation_is_refused_at_the_request_boundary():
    _, graph = backends(83)
    ids = torch.tensor([[3, 5, 7, 11]])
    graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    module = graph.model.model.layers[0].self_attn.q_proj
    original = module.weight_q[0, 0].clone()
    with torch.no_grad():
        module.weight_q[0, 0] = 1 if int(original) != 1 else 2
    with pytest.raises(ReferenceArithmeticError, match="digest|changed"):
        graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    with torch.no_grad():
        module.weight_q[0, 0] = original
    tokens = graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    assert tokens.shape[0] == 1


@gpu
def test_metadata_mutation_is_refused_at_the_request_boundary():
    _, graph = backends(87)
    ids = torch.tensor([[3, 5, 7, 11]])
    graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    graph.model.model.layers[0].self_attn.q_proj.artifact_metadata["forged"] = True
    with pytest.raises(ReferenceArithmeticError, match="digest|metadata"):
        graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)


@gpu
def test_replacing_a_frozen_buffer_with_a_different_payload_is_refused():
    _, graph = backends(89)
    ids = torch.tensor([[3, 5, 7, 11]])
    graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    module = graph.model.model.layers[0].self_attn.q_proj
    original = module.weight_q
    replacement = original.clone()
    replacement[0, 0] = 1 if int(original[0, 0]) != 1 else 2
    module.weight_q = replacement
    with pytest.raises(ReferenceArithmeticError, match="digest|changed"):
        graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True)
    graph.release_graph()
    module.weight_q = original
    assert graph.generate(ids.cuda(), max_new_tokens=2, use_cache=True).shape[0] == 1


@gpu
def test_canonical_plus_minus_adapters_match_cpu_bits_and_restore_exactly():
    reference, graph = backends(91)
    ids = torch.tensor([[1, 4, 9, 16, 25, 36]])
    reference_schema = trainable_schema(reference.model)
    graph_schema = trainable_schema(graph.model)
    reference_snapshot = take_snapshot(reference.model, reference_schema)
    graph_snapshot = take_snapshot(graph.model, graph_schema)
    baseline, _ = reference.forward_tokens(ids)
    baseline_tokens = reference.generate(ids, max_new_tokens=3, use_cache=True)
    assert torch.equal(graph.generate(ids.cuda(), max_new_tokens=3, use_cache=True).cpu(), baseline_tokens)
    for sign in (1, -1):
        perturb_model_(reference.model, reference_schema, 93, sign * 5e-2, 64)
        perturb_model_(graph.model, graph_schema, 93, sign * 5e-2, 64)
        expected, _ = reference.forward_tokens(ids)
        actual, _ = graph.forward_tokens(ids.cuda())
        assert torch.equal(bits(actual.cpu()), bits(expected))
        expected_tokens = reference.generate(ids, max_new_tokens=3, use_cache=True)
        actual_tokens = graph.generate(ids.cuda(), max_new_tokens=3, use_cache=True)
        assert torch.equal(actual_tokens.cpu(), expected_tokens)
        assert not torch.equal(bits(expected), bits(baseline))
        restore_from_snapshot_(reference.model, reference_schema, reference_snapshot)
        restore_from_snapshot_(graph.model, graph_schema, graph_snapshot)
        restored, _ = reference.forward_tokens(ids)
        assert torch.equal(bits(restored), bits(baseline))


@gpu
def test_cuda_adapter_combine_is_capture_safe_with_signed_zero_base():
    from heteroes.strict import strict_cuda

    kernels = strict_cuda.StrictCudaKernels("cuda")
    base = torch.tensor([-0.0, 0.0, -1.0], device="cuda", dtype=torch.float32)
    delta = torch.zeros(3, device="cuda", dtype=torch.float32)
    flag = kernels.new_error_flag()
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        added = kernels.add(base, delta, error_flag=flag)
        combined = torch.where(delta == 0, base, added)
    graph.replay()
    kernels.raise_if_error(flag)
    assert torch.equal(bits(combined.cpu()), bits(base.cpu()))
