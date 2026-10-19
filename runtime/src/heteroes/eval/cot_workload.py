"""
A longer arithmetic workload (G7): the model reasons step by step (up to 256 new tokens) and ends with "Answer: <integer>".

Why: the workload of the contract (`workload.py`) answers in at most 16 tokens, 0.16 s of rollout on the 5070 Ti, so the CPU noise and the restore dominate a
candidate and a slow GPU cannot matter. Here the rollout is the main cost. The questions are generated from a seed, so every machine builds the same ones;
the answer is computed, never typed. `cot_l3_q32` (word problems, 32 questions) is the workload of the G7 experiments (accuracy 0.28 of the base model).
"""
import operator
import random
import re

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval.generate import EvalRecord, EvalResult

SYSTEM_PROMPT = "Solve the problem step by step. End your reply with a line 'Answer: <integer>'."
MAX_NEW_TOKENS = 256
DO_SAMPLE = False
REWARD_TYPE = "exact_integer_match_after_answer_line"
GENERATOR_SEED = 20261007

_OPERATORS = {"+": operator.add, "-": operator.sub, "*": operator.mul}
_ANSWER = re.compile(r"Answer:\s*\$?\s*(-?\d[\d,]*)")
_INTEGER = re.compile(r"-?\d[\d,]*")


def _check_int(name: str, value, minimum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer of at least {minimum}, got {value!r}")


def make_questions(count: int, level: int, seed: int = GENERATOR_SEED) -> list[tuple[str, int]]:
    """
    `count` questions of a level: 1 = two operands of two digits; 2 = three operands (+, -, *) of at most two digits;
    3 = a word problem (boxes of pens). Returns (question, answer). Python's precedence applies to level 2 (the product first).
    """
    _check_int("count", count, 0)
    _check_int("level", level, 1)
    _check_int("seed", seed, 0)
    if level > 3:
        raise ValueError(f"level must be 1, 2 or 3, got {level}")
    rng = random.Random(seed * 10 + level)
    out = []
    for _ in range(count):
        if level == 1:
            a, b = rng.randint(11, 99), rng.randint(11, 99)
            op = rng.choice("+-*")
            out.append((f"What is {a} {op} {b}?", _OPERATORS[op](a, b)))
        elif level == 2:
            a, b, c = rng.randint(2, 40), rng.randint(2, 40), rng.randint(2, 40)
            op1, op2 = rng.choice("+-*"), rng.choice("+-*")
            # the same precedence as Python: * before + and -
            if op2 == "*" and op1 != "*":
                answer = _OPERATORS[op1](a, _OPERATORS[op2](b, c))
            else:
                answer = _OPERATORS[op2](_OPERATORS[op1](a, b), c)
            out.append((f"What is {a} {op1} {b} {op2} {c}?", answer))
        else:
            packs, per, sold = rng.randint(12, 60), rng.randint(12, 48), rng.randint(100, 500)
            out.append((f"A shop has {packs} boxes with {per} pens in each box. It sells {sold} pens. How many pens remain?", packs * per - sold))
    return out


def extract_answer(text: str) -> int | None:
    """The integer after the last 'Answer:'; if there is none, the last integer of the text; None if the text has no integer."""
    found = _ANSWER.findall(text) or _INTEGER.findall(text)
    if not found:
        return None
    try:
        return int(found[-1].replace(",", ""))
    except ValueError:
        return None


def _check_decode_engine(decode_engine) -> None:
    from heteroes.manifest import DECODE_ENGINES
    if not isinstance(decode_engine, str) or decode_engine not in DECODE_ENGINES:
        raise ValueError(f"decode_engine must be one of {DECODE_ENGINES}, got {decode_engine!r}")


def generate(model, tokenizer, questions: list[str], chunk: int, decode_engine: str = "hf_generate") -> tuple[list[str], int]:
    """
    Greedy answers, `chunk` prompts per call (left padding). Returns the texts and the number of tokens generated in total.
    `decode_engine`: "hf_generate" is the library's `generate()`; "hf_compact" is the compacting greedy decoder (`heteroes.eval.compact_decode`), which gives the same
    answers without computing the ones that have already ended; it refuses a generation config it does not reproduce (`UnsupportedDecode`) before decoding anything.
    """
    _check_decode_engine(decode_engine)
    device = next(model.parameters()).device
    if decode_engine == "hf_compact":
        from heteroes.eval.compact_decode import compact_generate_ids, decode_settings
        eos_ids, pad_id, processors = decode_settings(model, MAX_NEW_TOKENS, tokenizer.pad_token_id)
    texts_out, tokens = [], 0
    previous = tokenizer.padding_side
    tokenizer.padding_side = "left"
    try:
        for start in range(0, len(questions), chunk):
            group = questions[start:start + chunk]
            prompts = [tokenizer.apply_chat_template([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}],
                                                     tokenize=False, add_generation_prompt=True) for question in group]
            inputs = tokenizer(prompts, return_tensors="pt", padding=True)
            inputs = {key: value.to(device) for key, value in inputs.items()}
            if decode_engine == "hf_compact":
                new, _ = compact_generate_ids(model, inputs["input_ids"], inputs["attention_mask"], MAX_NEW_TOKENS, eos_ids, pad_id, processors)
            else:
                with torch.no_grad():
                    ids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=DO_SAMPLE)
                new = ids[:, inputs["input_ids"].shape[1]:]
            tokens += int((new != tokenizer.pad_token_id).sum())
            texts_out += [text.strip() for text in tokenizer.batch_decode(new, skip_special_tokens=True)]
    finally:
        tokenizer.padding_side = previous
    return texts_out, tokens


def evaluate_cot(model, tokenizer, chunk: int, level: int = 3, count: int = 32, decode_engine: str = "hf_generate") -> EvalResult:
    """
    Ask the questions and score them: the mean of the exact matches. A failure while generating (for example CUDA out of memory) is raised, never
    turned into a reward of 0 (an infrastructure failure is not a wrong answer); a reply without any integer is a wrong answer.
    """
    if isinstance(chunk, bool) or not isinstance(chunk, int) or chunk < 1:
        raise ValueError(f"chunk must be an integer of at least 1, got {chunk!r}")
    _check_decode_engine(decode_engine)
    qa = make_questions(count, level)
    texts, _ = generate(model, tokenizer, [question for question, _ in qa], chunk, decode_engine)
    records = []
    for (question, answer), text in zip(qa, texts, strict=True):
        prediction = extract_answer(text)
        records.append(EvalRecord(question, answer, text, prediction, 1.0 if prediction == answer else 0.0))
    return EvalResult(sum(r.reward for r in records) / len(records), tuple(records))


def workload_dict(level: int, count: int) -> dict:
    """The workload as plain data: everything that makes two machines ask the same questions the same way."""
    return {
        "kind": "arithmetic_with_reasoning",
        "system_prompt": SYSTEM_PROMPT,
        "max_new_tokens": MAX_NEW_TOKENS,
        "do_sample": DO_SAMPLE,
        "reward_type": REWARD_TYPE,
        "examples": [{"question": question, "answer": answer} for question, answer in make_questions(count, level)],
    }


def workload_hash_of(level: int, count: int) -> str:
    return canonical_json_hash(workload_dict(level, count))
