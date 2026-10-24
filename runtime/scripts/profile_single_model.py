#!/usr/bin/env python3
"""Profile a single native FP16 model's lifecycle without a shadow (ADR-012).

This is a resource/timing baseline, not a strict cross-device inference backend.
CPU is the default. CUDA requires --device cuda --gpu and HETEROES_GPU_ACCEPTANCE=1.
Local safetensors only; no network/model downloads, lab state or remote device changes.
"""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import platform


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--candidates", type=int, default=3)
    parser.add_argument("--max-new-tokens", type=int, default=8)
    parser.add_argument("--prompt", default="Return only the answer: 2 + 2 =")
    parser.add_argument("--expected-answer", type=int)
    parser.add_argument("--seed", type=int, default=7001)
    parser.add_argument("--sigma", type=float, default=1e-3)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("Evidence already exists; choose a fresh --out")
    if args.device == "cuda" and (not args.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1"):
        parser.error("CUDA requires --gpu and HETEROES_GPU_ACCEPTANCE=1")
    if args.gpu and args.device != "cuda":
        parser.error("--gpu requires --device cuda")
    if not 1 <= args.candidates <= 10000 or not 1 <= args.max_new_tokens <= 4096 or args.threads < 1:
        parser.error("Invalid candidate/token/thread limits")

    import torch

    from heteroes.canonical import canonical_json_hash
    from heteroes.es.perturb import perturb_model_
    from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
    from heteroes.eval.candidate import model_weights_sha256, tensors_sha256
    from heteroes.eval.phase_trace import PhaseTrace, storage_inventory
    from heteroes.eval.workload import extract_integer
    from heteroes.model.schema import build_parameter_schema
    from heteroes.noise.contracts import ENGINE_V2
    from heteroes.v3.model import file_manifest, load

    cuda = args.device == "cuda"
    if cuda and not torch.cuda.is_available():
        parser.error("CUDA is unavailable in this execution environment")
    original_threads = torch.get_num_threads()
    torch.set_num_threads(args.threads)
    events = []
    trace = PhaseTrace(events.append)
    identity = {"candidate_id": None, "generation": None, "recipe_hash": None, "device": args.device}
    report = {
        "formatVersion": 1,
        "status": "running",
        "device": args.device,
        "inferenceBackend": "hf_native_fp16_baseline",
        "strictInference": False,
        "synchronizedPhases": cuda,
        "environment": {"python": platform.python_version(), "torch": torch.__version__, "threads": args.threads},
        "maxNewTokens": args.max_new_tokens,
        "sigma": args.sigma,
        "samples": [],
        "phases": events,
        "cudaPeakAllocatedBytes": None,
        "cudaPeakReservedBytes": None,
        "limitations": [
            "not a cross-device equality test",
            "host wall timings include synchronization overhead on CUDA and are not kernel elapsed time",
            "storage inventory excludes allocator reserve, temporaries, other processes and the CPU snapshot",
            "a finite CPU fixture run does not establish strict inference or native GPU/Windows acceptance",
        ],
    }

    @contextmanager
    def phase(name):
        with trace.phase(name, **identity):
            if cuda:
                torch.cuda.synchronize()
            yield
            if cuda:
                torch.cuda.synchronize()

    try:
        if cuda:
            torch.cuda.reset_peak_memory_stats()
        with phase("model_files_hash"):
            files = file_manifest(args.model_path)
        with phase("model_load"):
            model, tokenizer = load(args.model_path, files, args.device)
        report["modelFilesHash"] = canonical_json_hash(files)
        report["storage"] = storage_inventory({"inference": model})
        schema = build_parameter_schema(model)
        with phase("snapshot"):
            snapshot = take_snapshot(model, schema)
        report["snapshotBytes"] = sum(t.untyped_storage().nbytes() for t in snapshot.tensors)
        with phase("parent_hash"):
            report["parentBeforeSha256"] = tensors_sha256(snapshot.tensors)
        report["schemaHash"] = schema.hash
        with phase("tokenize"):
            encoded = tokenizer(args.prompt, return_tensors="pt").to(args.device)
        report["promptTokenIds"] = encoded["input_ids"][0].tolist()
        width = encoded["input_ids"].shape[-1]
        for index in range(args.candidates):
            identity.update(candidate_id=f"baseline/g0/c{index}", generation=0)
            sample = {"seed": args.seed + index, "restoreExact": False}
            report["samples"].append(sample)
            try:
                with phase("perturb"):
                    perturb_model_(model, schema, sample["seed"], args.sigma, engine=ENGINE_V2)
                with phase("rollout"), torch.inference_mode():
                    output = model.generate(
                        **encoded, max_new_tokens=args.max_new_tokens, do_sample=False, use_cache=True
                    )
                sample["tokenIds"] = output[0, width:].tolist()
                sample["text"] = tokenizer.decode(sample["tokenIds"], skip_special_tokens=True)
                if args.expected_answer is not None:
                    sample["reward"] = float(extract_integer(sample["text"]) == args.expected_answer)
                    report["scorer"] = {"name": "last-integer", "expectedAnswer": args.expected_answer}
            finally:
                with phase("restore"):
                    restore_from_snapshot_(model, schema, snapshot)
                sample["restoreExact"] = True
        with phase("parent_hash_after"):
            report["parentAfterSha256"] = model_weights_sha256(model, schema)
        if report["parentAfterSha256"] != report["parentBeforeSha256"]:
            raise ValueError("Parent hash differs after exact restore")
        report["status"] = "ok"
    except Exception as error:
        report.update(status="error", errorType=type(error).__name__)
    finally:
        if cuda:
            report["cudaPeakAllocatedBytes"] = torch.cuda.max_memory_allocated()
            report["cudaPeakReservedBytes"] = torch.cuda.max_memory_reserved()
        report["droppedTraceEvents"] = trace.dropped_events
        try:
            import resource

            if platform.system() == "Linux":
                report["processPeakResidentBytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            else:
                report["processPeakResidentBytes"] = None
        except ImportError:
            report["processPeakResidentBytes"] = None
        torch.set_num_threads(original_threads)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "out": str(args.out), "samples": len(report["samples"])}))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
