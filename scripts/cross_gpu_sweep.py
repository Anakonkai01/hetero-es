#!/usr/bin/env python3
"""
Find out how often, and why, the same candidate gives a different answer on two GPUs (the open finding of G4/G5: candidate 21 of
generation 0 scored 0.25 on the 5070 Ti and 0.1875 on the 1660S).

    # on each machine, with the same seeds (and, to be a clean comparison, the same torch / CUDA / transformers):
    python scripts/cross_gpu_sweep.py run --model-path <snapshot dir> --worker-id worker-5070ti --seeds 0:240 --out sweep-5070ti.jsonl
    # then anywhere:
    python scripts/cross_gpu_sweep.py compare sweep-5070ti.jsonl sweep-1660s.jsonl --out comparison.json
    # on one machine: do padding and the tokenization path change the answers at all?
    python scripts/cross_gpu_sweep.py ladder --model-path <snapshot dir> --seeds 0:8 --out ladder.json

`run` perturbs the model with each seed (sigma 1e-3, the contract perturbation), answers the 16 prompts one at a time (the reference
path) and records, per prompt, the answer text, its token ids and the margin between the two best scores at every step. `compare`
joins two such files by seed and prompt and, for every prompt whose answer differs, says at which step the two answers diverge
and how close the decision was there on each GPU: a flip at a margin below the FP16 rounding noise is the expected kind; a flip at a
large margin would be a bug. The output file of every mode must not exist (evidence is never overwritten).
"""
import argparse
import copy
import json
import statistics
import sys
import time
from pathlib import Path


def fail(message: str, code: int = 2) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(code)


def parse_seeds(text: str) -> list[int]:
    start, _, stop = text.partition(":")
    if not start.isdigit() or not stop.isdigit() or int(stop) <= int(start):
        fail(f"--seeds must be START:STOP with START < STOP, got {text!r}")
    return list(range(int(start), int(stop)))


def load(model_path, device):
    from heteroes.es.perturb import perturb_model_
    from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
    from heteroes.model.loading import load_pinned_model

    loaded = load_pinned_model(model_path, device)
    snapshot = take_snapshot(loaded.model, loaded.schema)
    return loaded, snapshot, perturb_model_, restore_from_snapshot_


def cmd_run(args) -> int:
    import contextlib

    import torch

    from heteroes.eval.diagnostics import fp32_lm_head

    from heteroes.eval.diagnostics import generate_with_trace
    from heteroes.eval.generate import generate_answer
    from heteroes.eval.workload import EXAMPLES, exact_match_reward, extract_integer
    from heteroes.runtime_info import code_info, environment_info

    if Path(args.out).exists():
        fail(f"{args.out} already exists; evidence is never overwritten")
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    loaded, snapshot, perturb, restore = load(args.model_path, device)
    model, tokenizer, schema = loaded.model, loaded.tokenizer, loaded.schema
    questions = [example.question for example in EXAMPLES]
    # the trace path must give the texts of the production path, or the sweep would measure something else
    production = [generate_answer(model, tokenizer, question) for question in questions]
    traced = [generate_with_trace(model, tokenizer, [question])[0]["text"] for question in questions]
    if production != traced and not (args.fp32_logits or args.fp32_model):
        fail("the traced answers differ from generate_answer on the base weights: the sweep would not measure the workload", 3)
    seeds = parse_seeds(args.seeds)
    with open(args.out, "x", encoding="utf-8") as file:
        file.write(json.dumps({"kind": "header", "worker_id": args.worker_id, "environment": environment_info(device), "code": code_info(),
                               "sigma": args.sigma, "fp32_logits": args.fp32_logits, "fp32_model": args.fp32_model, "seeds": [seeds[0], seeds[-1] + 1], "t": time.time()}) + "\n")
        started = time.perf_counter()
        for done, seed in enumerate(seeds, 1):
            perturb(model, schema, seed, args.sigma)
            try:
                evaluated = copy.deepcopy(model).float() if args.fp32_model else model       # EXPERIMENT: the forward pass in float32
                with (fp32_lm_head(evaluated) if args.fp32_logits else contextlib.nullcontext()):
                    traces = [generate_with_trace(evaluated, tokenizer, [question])[0] for question in questions]
                del evaluated
            finally:
                restore(model, schema, snapshot)
            rewards = [exact_match_reward(extract_integer(trace["text"]), example.answer) for trace, example in zip(traces, EXAMPLES)]
            file.write(json.dumps({"kind": "candidate", "seed": seed, "reward": sum(rewards) / len(rewards), "rewards": rewards,
                                   "prompts": traces}) + "\n")
            file.flush()
            if done % 10 == 0:
                print(f"{done}/{len(seeds)} candidates, {time.perf_counter() - started:.0f} s", flush=True)
    return 0


def read_sweep(path: str):
    lines = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    header = lines[0]
    return header, {line["seed"]: line for line in lines[1:] if line["kind"] == "candidate"}


def compare_sweeps(a: dict, b: dict) -> dict:
    """Pure: join two {seed: candidate} dicts. The unit of replication is the candidate (its 16 prompts are one draw of one noise)."""
    from heteroes.eval.diagnostics import summarize_pair

    seeds = sorted(set(a) & set(b))
    differing, reward_differs = [], 0
    min_margins = []
    for seed in seeds:
        if a[seed]["reward"] != b[seed]["reward"]:
            reward_differs += 1
        for index, (pa, pb) in enumerate(zip(a[seed]["prompts"], b[seed]["prompts"])):
            summary = summarize_pair(pa, pb)
            if summary["differs"]:
                differing.append({"seed": seed, "prompt": index, **summary, "reward_a": a[seed]["reward"], "reward_b": b[seed]["reward"]})
            finite = [m for m in pa["margins"] if m is not None and m != float("inf")]
            if finite:
                min_margins.append(min(finite))
    candidates_with_difference = len({entry["seed"] for entry in differing})
    margins_at_flip = [min(m for m in (entry["margin_a"], entry["margin_b"]) if m is not None) for entry in differing
                       if entry["margin_a"] is not None or entry["margin_b"] is not None]
    return {"candidates_compared": len(seeds), "prompts_compared": 16 * len(seeds),
            "candidates_with_a_different_answer": candidates_with_difference,
            "candidates_with_a_different_reward": reward_differs, "prompts_with_a_different_answer": len(differing),
            "rate_candidates_with_difference": candidates_with_difference / len(seeds) if seeds else None,
            "rate_prompts_with_difference": len(differing) / (16 * len(seeds)) if seeds else None,
            "margin_at_flip": {"median": statistics.median(margins_at_flip) if margins_at_flip else None,
                               "max": max(margins_at_flip) if margins_at_flip else None},
            "median_of_the_smallest_margin_per_prompt": statistics.median(min_margins) if min_margins else None,
            "differences": differing}


def cmd_compare(args) -> int:
    if Path(args.out).exists():
        fail(f"{args.out} already exists; evidence is never overwritten")
    header_a, a = read_sweep(args.a)
    header_b, b = read_sweep(args.b)
    result = compare_sweeps(a, b)
    keys = ("torch", "torch_cuda", "transformers", "numpy", "gpu_name", "gpu_capability")
    result["a"] = {"worker_id": header_a["worker_id"], **{k: header_a["environment"].get(k) for k in keys}}
    result["b"] = {"worker_id": header_b["worker_id"], **{k: header_b["environment"].get(k) for k in keys}}
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "differences"}, indent=1))
    return 0


def cmd_ladder(args) -> int:
    import torch

    import contextlib

    from heteroes.eval.diagnostics import fp32_lm_head, generate_with_trace, summarize_pair
    from heteroes.eval.workload import EXAMPLES

    if Path(args.out).exists():
        fail(f"{args.out} already exists; evidence is never overwritten")
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    loaded, snapshot, perturb, restore = load(args.model_path, device)
    model, tokenizer, schema = loaded.model, loaded.tokenizer, loaded.schema
    questions = [example.question for example in EXAMPLES]

    def variants():
        single = [generate_with_trace(current['model'], tokenizer, [q])[0] for q in questions]
        yield "single_prompt (reference)", single
        yield "batch_of_one_with_padding_enabled", [generate_with_trace(current['model'], tokenizer, [q], pad=True)[0] for q in questions]
        yield "batch_of_all_16_left_padded", generate_with_trace(current['model'], tokenizer, questions)
        pairs = []
        for start in range(0, len(questions), 2):
            pairs += generate_with_trace(current['model'], tokenizer, questions[start:start + 2])
        yield "batches_of_two_left_padded", pairs

    current = {'model': model}
    report = {}
    for label, seed in [("parent weights", None)] + [(f"seed {s}", s) for s in parse_seeds(args.seeds)]:
        if seed is not None:
            perturb(model, schema, seed, args.sigma)
        try:
            reference, entry = None, {}
            if args.fp32_model:
                current['model'] = copy.deepcopy(model).float()       # EXPERIMENT: the whole forward pass in float32, from the FP16 weights
            with (fp32_lm_head(current['model']) if args.fp32_logits else contextlib.nullcontext()):
                for name, traces in variants():
                    if reference is None:
                        reference = traces
                        continue
                    pairs = [summarize_pair(r, t) for r, t in zip(reference, traces)]
                    entry[name] = {"prompts_with_a_different_answer": sum(p["differs"] for p in pairs),
                                   "margins_at_the_flip": [min(m for m in (p["margin_a"], p["margin_b"]) if m is not None)
                                                           for p in pairs if p["differs"] and (p["margin_a"] is not None or p["margin_b"] is not None)]}
            report[label] = entry
        finally:
            current['model'] = model
            if seed is not None:
                restore(model, schema, snapshot)
        print(label, {name: value["prompts_with_a_different_answer"] for name, value in entry.items()}, flush=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    run = sub.add_parser("run")
    run.add_argument("--model-path", required=True)
    run.add_argument("--worker-id", required=True)
    run.add_argument("--seeds", required=True, help="START:STOP")
    run.add_argument("--sigma", type=float, default=1e-3)
    run.add_argument("--out", required=True)
    run.add_argument("--device", choices=["cuda", "cpu"], default=None)
    run.add_argument("--fp32-logits", action="store_true", help="EXPERIMENT: compute the output scores in float32 (not the production evaluation)")
    run.add_argument("--fp32-model", action="store_true", help="EXPERIMENT: run the whole forward pass in float32 from the FP16 weights (not the production evaluation)")
    compare = sub.add_parser("compare")
    compare.add_argument("a")
    compare.add_argument("b")
    compare.add_argument("--out", required=True)
    ladder = sub.add_parser("ladder")
    ladder.add_argument("--model-path", required=True)
    ladder.add_argument("--seeds", default="0:4")
    ladder.add_argument("--sigma", type=float, default=1e-3)
    ladder.add_argument("--out", required=True)
    ladder.add_argument("--device", choices=["cuda", "cpu"], default=None)
    ladder.add_argument("--fp32-logits", action="store_true", help="EXPERIMENT: compute the output scores in float32 (not the production evaluation)")
    ladder.add_argument("--fp32-model", action="store_true", help="EXPERIMENT: run the whole forward pass in float32 from the FP16 weights (not the production evaluation)")
    args = parser.parse_args(argv)
    return {"run": cmd_run, "compare": cmd_compare, "ladder": cmd_ladder}[args.mode](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
