"""CPU graph/oracle tests for a candidate strict backend, not hardware qualification."""

import copy
from decimal import localcontext

import pytest
import torch
from transformers import Qwen2Config, Qwen2ForCausalLM

from heteroes.eval.candidate import model_weights_sha256
from heteroes.eval.phase_trace import storage_inventory
from heteroes.strict.qwen2_reference import Qwen2Reference
from heteroes.strict.reference_ops import ReferenceArithmeticError
from heteroes.model.schema import build_parameter_schema


@pytest.fixture
def model():
    torch.manual_seed(2410)
    config = Qwen2Config(
        vocab_size=41,
        hidden_size=16,
        intermediate_size=32,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        max_position_embeddings=128,
        tie_word_embeddings=True,
        eos_token_id=40,
        pad_token_id=0,
    )
    config._attn_implementation = "eager"
    return Qwen2ForCausalLM(config).half().eval()


def test_reference_implements_the_qwen_graph_close_to_a_cpu_fp32_oracle(model):
    # An independent CPU-only test oracle; it is never a second GPU model in the runtime.
    oracle = copy.deepcopy(model).float().eval()
    reference = Qwen2Reference(model, max_context=64, allow_fixture=True)
    tokens = torch.tensor([[2, 5, 7, 11, 13]])
    with torch.inference_mode():
        expected = oracle(input_ids=tokens).logits[:, -1]

    actual, cache = reference.forward_tokens(tokens)

    assert torch.allclose(actual, expected, rtol=5e-4, atol=3e-5)
    assert len(cache) == 2 and cache[0][0].shape == (1, 2, 5, 4)
    assert cache[0][0].dtype == torch.float32


def test_prefill_and_incremental_cache_give_identical_bits(model):
    reference = Qwen2Reference(model, max_context=64, allow_fixture=True)
    tokens = torch.tensor([[2, 5, 7, 11, 13]])
    direct, _ = reference.forward_tokens(tokens)
    _, cache = reference.forward_tokens(tokens[:, :3])
    incremental, _ = reference.forward_tokens(tokens[:, 3:], cache)
    assert torch.equal(direct.view(torch.int32), incremental.view(torch.int32))


def test_generation_is_invariant_to_left_padding_batch_composition_and_cache_choice(model):
    reference = Qwen2Reference(model, max_context=64, allow_fixture=True)
    short = torch.tensor([[2, 5]])
    batch = torch.tensor([[0, 0, 2, 5], [7, 11, 13, 17]])
    allowed = batch != 0
    alone = reference.generate(short, max_new_tokens=3, do_sample=False)
    together = reference.generate(batch, attention_mask=allowed, max_new_tokens=3, do_sample=False)
    no_cache = reference.generate(batch, attention_mask=allowed, max_new_tokens=3, do_sample=False, use_cache=False)
    assert torch.equal(alone[0, 2:], together[0, 4:])
    assert torch.equal(together, no_cache)


def test_generation_uses_the_live_fp16_weights_without_a_shadow_or_hf_forward(model, monkeypatch):
    schema = build_parameter_schema(model)
    before = model_weights_sha256(model, schema)
    original_storage = storage_inventory({"inference": model})

    def forbidden(*args, **kwargs):
        raise AssertionError("No model deepcopy, model.float or HF forward in the one-model reference")

    monkeypatch.setattr(copy, "deepcopy", forbidden)
    monkeypatch.setattr(torch.nn.Module, "float", forbidden)
    monkeypatch.setattr(model, "forward", forbidden)
    reference = Qwen2Reference(model, max_context=64, allow_fixture=True)
    tokens = reference.generate(torch.tensor([[2, 5]]), max_new_tokens=2, do_sample=False)
    assert tokens.shape == (1, 4)
    assert reference.model is model
    assert all(parameter.dtype == torch.float16 for parameter in reference.parameters())
    assert storage_inventory({"inference": model}) == original_storage
    assert model_weights_sha256(model, schema) == before


def test_eos_rows_are_padded_without_changing_other_rows(model):
    reference = Qwen2Reference(model, max_context=64, allow_fixture=True)
    first = reference.generate(torch.tensor([[2, 5]]), max_new_tokens=1, do_sample=False)[0, -1].item()
    batch = torch.tensor([[2, 5], [7, 11]])
    actual = reference.generate(batch, max_new_tokens=3, do_sample=False, eos_token_id=first, pad_token_id=0)
    assert actual[0, 2].item() == first
    assert torch.equal(actual[0, 3:], torch.zeros_like(actual[0, 3:]))
    separate = reference.generate(batch[1:2], max_new_tokens=3, do_sample=False, eos_token_id=first, pad_token_id=0)
    assert torch.equal(actual[1, 2 : separate.shape[1]], separate[0, 2:])


def test_unsupported_options_fail_before_model_computation(model, monkeypatch):
    reference = Qwen2Reference(model, max_context=64, allow_fixture=True)

    def forbidden(*args, **kwargs):
        raise AssertionError("Unsupported options must fail before any forward")

    monkeypatch.setattr(reference, "forward_tokens", forbidden)
    for options in ({"do_sample": True}, {"num_beams": 2}, {"temperature": 0.7}, {"max_new_tokens": 65}):
        with pytest.raises(ReferenceArithmeticError):
            reference.generate(torch.tensor([[2, 5]]), **options)


def test_model_dtype_and_initial_scope_are_explicit(model):
    with pytest.raises(ReferenceArithmeticError, match="scope"):
        Qwen2Reference(model, max_context=64)
    model.float()
    with pytest.raises(ReferenceArithmeticError, match="FP16"):
        Qwen2Reference(model, max_context=64, allow_fixture=True)


def test_reference_identity_does_not_depend_on_ambient_decimal_context(model):
    first = Qwen2Reference(model, max_context=64, allow_fixture=True)
    with localcontext() as context:
        context.prec = 3
        second = Qwen2Reference(model, max_context=64, allow_fixture=True)
    assert first.identity == second.identity and first.fingerprint == second.fingerprint


def test_masked_out_of_range_tokens_are_rejected_before_forward(model, monkeypatch):
    reference = Qwen2Reference(model, max_context=64, allow_fixture=True)

    def forbidden(*args, **kwargs):
        raise AssertionError("Validate all token ids before computing any row")

    monkeypatch.setattr(reference, "forward_tokens", forbidden)
    with pytest.raises(ReferenceArithmeticError):
        reference.generate(torch.tensor([[-1, 2, 5]]), attention_mask=torch.tensor([[0, 1, 1]]))


def test_candidate_changes_are_observed_and_no_cache_survives_generation(model):
    reference = Qwen2Reference(model, max_context=64, allow_fixture=True)
    tokens = torch.tensor([[2, 5, 7]])
    parent, _ = reference.forward_tokens(tokens)
    before = reference.generate(tokens, max_new_tokens=2)
    snapshot = model.model.norm.weight.detach().clone()
    with torch.no_grad():
        model.model.norm.weight.zero_()
    changed, _ = reference.forward_tokens(tokens)
    assert not torch.equal(changed, parent)
    assert torch.equal(changed, torch.zeros_like(changed))
    # All logits tie: the declared lowest-id rule must select token zero.
    tied = reference.generate(tokens, max_new_tokens=2)
    assert tied[0, 3:].tolist() == [0, 0]
    with torch.no_grad():
        model.model.norm.weight.copy_(snapshot)
    restored, _ = reference.forward_tokens(tokens)
    assert torch.equal(parent.view(torch.int32), restored.view(torch.int32))
    assert torch.equal(before, reference.generate(tokens, max_new_tokens=2))


def test_repetition_penalty_changes_positive_and_negative_repeated_logits(model, monkeypatch):
    reference = Qwen2Reference(model, max_context=64, allow_fixture=True)
    logits = torch.full((1, 41), -10.0)
    logits[0, 2], logits[0, 5], logits[0, 9] = -1.0, 3.0, 2.0
    monkeypatch.setattr(reference, "forward_tokens", lambda *args: (logits.clone(), ()))
    plain = reference.generate(torch.tensor([[2, 5]]), max_new_tokens=1, repetition_penalty=1.0)
    penalized = reference.generate(torch.tensor([[2, 5]]), max_new_tokens=1, repetition_penalty=2.0)
    assert plain[0, -1].item() == 5 and penalized[0, -1].item() == 9
    logits.fill_(-10)
    logits[0, 2], logits[0, 9] = -1.0, -1.5
    penalized_negative = reference.generate(torch.tensor([[2, 5]]), max_new_tokens=1, repetition_penalty=2.0)
    assert penalized_negative[0, -1].item() == 9
