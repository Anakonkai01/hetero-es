#!/usr/bin/env python3
"""
The compacting greedy decoder on OTHER models and OTHER tasks (an EXPERIMENT, not package code; the first version, for Qwen2.5-0.5B and the project's workload, is `compact_decode.py`).

    python compact_general.py --model-path <dir> --task gsm8k|countdown|sudoku4|arith --count 128 --max-new-tokens 512 --chunks 64,128 --candidates 2 --out result.json
        [--dtype float32|float16|bfloat16] [--gsm8k-file test.jsonl] [--thinking]

Differences from `compact_decode.py`: any decoder-only model of the library (the model is loaded with `AutoModelForCausalLM`); the logits processors are the ones the library itself builds from the
model's generation config for greedy decoding (not only the repetition penalty); the end tokens and the padding token fall back to the tokenizer's; the key/value cache is cut with
`batch_select_indices`, and if the cache of a model does not support that, the decoder says so and goes on WITHOUT removing rows (still correct, no speed-up).
"Candidates" here are only a way to get other texts: the weights get a small Gaussian noise (sigma 1e-3, a torch generator seeded 7001, ...), which is NOT the project's canonical noise
engine, and are restored afterwards from a copy. For every condition and chunk: the library's `generate()` is the reference, and the record says how many texts differ.
The output file must not exist.
"""
import argparse
import copy
import hashlib
import json
import random
import statistics
import sys
import time
from pathlib import Path

SYSTEM = "Solve the problem step by step. End your reply with a line 'Answer: <answer>'."


def questions_for(task, count, seed, gsm8k_file):
    rng = random.Random(seed)
    if task == "arith":
        out = []
        for _ in range(count):
            a, b, op = rng.randint(11, 99), rng.randint(11, 99), rng.choice("+-*")
            out.append(f"What is {a} {op} {b}?")
        return out
    if task == "gsm8k":
        lines = [json.loads(line)["question"] for line in Path(gsm8k_file).read_text(encoding="utf-8").splitlines() if line.strip()]
        rng.shuffle(lines)
        return lines[:count]
    if task == "countdown":
        out = []
        for _ in range(count):
            numbers = [rng.randint(1, 50) for _ in range(rng.choice([3, 4]))]
            value, pool = numbers[0], numbers[1:]
            for n in pool:                                                  # a target that IS reachable, built by a random left-to-right expression
                value = rng.choice([value + n, value * n if value * n < 1000 else value + n, abs(value - n)])
            out.append(f"Using the numbers {numbers}, create an equation that equals {value}. You can use + - * / and each number at most once. Show your reasoning.")
        return out
    if task == "sudoku4":
        out = []
        for _ in range(count):
            base = [[(r * 2 + r // 2 + c) % 4 + 1 for c in range(4)] for r in range(4)]          # a valid 4x4 grid, then shuffled rows/columns inside the bands
            top, bottom = [0, 1], [2, 3]
            rng.shuffle(top)
            rng.shuffle(bottom)
            grid = [base[r] for r in top + bottom]
            perm = [1, 2, 3, 4]; rng.shuffle(perm)
            grid = [[perm[v - 1] for v in row] for row in grid]
            puzzle = [[v if rng.random() > 0.5 else 0 for v in row] for row in grid]
            text = "\n".join(" ".join(str(v) for v in row) for row in puzzle)
            out.append(f"Solve this 4x4 Sudoku (0 is an empty cell; each row, column and 2x2 box holds 1 to 4 once):\n{text}")
        return out
    raise ValueError(f"unknown task {task}")


def compact_generate(model, tokenizer, prompts, processors, eos_ids, pad, max_new_tokens, drop_fraction):
    """Greedy answers with finished rows dropped from the batch. Returns (texts, counters)."""
    import torch

    device = next(model.parameters()).device
    eos_t = torch.tensor(eos_ids, device=device)
    previous = tokenizer.padding_side
    tokenizer.padding_side = "left"
    try:
        inputs = tokenizer(prompts, return_tensors="pt", padding=True)
    finally:
        tokenizer.padding_side = previous
    ids, mask = inputs["input_ids"].to(device), inputs["attention_mask"].to(device)
    total = ids.shape[0]
    position = (mask.long().cumsum(-1) - 1).masked_fill(mask == 0, 0)
    out = torch.full((total, max_new_tokens), pad, dtype=torch.long, device=device)
    rows = torch.arange(total, device=device)
    counters = {"steps": 0, "slot_steps": 0, "compactions": 0, "compaction_supported": True}
    with torch.no_grad():
        result = model(input_ids=ids, attention_mask=mask, position_ids=position, use_cache=True, logits_to_keep=1)      # like generate(): only the last position's logits
        cache = result.past_key_values
        scores = result.logits[:, -1].to(dtype=torch.float32)
        all_ids, last_position = ids, position[:, -1]
        finished = torch.zeros(total, dtype=torch.bool, device=device)
        for step in range(max_new_tokens):
            counters["steps"] += 1
            counters["slot_steps"] += int(rows.shape[0])
            scores = processors(all_ids, scores)
            next_tokens = torch.argmax(scores, dim=-1)
            next_tokens = torch.where(finished, torch.full_like(next_tokens, pad), next_tokens)
            out[rows, step] = next_tokens
            finished = finished | torch.isin(next_tokens, eos_t)
            if step == max_new_tokens - 1 or bool(finished.all()):
                break
            if counters["compaction_supported"] and finished.any() and (int(finished.sum()) >= max(1, drop_fraction * rows.shape[0])):
                keep = torch.nonzero(~finished).squeeze(1)
                try:
                    cache.batch_select_indices(keep)
                except Exception as error:                                  # noqa: BLE001 - a cache without row selection: go on without removing rows
                    counters["compaction_supported"] = False
                    counters["compaction_error"] = f"{type(error).__name__}: {str(error)[:120]}"
                else:
                    rows, mask, all_ids, last_position = rows[keep], mask[keep], all_ids[keep], last_position[keep]
                    next_tokens = next_tokens[keep]
                    finished = torch.zeros(rows.shape[0], dtype=torch.bool, device=device)
                    counters["compactions"] += 1
            all_ids = torch.cat([all_ids, next_tokens[:, None]], dim=-1)
            mask = torch.cat([mask, mask.new_ones((mask.shape[0], 1))], dim=-1)
            last_position = last_position + 1
            result = model(input_ids=next_tokens[:, None], attention_mask=mask, position_ids=last_position[:, None], past_key_values=cache, use_cache=True)
            cache = result.past_key_values
            scores = result.logits[:, -1].to(dtype=torch.float32)
    texts = [t.strip() for t in tokenizer.batch_decode(out, skip_special_tokens=True)]
    lengths = [int((row != pad).sum()) for row in out]
    return texts, counters, lengths


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--task", required=True, choices=["arith", "gsm8k", "countdown", "sudoku4"])
    parser.add_argument("--count", type=int, default=128)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--chunks", default="64,128")
    parser.add_argument("--candidates", type=int, default=2)
    parser.add_argument("--dtype", default="float32", choices=["float32", "float16", "bfloat16"])
    parser.add_argument("--drop-fraction", type=float, default=0.1)
    parser.add_argument("--gsm8k-file", default=None)
    parser.add_argument("--thinking", action="store_true", help="models with a thinking switch in the chat template (Qwen3): leave thinking ON (default OFF)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if Path(args.out).exists():
        print(f"error: {args.out} already exists; evidence is never overwritten", file=sys.stderr)
        return 2
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    dtype = getattr(torch, args.dtype)
    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    model = AutoModelForCausalLM.from_pretrained(args.model_path, dtype=dtype).to("cuda").eval()
    gen = copy.deepcopy(model.generation_config)
    gen.do_sample = False
    gen.max_new_tokens = args.max_new_tokens
    pad = gen.pad_token_id if gen.pad_token_id is not None else (tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id)
    eos = gen.eos_token_id if gen.eos_token_id is not None else tokenizer.eos_token_id
    eos_ids = list(eos) if isinstance(eos, (list, tuple)) else [eos]
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    processors = model._get_logits_processor(gen, 1, None, None, [])
    processor_names = [type(p).__name__ for p in processors]

    raw = questions_for(args.task, args.count, 20261009, args.gsm8k_file)
    kwargs = {} if args.thinking else {"enable_thinking": False}
    messages = lambda q: [{"role": "system", "content": SYSTEM}, {"role": "user", "content": q}]            # noqa: E731
    try:
        prompts = [tokenizer.apply_chat_template(messages(q), tokenize=False, add_generation_prompt=True, **kwargs) for q in raw]
    except Exception:                                                        # noqa: BLE001 - a template without a system role
        prompts = [tokenizer.apply_chat_template([{"role": "user", "content": SYSTEM + "\n\n" + q}], tokenize=False, add_generation_prompt=True, **kwargs) for q in raw]
    chunks = [int(c) for c in args.chunks.split(",")]

    def library(chunk):
        texts, steps, slots = [], 0, 0
        previous = tokenizer.padding_side
        tokenizer.padding_side = "left"
        try:
            for start in range(0, len(prompts), chunk):
                inputs = tokenizer(prompts[start:start + chunk], return_tensors="pt", padding=True).to("cuda")
                with torch.no_grad():
                    ids = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False, pad_token_id=pad)
                new = ids[:, inputs["input_ids"].shape[1]:]
                steps += new.shape[1]
                slots += new.shape[1] * new.shape[0]
                texts += [t.strip() for t in tokenizer.batch_decode(new, skip_special_tokens=True)]
        finally:
            tokenizer.padding_side = previous
        return texts, steps, slots

    def compact(chunk):
        texts, steps, slots, lengths, supported = [], 0, 0, [], True
        for start in range(0, len(prompts), chunk):
            part, counters, lens = compact_generate(model, tokenizer, prompts[start:start + chunk], processors, eos_ids, pad, args.max_new_tokens, args.drop_fraction)
            texts += part
            steps += counters["steps"]
            slots += counters["slot_steps"]
            lengths += lens
            supported = supported and counters["compaction_supported"]
        return texts, steps, slots, lengths, supported

    def timed(function):
        torch.cuda.synchronize()
        start = time.perf_counter()
        value = function()
        torch.cuda.synchronize()
        return value, time.perf_counter() - start

    with torch.no_grad():                                                    # an untimed warm-up of both paths, so that the first timed call is not a start-up
        warm = tokenizer(prompts[:8], return_tensors="pt", padding=True).to("cuda")
        model.generate(**warm, max_new_tokens=16, do_sample=False, pad_token_id=pad)
        compact_generate(model, tokenizer, prompts[:8], processors, eos_ids, pad, 16, args.drop_fraction)
    original = {name: p.detach().cpu().clone() for name, p in model.named_parameters()}      # on the CPU: a second copy of the weights on the GPU is memory a big cache needs
    records = []
    for index in range(args.candidates + 1):
        seed = None if index == 0 else 7000 + index
        if seed is not None:
            generator = torch.Generator(device="cpu").manual_seed(seed)
            with torch.no_grad():
                for p in model.parameters():
                    p.add_((torch.randn(p.shape, generator=generator, dtype=torch.float32) * 1e-3).to(device=p.device, dtype=p.dtype))
        try:
            for chunk in chunks:
                (ref, lib_steps, lib_slots), t_lib = timed(lambda: library(chunk))
                (txt, steps, slots, lengths, supported), t_cmp = timed(lambda: compact(chunk))
                different = [q for q, (a, b) in enumerate(zip(ref, txt)) if a != b]
                records.append({"seed": seed, "chunk": chunk, "library_seconds": t_lib, "compact_seconds": t_cmp, "library_slots": lib_slots, "compact_slots": slots,
                                "answer_tokens_mean": statistics.mean(lengths), "answer_tokens_max": max(lengths), "answers_at_limit": sum(l >= args.max_new_tokens for l in lengths),
                                "compaction_supported": supported, "different_questions": different, "texts_sha256": hashlib.sha256("\n".join(txt).encode("utf-8")).hexdigest()})
                print(f"seed {seed} chunk {chunk}: library {t_lib:.1f} s, compact {t_cmp:.1f} s, slots {lib_slots} -> {slots}, mean answer {statistics.mean(lengths):.0f} tokens, "
                      f"at limit {records[-1]['answers_at_limit']}, different {len(different)}, compaction {'on' if supported else 'NOT SUPPORTED'}", flush=True)
        finally:
            if seed is not None:
                with torch.no_grad():
                    for name, p in model.named_parameters():
                        p.copy_(original[name])
    Path(args.out).write_text(json.dumps({"format": 1, "model": args.model_path, "task": args.task, "dtype": args.dtype, "max_new_tokens": args.max_new_tokens,
                                          "processors": processor_names, "eos_ids": eos_ids, "pad": pad, "gpu": torch.cuda.get_device_name(0), "torch": torch.__version__,
                                          "drop_fraction": args.drop_fraction, "records": records}, indent=1), encoding="utf-8")
    return 0 if all(not r["different_questions"] for r in records) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
