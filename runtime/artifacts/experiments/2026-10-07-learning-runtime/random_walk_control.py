#!/usr/bin/env python3
"""
EXPLORATORY (not in PREREGISTRATION.md, written after run A was analysed): is the drift of the held-out accuracy after the training accuracy saturated (generation ~30)
caused by what the update learned, or would any step of the same size do it? From a checkpoint of a run it walks `--steps` generations, but at each one it applies the recorded
update with its coefficients SHUFFLED (same noise directions, same size, unrelated to the rewards), and measures the held-out sets every `--every` steps. Compare with the real
trajectory (the checkpoints of the same generations). Run with the heteroes-match python and PYTHONPATH=src.
"""
import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import learnlib  # noqa: E402
from heteroes.es.cuda_ops import apply_coefficients_cuda_  # noqa: E402
from heteroes.eval.precision import EvalModel  # noqa: E402
from heteroes.ledger import Ledger  # noqa: E402
from heteroes.model.loading import load_pinned_model  # noqa: E402
from heteroes.model.weights_io import load_weights_  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--run-dir", required=True)
parser.add_argument("--experiment-id", required=True)
parser.add_argument("--checkpoint", required=True, help="path of a g<NNN>-<sha>.bin checkpoint")
parser.add_argument("--model-path", required=True)
parser.add_argument("--steps", type=int, default=50)
parser.add_argument("--every", type=int, default=10)
parser.add_argument("--walks", type=int, default=2, help="independent shufflings")
parser.add_argument("--output", required=True)
args = parser.parse_args()
if Path(args.output).exists():
    sys.exit(f"{args.output} exists")
path = Path(args.checkpoint)
start, sha = int(path.stem[1:].split("-")[0]), path.stem.split("-")[1]
ledger = Ledger(Path(args.run_dir) / "coordinator/ledger.sqlite", enforce_chain=True)
loaded = load_pinned_model(args.model_path, "cuda")
ev = EvalModel(loaded.model, "float32")
sets = {"train": learnlib.train_questions(), **learnlib.heldout_sets()}
result = {"start_checkpoint": start, "steps": args.steps, "walks": {}}
for walk in range(args.walks):
    load_weights_(loaded.model, loaded.schema, path, sha)
    rows = {}
    for step in range(0, args.steps + 1):
        if step % args.every == 0:
            ev.refresh()
            rows[step] = {name: learnlib.summarize(learnlib.evaluate_questions(ev.model, loaded.tokenizer, qa)) for name, qa in sets.items()}
            print(f"[{time.strftime('%H:%M:%S')}] walk {walk} step {step}: " + " ".join(f"{k}={v['correct']}/{v['n']}" for k, v in rows[step].items()), flush=True)
        if step == args.steps:
            break
        record = ledger.get_update(args.experiment_id, start + step).record
        coefficients = list(record.coefficients)
        random.Random(1000 * (walk + 1) + step).shuffle(coefficients)
        apply_coefficients_cuda_(loaded.model, loaded.schema, list(record.seeds), coefficients, record.alpha)
    result["walks"][walk] = rows
learnlib.dump(args.output, result)
