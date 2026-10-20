"""
Score checkpoints of a local Recipe v3 run (`heteroes run` / `run_local`) on one split of its dataset.

    python v3_evaluate_checkpoints.py RUN_DIR --model-path MODEL --generations -1,9,29 --split validation \
        --out report.json [--device cuda] [--scorer-path reward.py --scorer-function name] \
        [--rows other.jsonl --rows-scorer scorer.json]

The coordinator keeps only its latest weights; any checkpoint is rebuilt here from the base model by replaying the
recorded updates, and each rebuilt checkpoint must hash to the child the ledger recorded (generation -1 is the base
model). Evaluation is the run's: greedy decoding, its prompt, token budget, precision and chunk, scored with its plan's
scorer (a python scorer needs `--scorer-path`, the file whose SHA-256 the plan pins).
`--rows` scores the checkpoints on OTHER rows (a JSONL file of rows with the run's prompt field), for example to look for
forgetting on another task, with the declarative scorer spec in the `--rows-scorer` JSON file instead of the plan's.
GPU use in this repository needs the owner's authorization and HETEROES_GPU_ACCEPTANCE=1.
"""

import argparse
import json
import math
import re
import sqlite3
from collections import Counter
from pathlib import Path

SPLITS = ("train", "validation", "test")


def _vote_key(spec, text):
    name = spec["name"] if spec["kind"] == "declarative" else "python"
    if name == "last-integer":
        from heteroes.eval.workload import extract_integer

        answer = extract_integer(text)
    elif name == "answer-line-integer":
        from heteroes.eval.cot_workload import extract_answer

        answer = extract_answer(text)
    elif name == "answer-line-last-number":
        from heteroes.study.evaluation import extract

        answer = extract(text)
    elif name == "choice-letter":
        found = re.findall(r"\b([A-E])\b", text)
        answer = found[-1] if found else None
    elif name == "regex":
        found = re.findall(spec["config"]["pattern"], text)
        answer = (found[-1][0] if isinstance(found[-1], tuple) else found[-1]).strip() if found else None
    elif name == "exact-string":
        answer = text.strip() if spec["config"]["strip"] else text
        answer = answer.casefold() if spec["config"]["casefold"] else answer
    else:
        answer = text  # arbitrary Python/expression scorers: vote on complete output text, stated in the report
    return None if answer is None else str(answer)


def sample_metrics(texts, rows, scorer, ks, python_scorer=None):
    from heteroes.study.evaluation import pass_at_k
    from heteroes.v3.scoring import score

    if len(texts) != len(rows) or not rows or not ks:
        raise ValueError("Samples and nonempty rows/ks must match")
    counts = {len(outputs) for outputs in texts}
    if len(counts) != 1 or any(type(k) is not int or not 1 <= k <= min(counts) for k in ks):
        raise ValueError("Each row needs the same sample count, at least k")
    records = []
    for outputs, row in zip(texts, rows, strict=True):
        _, scores = score(scorer, outputs, [row] * len(outputs), python_scorer)
        keys = [_vote_key(scorer, text) for text in outputs]
        votes = Counter(key for key in keys if key is not None)
        majority = min(votes, key=lambda key: (-votes[key], key)) if votes else None
        correct = sum(s == 1 for s in scores)
        records.append(
            {
                "outputs": outputs,
                "scores": scores,
                "correct": correct,
                "passAtK": {str(k): pass_at_k(len(outputs), correct, k) for k in ks},
                "majorityAnswer": majority,
                "majorityCorrect": majority is not None and scores[keys.index(majority)] == 1,
            }
        )
    return {
        "samplesPerRow": min(counts),
        "successDefinition": "score == 1",
        "tieRule": "lexicographically smallest extracted answer; unparsed outputs excluded",
        "passAtK": {str(k): sum(r["passAtK"][str(k)] for r in records) / len(records) for k in ks},
        "majorityAccuracy": sum(r["majorityCorrect"] for r in records) / len(records),
        "rows": records,
    }


def evaluate(
    run_dir,
    model_path,
    generations,
    split,
    device="cpu",
    scorer_path=None,
    scorer_function=None,
    rows=None,
    rows_scorer=None,
    *,
    samples=0,
    ks=(1,),
    seed=11,
    temperature=0.6,
):
    from heteroes.es.update import apply_coefficients_
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.eval.precision import EvalModel
    from heteroes.ledger import Ledger
    from heteroes.study.evaluation import generate_rows
    from heteroes.v3.model import load, trainable_schema
    from heteroes.v3.run import RecipeV3Run, load_python_scorer
    from heteroes.v3.scoring import score, validate_spec
    from heteroes.canonical import canonical_json_hash

    run_dir = Path(run_dir)
    recipe, plan, dataset = (json.loads((run_dir / f"{n}.json").read_text()) for n in ("recipe", "plan", "dataset"))
    run = RecipeV3Run(recipe, plan)
    if split not in SPLITS:
        raise ValueError(f"split is one of {SPLITS}")
    if any(type(g) is not int for g in generations):
        raise ValueError("generations must be integers")
    wanted = sorted(set(generations))
    if not wanted or wanted[0] < -1 or wanted[-1] >= plan["generations"]:
        raise ValueError("generations are -1 (the base model) to the plan's last generation")
    if (
        type(samples) is not int
        or not 0 <= samples <= 1000
        or type(seed) is not int
        or seed < 0
        or not math.isfinite(temperature)
        or temperature <= 0
        or not ks
        or any(type(k) is not int or not 1 <= k <= max(samples, 1) for k in ks)
    ):
        raise ValueError("Invalid sample count, ks, seed or temperature")
    if samples and run.decode_engine == "hf_compact":
        raise ValueError("The recipe's compact decoder is greedy only; sampled evaluation needs hf_generate")
    if (rows is None) != (rows_scorer is None):
        raise ValueError("other rows and their scorer are given together")
    function = None
    scorer = plan["scorer"]
    if rows is not None:
        validate_spec(rows_scorer)  # declarative only: no allow_python
        scorer, split = rows_scorer, "external"
    elif plan["scorer"]["kind"] == "python":
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
    rows = dataset["splits"][split] if rows is None else rows
    if not rows:
        raise ValueError("Cannot evaluate empty rows")
    evaluator = EvalModel(model, run.eval_dtype)
    checkpoints = []

    def measure(generation, weights):
        evaluator.refresh()
        raw = generate_rows(evaluator.model, tokenizer, rows, run.evaluation, run.chunk or 16)
        outputs = [r["output"] for r in raw]
        reward, scores = score(scorer, outputs, rows, function)
        counts = {}
        for value in scores:
            counts[repr(value)] = counts.get(repr(value), 0) + 1
        sampled = None
        if samples:
            sampled_outputs = [[] for _ in rows]
            for index in range(samples):
                generated = generate_rows(
                    evaluator.model,
                    tokenizer,
                    rows,
                    run.evaluation,
                    run.chunk or 16,
                    sample=True,
                    seed=seed + index * len(rows),
                    temperature=temperature,
                )
                for output, observation in zip(sampled_outputs, generated, strict=True):
                    output.append(observation["output"])
            sampled = sample_metrics(sampled_outputs, rows, scorer, ks, function)
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
                "scores": scores,
                **({"sampled": sampled} if sampled is not None else {}),
            }
        )

    if wanted[0] == -1:
        measure(-1, model_weights_sha256(model, schema))
    ledger_path = run_dir / "ledger.sqlite"
    with sqlite3.connect(ledger_path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        identities = [row[0] for row in connection.execute("SELECT DISTINCT experiment_id FROM generation")]
    if len(identities) != 1:
        raise ValueError("Evaluation requires a ledger containing one experiment")
    with Ledger(ledger_path) as ledger:
        for generation in range(wanted[-1] + 1):
            stored = ledger.get_update(identities[0], generation)
            if stored is None or stored.child_weights_sha256 is None:
                raise ValueError(f"generation {generation} has no applied update in this run")
            seeds, coefficients = stored.record.update_inputs()
            from heteroes.noise.contracts import CUDA_ENGINE_VERSION

            if recipe["noise"]["engine"] == CUDA_ENGINE_VERSION:
                from heteroes.es.cuda_ops import apply_coefficients_cuda_

                apply_coefficients_cuda_(model, schema, seeds, coefficients, stored.record.alpha)
            else:
                apply_coefficients_(
                    model, schema, seeds, coefficients, stored.record.alpha, recipe["noise"]["chunkElements"]
                )
            weights = model_weights_sha256(model, schema)
            if weights != stored.child_weights_sha256:
                raise ValueError(f"replayed generation {generation} does not hash to the recorded child")
            if generation in wanted:
                measure(generation, weights)
    report = {
        "runDir": str(run_dir),
        "recipeHash": run.hash,
        "planHash": run.plan_hash,
        "checkpoints": checkpoints,
        "rowsHash": canonical_json_hash(rows),
        "scorer": scorer,
        "evaluation": run.evaluation,
        "sampling": {
            "samples": samples,
            "ks": list(ks),
            "seed": seed,
            "temperature": temperature,
            "seedRule": "seed + sampleIndex * rowCount + chunkOffset",
        },
    }
    if scorer is not plan["scorer"]:
        report["externalScorer"] = scorer
    return report


def add_arguments(parser):
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--generations", required=True, help="comma separated; -1 is the base model")
    parser.add_argument("--split", default="validation", choices=SPLITS)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--scorer-path", type=Path)
    parser.add_argument("--scorer-function")
    parser.add_argument("--rows", type=Path, help="JSONL rows to score instead of a split of the run's dataset")
    parser.add_argument("--rows-scorer", type=Path, help="JSON declarative scorer spec for --rows")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=0, help="sampled completions per row, in addition to greedy")
    parser.add_argument("--ks", default="1", help="comma-separated k values, each at most --samples")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--temperature", type=float, default=0.6)


def command(args):
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; choose a fresh path")
    generations = [int(g) for g in args.generations.split(",")]
    rows = rows_scorer = None
    if args.rows is not None:
        rows = [json.loads(line) for line in args.rows.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.rows_scorer is not None:
        rows_scorer = json.loads(args.rows_scorer.read_text(encoding="utf-8"))
    report = evaluate(
        args.run_dir,
        args.model_path,
        generations,
        args.split,
        args.device,
        args.scorer_path,
        args.scorer_function,
        rows,
        rows_scorer,
        samples=args.samples,
        ks=[int(k) for k in args.ks.split(",")],
        seed=args.seed,
        temperature=args.temperature,
    )
    with args.out.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=1) + "\n")
    for c in report["checkpoints"]:
        print(
            json.dumps(
                {k: v for k, v in c.items() if k not in ("outputs", "scores", "sampled")}
                | ({"sampled": {k: v for k, v in c["sampled"].items() if k != "rows"}} if "sampled" in c else {})
            )
        )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(parser)
    return command(parser.parse_args(argv))


if __name__ == "__main__":
    main()
