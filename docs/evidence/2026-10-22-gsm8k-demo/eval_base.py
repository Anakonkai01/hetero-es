"""Score the BASE model on a run's split exactly as the lab's Tracker scores a checkpoint (same recipe decoding, chunk,
decoder and scorer), so the selected checkpoint's test reward has its baseline.

    python eval_base.py <run dir with recipe.json/plan.json> <dataset.json> <local model dir> <split> <out.json> [--device cuda]
"""

import argparse
import json
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.eval.candidate import model_weights_sha256
from heteroes.eval.precision import EvalModel
from heteroes.study.evaluation import generate_rows
from heteroes.v3.data import open_dataset
from heteroes.v3.model import load, trainable_schema
from heteroes.v3.run import RecipeV3Run
from heteroes.v3.scoring import score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "dataset", "model", "split", "out"):
        parser.add_argument(name)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    root = Path(args.run)
    recipe, plan = (json.loads((root / f"{n}.json").read_text()) for n in ("recipe", "plan"))
    run = RecipeV3Run(recipe, plan, allow_python=True)
    dataset = open_dataset(Path(args.dataset))
    if any(dataset[k] != recipe["data"][k] for k in ("contentHash", "splitHashes")):
        raise SystemExit("dataset differs from the recipe")
    model, tokenizer = load(args.model, recipe["model"]["files"], args.device)
    weights = model_weights_sha256(model, trainable_schema(model, recipe["weightSpace"]))
    rows = list(dataset["splits"][args.split])
    evaluator = EvalModel(model, run.eval_dtype)
    raw = generate_rows(evaluator.model, tokenizer, rows, run.evaluation, run.chunk or 16)
    reward, scores = score(plan["scorer"], [r["output"] for r in raw], rows)
    result = {
        "split": args.split,
        "count": len(rows),
        "rowsHash": canonical_json_hash(rows),
        "weightsSha256": weights,
        "meanReward": reward,
        "scores": scores,
        "outputs": [r["output"] for r in raw],
    }
    with open(args.out, "x") as stream:
        json.dump(result, stream)
    print(f"base {args.split}: {reward:.4f} over {len(rows)} rows (weights {weights[:16]}…)")


if __name__ == "__main__":
    main()
