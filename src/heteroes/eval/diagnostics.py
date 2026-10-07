"""
Tools to find out WHY two answers to the same prompt differ (between two GPUs, or between one prompt per call and a padded batch):
the greedy decision at each step is an argmax over FP16-computed scores, so an answer flips when the two best scores are closer
than the rounding noise of the computation. `generate_with_trace` returns the answer's token ids and, for every step, the margin
between the best and the second-best score; `summarize_pair` says where two traces first diverge and how close the decision was
there. A flip with a tiny margin is the expected numerical noise; a flip with a large margin would point at a real bug.
"""
import math

import torch

from heteroes.eval.workload import DO_SAMPLE, MAX_NEW_TOKENS, SYSTEM_PROMPT


def margins_from_scores(scores, row: int = 0) -> list[float]:
    """For each generated step (`scores` is the tuple of per-step score tensors of `generate(output_scores=True)`): top-1 minus top-2 of row `row`."""
    margins = []
    for step in scores:
        top = torch.topk(step[row].double(), k=min(2, step.shape[-1]))
        values = top.values.tolist()
        if len(values) < 2 or values[1] == -math.inf:
            margins.append(math.inf)
        else:
            margins.append(float(values[0] - values[1]))
    return margins


def first_divergence(ids_a: list[int], ids_b: list[int]) -> int | None:
    """The first position where the two token lists differ (the length of the shorter if one is a prefix of the other), or None."""
    for position, (a, b) in enumerate(zip(ids_a, ids_b)):
        if a != b:
            return position
    return None if len(ids_a) == len(ids_b) else min(len(ids_a), len(ids_b))


def summarize_pair(a: dict, b: dict) -> dict:
    """`a` and `b` are {"ids": [...], "margins": [...]}: where they first differ and how close the decision was at that step in each."""
    step = first_divergence(a["ids"], b["ids"])
    if step is None:
        return {"differs": False}
    margins = [m for m in (a["margins"][:step] + b["margins"][:step]) if m is not None]
    return {"differs": True, "step": step,
            "margin_a": a["margins"][step] if step < len(a["margins"]) else None,
            "margin_b": b["margins"][step] if step < len(b["margins"]) else None,
            "min_margin_before": min(margins) if margins else None}


def _prompt_texts(tokenizer, questions):
    return [tokenizer.apply_chat_template([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": q}],
                                          tokenize=False, add_generation_prompt=True) for q in questions]


def generate_with_trace(model, tokenizer, questions: list[str], pad: bool | None = None) -> list[dict]:
    """
    Greedy answers to `questions` in ONE generate() call, as [{"text", "ids", "margins"}] (ids and margins stop at the first end-of-sequence).
    One question: no padding (the reference path of the workload); several: left padding, like `generate_answers`.
    """
    device = next(model.parameters()).device
    texts = _prompt_texts(tokenizer, questions)
    previous_side = tokenizer.padding_side
    tokenizer.padding_side = "left"
    try:
        inputs = tokenizer(texts, return_tensors="pt", padding=len(texts) > 1 if pad is None else pad)
    finally:
        tokenizer.padding_side = previous_side
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=DO_SAMPLE, output_scores=True,
                                return_dict_in_generate=True)
    prompt_length = inputs["input_ids"].shape[1]
    eos = {tokenizer.eos_token_id, tokenizer.pad_token_id} - {None}
    results = []
    for row in range(len(questions)):
        ids = output.sequences[row, prompt_length:].tolist()
        end = next((i for i, token in enumerate(ids) if token in eos), len(ids))
        margins = margins_from_scores(output.scores, row)
        results.append({"text": tokenizer.decode(ids[:end], skip_special_tokens=True).strip(), "ids": ids[:end], "margins": margins[:end]})
    return results
