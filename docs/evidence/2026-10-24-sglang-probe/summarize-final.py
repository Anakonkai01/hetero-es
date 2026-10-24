"""Create-only summary; tuned Quang comparison explicitly selects a 32-prompt prefix of the local 208."""

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
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a fresh --out")
    sources = {}

    def read(name):
        path = HERE / name
        sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text())

    result = {"formatVersion": 1, "sourcesSha256": sources, "modes": {}}
    pairs = (
        ("stock-default", "thao", "sglang-nhan-default-large-01.json", "sglang-thao-default-large-02.json"),
        ("deterministic-fp16-stages2", "quang", "sglang-nhan-deterministic-stages2-large-01.json", "sglang-quang-deterministic-stages2-prefix32-02.json"),
    )
    for mode, host, left_name, right_name in pairs:
        left, right = read(left_name), read(right_name)
        probe.compare_receipts(left, left)
        probe.compare_receipts(right, right)
        if left["options"] != right["options"]:
            raise ValueError("Engine options differ")
        for key in ("sglang", "torch"):
            if left["environment"][key] != right["environment"][key]:
                raise ValueError("Inference package versions differ")
        n = len(right["workload"]["promptTokenIds"])
        if left["workload"]["promptTokenIds"][:n] != right["workload"]["promptTokenIds"]:
            raise ValueError("The remote prompts are not the exact local prefix")
        selected = {
            **left,
            "workload": {**left["workload"], "promptTokenIds": left["workload"]["promptTokenIds"][:n]},
            "single": left["single"][:n],
            "batched": left["batched"][:n],
        }
        if mode.endswith("stages2"):
            expected = read("fp16-stages2-source.json")["tunedSha256"]
            if any(r["environment"]["batchInvariantSourceSha256"] != expected for r in (left, right)):
                raise ValueError("Kernel source differs from the recorded patch")
        result["modes"][mode] = {
            "hosts": ["nhan-5070ti", host + "-3060"],
            "selection": {"localOriginalPrompts": len(left["single"]), "comparedPrompts": n, "indices": list(range(n))},
            "crossGpu": probe.compare_receipts(selected, right),
            "sameGpuBatchVsSingle": {
                "nhan": probe.compare_tokens(selected["batched"], selected["single"]),
                host: probe.compare_tokens(right["batched"], right["single"]),
            },
            "performanceSingleTrial": {
                name: {"batch128TokensPerSecond": receipt["throughput"]["tokensPerSecondTotal"], "singleSequenceTokensPerSecond": receipt["singleSequenceTokensPerSecond"]}
                for name, receipt in (("nhan", left), (host, right))
            },
            "environment": {"nhan": left["environment"], host: right["environment"]},
        }
    result["stockDeterministic"] = {"status": "launch-failed-on-both-gpus", "requiredSharedBytes": 106496, "availableSharedBytes": 101376}
    result["thaoInterruptedTunedRun"] = {"status": "no-receipt", "cause": "owner confirmed host sleep", "ownedProbePidsAfterWake": []}
    result["limitations"] = [
        "Parent FP16 Qwen2.5-0.5B only; no ES perturbation/restore, LoRA, managed ownership, native Windows or qualification.",
        "Default and tuned modes use different 3060 hosts and corpus sizes; do not treat this as a paired performance benchmark.",
        "Local tuned batch used 208 prompts; Quang used 32. Single-sequence comparison isolates the cross-GPU token differences; each host also matches its tested batched output.",
        "Raw local tuned receipt has 208/208 same-host batch/serial matches, not only the selected 32.",
        "Single-trial timings on unisolated hosts do not establish throughput thresholds or quality/learning.",
    ]
    with args.out.open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write("\n")
    for mode, value in result["modes"].items():
        print(mode, value["selection"], {k: len(v["differences"]) for k, v in value["crossGpu"].items()})


if __name__ == "__main__":
    main()
