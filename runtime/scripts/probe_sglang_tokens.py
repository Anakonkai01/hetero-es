#!/usr/bin/env python3
"""Standalone SGLang comparison, never a qualified HeteroES backend or a learning run.

Use an isolated environment, --gpu and HETEROES_GPU_ACCEPTANCE=1. Compare parent FP16 greedy tokens on the
same fixed/generated prompts as the strict/vLLM probes. Triton attention and PyTorch sampling work across
Ampere/Blackwell without selecting an architecture-specific attention backend. Test both default arithmetic
and --deterministic. Disabling prefix cache isolates batching from prefix reuse. All receipts are create-only.
"""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import time
import traceback


def compare_tokens(left, right):
    if len(left) != len(right):
        raise ValueError("Token sequence count differs")
    differences = []
    for index, (a, b) in enumerate(zip(left, right, strict=True)):
        if a != b:
            first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            differences.append({"prompt": index, "firstDifference": first, "leftLength": len(a), "rightLength": len(b)})
    return {"prompts": len(left), "equal": len(left) - len(differences), "differences": differences}


def compare_receipts(left, right):
    if left.get("status") != "ok" or right.get("status") != "ok":
        raise ValueError("Both receipts must be successful")
    if left["workload"] != right["workload"]:
        raise ValueError("Receipts used a different workload")
    count = len(left["workload"]["promptTokenIds"])
    if any(len(r[mode]) != count for r in (left, right) for mode in ("single", "batched")):
        raise ValueError("Receipt output count differs from the workload")
    return {mode: compare_tokens(left[mode], right[mode]) for mode in ("single", "batched")}


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--deterministic", action="store_true")
    parser.add_argument("--generated", type=int, default=200)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--memory-fraction", type=float, default=0.35)
    parser.add_argument("--throughput-copies", type=int, default=16)
    parser.add_argument("--disable-cuda-graph", action="store_true")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("Evidence already exists; choose a fresh --out")
    if not args.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        parser.error("This probe requires --gpu and HETEROES_GPU_ACCEPTANCE=1")
    if not (0 <= args.generated <= 10000 and 1 <= args.max_new_tokens <= 512 and 1 <= args.throughput_copies <= 16):
        parser.error("Invalid prompt/token/batch limits")
    if not 0 < args.memory_fraction <= 0.6:
        parser.error("memory fraction must be in (0, 0.6]")

    report = {
        "formatVersion": 1,
        "status": "running",
        "experiment": "sglang-greedy-comparison",
        "sourceSha256": file_sha256(Path(__file__)),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "options": {
            "deterministic": args.deterministic,
            "attentionBackend": "triton",
            "samplingBackend": "pytorch",
            "dtype": "float16",
            "disableRadixCache": True,
            "disableCudaGraph": args.disable_cuda_graph,
            "memoryFraction": args.memory_fraction,
        },
    }
    engine = None
    started = time.perf_counter()
    try:
        import sglang as sgl
        import torch
        from transformers import AutoTokenizer

        report["environment"].update(
            sglang=importlib.metadata.version("sglang"),
            torch=torch.__version__,
            cuda=torch.version.cuda,
            gpu=torch.cuda.get_device_name(0),
            computeCapability=list(torch.cuda.get_device_capability(0)),
            jitDeepGemm=os.environ.get("SGLANG_ENABLE_JIT_DEEPGEMM", "default"),
            variant=os.environ.get("HETEROES_SGLANG_VARIANT", "stock"),
        )
        report["environment"]["batchInvariantSourceSha256"] = file_sha256(
            Path(sgl.__file__).parent / "srt/batch_invariant_ops/batch_invariant_ops.py"
        )
        spec = importlib.util.spec_from_file_location(
            "strict_probe", Path(__file__).with_name("probe_strict_backend.py")
        )
        strict_probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(strict_probe)
        tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True)
        prompt_ids = [
            tokenizer(text)["input_ids"]
            for text in list(strict_probe.PROMPTS) + strict_probe.generated_prompts(args.generated)
        ]
        files = sorted(
            {*args.model_path.glob("*.safetensors"), *args.model_path.glob("*.json"), *args.model_path.glob("*.txt")}
        )
        if not any(path.suffix == ".safetensors" for path in files):
            raise ValueError("Local safetensors weights required")
        report["workload"] = {
            "modelFiles": {path.name: file_sha256(path) for path in files},
            "promptTokenIds": prompt_ids,
            "maxNewTokens": args.max_new_tokens,
        }
        options = dict(
            model_path=str(args.model_path),
            dtype="float16",
            attention_backend="triton",
            sampling_backend="pytorch",
            enable_deterministic_inference=args.deterministic,
            disable_radix_cache=True,
            disable_cuda_graph=args.disable_cuda_graph,
            cuda_graph_max_bs_decode=128,
            max_running_requests=128,
            context_length=1024,
            mem_fraction_static=args.memory_fraction,
            random_seed=0,
            skip_tokenizer_init=True,
            log_level="warning",
        )
        t0 = time.perf_counter()
        engine = sgl.Engine(**options)
        report["startupSeconds"] = time.perf_counter() - t0
        params = {"temperature": 0.0, "max_new_tokens": args.max_new_tokens, "ignore_eos": False}

        def run(ids):
            outputs = engine.generate(input_ids=ids, sampling_params=params)
            if not isinstance(outputs, list) or len(outputs) != len(ids):
                raise ValueError("Engine returned an unexpected output count")
            return [list(output["output_ids"]) for output in outputs]

        run([prompt_ids[0]])  # unmeasured warmup
        t0 = time.perf_counter()
        report["batched"] = run(prompt_ids)
        report["batchedSeconds"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        report["single"] = [run([ids])[0] for ids in prompt_ids]
        report["serialSeconds"] = time.perf_counter() - t0
        report["batchedVsSingle"] = compare_tokens(report["batched"], report["single"])
        copies = [ids for ids in prompt_ids[:8] for _ in range(args.throughput_copies)]
        t0 = time.perf_counter()
        many = run(copies)
        seconds = time.perf_counter() - t0
        report["throughput"] = {
            "sequences": len(copies),
            "generatedTokens": sum(map(len, many)),
            "seconds": seconds,
            "tokensPerSecondTotal": sum(map(len, many)) / seconds,
            "copiesVsSingle": compare_tokens(
                many, [row for row in report["single"][:8] for _ in range(args.throughput_copies)]
            ),
        }
        t0 = time.perf_counter()
        one = run([prompt_ids[0]])[0]
        report["singleSequenceTokensPerSecond"] = len(one) / (time.perf_counter() - t0)
        report["status"] = "ok"
    except Exception as error:
        traceback.print_exc()
        report.update(status="error", errorType=type(error).__name__, error=str(error)[:3000])
    finally:
        if engine is not None:
            engine.shutdown()
        report["wallSeconds"] = time.perf_counter() - started
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
    print(json.dumps({"status": report["status"], "out": str(args.out)}))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
