#!/usr/bin/env python3
"""
Cumulative control of the second learning experiment (preregistered, criterion P2): from a checkpoint of a run, `--steps` generations in which the recorded update is applied with its coefficients SHUFFLED
(same noise, same size, unrelated to the rewards), `--walks` independent shufflings; the training accuracy (and H1) is measured at the end of each walk and every `--every` steps. Compare with the real trajectory.
"""
import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import learnlib2 as l2  # noqa: E402
from heteroes.es.cuda_ops import apply_coefficients_cuda_  # noqa: E402
from heteroes.eval.precision import EvalModel  # noqa: E402
from heteroes.ledger import Ledger  # noqa: E402
from heteroes.model.loading import load_pinned_model  # noqa: E402
from heteroes.model.weights_io import load_weights_  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--run-dir", required=True)
parser.add_argument("--experiment-id", required=True)
parser.add_argument("--checkpoint", required=True)
parser.add_argument("--model-path", required=True)
parser.add_argument("--steps", type=int, default=20)
parser.add_argument("--every", type=int, default=10)
parser.add_argument("--walks", type=int, default=3)
parser.add_argument("--output", required=True)
args = parser.parse_args()
if Path(args.output).exists():
    sys.exit(f"{args.output} exists")
path = Path(args.checkpoint)
start, sha = int(path.stem[1:].split("-")[0]), path.stem.split("-")[1]
ledger = Ledger(Path(args.run_dir) / "coordinator/ledger.sqlite", enforce_chain=True)
loaded = load_pinned_model(args.model_path, "cuda")
ev = EvalModel(loaded.model, "float32")
train, h1 = l2.train_questions(), l2.heldout_sets()["H1"]
result = {"start_checkpoint": start, "steps": args.steps, "walks": {}}
for walk in range(args.walks):
    load_weights_(loaded.model, loaded.schema, path, sha)
    rows = {}
    for step in range(args.steps + 1):
        if step % args.every == 0 or step == args.steps:
            ev.refresh()
            with l2.token_limit(l2.TRAIN_TOKEN_LIMIT):
                t = l2.summarize(l2.evaluate_questions(ev.model, loaded.tokenizer, train, chunk=len(train)))
            with l2.token_limit(l2.HELDOUT_TOKEN_LIMIT):
                h = l2.summarize(l2.evaluate_questions(ev.model, loaded.tokenizer, h1, chunk=len(h1)))
            rows[step] = {"train": t, "H1": h}
            print(f"[{time.strftime('%H:%M:%S')}] walk {walk} step {step}: train {t['accuracy'] * 100:.1f}% H1 {h['accuracy'] * 100:.1f}%", flush=True)
        if step == args.steps:
            break
        record = ledger.get_update(args.experiment_id, start + step).record
        coefficients = list(record.coefficients)
        random.Random(1000 * (walk + 1) + step).shuffle(coefficients)
        apply_coefficients_cuda_(loaded.model, loaded.schema, list(record.seeds), coefficients, record.alpha)
    result["walks"][walk] = rows
l2.dump(args.output, result)
