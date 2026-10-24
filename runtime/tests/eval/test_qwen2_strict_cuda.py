"""Graph checks for the experimental strict CUDA Qwen2 backend against the eager ADR-012 reference.

GPU tests need HETEROES_GPU_ACCEPTANCE=1 and a visible GPU. The tiny fixture covers graph wiring, caches,
batching and candidate changes; it is not full-model or hardware qualification.
"""

import copy
import hashlib
import os
from pathlib import Path

import pytest
import torch
from transformers import Qwen2Config, Qwen2ForCausalLM

from heteroes.eval.candidate import model_weights_sha256
from heteroes.eval import reference_ops as ops
from heteroes.eval import qwen2_strict_cuda, strict_decoder
from heteroes.eval.phase_trace import storage_inventory
from heteroes.eval.qwen2_reference import Qwen2Reference
from heteroes.eval.qwen2_strict_cuda import STRICT_CUDA_BACKEND, Qwen2StrictCuda
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.model.schema import build_parameter_schema

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(),
    reason="strict CUDA graph checks need HETEROES_GPU_ACCEPTANCE=1 and a visible GPU",
)


def bits(value):
    return value.contiguous().view(torch.int32)


def make_model(seed=2410, *, heads=4, kv_heads=2, hidden=16):
    torch.manual_seed(seed)
    config = Qwen2Config(
        vocab_size=41,
        hidden_size=hidden,
        intermediate_size=2 * hidden + 3,
        num_hidden_layers=2,
        num_attention_heads=heads,
        num_key_value_heads=kv_heads,
        max_position_embeddings=128,
        tie_word_embeddings=True,
        eos_token_id=40,
        pad_token_id=0,
    )
    config._attn_implementation = "eager"
    return Qwen2ForCausalLM(config).half().eval()


def test_backend_refuses_cpu_models_and_missing_acceptance_before_cuda(monkeypatch):
    model = make_model()

    def forbidden(*args, **kwargs):
        raise AssertionError("CUDA touched before the guard")

    monkeypatch.setattr(torch.cuda, "is_available", forbidden)
    monkeypatch.setattr(torch.cuda, "init", forbidden)
    monkeypatch.setenv("HETEROES_GPU_ACCEPTANCE", "1")
    with pytest.raises(ReferenceArithmeticError, match="CUDA"):
        Qwen2StrictCuda(model, max_context=64, allow_fixture=True)
    monkeypatch.delenv("HETEROES_GPU_ACCEPTANCE")
    with pytest.raises(ReferenceArithmeticError, match="HETEROES_GPU_ACCEPTANCE"):
        Qwen2StrictCuda(model, max_context=64, allow_fixture=True)


@pytest.fixture
def cuda_model():
    return make_model().cuda()


@gpu
@pytest.mark.parametrize("tokens", [[2], [2, 5, 7, 11, 13], list(range(1, 40))])
def test_strict_forward_matches_eager_reference_on_device_and_cpu(cuda_model, tokens):
    strict = Qwen2StrictCuda(cuda_model, max_context=64, allow_fixture=True)
    eager = Qwen2Reference(cuda_model, max_context=64, allow_fixture=True)
    ids = torch.tensor([tokens], device="cuda")
    logits, cache = strict.forward_tokens(ids)
    expected, expected_cache = eager.forward_tokens(ids)
    assert torch.equal(bits(logits), bits(expected))
    for (k, v), (ek, ev) in zip(cache, expected_cache):
        assert torch.equal(bits(k), bits(ek)) and torch.equal(bits(v), bits(ev))
    cpu = Qwen2Reference(copy.deepcopy(cuda_model).cpu(), max_context=64, allow_fixture=True)
    assert torch.equal(bits(logits.cpu()), bits(cpu.forward_tokens(ids.cpu())[0]))


@gpu
def test_strict_forward_covers_other_head_layouts(monkeypatch):
    for heads, kv_heads, hidden in ((2, 1, 16), (4, 4, 32), (6, 2, 24)):
        model = make_model(7, heads=heads, kv_heads=kv_heads, hidden=hidden).cuda()
        ids = torch.tensor([[3, 1, 4, 1, 5, 9, 2, 6]], device="cuda")
        strict = Qwen2StrictCuda(model, max_context=64, allow_fixture=True).forward_tokens(ids)[0]
        eager = Qwen2Reference(model, max_context=64, allow_fixture=True).forward_tokens(ids)[0]
        assert torch.equal(bits(strict), bits(eager))


@gpu
def test_strict_incremental_cache_equals_prefill_and_eager_cache_format(cuda_model):
    strict = Qwen2StrictCuda(cuda_model, max_context=64, allow_fixture=True)
    eager = Qwen2Reference(cuda_model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[2, 5, 7, 11, 13, 17]], device="cuda")
    direct, _ = strict.forward_tokens(ids)
    _, cache = strict.forward_tokens(ids[:, :4])
    incremental, _ = strict.forward_tokens(ids[:, 4:], cache)
    assert torch.equal(bits(direct), bits(incremental))
    _, eager_cache = eager.forward_tokens(ids[:, :4])
    assert torch.equal(bits(strict.forward_tokens(ids[:, 4:], eager_cache)[0]), bits(direct))


@gpu
def test_rope_tables_are_exact_bounded_buffers_reused_by_prefill_and_decode(cuda_model, monkeypatch):
    strict = Qwen2StrictCuda(cuda_model, max_context=64, allow_fixture=True)
    positions = torch.arange(64, device="cuda", dtype=torch.float32)
    sine, cosine = ops.sin_cos(ops.mul(positions[:, None], strict._inverse_frequency[None, :]))
    for actual, expected in ((strict._rope_sine, sine), (strict._rope_cosine, cosine)):
        assert torch.equal(bits(actual), bits(torch.cat((expected, expected), dim=-1)))
        assert actual.dtype == torch.float32 and actual.is_contiguous()
        assert any(buffer is actual for buffer in strict.buffers())
    size = sum(t.numel() * t.element_size() for t in (strict._rope_sine, strict._rope_cosine))
    assert size == 2 * strict.max_context * strict.head_dim * 4
    ids = torch.tensor([[2, 5, 7, 11, 13]], device="cuda")
    eager = Qwen2Reference(cuda_model, max_context=64, allow_fixture=True)
    expected = eager.forward_tokens(ids)[0]

    def forbidden(*args, **kwargs):
        raise AssertionError("RoPE tables must not be recomputed during forward")

    monkeypatch.setattr(ops, "sin_cos", forbidden)
    _, cache = strict.forward_tokens(ids[:, :3])
    assert torch.equal(bits(strict.forward_tokens(ids[:, 3:], cache)[0]), bits(expected))


@gpu
def test_strict_generation_matches_eager_with_padding_batches_eos_and_penalty(cuda_model):
    strict = Qwen2StrictCuda(cuda_model, max_context=64, allow_fixture=True)
    eager = Qwen2Reference(cuda_model, max_context=64, allow_fixture=True)
    batch = torch.tensor([[0, 0, 2, 5], [7, 11, 13, 17], [0, 3, 3, 3]], device="cuda")
    mask = batch != 0
    for options in ({}, {"repetition_penalty": 1.3}, {"use_cache": False}, {"eos_token_id": 9, "pad_token_id": 1}):
        expected = eager.generate(batch, attention_mask=mask, max_new_tokens=6, do_sample=False, **options)
        actual = strict.generate(batch, attention_mask=mask, max_new_tokens=6, do_sample=False, **options)
        assert torch.equal(actual, expected)


@gpu
def test_strict_backend_observes_candidate_changes_and_exact_restore(cuda_model):
    strict = Qwen2StrictCuda(cuda_model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[2, 5, 7]], device="cuda")
    parent, _ = strict.forward_tokens(ids)
    snapshot = cuda_model.model.layers[1].mlp.down_proj.weight.detach().clone()
    with torch.no_grad():
        cuda_model.model.layers[1].mlp.down_proj.weight.mul_(-1)
    changed, _ = strict.forward_tokens(ids)
    assert not torch.equal(bits(changed), bits(parent))
    assert torch.equal(
        bits(changed), bits(Qwen2Reference(cuda_model, max_context=64, allow_fixture=True).forward_tokens(ids)[0])
    )
    with torch.no_grad():
        cuda_model.model.layers[1].mlp.down_proj.weight.copy_(snapshot)
    assert torch.equal(bits(strict.forward_tokens(ids)[0]), bits(parent))


@gpu
def test_strict_backend_uses_live_fp16_weights_without_shadow_or_hf_forward(cuda_model, monkeypatch):
    schema = build_parameter_schema(cuda_model)
    before = model_weights_sha256(cuda_model, schema)
    inventory = storage_inventory({"inference": cuda_model})

    def forbidden(*args, **kwargs):
        raise AssertionError("No deepcopy, model.float or HF forward")

    monkeypatch.setattr(copy, "deepcopy", forbidden)
    monkeypatch.setattr(torch.nn.Module, "float", forbidden)
    monkeypatch.setattr(cuda_model, "forward", forbidden)
    strict = Qwen2StrictCuda(cuda_model, max_context=64, allow_fixture=True)
    assert strict.generate(torch.tensor([[2, 5]], device="cuda"), max_new_tokens=3).shape == (1, 5)
    assert storage_inventory({"inference": cuda_model}) == inventory
    assert model_weights_sha256(cuda_model, schema) == before


@gpu
def test_strict_backend_fails_nonfinite_candidates(cuda_model):
    strict = Qwen2StrictCuda(cuda_model, max_context=64, allow_fixture=True)
    with torch.no_grad():
        cuda_model.model.layers[0].self_attn.q_proj.weight[0, 0] = float("inf")
    with pytest.raises(ReferenceArithmeticError):
        strict.forward_tokens(torch.tensor([[2, 5]], device="cuda"))
    with pytest.raises(ReferenceArithmeticError):
        strict.generate(torch.tensor([[2, 5]], device="cuda"), max_new_tokens=2)


@gpu
def test_strict_identity_is_distinct_and_names_kernel_builds(cuda_model):
    strict = Qwen2StrictCuda(cuda_model, max_context=64, allow_fixture=True)
    eager = Qwen2Reference(cuda_model, max_context=64, allow_fixture=True)
    strict.forward_tokens(torch.tensor([[2, 5]], device="cuda"))
    assert strict.identity["backend"] == STRICT_CUDA_BACKEND != eager.identity["backend"]
    assert strict.identity["hardwareQualified"] is False
    assert strict.fingerprint != eager.fingerprint
    builds = strict.kernel_identity()["builds"]
    assert {"ops", "linear-16-bias-rows4", "linear-16-nobias", "linear-35-nobias-rows4"} <= set(builds)
    assert (
        strict.identity["graphSourceSha256"] == hashlib.sha256(Path(strict_decoder.__file__).read_bytes()).hexdigest()
    )
    assert (
        strict.identity["wrapperSourceSha256"]
        == hashlib.sha256(Path(qwen2_strict_cuda.__file__).read_bytes()).hexdigest()
    )
    assert all(build["ptxAudit"]["violations"] == [] for build in builds.values())
    with pytest.raises(ReferenceArithmeticError):
        Qwen2StrictCuda(cuda_model, max_context=8192, allow_fixture=True)
