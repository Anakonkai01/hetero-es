"""
    python -m heteroes.v3 run spec.json --out RUN_DIR [--device cpu|cuda] [--workers N]

Runs a Recipe v3 experiment on this machine (`heteroes.v3.local.run_local`). `spec.json` is the configuration documented in
`runtime/docs/v3-local-runs.md`; relative paths in it are read from the spec's directory. Prints one line per generation.
"""

import argparse
import json
from pathlib import Path


def _resolve(spec, base):
    spec = json.loads(json.dumps(spec))
    for section, key in (("model", "path"), ("data", "path"), ("scorer", "path")):
        if key in spec.get(section, {}) and not Path(spec[section][key]).is_absolute():
            spec[section][key] = str(base / spec[section][key])
    return spec


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="heteroes", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run an experiment on this machine")
    run.add_argument("spec", type=Path)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--device", default="cpu")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--timeout-seconds", type=float, default=None, help="bound on each generation")
    args = parser.parse_args(argv)

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
