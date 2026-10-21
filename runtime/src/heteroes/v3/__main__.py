"""
    python -m heteroes.v3 run spec.json --out RUN_DIR [--device cpu|cuda] [--workers N]

Runs a Recipe v3 experiment on this machine (`heteroes.v3.local.run_local`). `spec.json` is the configuration documented in
`runtime/docs/v3-local-runs.md`; relative paths in it are read from the spec's directory. Prints one line per generation.
"""

import argparse
import json
from pathlib import Path

from heteroes.catalog import DEFAULT_SCHEDULER_POLICY, SCHEDULER_POLICIES


def _resolve(spec, base):
    spec = json.loads(json.dumps(spec))
    for section, key in (("model", "path"), ("data", "path"), ("scorer", "path"), ("coefficientRule", "path")):
        value = spec.get(section)
        if isinstance(value, dict) and key in value and not Path(value[key]).is_absolute():
            value[key] = str(base / value[key])
    for name, path in spec.get("data", {}).get("splits", {}).items():
        if not Path(path).is_absolute():
            spec["data"]["splits"][name] = str(base / path)
    return spec


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="heteroes", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    from heteroes.v3 import evaluation

    evaluate = commands.add_parser("eval", help="replay and evaluate recorded checkpoints")
    evaluation.add_arguments(evaluate)
    compare = commands.add_parser("compare", help="compare paired evaluation reports")
    compare.add_argument("a", type=Path)
    compare.add_argument("b", type=Path)
    compare.add_argument("--generation-a", type=int)
    compare.add_argument("--generation-b", type=int)
    compare.add_argument("--resamples", type=int, default=10000)
    compare.add_argument("--seed", type=int, default=11)
    compare.add_argument("--out", type=Path, required=True)
    manifest = commands.add_parser("manifest", help="build a pinned model manifest for registration on the lab")
    manifest.add_argument("directory", type=Path)
    manifest.add_argument("--model-id", required=True)
    manifest.add_argument("--revision", required=True, help="exact 40-character model and tokenizer commit")
    manifest.add_argument("--out", type=Path, help="new JSON file outside the model directory (default: stdout)")
    run = commands.add_parser("run", help="run an experiment on this machine")
    run.add_argument("spec", type=Path)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--device", default="cpu")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--timeout-seconds", type=float, default=None, help="bound on each generation")
    serve = commands.add_parser("serve", help="coordinate an experiment with external workers")
    serve.add_argument("spec", type=Path)
    serve.add_argument("--out", type=Path, required=True)
    serve.add_argument(
        "--host", help="bind address; standalone default is loopback, --lab requires an explicit address"
    )
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    serve.add_argument("--token-env", default="HETEROES_TOKEN")
    serve.add_argument("--timeout-seconds", type=float, default=1800)
    serve.add_argument("--worker-ids", help="comma-separated worker IDs eligible for audits")
    serve.add_argument("--audit-rate", type=float, default=0.05)
    serve.add_argument(
        "--scheduler", choices=SCHEDULER_POLICIES, default=DEFAULT_SCHEDULER_POLICY, help="how candidates go to workers"
    )
    serve.add_argument("--initial-adapter", type=Path, help="pinned initial LoRA weights (required on Windows)")
    serve.add_argument("--lab", help="offer the specification through an installed Worker's managed-lab agent")
    serve.add_argument("--workspace", help="workspace ID with --lab")
    serve.add_argument("--worker-home", type=Path, help="installed Linux CLI Worker home with --lab")
    serve.add_argument("--lab-token-env", default="HETEROES_LAB_ACCESS_TOKEN")
    worker = commands.add_parser("worker", help="generate texts for a self-hosted coordinator")
    worker.add_argument("--coordinator", required=True)
    worker.add_argument("--model-path", type=Path, required=True)
    worker.add_argument("--worker-id", required=True)
    worker.add_argument("--out", type=Path, required=True)
    worker.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    worker.add_argument("--token-env", default="HETEROES_TOKEN")
    worker.add_argument("--recipe-hash", help="expected recipe hash from the coordinator's ready receipt")
    args = parser.parse_args(argv)

    if args.command in ("serve", "worker"):
        from heteroes.v3 import distributed

        if args.command == "worker":
            return distributed.worker(
                args.coordinator,
                args.model_path,
                args.out,
                args.worker_id,
                device=args.device,
                token_env=args.token_env,
                expected_recipe_hash=args.recipe_hash,
            )
        spec = _resolve(json.loads(args.spec.read_text(encoding="utf-8")), args.spec.resolve().parent)
        if args.lab:
            if args.initial_adapter is not None:
                parser.error("the managed lab controls initial adapter creation")
            if (
                args.port != 8765
                or args.audit_rate != 0.05
                or args.timeout_seconds != 1800
                or args.scheduler != DEFAULT_SCHEDULER_POLICY
            ):
                parser.error(
                    "--lab uses the installed Worker's port and the managed lab's audit/time/scheduling settings"
                )
            from heteroes.v3.lab_cli import serve_lab

            return serve_lab(
                spec,
                args.lab,
                args.out,
                workspace=args.workspace,
                host=args.host,
                worker_ids=args.worker_ids.split(",") if args.worker_ids else [],
                worker_home=args.worker_home,
                device=args.device,
                token_env=args.lab_token_env,
            )
        distributed.serve(
            spec,
            args.out,
            host=args.host or "127.0.0.1",
            port=args.port,
            device=args.device,
            token_env=args.token_env,
            timeout_seconds=args.timeout_seconds,
            worker_ids=args.worker_ids.split(",") if args.worker_ids else None,
            audit_rate=args.audit_rate,
            initial_adapter=args.initial_adapter,
            scheduler=args.scheduler,
        )
        return 0

    if args.command == "eval":
        return evaluation.command(args)
    if args.command == "compare":
        from heteroes.v3.comparison import compare as compare_reports

        if args.out.exists():
            parser.error("choose a fresh output path")
        result = compare_reports(
            json.loads(args.a.read_text()),
            json.loads(args.b.read_text()),
            args.generation_a,
            args.generation_b,
            resamples=args.resamples,
            seed=args.seed,
        )
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return 0

    if args.command == "manifest":
        from heteroes.v3.model import registration_manifest

        if args.out is not None and args.out.resolve().is_relative_to(args.directory.resolve()):
            parser.error("write the manifest outside the model directory so it does not change the pinned file set")
        document = registration_manifest(args.directory, args.model_id, args.revision)
        text = json.dumps(document, sort_keys=True, indent=2) + "\n"
        if args.out is None:
            print(text, end="")
        else:
            with args.out.open("x", encoding="utf-8") as stream:
                stream.write(text)
        return 0

    from heteroes.v3.local import run_local

    spec = _resolve(json.loads(args.spec.read_text(encoding="utf-8")), args.spec.resolve().parent)
    summaries = run_local(
        spec, args.out, device=args.device, workers=args.workers, timeout_seconds=args.timeout_seconds
    )
    for summary in summaries:
        rewards = summary["rewards"]
        print(
            f"generation {summary['generation']}: mean reward {sum(rewards) / len(rewards):.4f}, "
            f"max {max(rewards):.4f}, child {summary['child_sha256'][:12]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
