"""
Score checkpoints of a local Recipe v3 run (`heteroes run` / `run_local`) on one split of its dataset.

    python v3_evaluate_checkpoints.py RUN_DIR --model-path MODEL --generations -1,9,29 --split validation \
        --out report.json [--device cuda] [--scorer-path reward.py --scorer-function name]

The coordinator keeps only its latest weights; any checkpoint is rebuilt here from the base model by replaying the
recorded updates, and each rebuilt checkpoint must hash to the child the ledger recorded (generation -1 is the base
model). Evaluation is the run's: greedy decoding, its prompt, token budget, precision and chunk, scored with its plan's
scorer (a python scorer needs `--scorer-path`, the file whose SHA-256 the plan pins).
GPU use in this repository needs the owner's authorization and HETEROES_GPU_ACCEPTANCE=1.
"""

import argparse
import json
from pathlib import Path

SPLITS = ("train", "validation", "test")


def evaluate(run_dir, model_path, generations, split, device="cpu", scorer_path=None, scorer_function=None):
    from heteroes.es.update import apply_coefficients_
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.eval.precision import EvalModel
    from heteroes.ledger import Ledger
    from heteroes.study.evaluation import generate_rows
    from heteroes.v3.model import load, trainable_schema
    from heteroes.v3.run import RecipeV3Run, load_python_scorer
    from heteroes.v3.scoring import score

    run_dir = Path(run_dir)
    recipe, plan, dataset = (json.loads((run_dir / f"{n}.json").read_text()) for n in ("recipe", "plan", "dataset"))
    run = RecipeV3Run(recipe, plan)
    if split not in SPLITS:
        raise ValueError(f"split is one of {SPLITS}")
    wanted = sorted(set(generations))
    if not wanted or wanted[0] < -1 or wanted[-1] >= plan["generations"]:
        raise ValueError("generations are -1 (the base model) to the plan's last generation")
    function = None
    if plan["scorer"]["kind"] == "python":
        if scorer_path is None or scorer_function is None:
            raise ValueError("a python scorer needs --scorer-path and --scorer-function")
        function, digest = load_python_scorer(scorer_path, scorer_function)
        if digest != plan["scorer"]["codeSha256"]:
            raise ValueError("the scorer file is not the one the plan pins")
    model, tokenizer = load(model_path, recipe["model"]["files"], device)
    adapter = run_dir / "initial-adapter.bin"
    schema = trainable_schema(model, recipe["weightSpace"], adapter if adapter.exists() else None)
    if schema.hash != recipe["schemaHash"]:
        raise ValueError("the model does not have the run's trainable schema")
    rows = dataset["splits"][split]
    evaluator = EvalModel(model, run.eval_dtype)
    checkpoints = []

    def measure(generation, weights):
        evaluator.refresh()
        raw = generate_rows(evaluator.model, tokenizer, rows, run.evaluation, run.chunk or 16)
        outputs = [r["output"] for r in raw]
        reward, scores = score(plan["scorer"], outputs, rows, function)
        counts = {}
        for value in scores:
            counts[repr(value)] = counts.get(repr(value), 0) + 1
        checkpoints.append(
            {
                "generation": generation,
                "weightsSha256": weights,
                "split": split,
                "count": len(rows),
                "meanReward": reward,
                "scoreCounts": counts,
                "truncated": sum(bool(r["truncated"]) for r in raw),
                "meanCharacters": sum(map(len, outputs)) / len(outputs),
                "outputs": outputs,
            }
        )

    if wanted[0] == -1:
        measure(-1, model_weights_sha256(model, schema))
    with Ledger(run_dir / "ledger.sqlite") as ledger:
        for generation in range(wanted[-1] + 1):
            stored = ledger.get_update("local", generation)
            if stored is None or stored.child_weights_sha256 is None:
                raise ValueError(f"generation {generation} has no applied update in this run")
            seeds, coefficients = stored.record.update_inputs()
            apply_coefficients_(
                model, schema, seeds, coefficients, stored.record.alpha, recipe["noise"]["chunkElements"]
            )
            weights = model_weights_sha256(model, schema)
            if weights != stored.child_weights_sha256:
                raise ValueError(f"replayed generation {generation} does not hash to the recorded child")
            if generation in wanted:
                measure(generation, weights)
    return {"runDir": str(run_dir), "recipeHash": run.hash, "planHash": run.plan_hash, "checkpoints": checkpoints}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--generations", required=True, help="comma separated; -1 is the base model")
    parser.add_argument("--split", default="validation", choices=SPLITS)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--scorer-path", type=Path)
    parser.add_argument("--scorer-function")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; choose a fresh path")
    generations = [int(g) for g in args.generations.split(",")]
    report = evaluate(
        args.run_dir, args.model_path, generations, args.split, args.device, args.scorer_path, args.scorer_function
    )
    args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    for c in report["checkpoints"]:
        print(json.dumps({k: v for k, v in c.items() if k != "outputs"}))


if __name__ == "__main__":
    main()
