"""
A longer arithmetic workload for the experiments of G7: the model reasons step by step and ends with "Answer: <integer>".

Why: the 16-prompt workload of the contract answers in at most 16 tokens (0.16 s of rollout), so the CPU noise and the restore dominate
a candidate and a slow GPU cannot matter. Here the rollout is up to MAX_NEW_TOKENS tokens per question, which makes the GPU the main
cost. This file is an EXPERIMENT script, not part of the contract (the contract workload and its hash are untouched).

Questions are generated from a seed, so that every machine builds the same ones; the answer is computed, never typed.
"""
import random
import re
import time

import torch

SYSTEM_PROMPT = "Solve the problem step by step. End your reply with a line 'Answer: <integer>'."
MAX_NEW_TOKENS = 256


def make_questions(count: int, level: int, seed: int = 20261007) -> list[tuple[str, int]]:
    """level 1: two operands of two digits; 2: three operands (+, -, *) with small numbers; 3: like 2 with larger numbers and a word problem."""
    rng = random.Random(seed * 10 + level)
    out = []
    for _ in range(count):
        if level == 1:
            a, b = rng.randint(11, 99), rng.randint(11, 99)
            op = rng.choice("+-*")
            out.append((f"What is {a} {op} {b}?", eval(f"{a}{op}{b}")))
        elif level == 2:
            a, b, c = rng.randint(2, 40), rng.randint(2, 40), rng.randint(2, 40)
            op1, op2 = rng.choice("+-*"), rng.choice("+-*")
            out.append((f"What is {a} {op1} {b} {op2} {c}?", eval(f"{a}{op1}{b}{op2}{c}")))
        else:
            packs, per, sold = rng.randint(12, 60), rng.randint(12, 48), rng.randint(100, 500)
            out.append((f"A shop has {packs} boxes with {per} pens in each box. It sells {sold} pens. How many pens remain?", packs * per - sold))
    return out


_ANSWER = re.compile(r"Answer:\s*\$?\s*(-?\d[\d,]*)")
_INTEGER = re.compile(r"-?\d[\d,]*")


def extract_answer(text: str) -> int | None:
    """The integer after the last 'Answer:'; if there is none, the last integer of the text (a reply without any integer is wrong)."""
    found = _ANSWER.findall(text) or _INTEGER.findall(text)
    if not found:
        return None
    try:
        return int(found[-1].replace(",", ""))
    except ValueError:
        return None


def generate(model, tokenizer, questions: list[str], chunk: int) -> tuple[list[str], int]:
    """Greedy answers, `chunk` prompts per generate() call (left padding). Returns the texts and the number of tokens generated in total."""
    device = next(model.parameters()).device
    texts_out, tokens = [], 0
    previous = tokenizer.padding_side
    tokenizer.padding_side = "left"
    try:
        for start in range(0, len(questions), chunk):
            group = questions[start:start + chunk]
            prompts = [tokenizer.apply_chat_template([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": q}],
                                                     tokenize=False, add_generation_prompt=True) for q in group]
            inputs = tokenizer(prompts, return_tensors="pt", padding=True)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                ids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
            new = ids[:, inputs["input_ids"].shape[1]:]
            for row in new:
                tokens += int((row != tokenizer.pad_token_id).sum())
            texts_out += [t.strip() for t in tokenizer.batch_decode(new, skip_special_tokens=True)]
    finally:
        tokenizer.padding_side = previous
    return texts_out, tokens


def evaluate(model, tokenizer, qa: list[tuple[str, int]], chunk: int) -> dict:
    start = time.perf_counter()
    texts, tokens = generate(model, tokenizer, [q for q, _ in qa], chunk)
    if next(model.parameters()).is_cuda:
        torch.cuda.synchronize()
    seconds = time.perf_counter() - start
    rewards = [1.0 if extract_answer(t) == a else 0.0 for t, (_, a) in zip(texts, qa)]
    return {"mean_reward": sum(rewards) / len(rewards), "rewards": rewards, "texts": texts, "tokens": tokens, "seconds": seconds}
