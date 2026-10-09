#!/usr/bin/env python3
"""
Greedy decoding that drops the answers which have finished from the batch (an EXPERIMENT, not package code).

`generate()` of the library keeps computing a finished answer (as padding) until the longest answer of its batch ends: on `cot_l1_q128` only 44 percent
of the token slots at chunk 64 hold a real token (`../2026-10-09-rollout-waste/`). `compact_generate` does the same greedy decoding by hand: the same prompts, the same left
padding, the same position ids (from the attention mask), the same repetition penalty that the model's generation config applies, the same two end tokens, but every
time enough rows have finished it removes them from the input, the attention mask and the key/value cache.

    python compact_decode.py --model-path <snapshot dir> --candidates 8 --out result.json [--chunks 64,128] [--drop-fraction 0.1]

For the parent weights and for the same perturbed candidates as `scripts/profile_worker.py` (seeds 7001, ...), it answers the 128 questions with the library's `generate()` (the
reference, through `heteroes.eval.cot_workload.generate`) and with `compact_generate`, at each chunk, and records whether every text is equal and how long each took.
The output file must not exist.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

PROFILE_SEED_BASE = 7001


def compact_generate(model, tokenizer, prompts, max_new_tokens=256, drop_fraction=0.1):
    """
    Greedy answers for `prompts` (one batch), the way `model.generate(..., do_sample=False)` gives them, but finished rows are removed from the batch.
    `drop_fraction`: rows are removed when at least that fraction of the CURRENT rows has finished (0 = at every step where a row finished).
    Returns the texts (decoded without special tokens, stripped) and a dict of counters (steps, slot_steps = sum over steps of the rows computed).
    """
    import torch
    from transformers.generation.logits_process import RepetitionPenaltyLogitsProcessor

    device = next(model.parameters()).device
    gen = model.generation_config
    eos = gen.eos_token_id if isinstance(gen.eos_token_id, (list, tuple)) else [gen.eos_token_id]
    eos_ids = torch.tensor(eos, device=device)
    pad = gen.pad_token_id
    penalty = RepetitionPenaltyLogitsProcessor(gen.repetition_penalty) if gen.repetition_penalty not in (None, 1.0) else None

    previous = tokenizer.padding_side
    tokenizer.padding_side = "left"
    try:
        inputs = tokenizer(prompts, return_tensors="pt", padding=True)
    finally:
        tokenizer.padding_side = previous
    ids = inputs["input_ids"].to(device)
    mask = inputs["attention_mask"].to(device)
    total = ids.shape[0]
    position = mask.long().cumsum(-1) - 1
    position = position.masked_fill(mask == 0, 0)

    out = torch.full((total, max_new_tokens), pad, dtype=torch.long, device=device)
    rows = torch.arange(total, device=device)                  # original index of every row that is still in the batch
    counters = {"steps": 0, "slot_steps": 0, "compactions": 0}

    with torch.no_grad():
        result = model(input_ids=ids, attention_mask=mask, position_ids=position, use_cache=True)
        cache = result.past_key_values
        scores = result.logits[:, -1].to(dtype=torch.float32)
        all_ids = ids
        last_position = position[:, -1]
        finished = torch.zeros(total, dtype=torch.bool, device=device)
        for step in range(max_new_tokens):
            counters["steps"] += 1
            counters["slot_steps"] += int(rows.shape[0])
            if penalty is not None:
                scores = penalty(all_ids, scores)
            next_tokens = torch.argmax(scores, dim=-1)
            next_tokens = torch.where(finished, torch.full_like(next_tokens, pad), next_tokens)      # a finished row gets padding, like the library
            out[rows, step] = next_tokens
            finished = finished | torch.isin(next_tokens, eos_ids)
            if step == max_new_tokens - 1:
                break
            if bool(finished.all()):
                break
            alive = int((~finished).sum())
            if finished.any() and (rows.shape[0] - alive) >= max(1, drop_fraction * rows.shape[0]):
                keep = torch.nonzero(~finished).squeeze(1)
                rows, mask, all_ids, last_position = rows[keep], mask[keep], all_ids[keep], last_position[keep]
                next_tokens = next_tokens[keep]
                cache.batch_select_indices(keep)
                finished = torch.zeros(rows.shape[0], dtype=torch.bool, device=device)
                counters["compactions"] += 1
            all_ids = torch.cat([all_ids, next_tokens[:, None]], dim=-1)
            mask = torch.cat([mask, mask.new_ones((mask.shape[0], 1))], dim=-1)
            last_position = last_position + 1
            result = model(input_ids=next_tokens[:, None], attention_mask=mask, position_ids=last_position[:, None], past_key_values=cache, use_cache=True)
            cache = result.past_key_values
            scores = result.logits[:, -1].to(dtype=torch.float32)
    texts = [text.strip() for text in tokenizer.batch_decode(out, skip_special_tokens=True)]
    return texts, counters


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--chunks", default="64,128")
    parser.add_argument("--drop-fraction", type=float, default=0.1)
    parser.add_argument("--sigma", type=float, default=1e-3)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if Path(args.out).exists():
        print(f"error: {args.out} already exists; evidence is never overwritten", file=sys.stderr)
        return 2
    import torch

    from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
    from heteroes.eval.cot_workload import MAX_NEW_TOKENS, SYSTEM_PROMPT, generate as library_generate, make_questions
    from heteroes.eval.precision import EvalModel
    from heteroes.model.loading import build_recipe, check_recipe_selftest, load_pinned_model
    from heteroes.profile_setup import noise_ops
    from heteroes.runtime_info import environment_info

    device = "cuda"
    loaded = load_pinned_model(args.model_path, device)
    model, tokenizer, schema = loaded.model, loaded.tokenizer, loaded.schema
    recipe = build_recipe(loaded, sigma=args.sigma, eval_dtype="float32", noise_engine="cuda", workload="cot_l1_q128")
    check_recipe_selftest(recipe, device)
    perturb_op, _ = noise_ops(recipe.engine_version, None)
    evaluation = EvalModel(model, "float32")
    snapshot = take_snapshot(model, schema)
    questions = [question for question, _ in make_questions(128, 1)]
    prompts = [tokenizer.apply_chat_template([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": q}], tokenize=False, add_generation_prompt=True)
               for q in questions]
    chunks = [int(c) for c in args.chunks.split(",")]

    def timed(function):
        torch.cuda.synchronize()
        start = time.perf_counter()
        value = function()
        torch.cuda.synchronize()
        return value, time.perf_counter() - start

    def compact_all(chunk):
        texts, steps, slots = [], 0, 0
        for start in range(0, len(prompts), chunk):
            part, counters = compact_generate(evaluation.model, tokenizer, prompts[start:start + chunk], MAX_NEW_TOKENS, args.drop_fraction)
            texts += part
            steps += counters["steps"]
            slots += counters["slot_steps"]
        return texts, steps, slots

    records = []
    warm = False
    for index in range(args.candidates + 1):
        seed = None if index == 0 else PROFILE_SEED_BASE + index - 1
        if seed is not None:
            perturb_op(model, schema, seed, recipe.sigma)
        try:
            evaluation.refresh()
            for chunk in chunks:
                if not warm:                                           # one untimed pass of each, so that the first timed call is not a start-up
                    library_generate(evaluation.model, tokenizer, questions[:chunk], chunk)
                    compact_generate(evaluation.model, tokenizer, prompts[:chunk], MAX_NEW_TOKENS, args.drop_fraction)
                (reference, _), t_library = timed(lambda: library_generate(evaluation.model, tokenizer, questions, chunk))
                (texts, steps, slots), t_compact = timed(lambda: compact_all(chunk))
                different = [q for q, (a, b) in enumerate(zip(reference, texts)) if a != b]
                records.append({"seed": seed, "chunk": chunk, "library_seconds": t_library, "compact_seconds": t_compact, "steps": steps, "slot_steps": slots,
                                "different_questions": different, "texts_sha256": hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()})
                print(f"seed {seed} chunk {chunk}: library {t_library:.2f} s, compact {t_compact:.2f} s, steps {steps}, slots {slots}, different {len(different)}", flush=True)
            warm = True
        finally:
            if seed is not None:
                restore_from_snapshot_(model, schema, snapshot)
    Path(args.out).write_text(json.dumps({"format": 1, "environment": environment_info(device), "drop_fraction": args.drop_fraction, "records": records}, indent=1), encoding="utf-8")
    return 0 if all(not r["different_questions"] for r in records) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
