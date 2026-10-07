"""Calibrate the workload: accuracy of the base model per level, tokens and rollout time, FP32 forward pass (the default, O8).
Usage: python calibrate_workload.py --model-path SNAP --questions 32 --chunk 16 --out FILE"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import torch

import cot_workload as W
from heteroes.eval.precision import EvalModel
from heteroes.model.loading import load_pinned_model


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model-path", required=True)
    p.add_argument("--questions", type=int, default=32)
    p.add_argument("--chunk", type=int, default=16)
    p.add_argument("--levels", default="1,2,3")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to overwrite {out}")
    loaded = load_pinned_model(a.model_path, "cuda")
    ev = EvalModel(loaded.model, "float32")
    ev.refresh()
    # one warm-up call so that the first timing does not contain the kernel start-up
    W.evaluate(ev.model, loaded.tokenizer, W.make_questions(a.chunk, 1), a.chunk)
    result = {"gpu": torch.cuda.get_device_name(), "torch": torch.__version__, "chunk": a.chunk, "max_new_tokens": W.MAX_NEW_TOKENS, "levels": {}}
    for level in [int(x) for x in a.levels.split(",")]:
        qa = W.make_questions(a.questions, level)
        r = W.evaluate(ev.model, loaded.tokenizer, qa, a.chunk)
        result["levels"][level] = {"mean_reward": r["mean_reward"], "tokens": r["tokens"], "seconds": r["seconds"],
                                   "tokens_per_second": r["tokens"] / r["seconds"], "sample": [(qa[i][0], qa[i][1], r["texts"][i][-120:]) for i in range(3)]}
        print(level, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in result["levels"][level].items() if k != "sample"}, flush=True)
    out.write_text(json.dumps(result, indent=1) + "\n")


if __name__ == "__main__":
    main()
