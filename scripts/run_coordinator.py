#!/usr/bin/env python3
"""
Run the coordinator of an experiment: it serves the workers over HTTP, runs the generations and applies the updates.

    python scripts/run_coordinator.py --model-path <snapshot dir of Qwen2.5-0.5B-Instruct@7ae55760...> \
        --out-dir artifacts/experiments/<date>-<name>/coordinator --candidates 8 --generations 2 --alpha 1e-3 --sigma 1e-3 \
        --policy greedy --host 0.0.0.0 --port 8765

Everything it writes goes under --out-dir, which must not exist (evidence is never overwritten): `ledger.sqlite`, `events.jsonl`
(one line per event, with timings) and `summary.json` (written at the end). The weights of every generation are published as
`<sha256>.bin` in --weights-dir (about 1 GB each: keep it OUT of the repository). A shared secret for the workers can be given in the
environment variable named by --token-env (default HETEROES_TOKEN); it is never a command-line argument, which other users can read.
"""
import argparse
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path


def fail(message: str, code: int = 2) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(code)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--out-dir", required=True, help="directory to create for ledger, events and summary (must not exist)")
    parser.add_argument("--weights-dir", default=str(Path.home() / ".cache" / "heteroes" / "published"),
                        help="where the weights of each generation are published (about 1 GB each: use a real disk, /tmp may be RAM)")
    parser.add_argument("--experiment-id", default="g3")
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--alpha", type=float, default=1e-3)
    parser.add_argument("--sigma", type=float, default=1e-3)
    parser.add_argument("--chunk-elements", type=int, default=None, help="default: the contract value")
    parser.add_argument("--policy", choices=["greedy", "wave", "proportional"], default="greedy",
                        help="greedy = B3, wave = B1 (static waves), proportional = B2 (needs one --quota per worker)")
    parser.add_argument("--quota", action="append", default=[], metavar="WORKER=N", help="B2: the candidates of that worker; they must add up to --candidates")
    parser.add_argument("--admit", default=None, help="comma-separated worker ids that get work (default: every worker); the others are refused work")
    parser.add_argument("--wave-size", type=int, default=2, help="candidates per wave for --policy wave: the number of workers")
    parser.add_argument("--lease-seconds", type=float, default=600.0, help="how long a worker may hold a candidate (the slowest worker needs several minutes for a candidate)")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--failed-grace-seconds", type=float, default=60.0)
    parser.add_argument("--timeout-seconds", type=float, default=None, help="give up on a generation after this long (default: wait)")
    parser.add_argument("--linger-seconds", type=float, default=20.0, help="keep answering FINISHED this long after the last generation, so that the workers see the end")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token-env", default="HETEROES_TOKEN")
    parser.add_argument("--device", choices=["cuda", "cpu"], default=None)
    args = parser.parse_args(argv)

    quotas = {}
    for item in args.quota:
        name, _, number = item.partition("=")
        if not name or not number.isdigit() or name in quotas:
            fail(f"bad --quota {item!r}: use WORKER=N, once per worker")
        quotas[name] = int(number)
    if args.policy == "proportional" and sum(quotas.values()) != args.candidates:
        fail(f"the quotas add up to {sum(quotas.values())}, not to --candidates {args.candidates}")
    if args.policy != "proportional" and quotas:
        fail("--quota is only for --policy proportional")
    out_dir = Path(args.out_dir)
    if out_dir.exists():
        fail(f"{out_dir} already exists; evidence is never overwritten")
    if args.candidates < 2 or args.generations < 1:
        fail("--candidates must be at least 2 and --generations at least 1")

    import torch

    from heteroes.coordinator import Coordinator
    from heteroes.dispatch import AdmittedOnly, Greedy, StaticProportional, StaticWave
    from heteroes.ledger import Ledger
    from heteroes.model.loading import build_recipe, check_noise_selftest, load_pinned_model
    from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS
    from heteroes.runtime_info import JsonlLog, code_info, environment_info

    try:
        selftest_seconds = check_noise_selftest()
    except RuntimeError as error:
        fail(str(error))

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    out_dir.mkdir(parents=True)
    log = JsonlLog(out_dir / "events.jsonl")
    started = time.time()
    loaded = load_pinned_model(args.model_path, device)
    recipe = build_recipe(loaded, sigma=args.sigma, chunk_elements=args.chunk_elements or DEFAULT_CHUNK_ELEMENTS)
    ledger = Ledger(out_dir / "ledger.sqlite", max_attempts=args.max_attempts)

    def emit(event: dict) -> None:
        log(event)
        print(json.dumps({key: value for key, value in event.items() if key not in ("rewards", "coefficients")}), flush=True)

    emit({"event": "coordinator_start", "t": time.time(), "environment": environment_info(device), "code": code_info(),
          "args": vars(args), "recipe_hash": recipe.hash, "recipe": recipe.to_dict(), "noise_selftest_seconds": selftest_seconds})
    base = {"greedy": Greedy, "wave": lambda: StaticWave(args.wave_size), "proportional": lambda: StaticProportional(quotas)}[args.policy]
    admitted = None if args.admit is None else args.admit.split(",")
    policy = base if admitted is None else (lambda: AdmittedOnly(base(), admitted))
    coordinator = Coordinator(
        loaded.model, loaded.schema, recipe, ledger, args.weights_dir, args.experiment_id, args.candidates, args.alpha,
        policy_factory=policy, lease_seconds=args.lease_seconds, host=args.host, port=args.port,
        token=os.environ.get(args.token_env) or None, failed_grace_seconds=args.failed_grace_seconds,
        timeout_seconds=args.timeout_seconds, log=emit)
    coordinator.start()
    emit({"event": "listening", "t": time.time(), "url": coordinator.url, "initial_weights_sha256": coordinator.parent_sha256})

    stop = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: (stop.set(), os._exit(130)))

    outcome, summaries = "ok", []
    try:
        summaries = coordinator.run(args.generations)
    except BaseException as error:                    # noqa: BLE001 - the summary must say how it ended
        outcome = f"{type(error).__name__}: {error}"
        emit({"event": "coordinator_error", "t": time.time(), "error": outcome})
    finally:
        time.sleep(args.linger_seconds)
        coordinator.stop()
    summary = {"outcome": outcome, "total_seconds": time.time() - started, "recipe_hash": recipe.hash, "args": vars(args),
               "initial_weights_sha256": summaries[0]["parent_sha256"] if summaries else None,
               "final_weights_sha256": coordinator.parent_sha256, "generations": summaries,
               "internal_errors": coordinator.server.internal_errors, "environment": environment_info(device), "code": code_info()}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    log.close()
    print(f"wrote {out_dir / 'summary.json'}: {outcome}", flush=True)
    return 0 if outcome == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
