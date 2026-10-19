"""Countdown decoding speed: generate() vs the compacting decoder at chunks 16/64 (FP32), and whether the texts agree."""

import json
import sys
import time

import torch

from heteroes.eval.compact_decode import compact_generate_ids, decode_settings
from heteroes.v3 import data as v3data
from heteroes.v3.model import file_manifest, load

model_path, data_path, out_path, count, budget = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
rows = v3data.build(v3data.read_rows(data_path), split_seed=42)["splits"]["validation"][:count]
model, tokenizer = load(model_path, file_manifest(model_path), "cuda")
model = model.float()
tokenizer.padding_side = "left"
eos_ids, pad_id, processors = decode_settings(model, budget, tokenizer.pad_token_id)


def run(engine, chunk):
    texts = []
    torch.cuda.synchronize()
    started = time.time()
    for offset in range(0, len(rows), chunk):
        prompts = [
            tokenizer.apply_chat_template([{"role": "user", "content": r["prompt"]}], tokenize=False, add_generation_prompt=True)
            for r in rows[offset : offset + chunk]
        ]
        inputs = {k: v.to("cuda") for k, v in tokenizer(prompts, return_tensors="pt", padding=True).items()}
        with torch.no_grad():
            if engine == "compact":
                new, _ = compact_generate_ids(
                    model, inputs["input_ids"], inputs["attention_mask"], budget, eos_ids, pad_id, processors
                )
            else:
                new = model.generate(**inputs, max_new_tokens=budget, do_sample=False)[:, inputs["input_ids"].shape[1] :]
        texts += tokenizer.batch_decode(new, skip_special_tokens=True)
    torch.cuda.synchronize()
    return time.time() - started, texts


results, reference = [], None
for engine, chunk in (("generate", 16), ("compact", 16), ("generate", 64), ("compact", 64)):
    seconds, texts = run(engine, chunk)
    reference = reference or texts
    same = sum(a == b for a, b in zip(texts, reference))
    entry = {"engine": engine, "chunk": chunk, "rows": len(rows), "budget": budget, "seconds": round(seconds, 1), "sameAsGenerate16": same}
    print(json.dumps(entry), flush=True)
    results.append(entry)
json.dump(results, open(out_path, "w"), indent=1)
