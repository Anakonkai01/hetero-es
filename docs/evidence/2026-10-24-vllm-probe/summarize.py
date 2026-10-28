#!/usr/bin/env python3
"""Summarize the vLLM vs strict cross-GPU token comparison in this folder into summary.json (fresh file)."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    return json.loads((HERE / name).read_text())


def compare(left, right):
    differing = []
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            position = next((k for k, (p, q) in enumerate(zip(a, b)) if p != q), min(len(a), len(b)))
            differing.append({"prompt": index, "firstDifferentToken": position})
    return {
        "prompts": len(left),
        "tokensFirstMachine": sum(len(t) for t in left),
        "promptsEqual": len(left) - len(differing),
        "promptsDiffering": len(differing),
        "differences": differing,
    }


def strict_tokens(receipt):
    return [p["tokenIds"] for p in receipt["comparison"]["candidates"][0]["prompts"]]


def main():
    out = HERE / "summary.json"
    if out.exists():
        raise SystemExit("summary.json exists; keep it and write a new name")
    inputs = sorted(p.name for p in HERE.glob("*-large-01.json"))
    summary = {"inputs": {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in inputs}, "crossGpu": {}}
    for mode in ("default", "invariant"):
        nhan, thao = load(f"vllm-nhan-{mode}-large-01.json"), load(f"vllm-thao-{mode}-large-01.json")
        summary["crossGpu"][f"vllm-{mode}"] = compare(nhan["single"], thao["single"])
        for name, receipt in (("nhan", nhan), ("thao", thao)):
            summary[f"vllm-{mode}-{name}"] = {
                "gpu": receipt["environment"]["gpu"],
                "vllm": receipt["environment"]["vllm"],
                "batchedEqualsSinglePrompts": sum(receipt["batchedEqualsSingle"]),
                "copiesEqualSingle": receipt["throughput"]["copiesEqualSingle"],
                "batchTokensPerSecondTotal": round(receipt["throughput"]["tokensPerSecondTotal"], 1),
                "batchSequences": receipt["throughput"]["sequences"],
                "singleSequenceTokensPerSecond": round(receipt["singleSequenceTokensPerSecond"], 1),
            }
    nhan, thao = load("strict-nhan-large-01.json"), load("strict-thao-large-01.json")
    summary["crossGpu"]["strict"] = compare(strict_tokens(nhan), strict_tokens(thao))
    summary["strictVsVllmInvariantNhan"] = compare(
        strict_tokens(nhan), load("vllm-nhan-invariant-large-01.json")["single"]
    )
    for name, receipt in (("nhan", nhan), ("thao", thao)):
        timing = receipt["timings"][0]
        summary[f"strict-{name}"] = {
            "gpu": receipt["environment"]["gpu"],
            "singleSequenceTokensPerSecond": round(timing["tokensPerSecond"], 1),
            "cudaPeakAllocatedBytes": receipt["cudaPeakAllocatedBytes"],
        }
    with out.open("x") as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: v for k, v in summary["crossGpu"].items()}, indent=1)[:3000])


if __name__ == "__main__":
    main()
