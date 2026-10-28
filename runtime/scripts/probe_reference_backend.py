#!/usr/bin/env python3
"""Portable operator/fixture comparison for the experimental one-model reference.

CPU by default; CUDA needs --device cuda --gpu and HETEROES_GPU_ACCEPTANCE=1.
The deterministic tiny Qwen fixture exercises the graph, not full-model hardware qualification.
Run this same source on each machine, then compare the complete `comparison` objects independently.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import time


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--gpu", action="store_true")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("Evidence already exists; choose a fresh --out")
    if args.device == "cuda" and (not args.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1"):
        parser.error("CUDA requires --gpu and HETEROES_GPU_ACCEPTANCE=1")
    if args.gpu and args.device != "cuda":
        parser.error("--gpu requires --device cuda")

    import torch
    import transformers

    from heteroes.es.perturb import perturb_model_
    from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
    from heteroes.strict import reference_ops as ops
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.eval.phase_trace import storage_inventory
    from heteroes.strict.qwen2_reference import Qwen2Reference
    from heteroes.model.schema import build_parameter_schema
    from heteroes.noise.contracts import ENGINE_V2

    cuda = args.device == "cuda"
    if cuda and not torch.cuda.is_available():
        parser.error("CUDA unavailable")
    original_threads = torch.get_num_threads()
    torch.set_num_threads(2)
    report = {
        "formatVersion": 1,
        "status": "running",
        "hardwareQualified": False,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "device": args.device,
        },
        "limitations": "Tiny fixture and finite operator vectors only; no full-model, native Windows, throughput or universal hardware qualification.",
    }
    started = time.perf_counter()

    def digest(tensor):
        return hashlib.sha256(tensor.detach().cpu().contiguous().numpy().tobytes()).hexdigest()

    try:
        if cuda:
            report["environment"]["gpu"] = torch.cuda.get_device_name(0)
            report["environment"]["computeCapability"] = list(torch.cuda.get_device_capability(0))
            torch.cuda.reset_peak_memory_stats()
        config = transformers.Qwen2Config(
            vocab_size=41,
            hidden_size=16,
            intermediate_size=32,
            num_hidden_layers=2,
            num_attention_heads=4,
            num_key_value_heads=2,
            max_position_embeddings=64,
            tie_word_embeddings=True,
            eos_token_id=40,
            pad_token_id=0,
        )
        model = transformers.Qwen2ForCausalLM(config).half().eval()
        # Integer patterns divided by powers of two publish exactly representable FP16 values.
        # Every random initializer is overwritten, so RNG/library initialization is not fixture identity.
        with torch.no_grad():
            for index, (name, parameter) in enumerate(model.named_parameters()):
                values = ((torch.arange(parameter.numel(), dtype=torch.int64) * 17 + index * 7) % 67 - 33).float() / 256
                if name.endswith("layernorm.weight") or name == "model.norm.weight":
                    values = values + 1.0
                parameter.copy_(values.reshape(parameter.shape))
        model = model.to(args.device)
        reference = Qwen2Reference(model, max_context=64, allow_fixture=True)
        schema = build_parameter_schema(model)
        snapshot = take_snapshot(model, schema)
        report["backendIdentity"] = reference.identity
        report["storage"] = storage_inventory({"inference": reference})
        report["snapshotBytes"] = sum(t.untyped_storage().nbytes() for t in snapshot.tensors)

        # Values originate on CPU, independent of CUDA RNG or device-dependent transcendental inputs.
        x = ((torch.arange(119) * 13) % 97 - 48).float().reshape(7, 17).to(args.device) / 16
        weight = (((torch.arange(221) * 11) % 71 - 35).float().reshape(13, 17) / 32).half().to(args.device)
        angles = torch.tensor([-32768, -2017.25, -3.125, -0.0, 0.0, 0.125, 1.5, 3123.5, 32768], device=args.device)
        sine, cosine = ops.sin_cos(angles)
        edge = torch.tensor(
            [1, -2147483647, 0x00800000, -2139095040, 0x3F800001], dtype=torch.int32, device=args.device
        ).view(torch.float32)
        values = {
            "linear": ops.linear(x, weight, output_tile=5),
            "rmsNorm": ops.rms_norm(x, torch.ones(17, dtype=torch.float16, device=args.device), 1e-6),
            "softmax": ops.softmax(x, (torch.arange(17, device=args.device) < 13)[None, :]),
            "sin": sine,
            "cos": cosine,
            "silu": ops.silu(x),
            "edgeArithmetic": ops.add(ops.mul(edge, 0.5), torch.zeros_like(edge)),
        }
        comparison = {
            "fixture": "integer_qwen2_h16_l2_v1",
            "backendFingerprint": reference.fingerprint,
            "schemaHash": schema.hash,
            "parentBeforeSha256": model_weights_sha256(model, schema),
            "operatorHashes": {name: digest(value) for name, value in values.items()},
            "cases": [],
            "noiseEngine": ENGINE_V2,
            "seed": 73,
            "sigma": 0.003,
        }
        report["comparison"] = comparison
        prompts = [[2, 5, 7, 11, 13], [17, 19, 23]]
        try:
            for state in ("parent", "candidate"):
                if state == "candidate":
                    perturb_model_(model, schema, comparison["seed"], comparison["sigma"], engine=ENGINE_V2)
                    comparison["candidateSha256"] = model_weights_sha256(model, schema)
                for prompt in prompts:
                    ids = torch.tensor([prompt], dtype=torch.long, device=args.device)
                    logits, _ = reference.forward_tokens(ids)
                    output = reference.generate(ids, max_new_tokens=2, eos_token_id=[])
                    tokens = output[0, len(prompt) :].tolist()
                    comparison["cases"].append(
                        {
                            "state": state,
                            "promptTokenIds": prompt,
                            "logitsSha256": digest(logits),
                            "tokenIds": tokens,
                            "reward": float(tokens == [11, 13]),
                        }
                    )
        finally:
            restore_from_snapshot_(model, schema, snapshot)
        comparison["parentAfterSha256"] = model_weights_sha256(model, schema)
        comparison["restoreExact"] = comparison["parentBeforeSha256"] == comparison["parentAfterSha256"]
        if not comparison["restoreExact"]:
            raise ValueError("Parent restore mismatch")
        report["status"] = "ok"
    except Exception as error:
        report.update(status="error", errorType=type(error).__name__)
    finally:
        report["wallSeconds"] = time.perf_counter() - started
        if cuda:
            report["cudaPeakAllocatedBytes"] = torch.cuda.max_memory_allocated()
            report["cudaPeakReservedBytes"] = torch.cuda.max_memory_reserved()
        torch.set_num_threads(original_threads)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "out": str(args.out)}))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
