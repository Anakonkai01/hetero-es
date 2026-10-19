import hashlib
import json
import os
from pathlib import Path

import pytest
import torch

from heteroes.eval import generate as generate_module
from heteroes.eval.generate import evaluate_model, generate_answer
from heteroes.eval.workload import EXAMPLES, MAX_NEW_TOKENS

PROBE_JSON = (
    Path(__file__).resolve().parents[2] / "artifacts" / "probes" / "2026-09-29" / "probe_5070ti.json"
)


# ---------------------------------------------------------------------------
# evaluate_model, with a fake generate_answer: no model needed (runs everywhere)
# ---------------------------------------------------------------------------

def fake_answers(monkeypatch, texts):
    # texts: the answer for each example, in order. Also records how the function was called.
    calls = []

    def fake(model, tokenizer, question):
        calls.append((model, tokenizer, question))
        return texts[len(calls) - 1]

    monkeypatch.setattr(generate_module, "generate_answer", fake)
    return calls


def correct_texts():
    return [f"The answer is {e.answer}." for e in EXAMPLES]


def test_all_correct_gives_reward_one_and_one_record_per_example_in_order(monkeypatch):
    calls = fake_answers(monkeypatch, correct_texts())

    result = evaluate_model("MODEL", "TOKENIZER")

    assert result.mean_reward == 1.0
    assert len(result.records) == 16
    assert [r.question for r in result.records] == [e.question for e in EXAMPLES]
    assert [r.expected for r in result.records] == [e.answer for e in EXAMPLES]
    assert [r.prediction for r in result.records] == [e.answer for e in EXAMPLES]
    assert all(r.reward == 1.0 for r in result.records)
    assert calls == [("MODEL", "TOKENIZER", e.question) for e in EXAMPLES]  # model and tokenizer passed on


def test_mean_reward_is_the_fraction_of_correct_answers(monkeypatch):
    texts = correct_texts()
    for index in (0, 5, 9):          # three wrong
        texts[index] = "0"
    texts[2] = "no number at all"    # one with no integer: counts as wrong, not as an error
    fake_answers(monkeypatch, texts)

    result = evaluate_model(None, None)

    assert result.mean_reward == 12 / 16
    assert [r.reward for r in result.records].count(0.0) == 4
    assert result.records[2].prediction is None
    assert result.records[2].output_text == "no number at all"  # the full text is kept for debugging


def test_every_record_keeps_the_full_output_text(monkeypatch):
    texts = [f"  text {i} with 7 in it  " for i in range(16)]
    fake_answers(monkeypatch, texts)

    result = evaluate_model(None, None)

    assert [r.output_text for r in result.records] == texts
    assert all(r.prediction == 7 for r in result.records)


def test_a_failure_while_generating_is_raised_not_turned_into_reward_zero(monkeypatch):
    # Infrastructure failure is never a task reward of 0 (numerical contract, section 7).
    def failing(model, tokenizer, question):
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(generate_module, "generate_answer", failing)

    with pytest.raises(RuntimeError, match="out of memory"):
        evaluate_model(None, None)


def test_records_and_result_are_immutable(monkeypatch):
    fake_answers(monkeypatch, correct_texts())
    result = evaluate_model(None, None)

    with pytest.raises(Exception):
        result.mean_reward = 0.0
    with pytest.raises(Exception):
        result.records[0].reward = 0.0
    assert isinstance(result.records, tuple)


# ---------------------------------------------------------------------------
# the real model, on the GPU
#   HETEROES_QWEN_PINNED_PATH=<snapshot dir of Qwen2.5-0.5B-Instruct @ 7ae55760...>
# ---------------------------------------------------------------------------

PINNED_PATH = os.environ.get("HETEROES_QWEN_PINNED_PATH")
needs_model = pytest.mark.skipif(
    PINNED_PATH is None or not torch.cuda.is_available(),
    reason="set HETEROES_QWEN_PINNED_PATH and use a CUDA GPU to run the real-model checks",
)


@pytest.fixture(scope="module")
def qwen():
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model = AutoModelForCausalLM.from_pretrained(PINNED_PATH, dtype=torch.float16).to("cuda")
    tokenizer = AutoTokenizer.from_pretrained(PINNED_PATH)
    return model, tokenizer


def weights_digest(model):
    digest = hashlib.sha256()
    for parameter in model.parameters():
        digest.update(parameter.detach().reshape(-1).view(torch.int16).cpu().numpy().tobytes())
    return digest.hexdigest()


@needs_model
def test_base_model_reproduces_the_probe_outputs_text_for_text(qwen):
    # The probe of 2026-09-29 recorded the output of the same model on the same questions.
    model, tokenizer = qwen
    recorded = json.loads(PROBE_JSON.read_text(encoding="utf-8"))["base_evaluation"]

    result = evaluate_model(model, tokenizer)

    assert result.mean_reward == recorded["mean_reward"] == 0.25
    for record, old in zip(result.records, recorded["records"], strict=True):
        assert record.question == old["question"]
        assert record.output_text == old["output_text"]
        assert record.prediction == old["prediction"]
        assert record.reward == old["reward"]


@needs_model
def test_the_same_evaluation_twice_gives_the_same_outputs(qwen):
    model, tokenizer = qwen

    first = evaluate_model(model, tokenizer)
    second = evaluate_model(model, tokenizer)

    assert first == second


@needs_model
def test_evaluating_does_not_change_the_weights(qwen):
    model, tokenizer = qwen
    before = weights_digest(model)

    evaluate_model(model, tokenizer)

    assert weights_digest(model) == before


@needs_model
def test_generate_answer_returns_stripped_text_and_matches_the_first_record(qwen):
    model, tokenizer = qwen

    text = generate_answer(model, tokenizer, EXAMPLES[0].question)

    assert text == "41"
    assert text == text.strip()


@needs_model
def test_generation_is_greedy_with_the_workload_token_budget(qwen, monkeypatch):
    # The sampling settings in the model's generation_config are ignored only if do_sample=False is passed.
    model, tokenizer = qwen
    seen = {}
    real_generate = model.generate

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real_generate(*args, **kwargs)

    monkeypatch.setattr(model, "generate", spy)

    generate_answer(model, tokenizer, EXAMPLES[0].question)

    assert seen["do_sample"] is False
    assert seen["max_new_tokens"] == MAX_NEW_TOKENS == 16


@needs_model
def test_generate_answer_uses_the_system_prompt_and_the_chat_template(qwen, monkeypatch):
    model, tokenizer = qwen
    seen = {}
    real_template = tokenizer.apply_chat_template

    def spy(messages, **kwargs):
        seen["messages"] = messages
        seen.update(kwargs)
        return real_template(messages, **kwargs)

    monkeypatch.setattr(tokenizer, "apply_chat_template", spy)

    generate_answer(model, tokenizer, EXAMPLES[0].question)

    assert seen["messages"] == [
        {"role": "system", "content": "You are a calculator. Answer with only with number"},
        {"role": "user", "content": "What is 17 + 24?"},
    ]
    assert seen["add_generation_prompt"] is True


@needs_model
def test_a_perturbed_model_gives_different_outputs_from_the_base_model(qwen):
    # Premise of the whole step: the evaluation can see a perturbation (the data tells the models apart).
    from heteroes.es.perturb import perturb_model_
    from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
    from heteroes.model.schema import build_parameter_schema

    model, tokenizer = qwen
    schema = build_parameter_schema(model)
    snapshot = take_snapshot(model, schema)
    base = evaluate_model(model, tokenizer)
    try:
        perturb_model_(model, schema, candidate_seed=0, sigma=1e-3)
        perturbed = evaluate_model(model, tokenizer)
    finally:
        restore_from_snapshot_(model, schema, snapshot)

    assert [r.output_text for r in perturbed.records] != [r.output_text for r in base.records]
    assert evaluate_model(model, tokenizer) == base  # and after restore it is the base model again


# ---------------------------------------------------------------------------
# chunk: how the 16 questions are grouped into generate() calls (no model needed)
# ---------------------------------------------------------------------------

def fake_batches(monkeypatch, texts):
    groups = []

    def fake(model, tokenizer, questions):
        groups.append(list(questions))
        return [texts[EXAMPLES_QUESTIONS.index(q)] for q in questions]

    monkeypatch.setattr(generate_module, "generate_answers", fake)
    return groups


EXAMPLES_QUESTIONS = [e.question for e in EXAMPLES]


@pytest.mark.parametrize("chunk,sizes", [(2, [2] * 8), (4, [4] * 4), (5, [5, 5, 5, 1]), (16, [16]), (100, [16])])
def test_a_chunk_groups_the_same_questions_in_the_same_order(monkeypatch, chunk, sizes):
    texts = correct_texts()
    texts[3] = "wrong 1"
    groups = fake_batches(monkeypatch, texts)

    result = evaluate_model(None, None, chunk=chunk)

    assert [len(g) for g in groups] == sizes
    assert [q for g in groups for q in g] == EXAMPLES_QUESTIONS            # nothing dropped, nothing reordered
    assert [r.question for r in result.records] == EXAMPLES_QUESTIONS
    assert [r.reward for r in result.records] == [0.0 if i == 3 else 1.0 for i in range(16)]
    assert result.mean_reward == 15 / 16


def test_chunk_one_is_the_one_prompt_at_a_time_reference_path(monkeypatch):
    calls = fake_answers(monkeypatch, correct_texts())
    monkeypatch.setattr(generate_module, "generate_answers", lambda *a: pytest.fail("the batch path must not be used"))

    evaluate_model("M", "T", chunk=1)

    assert len(calls) == 16


@pytest.mark.parametrize("bad", [0, -2, 1.0, True, "2", None])
def test_a_bad_chunk_is_refused_before_anything_runs(monkeypatch, bad):
    calls = fake_answers(monkeypatch, correct_texts())

    with pytest.raises(ValueError):
        evaluate_model(None, None, chunk=bad)
    assert calls == []
