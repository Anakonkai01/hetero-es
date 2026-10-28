"""Recompute cross-GPU comparisons from raw receipts; output is always create-only."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location("sglang_probe", ROOT / "runtime/scripts/probe_sglang_tokens.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--include-tuned", action="store_true")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a fresh --out")
    sources = {}

    def read(relative):
        path = HERE / relative
        sources[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text())

    modes = {
        "stock-default": ("sglang-nhan-default-large-01.json", "sglang-thao-default-large-02.json"),
    }
    if args.include_tuned:
        modes["deterministic-fp16-stages2"] = (
            "sglang-nhan-deterministic-stages2-large-01.json",
            "sglang-thao-deterministic-stages2-large-01.json",
        )
    result = {"formatVersion": 1, "crossGpu": {}, "sourcesSha256": sources}
    default = None
    for mode, names in modes.items():
        left, right = map(read, names)
        if left["options"] != right["options"]:
            raise ValueError("SGLang engine options differ between GPUs")
        if mode.endswith("stages2"):
            expected = read("fp16-stages2-source.json")["tunedSha256"]
            if any(r["environment"]["batchInvariantSourceSha256"] != expected for r in (left, right)):
                raise ValueError("Tuned kernels do not have the recorded source hash")
        if default is None:
            default = left
        result["crossGpu"][mode] = {
            **probe.compare_receipts(left, right),
            "sameGpuBatchVsSingle": {host: receipt["batchedVsSingle"] for host, receipt in (("nhan", left), ("thao", right))},
            "performance": {
                host: {
                    "batch128TokensPerSecond": receipt["throughput"]["tokensPerSecondTotal"],
                    "singleSequenceTokensPerSecond": receipt["singleSequenceTokensPerSecond"],
                    "wallSeconds": receipt["wallSeconds"],
                }
                for host, receipt in (("nhan", left), ("thao", right))
            },
            "environment": {host: receipt["environment"] for host, receipt in (("nhan", left), ("thao", right))},
        }
    # Historical vLLM receipts contain the actual prompt IDs; verify this is the same 208-prompt workload.
    old = read("../2026-10-24-vllm-probe/vllm-nhan-invariant-large-01.json")
    if old["promptTokenIds"] != default["workload"]["promptTokenIds"]:
        raise ValueError("SGLang/vLLM prompt IDs differ")
    strict = [read(f"../2026-10-24-vllm-probe/strict-{host}-large-01.json") for host in ("nhan", "thao")]
    if any(r["status"] != "ok" or r["comparison"]["maxNewTokens"] != default["workload"]["maxNewTokens"] for r in strict):
        raise ValueError("Historical strict receipt failed or used different token limits")
    rows = [r["comparison"]["candidates"][0]["prompts"] for r in strict]
    if any([p["promptTokens"] for p in row] != list(map(len, default["workload"]["promptTokenIds"])) for row in rows):
        raise ValueError("Historical strict prompt counts/lengths differ")
    result["historicalStrictCrossGpu"] = probe.compare_tokens(*[[p["tokenIds"] for p in row] for row in rows])
    result["limitations"] = [
        "Parent weights only; one model/revision and two unisolated GPUs; no universal equality or qualification.",
        "Stock deterministic mode failed to launch on both GPUs (106496 shared bytes required, 101376 available).",
        "The stages2 variant is patched SGLang, not the stock release.",
        "Performance samples are single trials, not acceptance thresholds or like-for-like strict batching measurements.",
        "Strict receipts are historical and omit actual prompt IDs; their counts/lengths and shared prompt source match.",
    ]
    with args.out.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    for mode, value in result["crossGpu"].items():
        print(mode, {kind: len(value[kind]["differences"]) for kind in ("single", "batched")})


if __name__ == "__main__":
    main()
