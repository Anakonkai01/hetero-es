#!/usr/bin/env python3
"""
Run a worker: it asks the coordinator for candidates, evaluates them on this machine's GPU and reports the rewards.

    python scripts/run_worker.py --model-path <snapshot dir of Qwen2.5-0.5B-Instruct@7ae55760...> \
        --coordinator-url http://<tailscale address of the coordinator>:8765 --worker-id worker-1660s \
        --log artifacts/experiments/<date>-<name>/worker-1660s.jsonl

The worker takes sigma, the chunk size and eta from the coordinator's job, builds its own recipe with them from its own model,
workload and noise engine, and works only if the recipe hash is the job's (otherwise it prints what differs and exits with 3).
When the parent weights of a generation are not the ones in its model it downloads them (hash checked first) and loads them.
Exit codes: 0 finished or stopped, 3 not admitted, 4 put in quarantine (a restore failed: look at this machine), 5 the coordinator
stopped answering, 6 the coordinator aborted the experiment, 7 the coordinator refused the token, 2 bad usage.
The shared secret, if the coordinator uses one, is read from the environment variable named by --token-env (default HETEROES_TOKEN).
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
    parser.add_argument("--coordinator-url", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--log", required=True, help="JSONL file for the events of this worker (must not exist)")
    parser.add_argument("--cache-dir", default=str(Path.home() / ".cache" / "heteroes" / "worker-cache"),
                        help="where downloaded weights are kept (about 1 GB; use a real disk, /tmp may be RAM)")
    parser.add_argument("--device", choices=["cuda", "cpu"], default=None)
    parser.add_argument("--token-env", default="HETEROES_TOKEN")
    parser.add_argument("--chunk", type=int, default=1, help="prompts per generate() call; use the safe chunk of this worker's profile (default 1)")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--give-up-after-seconds", type=float, default=120.0, help="exit (code 5) if the coordinator has not answered for this long")
    parser.add_argument("--noise-threads", type=int, default=None, help="threads for noise generation (default: min(16, CPUs); 1 = serial)")
    parser.add_argument("--startup-timeout-seconds", type=float, default=600.0, help="how long to wait for the coordinator to have a job")
    args = parser.parse_args(argv)

    if Path(args.log).exists():
        fail(f"{args.log} already exists; evidence is never overwritten")
    if args.noise_threads is not None:
        if args.noise_threads < 1:
            fail("--noise-threads must be at least 1")
        os.environ["HETEROES_NOISE_THREADS"] = str(args.noise_threads)

    import torch

    from heteroes.executor import CandidateExecutor
    from heteroes.http_transport import HttpClient, TransportError, UnauthorizedError
    from heteroes.model.loading import build_recipe, check_noise_selftest, load_pinned_model
    from heteroes.runtime_info import JsonlLog, code_info, environment_info
    from heteroes.worker_runtime import AdmissionError, WorkerRuntime

    try:
        selftest_seconds = check_noise_selftest()
    except RuntimeError as error:
        fail(str(error), 3)

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    log = JsonlLog(args.log)

    def emit(event: dict) -> None:
        log(event)
        if event["event"] != "step" or event["kind"] != "NO_WORK":
            print(json.dumps(event), flush=True)

    emit({"event": "worker_start", "t": time.time(), "worker_id": args.worker_id, "environment": environment_info(device),
          "code": code_info(), "args": vars(args), "noise_selftest_seconds": selftest_seconds})
    load_started = time.perf_counter()
    loaded = load_pinned_model(args.model_path, device)
    emit({"event": "model_loaded", "t": time.time(), "worker_id": args.worker_id, "seconds": time.perf_counter() - load_started})

    client = HttpClient(args.coordinator_url, token=os.environ.get(args.token_env) or None, timeout=60.0)
    deadline = time.time() + args.startup_timeout_seconds
    job = None
    while job is None:
        try:
            if client.get_json("/v1/health").get("ok") is True:
                job = client.get_json("/v1/job")["job"]
        except UnauthorizedError as error:
            emit({"event": "unauthorized", "t": time.time(), "error": str(error)})
            fail(f"the coordinator refused the token (set {args.token_env} to the coordinator's): {error}", 7)
        except TransportError as error:
            emit({"event": "waiting_for_coordinator", "t": time.time(), "error": str(error)})
        if job is None:
            if time.time() > deadline:
                fail("the coordinator did not give a job in time", 3)
            time.sleep(args.poll_seconds)

    declared = job["recipe"]
    recipe = build_recipe(loaded, sigma=declared["perturbation"]["sigma"], chunk_elements=declared["noise"]["chunk_elements"],
                          reward_eta=declared["update"]["reward_eta"], eval_dtype=declared["workload"].get("eval_dtype", "float16"))
    executor_started = time.perf_counter()
    executor = CandidateExecutor(loaded.model, loaded.tokenizer, loaded.schema, recipe, chunk=args.chunk)
    emit({"event": "executor_ready", "t": time.time(), "worker_id": args.worker_id, "recipe_hash": recipe.hash,
          "parent_weights_sha256": executor.parent_sha256, "snapshot_and_hash_seconds": time.perf_counter() - executor_started})

    runtime = WorkerRuntime(args.worker_id, client, executor, args.cache_dir, log=emit, poll_seconds=args.poll_seconds,
                            max_unreachable_seconds=args.give_up_after_seconds)
    stop = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stop.set())
    try:
        runtime.admit()
        reason = runtime.run(stop)
    except UnauthorizedError as error:
        log.close()
        print(f"the coordinator refused the token: {error}", file=sys.stderr)
        return 7
    except AdmissionError as error:
        emit({"event": "not_admitted", "t": time.time(), "worker_id": args.worker_id, "error": str(error)})
        log.close()
        print(f"not admitted: {error}", file=sys.stderr)
        return 3
    log.close()
    return {"quarantined": 4, "unreachable": 5, "aborted": 6}.get(reason, 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
