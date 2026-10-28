"""
Is a bigger chunk exact for the long workload on PERTURBED candidates? (G7)  For each of K candidates (seeds 0..K-1, the CUDA noise engine, sigma 1e-3) the same 64 questions of level 3
are answered at several chunks (prompts per generate() call), FP32 forward pass; the SHA-256 of the answers' text and the rewards are kept per (seed, chunk). Run it on each machine and compare the
JSON files with compare_chunk_probe.py: a chunk is exact if its answers are those of chunk 16 for every candidate, on both GPUs.
Usage: python chunk_probe_cot.py --model-path SNAP --candidates 24 --chunks 16,32,64 --out FILE
"""
import argparse, hashlib, json, sys, time
from pathlib import Path

import torch

from heteroes.es.cuda_ops import perturb_model_cuda_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.eval import cot_workload as W
from heteroes.eval.precision import EvalModel
from heteroes.model.loading import check_cuda_noise_selftest, load_pinned_model


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model-path", required=True); p.add_argument("--candidates", type=int, default=24)
    p.add_argument("--questions", type=int, default=64); p.add_argument("--chunks", default="16,32,64"); p.add_argument("--out", required=True)
    a = p.parse_args(); out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to overwrite {out}")
    check_cuda_noise_selftest("cuda")
    loaded = load_pinned_model(a.model_path, "cuda")
    ev = EvalModel(loaded.model, "float32")
    snapshot = take_snapshot(loaded.model, loaded.schema)
    qa = W.make_questions(a.questions, 3)
    questions = [q for q, _ in qa]
    chunks = [int(c) for c in a.chunks.split(",")]
    result = {"gpu": torch.cuda.get_device_name(), "torch": torch.__version__, "questions": a.questions, "chunks": chunks, "workload_hash": W.workload_hash_of(3, a.questions), "candidates": {}}
    for seed in range(-1, a.candidates):                         # seed -1 is the unperturbed parent
        if seed >= 0:
            perturb_model_cuda_(loaded.model, loaded.schema, seed, 1e-3)
        ev.refresh()
        row = {}
        for chunk in chunks:
            torch.cuda.synchronize(); t = time.perf_counter()
            texts, tokens = W.generate(ev.model, loaded.tokenizer, questions, chunk)
            torch.cuda.synchronize()
            rewards = [1.0 if W.extract_answer(x) == ans else 0.0 for x, (_, ans) in zip(texts, qa)]
            row[str(chunk)] = {"seconds": time.perf_counter() - t, "tokens": tokens, "mean_reward": sum(rewards) / len(rewards), "rewards": rewards,
                               "texts_sha256": hashlib.sha256("\x00".join(texts).encode()).hexdigest()[:16],
                               "text_sha256_each": [hashlib.sha256(x.encode()).hexdigest()[:8] for x in texts]}
        if seed >= 0:
            restore_from_snapshot_(loaded.model, loaded.schema, snapshot)
        result["candidates"][str(seed)] = row
        ref = row[str(chunks[0])]
        print(seed, {c: (round(row[str(c)]["seconds"], 1), sum(x != y for x, y in zip(row[str(c)]["text_sha256_each"], ref["text_sha256_each"]))) for c in chunks}, flush=True)
        out.write_text(json.dumps(result, indent=1) + "\n")


if __name__ == "__main__":
    main()
