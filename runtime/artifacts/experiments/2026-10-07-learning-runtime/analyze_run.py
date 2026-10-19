#!/usr/bin/env python3
"""
Offline analysis of one learning run (experiment code). Needs the run directory (ledger with the update records), the checkpoints kept by the run and the base model.

For every checkpoint (generation 0, 5, 10, ...) it loads the weights, then REPLAYS the recorded updates of the next generations to rebuild every parent in between, and
checks that the replay ends on the weights hash of the next checkpoint (the replay is verified, not assumed). Per generation g it measures on the training questions the
parent, parent+ (= the next parent) and the CONTROL parent- (same parent, same candidates, same noise, update with -alpha); every `--heldout-every` generations it also
measures the held-out sets for parent+, parent- and a second control (the coefficients shuffled). Every checkpoint is measured on the training and the held-out sets.
Output: a JSON file and a text summary with the verdict of PREREGISTRATION.md. Run with the heteroes-match python and PYTHONPATH=src.
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import learnlib  # noqa: E402
from heteroes.es.cuda_ops import apply_coefficients_cuda_  # noqa: E402
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot  # noqa: E402
from heteroes.eval.candidate import tensors_sha256  # noqa: E402
from heteroes.eval.precision import EvalModel  # noqa: E402
from heteroes.ledger import Ledger  # noqa: E402
from heteroes.model.loading import load_pinned_model  # noqa: E402
from heteroes.model.weights_io import load_weights_  # noqa: E402


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main(argv) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--ckpt-dir", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--output", required=True, help="JSON file to create (must not exist)")
    parser.add_argument("--heldout-every", type=int, default=10)
    parser.add_argument("--max-generation", type=int, default=None, help="analyse only the first generations (default: every checkpoint there is)")
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.exists():
        print(f"error: {output} exists; evidence is never overwritten", file=sys.stderr)
        return 2

    ckpts = {}
    for path in sorted(Path(args.ckpt_dir).glob("g*-*.bin")):
        generation, sha = path.stem[1:].split("-")
        ckpts[int(generation)] = (sha, path)
    if 0 not in ckpts:
        print("error: no checkpoint of generation 0", file=sys.stderr)
        return 2
    last = max(ckpts) if args.max_generation is None else max(g for g in ckpts if g <= args.max_generation)
    boundaries = [g for g in sorted(ckpts) if g <= last]
    ledger = Ledger(Path(args.run_dir) / "coordinator/ledger.sqlite", enforce_chain=True)

    loaded = load_pinned_model(args.model_path, "cuda")
    model, tokenizer, schema = loaded.model, loaded.tokenizer, loaded.schema
    ev = EvalModel(model, "float32")
    train, heldout = learnlib.train_questions(), learnlib.heldout_sets()

    def measure(sets: tuple[str, ...]) -> dict:
        ev.refresh()
        out = {}
        for name in sets:
            qa = train if name == "train" else heldout[name]
            out[name] = learnlib.summarize(learnlib.evaluate_questions(ev.model, tokenizer, qa))
        return out

    def load(generation: int) -> None:
        sha, path = ckpts[generation]
        load_weights_(model, schema, path, sha)

    SETS = ("train", "H3", "H1", "H2")
    result = {"experiment_id": args.experiment_id, "checkpoint_generations": boundaries, "last_generation": last, "ckpt_dir": args.ckpt_dir,
              "checkpoints": {}, "generations": {}, "controls": {}, "replay": {}}
    for index, start in enumerate(boundaries):
        load(start)
        if start not in result["checkpoints"]:
            result["checkpoints"][start] = measure(SETS)
            log(f"checkpoint {start}: " + " ".join(f"{k}={v['correct']}/{v['n']}" for k, v in result["checkpoints"][start].items()))
        if index + 1 == len(boundaries):
            break
        end = boundaries[index + 1]
        for g in range(start, end):
            stored = ledger.get_update(args.experiment_id, g)
            if stored is None:
                raise SystemExit(f"the ledger has no update record for generation {g}")
            record = stored.record
            seeds, coefficients, alpha = list(record.seeds), list(record.coefficients), record.alpha
            parent_train = result["checkpoints"][start]["train"] if g == start else result["generations"][g]["train_parent"]
            snapshot = take_snapshot(model, schema)
            with_heldout = g % args.heldout_every == 0
            sets = SETS if with_heldout else ("train",)
            apply_coefficients_cuda_(model, schema, seeds, coefficients, -alpha)
            minus = measure(sets)
            restore_from_snapshot_(model, schema, snapshot)
            if with_heldout:
                shuffled_coefficients = coefficients[:]
                random.Random(g).shuffle(shuffled_coefficients)
                apply_coefficients_cuda_(model, schema, seeds, shuffled_coefficients, alpha)
                shuffled = measure(sets)
                restore_from_snapshot_(model, schema, snapshot)
            apply_coefficients_cuda_(model, schema, seeds, coefficients, alpha)
            plus_sets = SETS if (with_heldout or g + 1 == end) else ("train",)
            plus = measure(plus_sets)
            entry = {"train_parent": parent_train, "train_plus": plus["train"], "train_minus": minus["train"],
                     "diff": plus["train"]["accuracy"] - minus["train"]["accuracy"],
                     "candidate_rewards": list(record.rewards), "candidate_mean": sum(record.rewards) / len(record.rewards),
                     "recorded_child": stored.child_weights_sha256}
            result["generations"][g] = entry
            if g + 1 < end or True:
                result["generations"].setdefault(g + 1, {})["train_parent"] = plus["train"]
            if with_heldout:
                result["controls"][g] = {"plus": plus, "minus": minus, "shuffled": shuffled}
            log(f"g{g}: parent {parent_train['correct']} plus {plus['train']['correct']} minus {minus['train']['correct']} diff {entry['diff']:+.3f}")
        actual = tensors_sha256(take_snapshot(model, schema).tensors)
        result["replay"][end] = {"expected": ckpts[end][0], "actual": actual, "match": actual == ckpts[end][0]}
        log(f"replay {start}->{end}: {'MATCH' if actual == ckpts[end][0] else 'MISMATCH'}")

    gens = [g for g in range(last) if g in result["generations"] and "diff" in result["generations"][g]]
    diffs = [result["generations"][g]["diff"] for g in gens]
    positive = learnlib.count_positive(diffs)
    negative = sum(1 for d in diffs if d < 0)
    result["s2"] = {"generations": len(gens), "positive": positive, "negative": negative, "ties": len(gens) - positive - negative,
                    "mean_diff": sum(diffs) / len(diffs) if diffs else None, "sign_test_p": learnlib.sign_test_p(positive, negative)}
    held = sorted(result["controls"])
    result["s2_heldout_h3"] = {"generations": held, "positive": sum(1 for g in held if result["controls"][g]["plus"]["H3"]["accuracy"] > result["controls"][g]["minus"]["H3"]["accuracy"]),
                               "negative": sum(1 for g in held if result["controls"][g]["plus"]["H3"]["accuracy"] < result["controls"][g]["minus"]["H3"]["accuracy"])}
    base, final = result["checkpoints"][0], result["checkpoints"][last]
    result["verdict"] = learnlib.verdict(base, final, positive, result["s2"]["mean_diff"] or 0.0, len(gens))
    result["verdict"]["note"] = "complete run" if last >= 100 else f"INCOMPLETE: analysed {last} generations; the thresholds of S2 scale with the generations analysed"
    learnlib.dump(output, result)
    log(f"wrote {output}: {result['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
