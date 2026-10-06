#!/usr/bin/env python3
"""
The same experiment as run_coordinator.py + workers, in ONE process, with no network and no ledger: the reference that a
distributed run is compared against.

    python scripts/reference_generations.py --model-path <snapshot dir> --output <new json file> \
        --experiment-id e2e --candidates 4 --generations 2 --alpha 1e-3 --sigma 1e-3

For each generation: the candidates (seeds from `derive_seed`, in index order) are evaluated one after the other on this machine's
GPU, the update is `apply_es_update_` (standardization and update in one call: a different route from the coordinator's, which
applies the coefficients of the generation record), and the hash of the new weights is taken. The output lists, per generation,
the rewards and the parent and child hashes; `scripts/compare_generation_runs.py` compares it with a coordinator's summary.json.
The output file must not exist.
"""
import argparse
import json
import sys
import time
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--experiment-id", default="g3")
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--alpha", type=float, default=1e-3)
    parser.add_argument("--sigma", type=float, default=1e-3)
    parser.add_argument("--chunk-elements", type=int, default=None)
    parser.add_argument("--device", choices=["cuda", "cpu"], default=None)
    args = parser.parse_args(argv)

    output = Path(args.output)
    if output.exists():
        print(f"error: {output} already exists; evidence is never overwritten", file=sys.stderr)
        return 2

    import torch

    from heteroes.es.update import DEFAULT_ETA, apply_es_update_
    from heteroes.executor import CandidateExecutor
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.manifest import CandidateDescriptor, derive_seed
    from heteroes.model.loading import build_recipe, check_noise_selftest, load_pinned_model
    from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS
    from heteroes.runtime_info import code_info, environment_info

    check_noise_selftest()
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    chunk = args.chunk_elements or DEFAULT_CHUNK_ELEMENTS
    loaded = load_pinned_model(args.model_path, device)
    recipe = build_recipe(loaded, sigma=args.sigma, chunk_elements=chunk)
    executor = CandidateExecutor(loaded.model, loaded.tokenizer, loaded.schema, recipe)
    started = time.time()
    generations = []
    for generation in range(args.generations):
        parent = model_weights_sha256(loaded.model, loaded.schema)
        executor.reset_parent(parent)
        seeds = [derive_seed(args.experiment_id, generation, index) for index in range(args.candidates)]
        rewards, candidate_seconds = [], []
        for index, seed in enumerate(seeds):
            descriptor = CandidateDescriptor(recipe_hash=recipe.hash, parent_weights_sha256=parent, experiment_id=args.experiment_id,
                                             generation=generation, index=index, seed=seed)
            begin = time.perf_counter()
            rewards.append(executor(descriptor))
            candidate_seconds.append(time.perf_counter() - begin)
        begin = time.perf_counter()
        report = apply_es_update_(loaded.model, loaded.schema, seeds, rewards, args.alpha, chunk, DEFAULT_ETA)
        update_seconds = time.perf_counter() - begin
        child = model_weights_sha256(loaded.model, loaded.schema)
        generations.append({"generation": generation, "parent_sha256": parent, "child_sha256": child, "rewards": rewards,
                            "seeds": seeds, "noop": report.noop, "changed": report.changed, "candidate_seconds": candidate_seconds,
                            "update_seconds": update_seconds})
        print(json.dumps({"generation": generation, "rewards": rewards, "child_sha256": child}), flush=True)
    record = {"recipe_hash": recipe.hash, "args": vars(args), "initial_weights_sha256": generations[0]["parent_sha256"],
              "final_weights_sha256": generations[-1]["child_sha256"], "generations": generations,
              "total_seconds": time.time() - started, "environment": environment_info(device), "code": code_info()}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
