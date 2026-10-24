#!/usr/bin/env python3
"""Experiment: greedy vLLM tokens for the strict-probe prompts, for comparison only (not a HeteroES backend).

Needs --gpu and HETEROES_GPU_ACCEPTANCE=1; run in a separate environment that has vLLM. Uses the same prompt
token ids as `probe_strict_backend.py` (parent weights only) and records tokens per prompt for a batched run and
a one-prompt-at-a-time run, plus throughput. Set VLLM_BATCH_INVARIANT=1 in the environment to test that mode.
With --strict-receipt it counts prompts whose tokens equal the strict backend's parent tokens.
Finite coverage; equality or difference here is evidence about these runs only.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import time


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--dtype", default="float16")
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--memory-fraction", type=float, default=0.45)
    parser.add_argument("--enforce-eager", action="store_true")
    parser.add_argument("--throughput-copies", type=int, default=16, help="prompt copies in the throughput batch")
    parser.add_argument("--strict-receipt", type=Path)
    parser.add_argument("--generated", type=int, default=0, help="extra deterministic templated prompts")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("Evidence already exists; choose a fresh --out")
    if not args.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        parser.error("This probe requires --gpu and HETEROES_GPU_ACCEPTANCE=1")

    spec = importlib.util.spec_from_file_location("strict_probe", Path(__file__).with_name("probe_strict_backend.py"))
    strict_probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(strict_probe)

    import torch
    import vllm
    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams

    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    texts = list(strict_probe.PROMPTS) + strict_probe.generated_prompts(args.generated)
    prompt_ids = [tokenizer(text)["input_ids"] for text in texts]
    report = {
        "formatVersion": 1,
        "status": "running",
        "experiment": "vllm-greedy-comparison",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "vllm": vllm.__version__,
            "torch": torch.__version__,
            "gpu": torch.cuda.get_device_name(0),
            "computeCapability": list(torch.cuda.get_device_capability(0)),
            "batchInvariant": os.environ.get("VLLM_BATCH_INVARIANT", "0"),
            "enforceEager": args.enforce_eager,
            "dtype": args.dtype,
        },
        "promptTokenIds": prompt_ids,
    }
    started = time.perf_counter()
    try:
        llm = LLM(
            model=str(args.model_path),
            dtype=args.dtype,
            gpu_memory_utilization=args.memory_fraction,
            max_model_len=1024,
            seed=0,
            enforce_eager=args.enforce_eager,
        )
        params = SamplingParams(temperature=0.0, max_tokens=args.max_new_tokens, ignore_eos=False)

        def run(batches):
            tokens = []
            for batch in batches:
                outputs = llm.generate([{"prompt_token_ids": ids} for ids in batch], params, use_tqdm=False)
                tokens += [list(o.outputs[0].token_ids) for o in outputs]
            return tokens

        batched = run([prompt_ids])
        single = run([[ids] for ids in prompt_ids])
        report["batched"] = batched
        report["single"] = single
        report["batchedEqualsSingle"] = [a == b for a, b in zip(batched, single)]
        copies = [ids for ids in prompt_ids[:8] for _ in range(args.throughput_copies)]
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        many = run([copies])
        torch.cuda.synchronize()
        seconds = time.perf_counter() - t0
        report["throughput"] = {
            "sequences": len(copies),
            "generatedTokens": sum(len(t) for t in many),
            "seconds": seconds,
            "tokensPerSecondTotal": sum(len(t) for t in many) / seconds,
            "copiesEqualSingle": all(
                many[i * args.throughput_copies + j] == single[i]
                for i in range(min(8, len(prompt_ids)))
                for j in range(args.throughput_copies)
            ),
        }
        t0 = time.perf_counter()
        one = run([[prompt_ids[0]]])
        report["singleSequenceTokensPerSecond"] = len(one[0]) / (time.perf_counter() - t0)
        report["tokensSha256"] = hashlib.sha256(json.dumps(single).encode()).hexdigest()
        if args.strict_receipt is not None:
            strict = json.loads(args.strict_receipt.read_text())
            parent = strict["comparison"]["candidates"][0]["prompts"]
            if [p["promptTokens"] for p in parent] != [len(ids) for ids in prompt_ids[: len(parent)]]:
                raise ValueError("Strict receipt used other prompts")
            report["strictComparison"] = [
                {
                    "equal": s["tokenIds"] == v,
                    "firstDifference": next((i for i, (a, b) in enumerate(zip(s["tokenIds"], v)) if a != b), None),
                }
                for s, v in zip(parent, single)
            ]
        report["status"] = "ok"
    except Exception as error:
        report.update(status="error", errorType=type(error).__name__, error=str(error)[:3000])
    finally:
        report["wallSeconds"] = time.perf_counter() - started
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "out": str(args.out)}))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
