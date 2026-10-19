#!/usr/bin/env python3
"""
Record the answer TEXTS of one workload at one chunk on this GPU, for the parent weights and for perturbed candidates, so that
the texts of different GPUs can be compared (the chunk-128 study asks for the same text on every GPU, not only for the same text
as chunk 1 on the same GPU, which is all `profile_worker.py` stores).

    python scripts/chunk_text_record.py run --model-path <snapshot dir> --workload cot_l1_q128 --noise-engine cuda --chunk 128 \
        --candidates 8 --out chunk-texts-5070ti.json
    python scripts/chunk_text_record.py compare chunk-texts-5070ti.json chunk-texts-3060.json [...] --out comparison.json

The conditions are the ones of the profile: the parent, then seeds 7001, 7002, ... (sigma 1e-3). Per question the record keeps the
sha256 of the text and its length; the texts themselves are kept too (they are small) so a difference can be read. The output file
must not exist (evidence is never overwritten).
"""
import argparse
import contextlib
import hashlib
import json
import sys
import time
from pathlib import Path

PROFILE_SEED_BASE = 7001                 # the same seeds as scripts/profile_worker.py


def fail(message: str, code: int = 2) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(code)


def run(args) -> int:
    if Path(args.out).exists():
        fail(f"{args.out} already exists; evidence is never overwritten")
    import torch

    from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
    from heteroes.eval.precision import EvalModel
    from heteroes.model.loading import build_recipe, check_recipe_selftest, load_pinned_model
    from heteroes.profile_setup import noise_ops, profile_texts
    from heteroes.runtime_info import environment_info

    device = "cuda" if torch.cuda.is_available() else "cpu"
    loaded = load_pinned_model(args.model_path, device)
    model, tokenizer, schema = loaded.model, loaded.tokenizer, loaded.schema
    recipe = build_recipe(loaded, sigma=args.sigma, eval_dtype=args.eval_dtype, noise_engine=args.noise_engine, workload=args.workload, decode_engine=args.decode_engine)
    check_recipe_selftest(recipe, device)
    perturb_op, _ = noise_ops(recipe.engine_version, recipe.chunk_elements if args.noise_engine == "cpu" else None)
    evaluation = EvalModel(model, args.eval_dtype)
    evaluation.refresh()
    snapshot = take_snapshot(model, schema)

    def texts() -> list[str]:
        evaluation.refresh()
        return profile_texts(args.workload, evaluation.model, tokenizer, args.chunk, recipe.decode_engine)

    conditions = []
    for index in range(args.candidates + 1):                      # index 0 is the parent
        seed = None if index == 0 else PROFILE_SEED_BASE + index - 1
        start = time.perf_counter()
        if seed is not None:
            perturb_op(model, schema, seed, recipe.sigma)
        try:
            answers = texts()
        finally:
            if seed is not None:
                restore_from_snapshot_(model, schema, snapshot)
        conditions.append({"seed": seed, "seconds": time.perf_counter() - start, "texts": answers,
                           "sha256": [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in answers]})
        print(f"condition {index} done", flush=True)
    record = {"format": 1, "environment": environment_info(device), "workload": args.workload, "noise_engine": args.noise_engine,
              "eval_dtype": args.eval_dtype, "sigma": args.sigma, "chunk": args.chunk, "conditions": conditions}
    Path(args.out).write_text(json.dumps(record, indent=1), encoding="utf-8")
    return 0


def compare(args) -> int:
    if Path(args.out).exists():
        fail(f"{args.out} already exists; evidence is never overwritten")
    files = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.files]
    name = lambda record: (record["environment"].get("gpu_name") or "?")          # noqa: E731
    reference = files[0]
    report = {"reference_gpu": name(reference), "chunk": reference["chunk"], "against": []}
    all_equal = True
    for other in files[1:]:
        differing = []
        if (other["chunk"], other["workload"], other["noise_engine"]) != (reference["chunk"], reference["workload"], reference["noise_engine"]):
            fail("the files do not describe the same chunk, workload and engine")
        for a, b in zip(reference["conditions"], other["conditions"]):
            if a["seed"] != b["seed"]:
                fail("the seeds of the conditions differ")
            differing += [[a["seed"], question] for question, (x, y) in enumerate(zip(a["sha256"], b["sha256"])) if x != y]
        report["against"].append({"gpu": name(other), "conditions": len(other["conditions"]),
                                  "texts_compared": sum(len(c["sha256"]) for c in other["conditions"]), "differing": differing})
        all_equal = all_equal and not differing
    report["all_equal"] = all_equal
    Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items()}, indent=1))
    return 0 if all_equal else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("run")
    r.add_argument("--model-path", required=True)
    r.add_argument("--workload", default="cot_l1_q128")
    r.add_argument("--noise-engine", choices=["cpu", "cuda"], default="cuda")
    r.add_argument("--eval-dtype", choices=["float16", "float32"], default="float32")
    r.add_argument("--chunk", type=int, default=128)
    r.add_argument("--decode-engine", choices=["hf_generate", "hf_compact"], default=None, help="default: the compacting decoder on a long workload")
    r.add_argument("--candidates", type=int, default=8)
    r.add_argument("--sigma", type=float, default=1e-3)
    r.add_argument("--out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("files", nargs="+")
    c.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    return run(args) if args.mode == "run" else compare(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
