"""What limits the rollout of the long workload? Time of the evaluation of the same questions with different numbers of prompts per generate() call (chunk), FP32 forward pass.
If the time per question falls with the chunk, the GPU is waiting (launch and Python overhead of the decode loop), not computing. Also: are the answers the same as at chunk 16
(is a bigger chunk exact)?  Usage: python rollout_scaling.py --model-path SNAP --questions 64 --out FILE"""
import argparse, hashlib, json, sys, time
from pathlib import Path

import torch

from heteroes.eval import cot_workload as W
from heteroes.eval.precision import EvalModel
from heteroes.model.loading import load_pinned_model


def main():
    p = argparse.ArgumentParser(); p.add_argument("--model-path", required=True); p.add_argument("--questions", type=int, default=64)
    p.add_argument("--chunks", default="8,16,32,64"); p.add_argument("--out", required=True)
    a = p.parse_args(); out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to overwrite {out}")
    loaded = load_pinned_model(a.model_path, "cuda")
    ev = EvalModel(loaded.model, "float32"); ev.refresh()
    qa = W.make_questions(a.questions, 3)
    questions = [q for q, _ in qa]
    W.generate(ev.model, loaded.tokenizer, questions[:16], 16)                       # warm-up
    res = {"gpu": torch.cuda.get_device_name(), "questions": a.questions, "chunks": {}}
    reference = None
    for chunk in [int(c) for c in a.chunks.split(",")] + [16]:
        torch.cuda.synchronize(); t = time.perf_counter()
        texts, tokens = W.generate(ev.model, loaded.tokenizer, questions, chunk)
        torch.cuda.synchronize(); seconds = time.perf_counter() - t
        rewards = [1.0 if W.extract_answer(x) == ans else 0.0 for x, (_, ans) in zip(texts, qa)]
        if chunk == 16 and reference is None:
            reference = texts
        res["chunks"][str(chunk)] = {"seconds": seconds, "seconds_per_question": seconds / len(questions), "tokens": tokens,
                                      "tokens_per_second": tokens / seconds, "accuracy": sum(rewards) / len(rewards),
                                      "answers_equal_to_chunk16": None if reference is None else sum(x == y for x, y in zip(texts, reference)),
                                      "texts_sha256": hashlib.sha256("\x00".join(texts).encode()).hexdigest()[:16]}
        print(chunk, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res["chunks"][str(chunk)].items()}, flush=True)
    out.write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
