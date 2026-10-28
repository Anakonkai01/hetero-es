"""Base-model Countdown probe: reward distribution, answer length, truncation and seconds, on the FP32 evaluation path."""

import json
import sys
import time

import torch

from heteroes.study.evaluation import generate_rows
from heteroes.v3 import data as v3data
from heteroes.v3.model import file_manifest, load
from heteroes.v3.scoring import score

model_path, data_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
count, budgets, chunk = int(sys.argv[4]), [int(b) for b in sys.argv[5].split(",")], int(sys.argv[6])
dataset = v3data.build(v3data.read_rows(data_path), split_seed=42)
rows = dataset["splits"]["validation"][:count]
model, tokenizer = load(model_path, file_manifest(model_path), "cuda")
model = model.float()
spec = {"kind": "declarative", "name": "countdown", "version": 1, "codeSha256": None}
spec["config"] = {"numbersField": "nums", "targetField": "target"}
report = []
for budget in budgets:
    torch.cuda.synchronize()
    started = time.time()
    out = generate_rows(model, tokenizer, rows, {"systemPrompt": None, "maxNewTokens": budget}, chunk)
    torch.cuda.synchronize()
    seconds = time.time() - started
    texts = [o["text"] if "text" in o else o.get("output", "") for o in out]
    reward, scores = score(spec, texts, rows)
    lengths = [len(tokenizer(t)["input_ids"]) for t in texts]
    entry = {
        "maxNewTokens": budget,
        "rows": len(rows),
        "chunk": chunk,
        "seconds": round(seconds, 1),
        "meanReward": reward,
        "correct": scores.count(1.0),
        "formatOnly": scores.count(0.1),
        "noAnswer": scores.count(0.0),
        "truncated": sum(bool(o.get("truncated")) for o in out),
        "meanTokens": sum(lengths) / len(lengths),
        "maxTokens": max(lengths),
        "examples": texts[:3],
    }
    print(json.dumps({k: v for k, v in entry.items() if k != "examples"}), flush=True)
    report.append(entry)
json.dump(report, open(out_path, "w"), indent=1)
