#!/usr/bin/env python3
"""
Whole-generation throughput of the strict B22 decoder on the matched Qwen B32 workloads, against a pinned floor.

short32: the 8 probe prompts repeated to 32 rows, 32 new tokens; chat128: the first 32 chat rows, 128 new tokens.
Prefix reuse off, no EOS stopping, greedy, one engine per process. `--processes` separate processes each time
`--samples` synchronized generations after one warm generation; the result is the mean of the process medians.
Pass: every generation gives the golden token hash and the mean is at least the floor pinned for this GPU in
acceptance/golden/throughput.json. This is a regression gate on one host, not a cross-host or vLLM comparison.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--models", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--golden", type=Path, default=HERE.parent / "golden" / "throughput.json")
p.add_argument("--chat-workload", type=Path, default=HERE.parent / "golden" / "workload-chat-01.json")
p.add_argument("--processes", type=int, default=2)
p.add_argument("--samples", type=int, default=5)
p.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
p.add_argument("--gpu", action="store_true")
a = p.parse_args()
if not a.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or a.out.exists():
    p.error("GPU opt-in (--gpu and HETEROES_GPU_ACCEPTANCE=1) and a fresh --out are required")


def child():
    import torch

    from heteroes.strict.integer_decoder import IntegerDecoderGraph
    from heteroes.v3.model import file_manifest, load
    from probe_strict_backend import PROMPTS

    path = a.models / "qwen"
    model, tok = load(path, file_manifest(path), "cuda")
    engine = IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3)
    short = [tok(t)["input_ids"] for t in PROMPTS]
    rows = json.loads(a.chat_workload.read_text())["models"]["qwen"]["rows"][:32]
    cases = [("short32", 32, [short[i % 8] for i in range(32)]), ("chat128", 128, [r["tokenIds"] for r in rows])]
    report = {"gpu": torch.cuda.get_device_name(), "fingerprint": engine.fingerprint, "cases": {}}
    for label, tokens, prompts in cases:
        width = max(map(len, prompts))
        ids = torch.full((32, width), tok.pad_token_id or 0, dtype=torch.long, device="cuda")
        mask = torch.zeros_like(ids)
        for i, row in enumerate(prompts):
            ids[i, -len(row) :] = torch.tensor(row, device="cuda")
            mask[i, -len(row) :] = 1

        def run():
            out = engine.generate(
                ids,
                attention_mask=mask,
                do_sample=False,
                max_new_tokens=tokens,
                eos_token_id=[],
                pad_token_id=tok.pad_token_id or 0,
                repetition_penalty=1.0,
                use_cache=True,
            )
            return out[:, width:].tolist()

        expected, times = run(), []
        for _ in range(a.samples):
            torch.cuda.synchronize()
            start = time.perf_counter()
            assert run() == expected
            torch.cuda.synchronize()
            times.append(time.perf_counter() - start)
        report["cases"][label] = {
            "secondsSamples": times,
            "medianTokensPerSecond": 32 * tokens / statistics.median(times),
            "tokensSha256": hashlib.sha256(json.dumps(expected).encode()).hexdigest(),
        }
    a.out.write_text(json.dumps(report, indent=1) + "\n")


if a.child:
    child()
    raise SystemExit(0)

golden = json.loads(a.golden.read_text())
processes = []
for i in range(a.processes):
    out = a.out.with_name(f"{a.out.stem}-process{i + 1}.json")
    command = [sys.executable, __file__, "--gpu", "--child", "--models", str(a.models), "--out", str(out)]
    command += ["--chat-workload", str(a.chat_workload), "--samples", str(a.samples)]
    subprocess.run(command, check=True)
    processes.append(json.loads(out.read_text()))
gpu = processes[0]["gpu"]
floors = golden["floors"].get(gpu)
report = {"gpu": gpu, "processes": processes, "cases": {}, "failures": []}
for label, expected in golden["tokensSha256"].items():
    hashes = {proc["cases"][label]["tokensSha256"] for proc in processes}
    mean = statistics.mean(proc["cases"][label]["medianTokensPerSecond"] for proc in processes)
    report["cases"][label] = {"meanOfMedians": mean, "floor": None if floors is None else floors[label]}
    if hashes != {expected}:
        report["failures"].append(f"{label}: tokens differ from the golden hash")
    if floors is None:
        report["failures"].append(f"no throughput floor pinned for {gpu!r}")
    elif mean < floors[label]:
        report["failures"].append(f"{label}: {mean:.1f} token/s is below the floor {floors[label]}")
    print(label, round(mean, 1), "token/s", "floor", report["cases"][label]["floor"], flush=True)
a.out.write_text(json.dumps(report, indent=1) + "\n")
if report["failures"]:
    print("\n".join(report["failures"]))
    raise SystemExit(1)
print("THROUGHPUT OK")
