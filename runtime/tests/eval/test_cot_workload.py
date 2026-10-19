"""
Tests of the long arithmetic workload with step-by-step reasoning (G7). No model needed: the generation is replaced by a function that returns texts.
The arithmetic of the oracle is written here (not taken from the module): the questions are parsed back from their text and solved again.
"""
import re

import pytest

import heteroes.eval.cot_workload as cot
from heteroes.eval.cot_workload import (MAX_NEW_TOKENS, SYSTEM_PROMPT, evaluate_cot, extract_answer, make_questions, workload_dict, workload_hash_of)
from heteroes.eval.generate import EvalResult
from heteroes.eval.workloads import WORKLOADS, get_workload
from heteroes.eval.workload import workload_hash


# ---- the questions ---------------------------------------------------------------------------------------------------------------

def test_the_questions_are_a_pure_function_of_the_count_the_level_and_the_seed():
    assert make_questions(32, 3) == make_questions(32, 3)
    assert make_questions(32, 3) != make_questions(32, 2)
    assert make_questions(32, 3, seed=1) != make_questions(32, 3, seed=2)
    assert len(make_questions(5, 1)) == 5 and make_questions(0, 1) == []


def solve(question: str) -> int:
    """The answer of a question, from its text only."""
    word = re.fullmatch(r"A shop has (\d+) boxes with (\d+) pens in each box\. It sells (\d+) pens\. How many pens remain\?", question)
    if word:
        packs, per, sold = map(int, word.groups())
        return packs * per - sold
    expression = re.fullmatch(r"What is (.*)\?", question).group(1)
    tokens = expression.split()
    values, operators = [int(t) for t in tokens[0::2]], tokens[1::2]
    # multiplication binds tighter than + and -: fold the products first
    terms, signs = [values[0]], []
    for operator, value in zip(operators, values[1:]):
        if operator == "*":
            terms[-1] *= value
        else:
            signs.append(operator)
            terms.append(value)
    result = terms[0]
    for sign, term in zip(signs, terms[1:]):
        result = result + term if sign == "+" else result - term
    return result


@pytest.mark.parametrize("level", [1, 2, 3])
def test_every_answer_is_the_solution_of_its_question(level):
    for question, answer in make_questions(200, level):
        assert answer == solve(question), question


def test_a_level_has_the_shape_it_says():
    assert all(re.fullmatch(r"What is \d+ [-+*] \d+\?", q) for q, _ in make_questions(50, 1))
    assert all(len(q.split()) == 7 for q, _ in make_questions(50, 2))                     # "What is a op b op c?"
    assert all(q.startswith("A shop has") for q, _ in make_questions(50, 3))


@pytest.mark.parametrize("count,level", [(-1, 1), (1, 0), (1, 4), (True, 1), (1, True), (1.0, 1)])
def test_bad_arguments_are_refused(count, level):
    with pytest.raises(ValueError):
        make_questions(count, level)


# ---- the answer in the text -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("so 3 + 4 = 7.\nAnswer: 7", 7),
    ("Answer: 1,003", 1003),
    ("Answer: -12", -12),
    ("first Answer: 5 then more steps, and Answer: 9", 9),               # the last 'Answer:' counts
    ("the result is \\boxed{208}", 208),                                 # no 'Answer:': the last integer
    ("Answer: $41", 41),
    ("no number at all", None),
    ("", None),
])
def test_the_answer_is_the_integer_after_the_last_answer_line_else_the_last_integer(text, expected):
    assert extract_answer(text) == expected


# ---- the evaluation ---------------------------------------------------------------------------------------------------------------

def fake_generate(monkeypatch, replies):
    calls = []

    def fake(model, tokenizer, questions, chunk, decode_engine="hf_generate"):
        calls.append((list(questions), chunk))
        return [replies(q) for q in questions], 7 * len(questions)

    monkeypatch.setattr(cot, "generate", fake)
    return calls


def test_the_reward_is_the_exact_match_averaged_over_the_questions(monkeypatch):
    qa = make_questions(8, 3)
    wrong = {q for q, _ in qa[:2]}
    fake_generate(monkeypatch, lambda q: f"Answer: {0 if q in wrong else solve(q)}")
    result = evaluate_cot(None, None, 4, level=3, count=8)
    assert isinstance(result, EvalResult) and result.mean_reward == pytest.approx(6 / 8)
    assert [r.reward for r in result.records] == [0.0, 0.0] + [1.0] * 6
    assert [r.question for r in result.records] == [q for q, _ in qa] and [r.expected for r in result.records] == [a for _, a in qa]


def test_a_reply_without_an_integer_is_a_wrong_answer_not_an_error(monkeypatch):
    fake_generate(monkeypatch, lambda q: "I do not know")
    result = evaluate_cot(None, None, 8, level=3, count=4)
    assert result.mean_reward == 0.0 and all(r.prediction is None for r in result.records)


def test_the_chunk_is_passed_to_the_generation_and_the_questions_are_the_workload_in_order(monkeypatch):
    calls = fake_generate(monkeypatch, lambda q: "Answer: 1")
    evaluate_cot(None, None, 16, level=3, count=32)
    assert calls == [([q for q, _ in make_questions(32, 3)], 16)]


@pytest.mark.parametrize("chunk", [0, -1, True, 1.0, "4"])
def test_a_bad_chunk_is_refused(monkeypatch, chunk):
    fake_generate(monkeypatch, lambda q: "Answer: 1")
    with pytest.raises(ValueError):
        evaluate_cot(None, None, chunk, level=3, count=4)


# ---- the identity of the workload ---------------------------------------------------------------------------------------------------

def test_the_hash_says_everything_that_makes_two_machines_ask_the_same_thing(monkeypatch):
    base = workload_hash_of(3, 32)
    assert base == workload_hash_of(3, 32) and len(base) == 64
    assert base != workload_hash_of(2, 32) and base != workload_hash_of(3, 31)
    monkeypatch.setattr(cot, "MAX_NEW_TOKENS", MAX_NEW_TOKENS + 1)
    assert workload_hash_of(3, 32) != base
    monkeypatch.undo()
    monkeypatch.setattr(cot, "SYSTEM_PROMPT", SYSTEM_PROMPT + " ")
    assert workload_hash_of(3, 32) != base


def test_the_workload_document_has_the_questions_and_their_answers():
    document = workload_dict(3, 4)
    assert document["max_new_tokens"] == MAX_NEW_TOKENS and document["system_prompt"] == SYSTEM_PROMPT and document["do_sample"] is False
    assert document["examples"] == [{"question": q, "answer": a} for q, a in make_questions(4, 3)]


def test_the_hash_of_the_workload_of_the_experiments_is_pinned():
    # a regression guard produced by this code on 2026-10-07 (the questions are generated, so this also pins the generator)
    assert workload_hash_of(3, 32) == "a052f8495c906b9211e91e22581894cbd9e6fa625834f1985f2e8643b19bd0de"


# ---- the registry of the names of the recipe --------------------------------------------------------------------------------------

def test_the_16_prompt_workload_is_the_one_of_the_contract():
    from heteroes.eval.generate import evaluate_model
    assert get_workload("arith16").hash() == workload_hash() and get_workload("arith16").evaluate is evaluate_model


def test_the_long_workload_is_level_3_with_32_questions(monkeypatch):
    workload = get_workload("cot_l3_q32")
    assert workload.hash() == workload_hash_of(3, 32)
    calls = fake_generate(monkeypatch, lambda q: "Answer: 1")
    workload.evaluate(None, None, 16)
    assert calls == [([q for q, _ in make_questions(32, 3)], 16)]


def test_every_name_of_the_manifest_has_a_workload_and_nothing_else_does():
    from heteroes.manifest import WORKLOAD_NAMES
    assert set(WORKLOADS) == set(WORKLOAD_NAMES)


@pytest.mark.parametrize("name", ["cot", "", None, "ARITH16"])
def test_an_unknown_workload_is_refused(name):
    with pytest.raises(ValueError):
        get_workload(name)


# ---- the 64-question workload (G7: a bigger batch is faster per question, and more questions make the reward less noisy) ----------------

def test_the_64_question_workload_is_level_3_with_64_questions_and_its_own_hash(monkeypatch):
    workload = get_workload("cot_l3_q64")
    assert workload.hash() == workload_hash_of(3, 64) and workload.hash() != get_workload("cot_l3_q32").hash()
    calls = fake_generate(monkeypatch, lambda q: "Answer: 1")
    workload.evaluate(None, None, 64)
    assert calls == [([q for q, _ in make_questions(64, 3)], 64)]


def test_the_first_32_questions_of_the_64_are_the_32_of_the_other_workload():
    # the questions come from one random stream: a longer workload extends a shorter one, so the data of the experiments with 32 questions stay comparable
    assert make_questions(64, 3)[:32] == make_questions(32, 3)


def test_the_hash_of_the_64_question_workload_is_pinned():
    assert workload_hash_of(3, 64) == "9049518d5d51ccfffe2687cc2fa4b731f03590b7e2a2a78de71c5952aa4adc35"


# ---- the 128-question level-1 workload (08/10: the level-3 word problems were limited by the 256-token cut, see artifacts/experiments/2026-10-08-uncut-probe) ----

def test_the_level_1_workload_has_128_questions_and_its_own_hash(monkeypatch):
    workload = get_workload("cot_l1_q128")
    assert workload.hash() == workload_hash_of(1, 128)
    assert len({workload.hash(), get_workload("cot_l3_q64").hash(), get_workload("cot_l3_q32").hash(), get_workload("arith16").hash()}) == 4
    calls = fake_generate(monkeypatch, lambda q: "Answer: 1")
    workload.evaluate(None, None, 128)
    assert calls == [([q for q, _ in make_questions(128, 1)], 128)]


def test_the_level_1_questions_are_two_digit_operations_with_computed_answers():
    questions = make_questions(128, 1)
    assert len(questions) == 128 and len({q for q, _ in questions}) > 100            # a few repeats are possible: the generator draws with replacement
    for question, answer in questions:
        a, op, b = re.fullmatch(r"What is (\d+) ([+\-*]) (\d+)\?", question).groups()
        assert 11 <= int(a) <= 99 and 11 <= int(b) <= 99 and answer == eval(f"{a}{op}{b}")


def test_the_first_64_questions_of_the_128_are_the_64_of_a_smaller_level_1_set():
    assert make_questions(128, 1)[:64] == make_questions(64, 1)


def test_the_level_1_workload_is_a_name_of_the_manifest_and_a_recipe_can_name_it():
    from heteroes.manifest import WORKLOAD_NAMES
    assert "cot_l1_q128" in WORKLOAD_NAMES


def test_every_workload_knows_its_own_name():
    assert all(workload.name == name for name, workload in WORKLOADS.items())


# ---- the decode engine (09/10) ---------------------------------------------------------------------------------------------------------

def test_the_decode_engine_goes_from_the_registry_through_the_evaluation_to_the_generation(monkeypatch):
    seen = []

    def fake(model, tokenizer, questions, chunk, decode_engine="hf_generate"):
        seen.append(decode_engine)
        return ["Answer: 1"] * len(questions), 0

    monkeypatch.setattr(cot, "generate", fake)
    evaluate_cot(None, None, 4, level=1, count=4)
    evaluate_cot(None, None, 4, level=1, count=4, decode_engine="hf_compact")
    get_workload("cot_l1_q128").evaluate(None, None, 128, "hf_compact")
    get_workload("cot_l3_q32").evaluate(None, None, 16)
    assert seen == ["hf_generate", "hf_compact", "hf_compact", "hf_generate"]


@pytest.mark.parametrize("bad", ["vllm", "", None, 3])
def test_an_unknown_decode_engine_is_refused_by_the_evaluation(monkeypatch, bad):
    fake_generate(monkeypatch, lambda q: "Answer: 1")
    with pytest.raises(ValueError, match="decode_engine"):
        evaluate_cot(None, None, 4, level=1, count=4, decode_engine=bad)


# the real glue, on a tiny model: both engines must give the same texts and the same token count

class FakeTokenizer:
    pad_token_id = 0
    padding_side = "right"

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        return messages[-1]["content"]

    def __call__(self, prompts, return_tensors="pt", padding=True):
        import torch
        rows = [[(ord(c) % 60) + 2 for c in prompt] for prompt in prompts]
        width = max(len(r) for r in rows)
        ids, mask = torch.zeros(len(rows), width, dtype=torch.long), torch.zeros(len(rows), width, dtype=torch.long)
        for i, row in enumerate(rows):
            start = width - len(row) if self.padding_side == "left" else 0
            ids[i, start:start + len(row)] = torch.tensor(row)
            mask[i, start:start + len(row)] = 1
        return {"input_ids": ids, "attention_mask": mask}

    def batch_decode(self, ids, skip_special_tokens=True):
        return ["".join(chr(97 + int(t) % 26) for t in row if int(t) != self.pad_token_id) for row in ids]


def test_both_decode_engines_give_the_same_texts_and_the_same_token_count_on_a_tiny_model(monkeypatch):
    import torch
    from transformers import Qwen2Config, Qwen2ForCausalLM
    torch.manual_seed(4321)
    model = Qwen2ForCausalLM(Qwen2Config(vocab_size=64, hidden_size=32, intermediate_size=64, num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
                                         max_position_embeddings=512, tie_word_embeddings=False, initializer_range=0.4)).float().eval()
    model.generation_config.pad_token_id = 0
    model.generation_config.do_sample = False
    monkeypatch.setattr(cot, "MAX_NEW_TOKENS", 24)
    tokenizer = FakeTokenizer()
    questions = [q for q, _ in make_questions(12, 1)] + ["What is 7 * 8 and the rest of a much longer question than the others?"]
    tokenizer.padding_side = "left"
    ids = tokenizer([cot_prompt for cot_prompt in questions])["input_ids"]
    model.generation_config.eos_token_id = [99]
    with torch.no_grad():
        free = model.generate(input_ids=ids, attention_mask=tokenizer(questions)["attention_mask"], max_new_tokens=24, do_sample=False, pad_token_id=0)[:, ids.shape[1]:]
    model.generation_config.eos_token_id = sorted({int(free[0, 3]), int(free[1, 6]), int(free[2, 9])})
    tokenizer.padding_side = "right"                 # generate() sets it to left by itself and puts it back
    for chunk in (4, 13):
        plain = cot.generate(model, tokenizer, questions, chunk)
        compact = cot.generate(model, tokenizer, questions, chunk, "hf_compact")
        assert compact == plain
        assert len(set(len(t) for t in plain[0])) > 2          # premise: the texts have different lengths (the rows ended at different steps)
    assert tokenizer.padding_side == "right"


def test_each_decode_engine_calls_only_its_own_decoder(monkeypatch):
    import torch
    from transformers import Qwen2Config, Qwen2ForCausalLM
    import heteroes.eval.compact_decode as compact_module
    torch.manual_seed(99)
    model = Qwen2ForCausalLM(Qwen2Config(vocab_size=64, hidden_size=32, intermediate_size=64, num_hidden_layers=1, num_attention_heads=4, num_key_value_heads=2,
                                         max_position_embeddings=128)).float().eval()
    model.generation_config.pad_token_id = 0
    model.generation_config.eos_token_id = [1]
    monkeypatch.setattr(cot, "MAX_NEW_TOKENS", 4)
    tokenizer = FakeTokenizer()
    calls = {"library": 0, "compact": 0}
    real_generate, real_compact = model.generate, compact_module.compact_generate_ids

    def counted_generate(*args, **kwargs):
        calls["library"] += 1
        return real_generate(*args, **kwargs)

    def counted_compact(*args, **kwargs):
        calls["compact"] += 1
        return real_compact(*args, **kwargs)

    monkeypatch.setattr(model, "generate", counted_generate)
    monkeypatch.setattr(compact_module, "compact_generate_ids", counted_compact)
    cot.generate(model, tokenizer, ["What is 1 + 2?", "What is 3 * 4?"], 2, "hf_compact")
    assert calls == {"library": 0, "compact": 1}
    cot.generate(model, tokenizer, ["What is 1 + 2?", "What is 3 * 4?"], 2, "hf_generate")
    assert calls == {"library": 1, "compact": 1}


def test_the_compacting_decoder_refuses_an_unsupported_generation_config_before_decoding(monkeypatch):
    import torch
    from transformers import Qwen2Config, Qwen2ForCausalLM
    from heteroes.eval.compact_decode import UnsupportedDecode
    model = Qwen2ForCausalLM(Qwen2Config(vocab_size=64, hidden_size=32, intermediate_size=64, num_hidden_layers=1, num_attention_heads=4, num_key_value_heads=2)).float().eval()
    model.generation_config.eos_token_id = [1]
    model.generation_config.no_repeat_ngram_size = 2
    with pytest.raises(UnsupportedDecode):
        cot.generate(model, FakeTokenizer(), ["What is 1 + 2?"], 1, "hf_compact")
