#!/usr/bin/env python3
"""python summarize_compact.py result.json [other.json ...]: per chunk, the total seconds of the library's generate() and of compact_generate over all conditions, the speed-up,
the number of different texts, and (with several files) whether the texts of the compact decoder are equal across the files (the GPUs)."""
import json
import sys
from collections import defaultdict

files = [json.load(open(path)) for path in sys.argv[1:]]
for path, data in zip(sys.argv[1:], files):
    total = defaultdict(lambda: [0.0, 0.0, 0, 0, 0])
    for r in data["records"]:
        t = total[r["chunk"]]
        t[0] += r["library_seconds"]; t[1] += r["compact_seconds"]; t[2] += len(r["different_questions"]); t[3] += r["slot_steps"]; t[4] += 1
    print(f"{path}  GPU {data['environment'].get('gpu_name')}  drop_fraction {data['drop_fraction']}")
    for chunk, (lib, comp, diff, slots, n) in sorted(total.items()):
        print(f"  chunk {chunk}: {n} conditions, library {lib:.1f} s, compact {comp:.1f} s, speed-up {lib / comp:.2f}, different texts {diff}, slot-steps {slots}")
if len(files) > 1:
    reference = {(r["seed"], r["chunk"]): r["texts_sha256"] for r in files[0]["records"]}
    for path, data in zip(sys.argv[2:], files[1:]):
        same = sum(reference.get((r["seed"], r["chunk"])) == r["texts_sha256"] for r in data["records"])
        print(f"compact texts of {path} equal to those of {sys.argv[1]}: {same} of {len(data['records'])} conditions")
