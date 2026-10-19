#!/usr/bin/env python3
"""
Is the gain of the learning runs only that the replies now finish before the 256-token limit? (experiment code, written after the runs.) Evaluate the base model and some checkpoints of
a run with the token limit of the workload (256) AND with a larger one (512), on H3 (new questions of the training family) and on the training questions, and report the accuracy, the
share of replies with an `Answer:` line and the mean reply length. If the base model gets much better with 512 tokens, then part of the gain of the runs at 256 was only "finish in time".
Usage: uncut_probe.py --ckpt-dir ~/.cache/heteroes/learn-ckpt/lrtA --generations 0 10 50 100 --model-path <snapshot> --output uncut-lrtA.json
"""
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-10-07-learning-runtime"))
import learnlib  # noqa: E402
import heteroes.eval.cot_workload as cot  # noqa: E402
from heteroes.eval.precision import EvalModel  # noqa: E402
from heteroes.model.loading import load_pinned_model  # noqa: E402
from heteroes.model.weights_io import load_weights_  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--ckpt-dir", required=True)
parser.add_argument("--generations", type=int, nargs="+", required=True)
parser.add_argument("--model-path", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--limits", type=int, nargs="+", default=[256, 512])
args = parser.parse_args()
if Path(args.output).exists():
    sys.exit(f"{args.output} exists")
ckpts = {}
for path in Path(args.ckpt_dir).glob("g*-*.bin"):
    generation, sha = path.stem[1:].split("-")
    ckpts[int(generation)] = (sha, path)
loaded = load_pinned_model(args.model_path, "cuda")
ev = EvalModel(loaded.model, "float32")
sets = {"train": learnlib.train_questions(), "H3": learnlib.heldout_sets()["H3"]}
result = {}
for generation in args.generations:
    sha, path = ckpts[generation]
    load_weights_(loaded.model, loaded.schema, path, sha)
    ev.refresh()
    result[generation] = {}
    for limit in args.limits:
        cot.MAX_NEW_TOKENS = limit                      # the module's generate() reads this when it is called
        row = {}
        for name, qa in sets.items():
            row[name] = learnlib.summarize(learnlib.evaluate_questions(ev.model, loaded.tokenizer, qa, chunk=len(qa)))
        result[generation][limit] = row
        print(f"[{time.strftime('%H:%M:%S')}] gen {generation} limit {limit}: " + " ".join(f"{k} {v['accuracy']*100:.1f}% (line {v['answer_line_rate']*100:.0f}%, {v['mean_chars']:.0f} chars)" for k, v in row.items()), flush=True)
learnlib.dump(args.output, {"ckpt_dir": args.ckpt_dir, "limits": args.limits, "results": result})
