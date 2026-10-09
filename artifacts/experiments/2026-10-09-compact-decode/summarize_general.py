#!/usr/bin/env python3
"""python summarize_general.py general/*.json : one line per (model, task, dtype) run of compact_general.py, and the batch-shape sensitivity files (sensitivity-*.json) as a second table."""
import json
import sys
from pathlib import Path

print(f"{'run':46s} {'texts differing from generate()':>31s} {'speed-up by chunk':>26s} {'slots (generate -> compact)':>28s} {'mean answer':>12s} {'at limit':>9s}")
for path in sys.argv[1:]:
    d = json.load(open(path))
    name = Path(path).name[:-5]
    if "pairs" in str(d.get("records", [{}])[0]):
        continue
    rs = d["records"]
    total = len(rs) * 128
    diff = sum(len(r["different_questions"]) for r in rs)
    ups = []
    for chunk in sorted({r["chunk"] for r in rs}):
        lib = sum(r["library_seconds"] for r in rs if r["chunk"] == chunk)
        cmp_ = sum(r["compact_seconds"] for r in rs if r["chunk"] == chunk)
        ups.append(f"{chunk}: {lib / cmp_:.2f}")
    ls, cs = sum(r["library_slots"] for r in rs), sum(r["compact_slots"] for r in rs)
    mean = sum(r["answer_tokens_mean"] for r in rs) / len(rs)
    limit = sum(r["answers_at_limit"] for r in rs)
    print(f"{name:46s} {f'{diff} of {total}':>31s} {'  '.join(ups):>26s} {f'{ls} -> {cs}':>28s} {mean:>12.0f} {limit:>9d}")
print()
print("batch-shape sensitivity (texts that differ, summed over the parent and the noisy candidates, 128 questions each):")
for path in sys.argv[1:]:
    d = json.load(open(path))
    if "pairs" in str(d.get("records", [{}])[0]):
        keys = d["records"][0]["pairs"].keys()
        print(Path(path).name[:-5], {k: sum(r["pairs"][k] for r in d["records"]) for k in keys}, "of", 128 * len(d["records"]))
