#!/usr/bin/env python3
"""Compare the NEW integer graph with the FP32 tree on one local model and canonical candidates.

Finite numerical/sensitivity measurements, not a model-quality benchmark or hardware qualification. All engines
share the original FP16 weights. Graph state is released between engine measurements. No learning or lab operation.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import time


def logit_metrics(reference, actual):
    import torch

    if reference.shape != actual.shape or reference.ndim != 2 or not reference.numel():
        raise ValueError("Logit metrics require equal nonempty row matrices")
    reference, actual = reference.detach().cpu().double(), actual.detach().cpu().double()
    if not torch.isfinite(reference).all() or not torch.isfinite(actual).all():
        raise ValueError("Nonfinite logits cannot produce a valid comparison")
    difference = actual - reference
    rms = difference.square().mean().sqrt().item()
    reference_rms = reference.square().mean().sqrt().item()
    left, right = reference.log_softmax(-1), actual.log_softmax(-1)
    return {
        "rows": reference.shape[0],
        "maxAbsoluteError": difference.abs().max().item(),
        "rmsError": rms,
        "relativeRmsError": rms / reference_rms if reference_rms else None,
        "top1EqualRows": int((reference.argmax(-1) == actual.argmax(-1)).sum()),
        "meanKLDivergence": (left.exp() * (left - right)).sum(-1).mean().item(),
    }


def token_comparison(reference, actual):
    if len(reference) != len(actual) or any(len(a) != len(b) for a, b in zip(reference, actual)):
        raise ValueError("Token comparisons require the same row/output lengths")
    return {
        "rows": len(reference),
        "equalRows": sum(a == b for a, b in zip(reference, actual)),
        "equalTokenPositions": sum(x == y for a, b in zip(reference, actual) for x, y in zip(a, b)),
        "totalTokenPositions": sum(map(len, reference)),
        "firstDivergence": [
            next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None) for a, b in zip(reference, actual)
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--sigma", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=7001)
    parser.add_argument("--max-new-tokens", type=int, default=32)
    parser.add_argument("--max-context", type=int, default=512)
    parser.add_argument("--integer-bits", type=int, nargs="+", choices=(14, 22), default=[14, 22])
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("Evidence exists; choose a fresh --out")
    if not args.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        parser.error("Requires --gpu and HETEROES_GPU_ACCEPTANCE=1")
    if (
        not math.isfinite(args.sigma)
        or not 0 < args.sigma <= 1
        or not 0 <= args.seed < 2**53
        or not 1 <= args.max_new_tokens <= 256
        or not 1 <= args.max_context <= 4096
    ):
        parser.error("Invalid finite probe limits")

    import torch
    import transformers

    from heteroes.canonical import canonical_json_hash
    from heteroes.es.perturb import perturb_model_
    from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.strict.integer_decoder import IntegerDecoderGraph
    from heteroes.strict.strict_decoder_graph import StrictDecoderGraph
    from heteroes.eval.workload import extract_integer
    from heteroes.model.schema import build_parameter_schema
    from heteroes.noise.contracts import ENGINE_V2
    from heteroes.v3.model import file_manifest, load
    from probe_strict_backend import PROMPTS, EXPECTED

    report = {
        "formatVersion": 1,
        "status": "running",
        "hardwareQualified": False,
        "sourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "platform": platform.platform(),
            "gpu": torch.cuda.get_device_name(),
            "computeCapability": list(torch.cuda.get_device_capability()),
        },
        "limitations": "Eight canned prompts, parent and one antithetic canonical seed pair, plus restored parent. "
        "Prefill logit differences and autoregressive token agreement are not general model quality. "
        "Single warm/cold wall measurements include compilation/capture, not steady throughput. "
        "No learning, managed lifecycle, native Windows or hardware qualification.",
        "noiseEngine": ENGINE_V2,
        "sigma": args.sigma,
        "seed": args.seed,
        "maxContext": args.max_context,
        "maxNewTokens": args.max_new_tokens,
        "cases": [],
    }
    started = time.perf_counter()

    def digest(tensor):
        return hashlib.sha256(tensor.detach().cpu().contiguous().numpy().tobytes()).hexdigest()

    try:
        files = file_manifest(args.model_path)
        model, tokenizer = load(args.model_path, files, "cuda")
        schema = build_parameter_schema(model)
        snapshot = take_snapshot(model, schema)
        parent_hash = model_weights_sha256(model, schema)
        report.update(
            modelFiles=files,
            modelFilesHash=canonical_json_hash(files),
            schemaHash=schema.hash,
            parentSha256=parent_hash,
            snapshotBytes=sum(t.numel() * t.element_size() for t in snapshot.tensors),
        )
        engines = {"fp32-tree": StrictDecoderGraph(model, max_context=args.max_context, max_graph_bytes=4 * 1024**3)}
        for bits in dict.fromkeys(args.integer_bits):
            engines[f"integer-b{bits}"] = IntegerDecoderGraph(
                model, magnitude_bits=bits, max_context=args.max_context, max_graph_bytes=4 * 1024**3
            )
        report["backendIdentities"] = {name: engine.identity for name, engine in engines.items()}
        prompts = [tokenizer(text, return_tensors="pt")["input_ids"].cuda() for text in PROMPTS]
        if max(p.shape[1] for p in prompts) + args.max_new_tokens > args.max_context:
            raise ValueError("Prompt/output exceeds context")
        report["promptTokenIds"] = [p[0].tolist() for p in prompts]
        width = max(p.shape[1] for p in prompts)
        ids = torch.zeros((len(prompts), width), dtype=torch.long, device="cuda")
        mask = torch.zeros_like(ids)
        for i, prompt in enumerate(prompts):
            ids[i, -prompt.shape[1] :] = prompt[0]
            mask[i, -prompt.shape[1] :] = 1
        parent_outputs, parent_logits = {}, {}
        torch.cuda.reset_peak_memory_stats()
        for state, seed, sigma in (
            ("parent", None, 0),
            ("plus", args.seed, args.sigma),
            ("minus", args.seed, -args.sigma),
            ("restored", None, 0),
        ):
            case = {"state": state, "seed": seed, "sigma": sigma, "engines": {}}
            report["cases"].append(case)
            try:
                if seed is not None:
                    perturb_model_(model, schema, seed, sigma, engine=ENGINE_V2)
                case["weightsSha256"] = model_weights_sha256(model, schema)
                reference_logits, reference_tokens = None, None
                for name, engine in engines.items():
                    torch.cuda.synchronize()
                    begin = time.perf_counter()
                    logits, caches = engine.forward_batch(prompts)
                    del caches
                    output = engine.generate(
                        ids,
                        attention_mask=mask,
                        max_new_tokens=args.max_new_tokens,
                        eos_token_id=[],
                        pad_token_id=0,
                        repetition_penalty=1.0,
                    )
                    tokens = output[:, width:].tolist()
                    torch.cuda.synchronize()
                    measured = time.perf_counter() - begin
                    # One independent row checks the packed operator path on this trained graph.
                    serial_logits, cache = engine.forward_tokens(prompts[0])
                    if digest(serial_logits) != digest(logits[:1]):
                        raise ValueError(f"{name} packed/serial prefill mismatch")
                    del cache
                    texts = [tokenizer.decode(row, skip_special_tokens=True) for row in tokens]
                    result = {
                        "prefillLogitsSha256": digest(logits),
                        "tokens": tokens,
                        "texts": texts,
                        "secondsIncludingWarmup": measured,
                        "rewards": [
                            float(extract_integer(text) == expected) if expected is not None else None
                            for text, expected in zip(texts, EXPECTED)
                        ],
                        "packedFirstRowLogitsEqualSerial": True,
                    }
                    case["engines"][name] = result
                    if reference_logits is None:
                        reference_logits, reference_tokens = logits.detach().cpu(), tokens
                    else:
                        result["prefillComparedToFp32Tree"] = logit_metrics(reference_logits, logits)
                        result["tokensComparedToFp32Tree"] = token_comparison(reference_tokens, tokens)
                    if state == "parent":
                        parent_outputs[name], parent_logits[name] = tokens, logits.detach().cpu()
                    else:
                        result["tokensComparedToParent"] = token_comparison(parent_outputs[name], tokens)
                        result["prefillComparedToParent"] = logit_metrics(parent_logits[name], logits)
                        if state == "restored" and (
                            tokens != parent_outputs[name] or digest(logits) != digest(parent_logits[name])
                        ):
                            raise ValueError(f"{name} restored parent inference mismatch")
                    engine.release_graph()
                    del logits, output
            finally:
                # Frozen canonical restore, even after an arithmetic/reporting error.
                restore_from_snapshot_(model, schema, snapshot)
                restored = model_weights_sha256(model, schema)
                case["restoreExact"] = restored == parent_hash
                if not case["restoreExact"]:
                    raise ValueError("Exact parent restore failed")
        report["kernelIdentities"] = {name: engine.kernel_identity() for name, engine in engines.items()}
        report["cudaPeakAllocatedBytes"] = torch.cuda.max_memory_allocated()
        report["cudaPeakReservedBytes"] = torch.cuda.max_memory_reserved()
        report["status"] = "ok"
    except Exception as error:
        report.update(status="error", errorType=type(error).__name__, error=str(error)[:2000])
    report["wallSeconds"] = time.perf_counter() - started
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "out": str(args.out), "wallSeconds": report["wallSeconds"]}))
    return int(report["status"] != "ok")


if __name__ == "__main__":
    raise SystemExit(main())
