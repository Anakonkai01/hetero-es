"""Base-model GSM8K probe on the first 200 validation rows: answer-line-last-number@1, FP32, chunk 64."""
import json, sys, time
import torch
from heteroes.study.evaluation import generate_rows
from heteroes.v3 import data as v3data
from heteroes.v3.model import file_manifest, load
from heteroes.v3.scoring import score
model_path, split_dir, budget = sys.argv[1], sys.argv[2], int(sys.argv[3])
rows = [json.loads(l) for l in open(f"{split_dir}/validation.jsonl")][:200]
model, tok = load(model_path, file_manifest(model_path), "cuda"); model = model.float()
spec = {"kind": "declarative", "name": "answer-line-last-number", "version": 1, "codeSha256": None, "config": {}}
t = time.time(); out = generate_rows(model, tok, rows, {"systemPrompt": None, "maxNewTokens": budget}, 64); torch.cuda.synchronize()
reward, scores = score(spec, [o["output"] for o in out], rows)
print(json.dumps({"rows": len(rows), "maxNewTokens": budget, "seconds": round(time.time() - t, 1), "accuracy": reward,
                  "truncated": sum(o["truncated"] for o in out), "answerLine": sum("Answer:" in o["output"] for o in out)}))
