"""Recompute a recorded run's coordinator updates on this machine's CPU and compare each child weights hash.

    CUDA_VISIBLE_DEVICES= python -I cpu_replay.py --source runtime/src RUN_ROOT MODEL_DIR OUT.json

RUN_ROOT is a finished coordinator run folder (config.json, recipe.json, plan.json, ledger.sqlite). The base weights are
loaded from MODEL_DIR (the pinned files of the recipe) in FP16 on the CPU; every generation's recorded update is applied
with the recipe's noise engine, as a worker's replay does, and the result is hashed.
"""

import argparse
import json
from pathlib import Path
import platform
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("run", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve()))
    import torch

    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.ledger import Ledger, LedgerError
    from heteroes.profile_setup import noise_ops
    from heteroes.v3.model import load, trainable_schema
    from heteroes.v3.run import RecipeV3Run

    config = json.loads((args.run / "config.json").read_text())
    recipe = json.loads((args.run / "recipe.json").read_text())
    run = RecipeV3Run(recipe, json.loads((args.run / "plan.json").read_text()), allow_python=True)
    model, _ = load(args.model, recipe["model"]["files"], "cpu")
    schema = trainable_schema(model, recipe["weightSpace"])
    _, apply_update = noise_ops(run.engine_version, run.chunk_elements)
    rows, parent = [], model_weights_sha256(model, schema)
    with Ledger(args.run / "ledger.sqlite") as ledger:
        generation = 0
        while True:
            try:
                stored = ledger.get_update(config["runId"], generation)
            except LedgerError:  # past the last generation
                break
            if stored is None:
                break
            if stored.record.parent_weights_sha256 != parent:
                rows.append(
                    {"generation": generation, "startsFrom": stored.record.parent_weights_sha256, "cpuHas": parent}
                )
                break
            started = time.perf_counter()
            seeds, coefficients = stored.record.update_inputs()
            apply_update(model, schema, seeds, coefficients, stored.record.alpha)
            seconds = time.perf_counter() - started
            parent = model_weights_sha256(model, schema)
            rows.append(
                {
                    "generation": generation,
                    "coordinatorChildSha256": stored.child_weights_sha256,
                    "cpuChildSha256": parent,
                    "equal": parent == stored.child_weights_sha256,
                    "candidates": len(seeds),
                    "updateSeconds": seconds,
                }
            )
            generation += 1
    report = {
        "runId": config["runId"],
        "recipeHash": run.hash,
        "noiseEngine": run.engine_version,
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpus": __import__("os").cpu_count(),
            "torch": torch.__version__,
            "python": platform.python_version(),
        },  # fmt: skip
        "generations": rows,
        "allEqual": bool(rows) and all(r.get("equal") for r in rows),
    }
    args.out.write_text(json.dumps(report, indent=1) + "\n")
    print(
        json.dumps(
            {
                "allEqual": report["allEqual"],
                "generations": len(rows),
                "rows": [{k: v for k, v in r.items() if k != "updateSeconds"} for r in rows],
            }
        )
    )


if __name__ == "__main__":
    main()
