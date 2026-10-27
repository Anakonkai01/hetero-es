#!/usr/bin/env python3
"""
M0 per-phase trace and memory map of the strict B22 worker path on a trained model, through the candidate executor.

A managed worker's numerical path for `strict_b22_v1` (ADR-013), measured on one GPU: model load, strict engine build,
then antithetic candidates with the executor's own phases (perturb, refresh, rollout, restore). Each phase is
synchronized before and after, so its wall time and CUDA peak belong to that phase. The receipt also lists the live
storage per role (FP16 weights, strict engine buffers), the CPU restore snapshot and the process peak host memory.

    HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=runtime/src python acceptance/probes/strict_phase_trace.py --gpu \\
        --model <dir with a trained model> --out receipt.json

Finite evidence only: one host, one model and workload. Synchronizing every phase adds a little time; network
transfer, coordinator scoring/update and multi-worker scheduling are outside this probe (they are M5).
"""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import tempfile
import time

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--model", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--rows", type=int, default=32, help="prompts per candidate (the batch)")
p.add_argument("--chunk", type=int, default=32, help="rows decoded together")
p.add_argument("--max-new-tokens", type=int, default=128)
p.add_argument("--pairs", type=int, default=3, help="antithetic pairs; the first pair is the cold start")
p.add_argument("--gpu", action="store_true")
a = p.parse_args()
if not a.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or a.out.exists():
    p.error("GPU opt-in (--gpu and HETEROES_GPU_ACCEPTANCE=1) and a fresh --out are required")
if a.pairs < 2:
    p.error("at least two pairs: one cold, one warm")

import torch  # noqa: E402
import transformers  # noqa: E402

from heteroes.canonical import canonical_json_hash  # noqa: E402
from heteroes.catalog import STRICT_B22_DECODER  # noqa: E402
from heteroes.eval import strict_backend  # noqa: E402
from heteroes.eval.candidate import model_weights_sha256  # noqa: E402
from heteroes.eval.phase_trace import storage_inventory  # noqa: E402
from heteroes.executor import CandidateExecutor  # noqa: E402
from heteroes.manifest import CandidateDescriptor  # noqa: E402
from heteroes.product.files import write_json  # noqa: E402
from heteroes.product.v3 import prepare_run  # noqa: E402
from heteroes.v3 import data  # noqa: E402
from heteroes.v3.model import file_manifest  # noqa: E402

GIB = 2**30


def sha(value):
    return hashlib.sha256(value).hexdigest()


def host_peak_bytes():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024  # Linux reports KiB


class SyncedTrace:
    """The executor's phase hook: synchronized wall time and the CUDA peak of each phase."""

    def __init__(self):
        self.events = []
        self.label = None

    @contextmanager
    def phase(self, name, *, candidate_id, generation, recipe_hash, device):
        with self.measure(name, candidateId=candidate_id, pass_=self.label):
            yield

    @contextmanager
    def measure(self, name, **fields):
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        before = torch.cuda.memory_allocated()
        start = time.perf_counter()
        status = "error"
        try:
            yield
            status = "ok"
        finally:
            torch.cuda.synchronize()
            self.events.append(
                {
                    "phase": name,
                    **{k.rstrip("_"): v for k, v in fields.items()},
                    "status": status,
                    "wallSeconds": time.perf_counter() - start,
                    "allocatedBeforeBytes": before,
                    "allocatedAfterBytes": torch.cuda.memory_allocated(),
                    "peakAllocatedBytes": torch.cuda.max_memory_allocated(),
                    "peakReservedBytes": torch.cuda.max_memory_reserved(),
                    "hostPeakBytes": host_peak_bytes(),
                }
            )


def config_for(root):
    rows = [
        {"prompt": f"What is {i} plus {i % 7 + 2}? Answer with a number.", "label": str(i + i % 7 + 2)}
        for i in range(64)
    ]
    dataset = data.build(rows)
    write_json(root / "dataset.json", dataset)
    files = file_manifest(a.model)
    manifest = {
        "formatVersion": 1,
        "modelId": a.model.name,
        "revision": canonical_json_hash(files)[:40],
        "tokenizerRevision": canonical_json_hash(files)[:40],
        "format": "safetensors",
        "files": files,
    }
    write_json(root / "model-manifest.json", manifest)
    return {
        "runId": "0" * 32,
        "recipeVersion": 3,
        "modelPath": str(a.model),
        "modelManifest": manifest,
        "modelManifestPath": str(root / "model-manifest.json"),
        "datasetPath": str(root / "dataset.json"),
        "datasetIdentity": {k: dataset[k] for k in ("contentHash", "splitHashes")},
        "maxGenerations": 1,
        "candidatesPerGeneration": 2 * a.pairs,
        "alpha": 0.001,
        "sigma": 0.001,
        "sigmaMinimum": 0.001,
        "sigmaSchedule": "constant",
        "batchSize": a.rows,
        "batchSeed": 11,
        "maxNewTokens": a.max_new_tokens,
        "systemPrompt": None,
        "antithetic": True,
        "coefficientRule": "zscore@1",
        "weightSpace": {"kind": "full"},
        "scorer": {
            "kind": "declarative",
            "name": "exact-string",
            "version": 1,
            "codeSha256": None,
            "config": {"answerField": "label", "strip": True, "casefold": False},
        },
        "decodeEngine": STRICT_B22_DECODER,
        "evalDtype": "float16",
        "evalChunk": a.chunk,
        "workerIds": ["probe"],
        "host": "127.0.0.1",
        "port": 0,
        "schedulerPolicy": "greedy",
        "syncMode": "synchronous",
    }


report = {
    "status": "running",
    "probeSha256": sha(Path(__file__).read_bytes()),
    "decoder": STRICT_B22_DECODER,
    "settings": {"rows": a.rows, "chunk": a.chunk, "maxNewTokens": a.max_new_tokens, "pairs": a.pairs},
    "environment": {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "platform": platform.platform(),
        "gpu": torch.cuda.get_device_name(),
        "computeCapability": list(torch.cuda.get_device_capability()),
        "gpuTotalBytes": torch.cuda.mem_get_info()[1],
    },
    "timingKind": "host_wall_synchronized_per_phase",
}
trace = SyncedTrace()
try:
    with tempfile.TemporaryDirectory(prefix="strict-phase-trace-") as scratch:
        root = Path(scratch)
        cfg = config_for(root)
        with trace.measure("load"):
            loaded, run, dataset = prepare_run(cfg, root, device="cuda")
        report["model"] = {"id": cfg["modelManifest"]["modelId"], "revision": cfg["modelManifest"]["revision"]}
        report["recipeHash"] = run.hash
        with trace.measure("engine"):
            executor = CandidateExecutor(
                loaded.model, loaded.tokenizer, loaded.schema, run, dataset=dataset, return_completions=True,
                chunk=a.chunk, phase_trace=trace,
            )  # fmt: skip
            executor.set_generation(0, run.context(dataset, 0))
        engine = strict_backend.engine_for(loaded.model)
        parent = model_weights_sha256(loaded.model, loaded.schema)
        texts, tokens = {}, {}
        for pair in range(a.pairs):
            trace.label = "cold" if pair == 0 else "warm"
            for sign in (1, -1):
                descriptor = CandidateDescriptor(
                    run.hash, parent, "0" * 32, 0, 2 * pair + (sign < 0), 7001 + pair, sign=sign
                )
                batch = executor(descriptor)
                texts[descriptor.candidate_id] = sha(json.dumps(list(batch)).encode())
                tokens[descriptor.candidate_id] = {
                    **executor.last_timing,
                    "generatedTokens": sum(batch.usage["generatedTokens"]),
                }
                if model_weights_sha256(loaded.model, loaded.schema) != parent:
                    raise RuntimeError("restore did not return the parent weights")
        engine_bytes = sum(b.untyped_storage().nbytes() for b in engine.buffers() if b.device.type == "cuda")
        snapshot = getattr(executor, "_snapshot", None)
        report["memoryMap"] = {
            "liveStorage": storage_inventory({"liveFp16Weights": loaded.model}),
            "strictEngineBufferBytes": engine_bytes,
            "cpuRestoreSnapshotBytes": None
            if snapshot is None
            else sum(t.untyped_storage().nbytes() for t in snapshot.tensors),
            "cudaAllocatedAtEndBytes": torch.cuda.memory_allocated(),
            "cudaReservedAtEndBytes": torch.cuda.memory_reserved(),
            "hostPeakBytes": host_peak_bytes(),
            "fp32ParametersOnGpu": any(p.dtype == torch.float32 and p.is_cuda for p in loaded.model.parameters()),
        }
        report["candidates"] = {"textSha256": texts, "executorTiming": tokens}
        report["parentSha256"] = parent
    events = trace.events
    report["phases"] = events
    summary = {}
    for event in events:
        key = event["phase"] if event.get("pass") is None else f"{event['pass']}:{event['phase']}"
        row = summary.setdefault(key, {"count": 0, "wallSeconds": 0.0, "peakAllocatedBytes": 0, "peakReservedBytes": 0})
        row["count"] += 1
        row["wallSeconds"] += event["wallSeconds"]
        row["peakAllocatedBytes"] = max(row["peakAllocatedBytes"], event["peakAllocatedBytes"])
        row["peakReservedBytes"] = max(row["peakReservedBytes"], event["peakReservedBytes"])
    for row in summary.values():
        row["meanWallSeconds"] = row["wallSeconds"] / row["count"]
        row["peakAllocatedGiB"] = round(row["peakAllocatedBytes"] / GIB, 3)
    report["summary"] = summary
    report["status"] = "PASS" if all(e["status"] == "ok" for e in events) else "FAIL"
except Exception as error:
    report["status"] = "FAIL"
    report["error"] = f"{type(error).__name__}: {error}"
    report["phases"] = trace.events
a.out.parent.mkdir(parents=True, exist_ok=True)
a.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
print(f"STRICT PHASE TRACE {report['status']}")
for key, row in report.get("summary", {}).items():
    print(
        f"  {key:16s} n={row['count']:2d} mean={row['meanWallSeconds']:8.3f}s peak={row['peakAllocatedGiB']:6.3f} GiB"
    )
raise SystemExit(0 if report["status"] == "PASS" else 1)
