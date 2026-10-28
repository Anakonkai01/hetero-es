"""Re-execute a managed run's candidates and updates from its own documents and compare with its ledger.

    python verify_managed_run.py <fetched run dir> <local model dir> <reward.py> <experiment id> <out.json> [--device cuda]

The fetched directory holds recipe.json, plan.json, dataset.json (+ split files) and a copy of the coordinator ledger.
Texts are regenerated here from the same recipe/plan/dataset, rewards are recomputed with an independent copy of the
reward function, the generation record is rebuilt from those rewards and the update is applied here; every value must
equal the distributed run's exactly. Only numerical receipts are written (no lease or device data).
"""

import argparse
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
from heteroes.worker_api import completions_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "model", "reward", "experiment", "out"):
        parser.add_argument(name)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    root = Path(args.run)
    recipe, plan = (json.loads((root / f"{n}.json").read_text()) for n in ("recipe", "plan"))
    run = RecipeV3Run(recipe, plan, allow_python=True)
    dataset = open_dataset(root / "dataset.json")
    if any(dataset[k] != recipe["data"][k] for k in ("contentHash", "splitHashes")):
        raise SystemExit("dataset differs from the recipe")
    spec = importlib.util.spec_from_file_location("reward", args.reward)
    reward_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reward_module)
    function = getattr(reward_module, plan["scorer"]["name"].replace("-", "_"))
    model, tokenizer = load(args.model, recipe["model"]["files"], args.device)
    schema = trainable_schema(model, recipe["weightSpace"])
    executor = CandidateExecutor(model, tokenizer, schema, run, dataset=dataset, return_completions=True)
    generations = []
    with Ledger(root / "ledger.sqlite") as ledger:
        parent = model_weights_sha256(model, schema)
        for generation in range(len(ledger.list_generations(args.experiment))):
            update = ledger.get_update(args.experiment, generation)
            rows = run.batch(dataset, generation)["rows"]
            executor.set_generation(generation, run.context(dataset, generation))  # computed here, not received
            candidates, rewards = [], []
            for record in ledger.list_candidates(args.experiment, generation):
                texts = list(executor(record.descriptor))
                stored_sha, stored = ledger.get_completions(record.descriptor.candidate_id)
                values = [float(v) for v in function(list(texts), [dict(r) for r in rows])]
                reward = sum(values) / len(values)  # the scorer's own mean rule (v3/scoring.py)
                candidates.append(
                    {
                        "candidateId": record.descriptor.candidate_id,
                        "seed": record.descriptor.seed,
                        "sign": record.descriptor.sign,
                        "textsEqual": texts == list(stored),
                        "textsHashEqual": completions_sha256(texts) == stored_sha,
                        "rewardEqual": reward == record.result.reward,
                        "reward": record.result.reward,
                        "completionsSha256": stored_sha,
                    }
                )
                rewards.append(reward)
            seeds, coefficients = update.record.update_inputs()
            apply_coefficients_(model, schema, seeds, coefficients, update.record.alpha, run.chunk_elements)
            child = model_weights_sha256(model, schema)
            executor.reset_parent(child)
            generations.append(
                {
                    "generation": generation,
                    "parentSha256": parent,
                    "recordHash": update.record.hash,
                    "rewardsEqualRecord": rewards == list(update.record.rewards),
                    "childSha256": update.child_weights_sha256,
                    "childEqual": child == update.child_weights_sha256,
                    "candidates": candidates,
                }
            )
            parent = child
    equal = all(
        g["childEqual"]
        and g["rewardsEqualRecord"]
        and all(c["textsEqual"] and c["textsHashEqual"] and c["rewardEqual"] for c in g["candidates"])
        for g in generations
    )
    result = {
        "allEqual": equal,
        "device": args.device,
        "generations": generations,
        "receiptHash": canonical_json_hash(generations),
    }
    with open(args.out, "x") as stream:
        json.dump(result, stream, indent=1)
        stream.write("\n")
    print("ALL EQUAL" if equal else "DIFFERENCES FOUND")


if __name__ == "__main__":
    main()
