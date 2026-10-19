"""Compare the JSON files of chunk_probe_cot.py. For each machine: how many answers differ from the reference chunk (the first one listed, 16) at each chunk, over all candidates
and questions; across machines: how many answers differ for the same (seed, chunk). Usage: python compare_chunk_probe.py FILE_A FILE_B [...]"""
import json, sys

files = [json.load(open(p)) for p in sys.argv[1:]]
for d in files:
    chunks = d["chunks"]; ref = str(chunks[0])
    print(f"\n{d['gpu']}: {len(d['candidates'])} states (the parent and perturbed candidates) x {d['questions']} questions, chunks {chunks}")
    for c in chunks[1:]:
        diff = states = 0
        reward_diff = 0
        for seed, row in d["candidates"].items():
            if str(c) not in row:
                continue
            states += 1
            diff += sum(x != y for x, y in zip(row[str(c)]["text_sha256_each"], row[ref]["text_sha256_each"]))
            reward_diff += row[str(c)]["mean_reward"] != row[ref]["mean_reward"]
        print(f"  chunk {c} against chunk {ref}: {diff} of {states * d['questions']} answers differ; {reward_diff} of {states} candidate rewards differ")
if len(files) >= 2:
    a, b = files[0], files[1]
    common = sorted(set(a["chunks"]) & set(b["chunks"]))
    print(f"\n{a['gpu']} against {b['gpu']}, same seed and chunk:")
    for c in common:
        seeds = [s for s in a["candidates"] if s in b["candidates"] and str(c) in b["candidates"][s] and str(c) in a["candidates"][s]]
        diff = sum(x != y for s in seeds for x, y in zip(a["candidates"][s][str(c)]["text_sha256_each"], b["candidates"][s][str(c)]["text_sha256_each"]))
        print(f"  chunk {c}: {len(seeds)} states, {diff} of {len(seeds) * a['questions']} answers differ")
    ra, rb = str(a["chunks"][0]), None
    # chunk 32 or 64 of the other machine against chunk 16 of this one
    for c in sorted(set(b["chunks"]) - {int(ra)}):
        seeds = [s for s in a["candidates"] if s in b["candidates"] and str(c) in b["candidates"][s] and ra in a["candidates"][s]]
        diff = sum(x != y for s in seeds for x, y in zip(a["candidates"][s][ra]["text_sha256_each"], b["candidates"][s][str(c)]["text_sha256_each"]))
        print(f"  {b['gpu']} chunk {c} against {a['gpu']} chunk {ra}: {diff} of {len(seeds) * a['questions']} answers differ")
