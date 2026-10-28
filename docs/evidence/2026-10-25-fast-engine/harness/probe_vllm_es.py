#!/usr/bin/env python3
"""Finite standalone vLLM-backed ES candidate/restore and throughput probe, never a managed worker.

Uses a single serving weight set through canonical HF-named views. CPU snapshots are allowed; there
is no second GPU inference model. Vendor inference has a separate, non-strict arithmetic identity.
"""

import argparse
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import platform
import time


def prepare(owner, config):
    import torch

    from heteroes.es.snapshot import take_snapshot
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.eval.vllm_weights import hf_parameter_view
    from heteroes.model.schema import build_parameter_schema

    view = hf_parameter_view(owner, config)
    schema = build_parameter_schema(view)
    snapshot = take_snapshot(view, schema)
    digest = model_weights_sha256(view, schema)
    object.__setattr__(owner, "_heteroes_probe_state", (view, schema, snapshot, digest))
    storages = {p.untyped_storage().data_ptr() for p in owner.parameters()}
    shared = all(p.untyped_storage().data_ptr() in storages for p in view.parameters())
    if not shared:
        raise ValueError("ES view allocated independent weight storage")
    return {
        "schemaHash": schema.hash,
        "parentSha256": digest,
        "allViewStoragesOwnedByVllm": shared,
        "snapshotCpuBytes": sum(t.numel() * t.element_size() for t in snapshot.tensors),
        "device": str(next(view.parameters()).device),
        "torch": torch.__version__,
    }


def select_candidate(owner, state, seed, sigma):
    import torch

    from heteroes.es.perturb import perturb_model_
    from heteroes.es.snapshot import restore_from_snapshot_
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.noise.contracts import ENGINE_V2

    view, schema, snapshot, parent = owner._heteroes_probe_state
    torch.cuda.synchronize()
    begin = time.perf_counter()
    restore_from_snapshot_(view, schema, snapshot)
    if state in ("plus", "minus"):
        perturb_model_(view, schema, seed, sigma if state == "plus" else -sigma, engine=ENGINE_V2)
    torch.cuda.synchronize()
    publication_seconds = time.perf_counter() - begin
    digest = model_weights_sha256(view, schema)
    if state in ("parent", "restored") and digest != parent:
        raise ValueError("Parent restore mismatch")
    return {"weightsSha256": digest, "publicationSeconds": publication_seconds, "parentRestored": digest == parent}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gpu", action="store_true")
    p.add_argument("--model-path", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--repeats", type=int, default=5)
    a = p.parse_args()
    if not a.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        p.error("GPU opt-in required")
    if a.out.exists() or not 1 <= a.repeats <= 10:
        p.error("Choose a fresh output and 1..10 repeats")
    if os.environ.get("VLLM_ENABLE_V1_MULTIPROCESSING") != "0":
        p.error("Standalone single-process probe requires VLLM_ENABLE_V1_MULTIPROCESSING=0")

    import torch
    import transformers
    import vllm
    from transformers import AutoConfig, AutoTokenizer
    from vllm import LLM, SamplingParams

    from benchmark_inference import measure
    from heteroes.eval.vllm_weights import VLLM_VIEW_VERSION
    from heteroes.eval.workload import extract_integer
    from heteroes.noise.contracts import ENGINE_V2
    from heteroes.v3.model import file_manifest
    from probe_strict_backend import EXPECTED, PROMPTS

    report = {
        "status": "running",
        "hardwareQualified": False,
        "backend": "vllm_fp16_canonical_hf_views_es_v1_experimental",
        "view": VLLM_VIEW_VERSION,
        "sourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "noiseEngine": ENGINE_V2,
        "seed": 7001,
        "sigma": 1e-3,
        "cases": [],
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "vllm": vllm.__version__,
            "gpu": torch.cuda.get_device_name(),
            "cuda": torch.version.cuda,
            "sampler": os.environ.get("VLLM_USE_FLASHINFER_SAMPLER", "default"),
        },
        "limitations": "Finite three-batch canned-prompt probe. Vendor inference is not B22 arithmetic. "
        "No learning, managed lifecycle, production activation or general model quality.",
    }
    engine = None
    prepared = False
    begin = time.perf_counter()
    try:
        report["modelFiles"] = file_manifest(a.model_path)
        config = AutoConfig.from_pretrained(a.model_path, local_files_only=True, trust_remote_code=False)
        tokenizer = AutoTokenizer.from_pretrained(a.model_path, local_files_only=True, trust_remote_code=False)
        prompts = [tokenizer(text)["input_ids"] for text in PROMPTS]
        report["promptTokenIds"] = prompts
        engine = LLM(
            model=str(a.model_path),
            dtype="float16",
            max_model_len=512,
            gpu_memory_utilization=0.35,
            seed=0,
            enable_prefix_caching=False,
        )

        def one(callback):
            result = engine.apply_model(callback)
            if len(result) != 1:
                raise ValueError("Only a single unsharded model owner is supported")
            return result[0]

        report["preparation"] = one(partial(prepare, config=config))
        prepared = True
        params = SamplingParams(temperature=0.0, max_tokens=32, ignore_eos=True, repetition_penalty=1.0)

        def run(rows):
            return [
                list(r.outputs[0].token_ids)
                for r in engine.generate([{"prompt_token_ids": ids} for ids in rows], params, use_tqdm=False)
            ]

        parent_tokens = {}
        for state in ("parent", "plus", "minus", "restored"):
            publication = one(partial(select_candidate, state=state, seed=7001, sigma=1e-3))
            if not engine.reset_prefix_cache():
                raise ValueError("Could not reset serving cache after candidate publication")
            case = {"state": state, **publication, "batches": []}
            report["cases"].append(case)
            for batch in (1, 8, 32):
                rows = [prompts[i % len(prompts)] for i in range(batch)]
                if state == "parent":
                    result = measure(run, rows, 32, a.repeats, torch.cuda.synchronize)
                    parent_tokens[batch] = result["tokens"]
                else:
                    result = {"tokens": run(rows), "sequences": batch}
                texts = [tokenizer.decode(row, skip_special_tokens=True) for row in result["tokens"]]
                result.update(
                    texts=texts,
                    rewards=[
                        float(extract_integer(text) == EXPECTED[i % len(EXPECTED)])
                        if EXPECTED[i % len(EXPECTED)] is not None
                        else None
                        for i, text in enumerate(texts)
                    ],
                )
                if state == "restored" and result["tokens"] != parent_tokens[batch]:
                    raise ValueError("Restored serving tokens differ from parent")
                case["batches"].append(result)
        report["status"] = "ok"
    except Exception as error:
        report.update(status="error", errorType=type(error).__name__, error=str(error)[:2000])
    finally:
        if prepared:
            try:
                result = engine.apply_model(partial(select_candidate, state="restored", seed=7001, sigma=1e-3))
                report["finalRestore"] = result[0]
                if len(result) != 1 or not result[0]["parentRestored"]:
                    raise ValueError("Final exact restore failed")
            except Exception as error:
                report.update(status="error", restoreError=str(error)[:2000])
    report["wallSeconds"] = time.perf_counter() - begin
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("x") as f:
        json.dump(report, f, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({"status": report["status"], "out": str(a.out), "wallSeconds": report["wallSeconds"]}))
    return int(report["status"] != "ok")


if __name__ == "__main__":
    raise SystemExit(main())
