#!/usr/bin/env python3
"""Compare `comparison` objects of strict-backend probe receipts from several machines.

Reports whether every machine produced identical candidate weight hashes, prefill logits hashes, token ids,
text hashes and rewards, lists the first differing paths, and hashes each input receipt. Timing summaries are
informational. Equality on this finite matrix is not hardware qualification.
"""

import argparse
import hashlib
import json
from pathlib import Path


# Machine-local diagnostics (present only where the slow eager check ran); reported, never compared.
LOCAL_ONLY = frozenset({"eagerPrefillLogitsEqual"})


def differences(left, right, path=""):
    if type(left) is not type(right):
        return [path or "/"]
    if isinstance(left, dict):
        found = []
        for key in sorted((set(left) | set(right)) - LOCAL_ONLY):
            if key not in left or key not in right:
                found.append(f"{path}/{key}")
            else:
                found += differences(left[key], right[key], f"{path}/{key}")
        return found
    if isinstance(left, list):
        if len(left) != len(right):
            return [f"{path}[len]"]
        return [d for i, (a, b) in enumerate(zip(left, right)) for d in differences(a, b, f"{path}[{i}]")]
    return [] if left == right else [path or "/"]


def summarize(paths):
    receipts = {}
    for path in paths:
        data = path.read_bytes()
        receipts[path.name] = (hashlib.sha256(data).hexdigest(), json.loads(data))
    names = list(receipts)
    base_name = names[0]
    base = receipts[base_name][1]
    if any(r["status"] != "ok" for _, r in receipts.values()):
        raise ValueError("Every receipt must have status ok")
    mismatches = {name: differences(base["comparison"], receipts[name][1]["comparison"])[:20] for name in names[1:]}
    cases = sum(len(c["prompts"]) for c in base["comparison"]["candidates"])
    tokens = sum(len(p["tokenIds"]) for c in base["comparison"]["candidates"] for p in c["prompts"])
    machines = {}
    for name, (_, receipt) in receipts.items():
        timings = receipt["timings"]
        machines[name] = {
            "gpu": receipt["environment"]["gpu"],
            "computeCapability": receipt["environment"]["computeCapability"],
            "platform": receipt["environment"]["platform"],
            "torch": receipt["environment"]["torch"],
            "arch": receipt["kernelIdentity"]["arch"],
            "nvrtcVersion": receipt["kernelIdentity"]["nvrtcVersion"],
            "cubinSha256": {k: v["cubinSha256"] for k, v in receipt["kernelIdentity"]["builds"].items()},
            "tokensPerSecondByCandidate": [round(t["tokensPerSecond"], 2) for t in timings],
            "perturbSecondsMedian": sorted(t["perturbSeconds"] for t in timings[1:])[len(timings[1:]) // 2]
            if len(timings) > 1
            else None,
            "restoreSecondsMedian": sorted(t["restoreSeconds"] for t in timings)[len(timings) // 2],
            "cudaPeakAllocatedBytes": receipt["cudaPeakAllocatedBytes"],
            "cudaPeakReservedBytes": receipt["cudaPeakReservedBytes"],
            "wallSeconds": receipt["wallSeconds"],
        }
    eager = {
        name: [
            p["eagerPrefillLogitsEqual"]
            for c in receipt["comparison"]["candidates"]
            for p in c["prompts"]
            if "eagerPrefillLogitsEqual" in p
        ]
        for name, (_, receipt) in receipts.items()
    }
    return {
        "formatVersion": 1,
        "eagerPrefillChecks": {name: checks for name, checks in eager.items() if checks},
        "hardwareQualified": False,
        "comparisonEqual": all(not found for found in mismatches.values()),
        "baseline": base_name,
        "mismatches": mismatches,
        "machines": machines,
        "candidates": len(base["comparison"]["candidates"]),
        "promptCasesPerMachine": cases,
        "generatedTokensPerMachine": tokens,
        "inputs": {name: digest for name, (digest, _) in receipts.items()},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("Output exists; choose a fresh --out")
    if len(args.receipts) < 2:
        parser.error("Compare at least two receipts")
    summary = summarize(args.receipts)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"comparisonEqual": summary["comparisonEqual"], "out": str(args.out)}))
    return 0 if summary["comparisonEqual"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
