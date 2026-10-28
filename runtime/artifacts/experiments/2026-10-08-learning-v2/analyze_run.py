#!/usr/bin/env python3
"""
Offline analysis of a run of the second learning experiment (experiment code; same idea as `2026-10-07-learning-runtime/analyze_run.py`, other sets). From the kept checkpoints and the
ledger's update records it replays every generation (and checks the hash of the next checkpoint), and measures on the 128 training questions the parent, parent+ (the real step) and the control
parent- (the same step with -alpha) for every generation, and every `--heldout-every` generations also the shuffled-coefficient control on train and H1; at every checkpoint it measures train, H1, V1 (the validation set that
chooses the checkpoint), H2 and H3 (held-out sets are evaluated with a token limit of 512, the training questions with the workload's 256).
Usage (heteroes-match python, PYTHONPATH=src):  analyze_run.py --run-dir <run> --experiment-id <id> --ckpt-dir <dir> --model-path <snapshot> --output <new json>
"""
import argparse
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import learnlib2 as l2  # noqa: E402
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
    parser.add_argument("--output", required=True)
    parser.add_argument("--heldout-every", type=int, default=5)
    parser.add_argument("--max-generation", type=int, default=None)
    args = parser.parse_args(argv)
    if Path(args.output).exists():
        print(f"error: {args.output} exists", file=sys.stderr)
        return 2
    ckpts = {}
    for path in sorted(Path(args.ckpt_dir).glob("g*-*.bin")):
        generation, sha = path.stem[1:].split("-")
        ckpts[int(generation)] = (sha, path)
    last = max(ckpts) if args.max_generation is None else max(g for g in ckpts if g <= args.max_generation)
    boundaries = [g for g in sorted(ckpts) if g <= last]
    ledger = Ledger(Path(args.run_dir) / "coordinator/ledger.sqlite", enforce_chain=True)
    loaded = load_pinned_model(args.model_path, "cuda")
    model, tokenizer, schema = loaded.model, loaded.tokenizer, loaded.schema
    ev = EvalModel(model, "float32")
    train, heldout = l2.train_questions(), l2.heldout_sets()

    def measure(names: tuple[str, ...]) -> dict:
        ev.refresh()
        out = {}
        for name in names:
            if name == "train":
                with l2.token_limit(l2.TRAIN_TOKEN_LIMIT):
                    out[name] = l2.summarize(l2.evaluate_questions(ev.model, tokenizer, train, chunk=len(train)))
            else:
                with l2.token_limit(l2.HELDOUT_TOKEN_LIMIT):
                    out[name] = l2.summarize(l2.evaluate_questions(ev.model, tokenizer, heldout[name], chunk=len(heldout[name])))
        return out

    ALL = ("train", "H1", "V1", "H2", "H3")
    SMALL = ("train", "H1")
    result = {"experiment_id": args.experiment_id, "checkpoint_generations": boundaries, "last_generation": last, "checkpoints": {}, "generations": {}, "controls": {}, "replay": {}}
    for index, start in enumerate(boundaries):
        sha, path = ckpts[start]
        load_weights_(model, schema, path, sha)
        if start not in result["checkpoints"]:
            result["checkpoints"][start] = measure(ALL)
            log(f"checkpoint {start}: " + " ".join(f"{k}={v['accuracy'] * 100:.1f}%" for k, v in result["checkpoints"][start].items()))
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
            with_controls = g % args.heldout_every == 0
            apply_coefficients_cuda_(model, schema, seeds, coefficients, -alpha)
            minus = measure(SMALL if with_controls else ("train",))
            restore_from_snapshot_(model, schema, snapshot)
            if with_controls:
                shuffled_coefficients = coefficients[:]
                random.Random(g).shuffle(shuffled_coefficients)
                apply_coefficients_cuda_(model, schema, seeds, shuffled_coefficients, alpha)
                shuffled = measure(SMALL)
                restore_from_snapshot_(model, schema, snapshot)
            apply_coefficients_cuda_(model, schema, seeds, coefficients, alpha)
            plus = measure(ALL if g + 1 == end else (SMALL if with_controls else ("train",)))
            entry = {"train_parent": parent_train, "train_plus": plus["train"], "train_minus": minus["train"], "diff": plus["train"]["accuracy"] - minus["train"]["accuracy"],
                     "candidate_rewards": list(record.rewards), "candidate_mean": sum(record.rewards) / len(record.rewards), "recorded_child": stored.child_weights_sha256}
            result["generations"][g] = entry
            result["generations"].setdefault(g + 1, {})["train_parent"] = plus["train"]
            if with_controls:
                result["controls"][g] = {"plus": plus, "minus": minus, "shuffled": shuffled}
            log(f"g{g}: parent {parent_train['correct']} plus {plus['train']['correct']} minus {minus['train']['correct']} of {parent_train['n']} diff {entry['diff']:+.3f}")
        actual = tensors_sha256(take_snapshot(model, schema).tensors)
        result["replay"][end] = {"expected": ckpts[end][0], "actual": actual, "match": actual == ckpts[end][0]}
        log(f"replay {start}->{end}: {'MATCH' if actual == ckpts[end][0] else 'MISMATCH'}")
    gens = [g for g in range(last) if "diff" in result["generations"].get(g, {})]
    diffs = [result["generations"][g]["diff"] for g in gens]
    pos, neg = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    result["s2"] = {"generations": len(gens), "positive": pos, "negative": neg, "ties": len(gens) - pos - neg, "mean_diff": sum(diffs) / len(diffs) if diffs else None, "sign_test_p": l2.sign_test_p(pos, neg)}
    l2.dump(args.output, result)
    log(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
