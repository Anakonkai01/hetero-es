#!/usr/bin/env python3
"""Explicitly authorized full/LoRA qualification and real model noise/perturb/update timing.

This does not run a learning experiment. Use a fresh --out, a pinned --reference and --adapter.
"""

import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        parser.error("GPU checks require explicit owner authorization and HETEROES_GPU_ACCEPTANCE=1")
    if args.out.exists():
        raise FileExistsError(args.out)
    from heteroes.product.qualification_v3 import qualify

    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    started = time.perf_counter()
    result = qualify(args.model, reference, args.reference.parent, emit=lambda e: print(json.dumps(e), flush=True))
    result["qualificationSeconds"] = time.perf_counter() - started
    import torch
    from heteroes.v3.model import load, trainable_schema
    from heteroes.noise.contracts import CPU_ENGINES, DEFAULT_CHUNK_ELEMENTS, ParameterNoiseAddress
    from heteroes.noise.engine import iter_parameter_noise_chunks
    from heteroes.noise.parallel import noise_threads
    from heteroes.es.perturb import perturb_model_
    from heteroes.es.update import apply_coefficients_
    from heteroes.es.snapshot import take_snapshot, restore_from_snapshot_
    from heteroes.eval.candidate import model_weights_sha256

    model, _ = load(args.model, reference["cells"]["full"]["recipe"]["model"]["files"], "cuda")
    schema = trainable_schema(model, {"kind": "full"})
    snapshot = take_snapshot(model, schema)
    parent = model_weights_sha256(model, schema)
    measured = {}
    for engine in CPU_ENGINES:

        def timed(function):
            torch.cuda.synchronize()
            before = time.perf_counter()
            function()
            torch.cuda.synchronize()
            return time.perf_counter() - before

        def noise():
            for entry in schema.entries:
                address = ParameterNoiseAddress(17, schema.hash, entry.index, DEFAULT_CHUNK_ELEMENTS)
                for _ in iter_parameter_noise_chunks(address, entry.numel, engine=engine):
                    pass

        noise_seconds = timed(noise)
        perturb_seconds = timed(lambda: perturb_model_(model, schema, 17, 0.001, engine=engine))
        perturbed = model_weights_sha256(model, schema)
        restore_from_snapshot_(model, schema, snapshot)
        update_seconds = timed(
            lambda: apply_coefficients_(model, schema, [17, 9, 5], [1.0, -0.5, 0.25], 0.001, engine=engine)
        )
        updated = model_weights_sha256(model, schema)
        restore_from_snapshot_(model, schema, snapshot)
        restored = model_weights_sha256(model, schema)
        if restored != parent:
            raise ValueError("Benchmark exact restore differs")
        measured[engine] = dict(
            threads=noise_threads(engine),
            noiseSeconds=noise_seconds,
            perturbSeconds=perturb_seconds,
            updateSeconds=update_seconds,
            parentSha256=parent,
            perturbedSha256=perturbed,
            updatedSha256=updated,
            restoredSha256=restored,
        )
        print(json.dumps({"engine": engine, **measured[engine]}), flush=True)
    result["modelPipelineMeasurements"] = measured
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "noiseVersion": result["noiseVersion"],
                "qualificationSeconds": result["qualificationSeconds"],
                "updateSecondsPerSeed": result["updateSecondsPerSeed"],
            }
        )
    )


if __name__ == "__main__":
    main()
