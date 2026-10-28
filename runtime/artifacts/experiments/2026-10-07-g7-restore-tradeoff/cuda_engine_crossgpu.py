"""
The check that decides whether the CUDA noise engine (G7, S1) can be used between two GPUs: on the REAL model, the noise fingerprint, the hash of
all the weights after a perturbation and after an update with the CUDA engine, the restore from the snapshot, and the times. Run it on
each machine and compare the JSON files: every `sha256` and the fingerprint must be equal.
Usage: python cuda_engine_crossgpu.py --model-path SNAP --out FILE
"""
import argparse, json, sys, time
from pathlib import Path

import torch

from heteroes.es.cuda_ops import apply_coefficients_cuda_, perturb_model_cuda_
from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.eval.candidate import model_weights_sha256
from heteroes.model.loading import load_pinned_model
from heteroes.noise.cuda_engine import CUDA_ENGINE_VERSION, compute_noise_fingerprint


def timed(fn, *args):
    torch.cuda.synchronize(); t = time.perf_counter()
    fn(*args)
    torch.cuda.synchronize()
    return time.perf_counter() - t


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model-path", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to overwrite {out}")
    loaded = load_pinned_model(a.model_path, "cuda")
    model, schema = loaded.model, loaded.schema
    props = torch.cuda.get_device_properties(0)
    result = {"gpu": props.name, "sm_count": props.multi_processor_count, "torch": torch.__version__, "cuda": torch.version.cuda,
              "engine": CUDA_ENGINE_VERSION, "fingerprint": compute_noise_fingerprint(), "schema_hash": schema.hash,
              "sha256": {"original": model_weights_sha256(model, schema)}, "seconds": {}}
    snapshot = take_snapshot(model, schema)
    for seed in (0, 1, 2):
        result["seconds"][f"cuda_perturb_seed{seed}"] = timed(perturb_model_cuda_, model, schema, seed, 1e-3)
        result["sha256"][f"perturbed_seed{seed}"] = model_weights_sha256(model, schema)
        restore_from_snapshot_(model, schema, snapshot)
        result["sha256"][f"restored_after_seed{seed}"] = model_weights_sha256(model, schema)
    seeds, coefficients = [10, 11, 12, 13, 14, 15, 16, 17], [1.5, -0.5, 0.25, -1.25, 0.75, -0.75, 0.5, -0.5]
    result["seconds"]["cuda_update_8_candidates"] = timed(lambda: apply_coefficients_cuda_(model, schema, seeds, coefficients, 1e-3))
    result["sha256"]["updated"] = model_weights_sha256(model, schema)
    restore_from_snapshot_(model, schema, snapshot)
    result["seconds"]["cpu_canonical_perturb_seed0"] = timed(perturb_model_, model, schema, 0, 1e-3)
    restore_from_snapshot_(model, schema, snapshot)
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
