#!/usr/bin/env python3
"""Qualify v3 full/subset/LoRA on a real pinned model; compare two independent GPUs.

Writes only to a new private run directory. It uses actual HTTP workers, records
texts, forces audits, re-scores the ledger and replays every update on the CPU.
This short engineering qualification does not establish learning performance.
"""

import argparse
import json
import os
from pathlib import Path
import time


def require_gpu(flag):
    if os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        raise ValueError("Set HETEROES_GPU_ACCEPTANCE=1 after owner authorization")
    if not flag:
        raise ValueError("Explicit --gpu is required")


def compare(left, right):
    for receipt in (left, right):
        if (
            not receipt["replayPassed"]
            or receipt["auditMismatches"]
            or receipt["auditCount"] < len(receipt["candidates"])
        ):
            raise ValueError("Replay or forced audits did not pass")
    for key in ("sourceTreeSha256", "recipeHash", "planHash", "candidates", "children"):
        if left[key] != right[key]:
            raise ValueError(f"Cross-GPU mismatch: {key}")
    return {
        "passed": True,
        "candidateCount": len(left["candidates"]),
        "textCount": sum(len(row["texts"]) for row in left["candidates"]),
        "generations": len(left["children"]),
    }


def qualification_rows():
    return [{"prompt": f"Compute {i} + {i + 2}. Reply with only the integer.", "answer": 2 * i + 2} for i in range(20)]


def configuration(model_path, rows_file, space):
    spaces = {
        "full": {"kind": "full"},
        "subset": {"kind": "subset", "include": [r"layers\.2[0-3]\.self_attn\.q_proj\.weight"]},
        "lora": {"kind": "lora", "rank": 4, "alpha": 8, "targetModules": ["q_proj", "v_proj"], "adapterSeed": 7},
    }
    return {
        "model": {
            "path": str(model_path),
            "id": "Qwen/Qwen2.5-0.5B-Instruct",
            "revision": "7ae557604adf67be50417f59c2c2f167def9a775",
        },
        "data": {"path": str(rows_file), "batchSize": 4, "batchSeed": 11, "splitSeed": 42},
        "weightSpace": spaces[space],
        "sigma": {"kind": "constant", "initial": 0.001, "minimum": 0.001},
        "antithetic": True,
        "systemPrompt": None,
        "maxNewTokens": 16,
        "evalDtype": "float32",
        "decoder": "hf_generate",
        "noiseEngine": "cpu",
        "population": 4,
        "generations": 2,
        "alpha": 0.001,
        "coefficientRule": "zscore@1",
        "scorer": {"kind": "declarative", "name": "last-integer", "config": {}},
    }


def run(args):
    require_gpu(args.gpu)
    import torch
    from heteroes.es.update import apply_coefficients_
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.ledger import Ledger
    from heteroes.product.recovery import source_identity
    from heteroes.runtime_info import environment_info
    from heteroes.v3.local import run_local
    from heteroes.v3.model import load, trainable_schema
    from heteroes.v3.run import RecipeV3Run
    from heteroes.v3.scoring import score

    if args.out.exists():
        raise FileExistsError(args.out)
    if not torch.cuda.is_available():
        raise ValueError("CUDA is unavailable")
    torch.set_num_threads(1)
    args.out.mkdir(parents=True, mode=0o700)
    rows = qualification_rows()
    rows_file = args.out / "rows.json"
    rows_file.write_text(json.dumps(rows))
    config = configuration(args.model_path, rows_file, args.space)
    (args.out / "spec.json").write_text(json.dumps(config, indent=2))
    started = time.time()
    run_dir = args.out / "run"
    summaries = run_local(
        config,
        run_dir,
        device="cuda",
        workers=2,
        experiment_id="v3-gpu-qualification",
        timeout_seconds=600,
        audit_rate=1,
    )
    recipe = json.loads((run_dir / "recipe.json").read_text())
    plan = json.loads((run_dir / "plan.json").read_text())
    dataset = json.loads((run_dir / "dataset.json").read_text())
    document = RecipeV3Run(recipe, plan)
    # Independent fresh CPU model, using recorded update inputs, never coordinator recovery.
    model, _ = load(args.model_path, recipe["model"]["files"], "cpu")
    adapter = run_dir / "initial-adapter.bin"
    schema = trainable_schema(model, recipe["weightSpace"], adapter if adapter.exists() else None)
    candidates, children = [], []
    with Ledger(run_dir / "ledger.sqlite") as ledger:
        for gen in range(plan["generations"]):
            batch = document.batch(dataset, gen)["rows"]
            for row in ledger.list_candidates("v3-gpu-qualification", gen):
                _, texts = ledger.get_completions(row.descriptor.candidate_id)
                actual, _ = score(plan["scorer"], texts, batch)
                if actual != row.result.reward:
                    raise ValueError("Stored reward differs from independently scored texts")
                candidates.append({"candidateId": row.descriptor.candidate_id, "texts": texts, "reward": actual})
            update = ledger.get_update("v3-gpu-qualification", gen)
            if model_weights_sha256(model, schema) != update.record.parent_weights_sha256:
                raise ValueError("Replay parent mismatch")
            update.record.verify_coefficients(plan["coefficientRule"]["eta"])
            seeds, coefficients = update.record.update_inputs()
            apply_coefficients_(
                model, schema, seeds, coefficients, update.record.alpha, recipe["noise"]["chunkElements"]
            )
            if model_weights_sha256(model, schema) != update.child_weights_sha256:
                raise ValueError("CPU replay child mismatch")
            children.append(update.child_weights_sha256)
        with ledger._lock:
            audit_count, mismatches = ledger._db.execute(
                "SELECT count(*),coalesce(sum(matched=0),0) FROM audit"
            ).fetchone()
        if ledger.list_quarantined() or mismatches or audit_count != len(candidates):
            raise ValueError("Forced audits were incomplete or mismatched")
    receipt = {
        "environment": environment_info("cuda"),
        **source_identity(Path(__file__).resolve().parents[1] / "src/heteroes"),
        "recipeHash": document.hash,
        "planHash": document.plan_hash,
        "candidates": candidates,
        "children": children,
        "replayPassed": True,
        "auditCount": audit_count,
        "auditMismatches": mismatches,
        "seconds": time.time() - started,
        "nonNoopGenerations": sum(not row["noop"] for row in summaries),
    }
    (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2))
    print(
        json.dumps(
            {
                k: receipt[k]
                for k in (
                    "recipeHash",
                    "auditCount",
                    "auditMismatches",
                    "replayPassed",
                    "seconds",
                    "nonNoopGenerations",
                )
            }
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("run")
    check.add_argument("--gpu", action="store_true")
    check.add_argument("--model-path", type=Path, required=True)
    check.add_argument("--space", choices=["full", "subset", "lora"], required=True)
    check.add_argument("--out", type=Path, required=True)
    comparison = sub.add_parser("compare")
    comparison.add_argument("left", type=Path)
    comparison.add_argument("right", type=Path)
    comparison.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        run(args)
    else:
        result = compare(json.loads(args.left.read_text()), json.loads(args.right.read_text()))
        with args.out.open("x") as target:
            json.dump(result, target, indent=2)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
