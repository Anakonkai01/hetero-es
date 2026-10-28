"""Architectural coverage is determined by graph operations, independently of model size and GPU tuning."""

import copy
import os

import pytest
import torch
from transformers import LlamaConfig, LlamaForCausalLM, MistralConfig, MistralForCausalLM, Qwen2Config, Qwen2ForCausalLM

from heteroes.strict.reference_ops import ReferenceArithmeticError


def classes():
    from heteroes.strict.strict_decoder import StrictDecoderCuda, StrictDecoderReference
    from heteroes.strict.strict_decoder_packed import StrictDecoderPacked

    return StrictDecoderReference, StrictDecoderCuda, StrictDecoderPacked


def model_for(family):
    torch.manual_seed(47)
    config_class, model_class, hidden, intermediate, heads, kv, tied = {
        "qwen2": (Qwen2Config, Qwen2ForCausalLM, 24, 47, 6, 2, True),
        "llama": (LlamaConfig, LlamaForCausalLM, 32, 67, 4, 1, False),
        "llama-wide": (LlamaConfig, LlamaForCausalLM, 32, 67, 4, 1, False),
        "mistral": (MistralConfig, MistralForCausalLM, 48, 91, 6, 3, False),
    }[family]
    config = config_class(
        hidden_size=hidden,
        intermediate_size=intermediate,
        num_attention_heads=heads,
        num_key_value_heads=kv,
        num_hidden_layers=2,
        vocab_size=43,
        max_position_embeddings=128,
        tie_word_embeddings=tied,
        eos_token_id=42,
        pad_token_id=0,
        sliding_window=None,
        attention_bias=True,
        mlp_bias=True,
        **({"head_dim": 12} if family == "llama-wide" else {}),
    )
    config._attn_implementation = "eager"
    return model_class(config).half().eval()


def bits(value):
    return value.contiguous().view(torch.int32)


@pytest.mark.parametrize("family", ["qwen2", "llama", "llama-wide", "mistral"])
def test_generic_reference_matches_independent_hf_graph_and_incremental_cache(family):
    model = model_for(family)
    reference, _, _ = classes()
    backend = reference(model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[3, 5, 7, 11, 13]])
    actual, cache = backend.forward_tokens(ids)
    oracle = copy.deepcopy(model).float()
    with torch.inference_mode():
        expected = oracle(ids).logits[:, -1]
    torch.testing.assert_close(actual, expected, rtol=5e-4, atol=5e-5)
    _, prefix = backend.forward_tokens(ids[:, :3])
    assert torch.equal(bits(backend.forward_tokens(ids[:, 3:], prefix)[0]), bits(actual))
    assert len(cache) == 2
    assert backend.identity["graph"]["family"] == family.split("-")[0]
    assert backend.identity["graph"]["tiedHead"] == (family == "qwen2")
    assert backend.identity["hardwareQualified"] is False


@pytest.mark.parametrize("defect", ["family", "rope", "sliding", "extra_weight", "head", "activation", "epsilon"])
def test_unsupported_graphs_fail_before_arithmetic(defect, monkeypatch):
    model = model_for("llama")
    if defect == "family":
        model.config.model_type = "gemma"
    elif defect == "rope":
        model.config.rope_parameters["rope_type"] = "yarn"
    elif defect == "sliding":
        model.config.sliding_window = 16
    elif defect == "extra_weight":
        model.register_parameter("unhandled_scale", torch.nn.Parameter(torch.ones(1, dtype=torch.float16)))
    elif defect == "head":
        model.config.head_dim = 6
    elif defect == "activation":
        model.config.hidden_act = "gelu"
    else:
        model.model.layers[0].input_layernorm.variance_epsilon = 0.5
    reference, _, _ = classes()
    monkeypatch.setattr(
        torch, "arange", lambda *a, **kw: pytest.fail("graph must be refused before constants/arithmetic")
    )
    with pytest.raises(ReferenceArithmeticError, match="[Uu]nsupported|[Gg]raph"):
        reference(model, max_context=64)


@pytest.mark.parametrize("family", ["qwen2", "llama", "mistral"])
def test_generic_cuda_guard_still_refuses_cpu_and_missing_opt_in(family, monkeypatch):
    _, cuda, packed = classes()
    model = model_for(family)
    for backend in (cuda, packed):
        monkeypatch.setenv("HETEROES_GPU_ACCEPTANCE", "1")
        with pytest.raises(ReferenceArithmeticError, match="CUDA"):
            backend(model)
        monkeypatch.delenv("HETEROES_GPU_ACCEPTANCE")
        with pytest.raises(ReferenceArithmeticError, match="HETEROES_GPU_ACCEPTANCE"):
            backend(model)


gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(),
    reason="opt-in GPU matrix",
)


@gpu
@pytest.mark.parametrize("family", ["qwen2", "llama", "llama-wide", "mistral"])
def test_three_families_share_cuda_operators_and_packed_execution(family, monkeypatch):
    reference, cuda, packed = classes()
    model = model_for(family).cuda()
    eager = reference(copy.deepcopy(model).cpu(), max_context=64, allow_fixture=True)
    serial = cuda(model, max_context=64, allow_fixture=True)
    batch = packed(model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[0, 0, 3, 5], [7, 11, 13, 17], [0, 19, 23, 29]], device="cuda")
    mask = ids != 0

    def forbidden(*args, **kwargs):
        raise AssertionError("strict execution must not copy weights, widen a model or call HF forward")

    monkeypatch.setattr(copy, "deepcopy", forbidden)
    monkeypatch.setattr(torch.nn.Module, "float", forbidden)
    monkeypatch.setattr(model, "forward", forbidden)
    for backend in (serial, batch):
        actual = backend.generate(ids, attention_mask=mask, max_new_tokens=4, repetition_penalty=1.2)
        expected = eager.generate(ids.cpu(), attention_mask=mask.cpu(), max_new_tokens=4, repetition_penalty=1.2)
        assert torch.equal(actual.cpu(), expected)
    rows = [ids[0:1, 2:], ids[1:2], ids[2:3, 1:]]
    actual, _ = batch.forward_batch(rows)
    expected = torch.cat([eager.forward_tokens(row.cpu())[0] for row in rows])
    assert torch.equal(bits(actual.cpu()), bits(expected))
