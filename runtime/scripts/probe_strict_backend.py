#!/usr/bin/env python3
"""Cross-device token/reward probe for the experimental strict CUDA Qwen2 backend (ADR-012).

Needs --gpu and HETEROES_GPU_ACCEPTANCE=1. Local safetensors only (no downloads, no lab/device state).
For the parent and each perturbed candidate it records the candidate weight hash, the prefill logits hash and
the greedy token ids/text hash/reward per prompt, plus timings and memory. Run the same source on each machine,
then compare the `comparison` objects independently. Optional --eager-check compares prefill logits bits with
the slow eager reference on the same device. Finite coverage only: not hardware or quality qualification.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import time

PROMPTS = (
    "Return only the answer: 2 + 2 =",
    "Q: Tom has 3 apples and buys 5 more. How many apples does he have? Answer with a number.\nA:",
    "Write the next number in the sequence 2, 4, 8, 16,",
    "Natalia sold clips to 48 of her friends in April, and then she sold half as many clips to her friends in "
    "May. How many clips did Natalia sell altogether in April and May? Think step by step, then give the final "
    "number.",
    "Translate to French: The cat is sleeping on the warm windowsill.",
    "A train travels 60 kilometres per hour for 2.5 hours, then 80 kilometres per hour for 1.5 hours. "
    "Explain how far it travels in total, showing each step of the calculation, and finish with the total "
    "distance in kilometres as a single integer on the last line. Be careful with the multiplication and the "
    "addition, and do not skip any intermediate result. The answer is",
    "List three prime numbers greater than 50:",
    "def fibonacci(n):\n    ",
)
EXPECTED = (4, 8, 32, 72, None, 270, None, None)


def generated_prompts(count):
    """Deterministic templated word problems (no RNG), shared with the vLLM comparison probe."""
    names = ("Ana", "Binh", "Chi", "Duc", "Emma", "Fatima", "Goro", "Hana")
    items = ("apples", "pencils", "marbles", "stickers", "books", "coins")
    prompts = []
    for i in range(count):
        a, b, c = 3 + (i * 7) % 41, 2 + (i * 11) % 23, 2 + (i * 5) % 9
        prompts.append(
            f"{names[i % 8]} has {a} {items[i % 6]}. She buys {b} more, then gives away a {c}th of what she has, "
            f"rounded down. How many {items[i % 6]} are left? Explain step by step and end with the number."
        )
    return prompts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--candidates", type=int, default=4, help="perturbed candidates besides the parent")
    parser.add_argument("--prompts", type=int, default=len(PROMPTS))
    parser.add_argument("--max-new-tokens", type=int, default=48)
    parser.add_argument("--seed", type=int, default=7001)
    parser.add_argument("--sigma", type=float, default=1e-3)
    parser.add_argument("--max-context", type=int, default=512)
    parser.add_argument("--eager-check", type=int, default=0, help="prompts whose prefill logits use eager too")
    parser.add_argument("--generated", type=int, default=0, help="extra templated prompts after the fixed ones")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("Evidence already exists; choose a fresh --out")
    if not args.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        parser.error("This probe requires --gpu and HETEROES_GPU_ACCEPTANCE=1")
    if (
        not 0 <= args.candidates <= 1000
        or not 1 <= args.prompts <= len(PROMPTS)
        or not 1 <= args.max_new_tokens
        or not 0 <= args.generated <= 10000
    ):
        parser.error("Invalid candidate/prompt/token limits")

    import torch
    import transformers

    from heteroes.canonical import canonical_json_hash
    from heteroes.es.perturb import perturb_model_
    from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
    from heteroes.eval.candidate import model_weights_sha256, tensors_sha256
    from heteroes.eval.phase_trace import storage_inventory
    from heteroes.eval.qwen2_reference import Qwen2Reference
    from heteroes.eval.qwen2_strict_cuda import Qwen2StrictCuda
    from heteroes.eval.workload import extract_integer
    from heteroes.model.schema import build_parameter_schema
    from heteroes.noise.contracts import ENGINE_V2
    from heteroes.v3.model import file_manifest, load

    if not torch.cuda.is_available():
        parser.error("CUDA unavailable")

    def digest(tensor):
        return hashlib.sha256(tensor.detach().cpu().contiguous().numpy().tobytes()).hexdigest()

    def synchronized():
        torch.cuda.synchronize()
        return time.perf_counter()

    report = {
        "formatVersion": 1,
        "status": "running",
        "hardwareQualified": False,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "gpu": torch.cuda.get_device_name(0),
            "computeCapability": list(torch.cuda.get_device_capability(0)),
        },
        "limitations": "Finite prompts/candidates on one model; no native Windows, managed lifecycle, quality, "
        "learning or universal hardware qualification. Host wall timings include synchronization.",
        "timings": [],
    }
    started = time.perf_counter()
    try:
        torch.cuda.reset_peak_memory_stats()
        files = file_manifest(args.model_path)
        model, tokenizer = load(args.model_path, files, "cuda")
        backend = Qwen2StrictCuda(model, max_context=args.max_context)
        schema = build_parameter_schema(model)
        snapshot = take_snapshot(model, schema)
        report["backendIdentity"] = backend.identity
        report["storage"] = storage_inventory({"inference": backend})
        report["snapshotBytes"] = sum(t.untyped_storage().nbytes() for t in snapshot.tensors)
        comparison = {
            "backendFingerprint": backend.fingerprint,
            "modelFilesHash": canonical_json_hash(files),
            "schemaHash": schema.hash,
            "parentBeforeSha256": tensors_sha256(snapshot.tensors),
            "noiseEngine": ENGINE_V2,
            "sigma": args.sigma,
            "maxNewTokens": args.max_new_tokens,
            "candidates": [],
        }
        report["comparison"] = comparison
        texts = list(PROMPTS[: args.prompts]) + generated_prompts(args.generated)
        prompts = [tokenizer(text, return_tensors="pt")["input_ids"].cuda() for text in texts]
        candidates = [("parent", None, 0.0)]
        for index in range(args.candidates):
            # Antithetic pairs: seed s with +sigma and -sigma, as ES rollouts use them.
            sign = 1.0 if index % 2 == 0 else -1.0
            candidates.append((f"c{index}", args.seed + index // 2, sign * args.sigma))
        for name, seed, sigma in candidates:
            entry = {"name": name, "seed": seed, "sigma": sigma, "prompts": []}
            comparison["candidates"].append(entry)
            try:
                t0 = synchronized()
                if seed is not None:
                    perturb_model_(model, schema, seed, sigma, engine=ENGINE_V2)
                t1 = synchronized()
                entry["weightsSha256"] = model_weights_sha256(model, schema)
                generated = 0
                rollout = 0.0
                for number, ids in enumerate(prompts):
                    logits, _ = backend.forward_tokens(ids)
                    case = {"promptTokens": ids.shape[1], "prefillLogitsSha256": digest(logits)}
                    if name == "parent" and number < args.eager_check:
                        eager = Qwen2Reference(model, max_context=args.max_context).forward_tokens(ids)[0]
                        case["eagerPrefillLogitsEqual"] = bool(
                            torch.equal(eager.view(torch.int32), logits.view(torch.int32))
                        )
                    s = synchronized()
                    output = backend.generate(ids, max_new_tokens=args.max_new_tokens, do_sample=False)
                    rollout += synchronized() - s
                    tokens = output[0, ids.shape[1] :].tolist()
                    generated += len(tokens)
                    text = tokenizer.decode(tokens, skip_special_tokens=True)
                    case.update(
                        tokenIds=tokens,
                        textSha256=hashlib.sha256(text.encode()).hexdigest(),
                        text=text,
                    )
                    if number < len(EXPECTED) and EXPECTED[number] is not None:
                        case["reward"] = float(extract_integer(text) == EXPECTED[number])
                    entry["prompts"].append(case)
            finally:
                t2 = synchronized()
                restore_from_snapshot_(model, schema, snapshot)
                t3 = synchronized()
            report["timings"].append(
                {
                    "candidate": name,
                    "perturbSeconds": t1 - t0,
                    "rolloutSeconds": rollout,
                    "restoreSeconds": t3 - t2,
                    "generatedTokens": generated,
                    "tokensPerSecond": generated / rollout if rollout else None,
                }
            )
        comparison["parentAfterSha256"] = model_weights_sha256(model, schema)
        comparison["restoreExact"] = comparison["parentAfterSha256"] == comparison["parentBeforeSha256"]
        if not comparison["restoreExact"]:
            raise ValueError("Parent restore mismatch")
        report["kernelIdentity"] = backend.kernel_identity()
        report["status"] = "ok"
    except Exception as error:
        report.update(status="error", errorType=type(error).__name__, error=str(error)[:2000])
    finally:
        report["wallSeconds"] = time.perf_counter() - started
        report["cudaPeakAllocatedBytes"] = torch.cuda.max_memory_allocated()
        report["cudaPeakReservedBytes"] = torch.cuda.max_memory_reserved()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "out": str(args.out), "wallSeconds": report["wallSeconds"]}))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
