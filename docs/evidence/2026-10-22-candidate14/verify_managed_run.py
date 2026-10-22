"""Re-execute a managed run's candidates and updates from its own documents and compare with its ledger.

    python verify_managed_run.py <run dir> <dataset.json> <local model dir> <experiment id> <out.json>
        [--device cuda] [--regenerate all|none|G,G,...] [--reward reward.py]

The GSM8K demo verifier (`../2026-10-22-gsm8k-demo/`), plus a Python sampler's rows read from the ledger's frozen
generation contexts. From candidate9's verifier (`../2026-10-21-restart-run-candidate9/`): a declarative scorer is
recomputed with `heteroes.v3.scoring.score` (a Python scorer still needs `--reward`), and `--regenerate` chooses the
generations whose texts are regenerated. Every update is applied from the ledger's record, so each child hash is checked
for every generation even when texts are regenerated only for some (the cheap ledger replay). Only numerical receipts
are written.
"""

import argparse
import os
import importlib.util
import json
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.es.update import apply_coefficients_
from heteroes.eval.candidate import model_weights_sha256
from heteroes.executor import CandidateExecutor
from heteroes.ledger import Ledger
from heteroes.v3.data import open_dataset
from heteroes.v3.model import load, trainable_schema
from heteroes.v3.run import RecipeV3Run
from heteroes.v3.scoring import score
from heteroes.worker_api import completions_sha256


def frozen_batch(path, experiment, generation):
    """A Python sampler's rows: the coordinator's frozen context, read directly (the ledger module stays unchanged)."""
    import sqlite3

    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        row = db.execute(
            "SELECT body FROM generation_context WHERE experiment_id=? AND generation=?", (experiment, generation)
        ).fetchone()
    return json.loads(row[0])["batchIndices"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "dataset", "model", "experiment", "out"):
        parser.add_argument(name)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--regenerate", default="all")
    parser.add_argument("--reward")
    parser.add_argument("--gpu", action="store_true")
    args = parser.parse_args()
    if args.device == "cuda" and (not args.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1"):
        parser.error("GPU replay requires explicit authorization, --gpu and HETEROES_GPU_ACCEPTANCE=1")
    root = Path(args.run)
    recipe, plan = (json.loads((root / f"{n}.json").read_text()) for n in ("recipe", "plan"))
    run = RecipeV3Run(recipe, plan, allow_python=True)
    dataset = open_dataset(Path(args.dataset))
    if any(dataset[k] != recipe["data"][k] for k in ("contentHash", "splitHashes")):
        raise SystemExit("dataset differs from the recipe")
    python_scorer = None
    if plan["scorer"]["kind"] == "python":
        spec = importlib.util.spec_from_file_location("reward", args.reward)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        python_scorer = getattr(module, plan["scorer"]["name"].replace("-", "_"))
    model, tokenizer = load(args.model, recipe["model"]["files"], args.device)
    schema = trainable_schema(model, recipe["weightSpace"])
    executor = CandidateExecutor(model, tokenizer, schema, run, dataset=dataset, return_completions=True)
    generations = []
    with Ledger(root / "ledger.sqlite") as ledger:
        count = len(ledger.list_generations(args.experiment))
        chosen = (
            set(range(count))
            if args.regenerate == "all"
            else set()
            if args.regenerate == "none"
            else {int(g) for g in args.regenerate.split(",")}
        )
        parent = model_weights_sha256(model, schema)
        for generation in range(count):
            update = ledger.get_update(args.experiment, generation)
            if update is None:  # a generation opened but not applied (an interrupted run): nothing to replay
                break
            candidates, rewards = [], []
            if generation in chosen:
                # a Python sampler's rows are the coordinator's frozen choice (checked here); any other is recomputed
                given = (
                    frozen_batch(root / "ledger.sqlite", args.experiment, generation) if run.python_sampler else None
                )
                rows = run.batch(dataset, generation, given)["rows"]
                executor.set_generation(
                    generation, run.context(dataset, generation, given)
                )  # computed here, not received
                for record in ledger.list_candidates(args.experiment, generation):
                    # ADR-010: at the chunk the result recorded (None: the recipe's own)
                    texts = list(
                        executor(record.descriptor, chunk=ledger.completion_chunk(record.descriptor.candidate_id))
                    )
                    stored_sha, stored = ledger.get_completions(record.descriptor.candidate_id)
                    reward, _ = score(plan["scorer"], texts, [dict(r) for r in rows], python_scorer)
                    candidates.append(
                        {
                            "candidateId": record.descriptor.candidate_id,
                            "seed": record.descriptor.seed,
                            "textsEqual": texts == list(stored),
                            "textsHashEqual": completions_sha256(texts) == stored_sha,
                            "rewardEqual": reward == record.result.reward,
                            "reward": record.result.reward,
                            "completionsSha256": stored_sha,
                        }
                    )
                    rewards.append(reward)
            seeds, coefficients = update.record.update_inputs()
            apply_coefficients_(model, schema, seeds, coefficients, update.record.alpha, run.chunk_elements, engine=run.engine_version)
            child = model_weights_sha256(model, schema)
            executor.reset_parent(child)
            generations.append(
                {
                    "generation": generation,
                    "parentSha256": parent,
                    "recordHash": update.record.hash,
                    "regenerated": generation in chosen,
                    "rewardsEqualRecord": rewards == list(update.record.rewards) if generation in chosen else None,
                    "childSha256": update.child_weights_sha256,
                    "childEqual": child == update.child_weights_sha256,
                    "candidates": candidates,
                }
            )
            parent = child
    equal = bool(generations) and all(
        g["childEqual"]
        and g["rewardsEqualRecord"] is not False
        and all(c["textsEqual"] and c["textsHashEqual"] and c["rewardEqual"] for c in g["candidates"])
        for g in generations
    )
    result = {
        "allEqual": equal,
        "device": args.device,
        "regenerated": sorted(chosen),
        "generations": generations,
        "receiptHash": canonical_json_hash(generations),
    }
    with open(args.out, "x") as stream:
        json.dump(result, stream, indent=1)
        stream.write("\n")
    print(
        "ALL EQUAL" if equal else "DIFFERENCES FOUND", f"({len(generations)} generations, regenerated {sorted(chosen)})"
    )


if __name__ == "__main__":
    main()
