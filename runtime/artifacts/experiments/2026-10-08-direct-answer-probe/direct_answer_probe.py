#!/usr/bin/env python3
"""
Did the second learning experiment teach arithmetic, or only to answer directly instead of reasoning in text? (experiment code, written after seeing run D1.) On H1 (256 new level-1 questions,
`learnlib2.heldout_sets()['H1']`) evaluate (a) the base model with the workload's system prompt, (b) the base model with a system prompt that asks for the final integer only, (c) a checkpoint of run D1 with the
workload's prompt (and (d) with the direct prompt), all with the 512-token limit. If (b) is already near (c), ES mostly moved the model to answering directly.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "2026-10-08-learning-v2"))
import learnlib2 as l2  # noqa: E402
import heteroes.eval.cot_workload as cot  # noqa: E402
from heteroes.eval.precision import EvalModel  # noqa: E402
from heteroes.model.loading import load_pinned_model  # noqa: E402
from heteroes.model.weights_io import load_weights_  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--ckpt-dir", required=True)
parser.add_argument("--generations", type=int, nargs="+", required=True)
parser.add_argument("--model-path", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
if Path(args.output).exists():
    sys.exit(f"{args.output} exists")
DIRECT = "Reply with only the final integer, nothing else."
ckpts = {}
for path in Path(args.ckpt_dir).glob("g*-*.bin"):
    g, sha = path.stem[1:].split("-")
    ckpts[int(g)] = (sha, path)
loaded = load_pinned_model(args.model_path, "cuda")
ev = EvalModel(loaded.model, "float32")
h1 = l2.heldout_sets()["H1"]
original = cot.SYSTEM_PROMPT
result = {}
for generation in args.generations:
    sha, path = ckpts[generation]
    load_weights_(loaded.model, loaded.schema, path, sha)
    ev.refresh()
    result[generation] = {}
    for name, prompt in (("workload_prompt", original), ("direct_prompt", DIRECT)):
        cot.SYSTEM_PROMPT = prompt
        try:
            with l2.token_limit(512):
                summary = l2.summarize(l2.evaluate_questions(ev.model, loaded.tokenizer, h1, chunk=len(h1)))
        finally:
            cot.SYSTEM_PROMPT = original
        result[generation][name] = summary
        print(f"gen {generation} {name}: H1 {summary['accuracy'] * 100:.1f}% (line {summary['answer_line_rate'] * 100:.0f}%, {summary['mean_chars']:.0f} chars)", flush=True)
l2.dump(args.output, {"direct_prompt": DIRECT, "results": result})
