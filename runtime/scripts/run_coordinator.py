#!/usr/bin/env python3
"""
Run the coordinator of an experiment: it serves the workers over HTTP, runs the generations and applies the updates.

    python scripts/run_coordinator.py --model-path <snapshot dir of Qwen2.5-0.5B-Instruct@7ae55760...> \
        --out-dir artifacts/experiments/<date>-<name>/coordinator --candidates 8 --generations 2 --alpha 1e-3 --sigma 1e-3 \
        --policy greedy --host 0.0.0.0 --port 8765

Everything it writes goes under --out-dir, which must not exist (evidence is never overwritten): `ledger.sqlite`, `events.jsonl`
(one line per event, with timings) and `summary.json` (written at the end). With --resume the directory must exist and is
continued: the ledger and the published weights say where the dead coordinator stopped (an unfinished generation is resumed, a
recorded update is applied from the stored record), the events are appended and the summary of the new run goes to the first free
`summary-resumeN.json`. Ctrl-C and SIGTERM end the run in an orderly way (the summary is written, the workers are told ABORTED). The weights of every generation are published as
`<sha256>.bin` in --weights-dir (about 1 GB each: keep it OUT of the repository). A shared secret for the workers can be given in the
environment variable named by --token-env (default HETEROES_TOKEN); it is never a command-line argument, which other users can read.
"""
import argparse
import json
import os
import signal
import sys
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
    parser.add_argument("--init-weights", default=None, help="start from these weights (a published `<sha256>.bin` file, for example a checkpoint of an earlier experiment) instead of the pinned checkpoint: "
                                                              "a new experiment that continues a model (needs --init-weights-sha256; not with --resume). The workers synchronize to them with the first job")
    parser.add_argument("--init-weights-sha256", default=None, help="the SHA-256 the --init-weights file must have (checked before the model is touched)")
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--alpha", type=float, default=1e-3)
    parser.add_argument("--sigma", type=float, default=1e-3)
    parser.add_argument("--chunk-elements", type=int, default=None, help="default: the contract value")
    parser.add_argument("--noise-engine", choices=["cpu", "cuda"], default="cpu",
                        help="the noise engine of the recipe: cpu = the canonical engine (any machine), cuda = the GPU engine of numerical contract section 16 (needs a CUDA GPU on the coordinator and on every worker)")
    parser.add_argument("--workload", choices=["arith16", "cot_l3_q32", "cot_l3_q64", "cot_l1_q128"], default="arith16",
                        help="the workload of the recipe: arith16 = the 16 prompts of the contract, cot_l3_q32 = the long arithmetic workload with reasoning (G7)")
    parser.add_argument("--decode-engine", choices=["hf_generate", "hf_compact"], default=None,
                        help="how the answers are generated, part of the recipe: the library's generate() or the compacting greedy decoder; default: the compacting decoder on a long workload, generate() on arith16")
    parser.add_argument("--eval-dtype", choices=["float16", "float32"], default="float32",
                        help="precision of the forward pass of the evaluation, part of the recipe: every worker takes it from the job (default float32, decision O8; see numerical contract section 15)")
    parser.add_argument("--policy", choices=["greedy", "wave", "proportional", "tail"], default="greedy",
                        help="greedy = B3, wave = B1 (static waves), proportional = B2 (needs one --quota per worker), tail = B4 (greedy that keeps a slow "
                             "worker away from the end of a generation; learns the speeds, see --speed-prior)")
    parser.add_argument("--speed-prior", action="append", default=[], metavar="WORKER=SECONDS", help="B4: the seconds a candidate takes on that worker, as a starting value (from a profile)")
    parser.add_argument("--tail-margin", type=float, default=1.0, help="B4: a worker waits when the others finish sooner than margin x its own duration")
    parser.add_argument("--quota", action="append", default=[], metavar="WORKER=N", help="B2: the candidates of that worker; they must add up to --candidates")
    parser.add_argument("--admit", default=None, help="comma-separated worker ids that get work (default: every worker); the others are refused work")
    parser.add_argument("--wave-size", type=int, default=2, help="candidates per wave for --policy wave: the number of workers")
    parser.add_argument("--lease-seconds", type=float, default=60.0, help="how long a lease lasts without a heartbeat: the workers renew it every third of this while they work, so it can be short and a dead worker is noticed in about this time")
    parser.add_argument("--stall-seconds", type=float, default=None, help="give up when nothing is committed for this long (default: five leases, at least a minute; 0 = never)")
    parser.add_argument("--resume", action="store_true", help="continue the experiment in an existing --out-dir (see above)")
    parser.add_argument("--allow-unauthenticated", action="store_true", help="listen on a non-loopback address without a token (a network that is private by other means)")
    parser.add_argument("--noise-threads", type=int, default=None, help="threads for noise generation (default: min(16, CPUs); 1 = serial)")
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
    priors = {}
    for item in args.speed_prior:
        name, _, number = item.partition("=")
        try:
            value = float(number)
        except ValueError:
            value = -1.0
        if not name or not value > 0 or name in priors:
            fail(f"bad --speed-prior {item!r}: use WORKER=SECONDS (positive), once per worker")
        priors[name] = value
    if args.policy != "tail" and (priors or args.tail_margin != 1.0):
        fail("--speed-prior and --tail-margin are only for --policy tail")
    out_dir = Path(args.out_dir)
    if args.resume and not (out_dir / "ledger.sqlite").is_file():
        fail(f"--resume needs {out_dir / 'ledger.sqlite'}: there is nothing to continue")
    if out_dir.exists() and not args.resume:
        fail(f"{out_dir} already exists; evidence is never overwritten (use --resume to continue it)")
    token = os.environ.get(args.token_env) or None
    if token is None and args.host not in ("127.0.0.1", "localhost", "::1") and not args.host.startswith("127.") and not args.allow_unauthenticated:
        fail(f"--host {args.host} without a token: set {args.token_env}, or pass --allow-unauthenticated for a private network")
    if args.noise_threads is not None:
        if args.noise_threads < 1:
            fail("--noise-threads must be at least 1")
        os.environ["HETEROES_NOISE_THREADS"] = str(args.noise_threads)
    if (args.init_weights is None) != (args.init_weights_sha256 is None):
        fail("--init-weights and --init-weights-sha256 go together")
    if args.init_weights is not None and args.resume:
        fail("--init-weights starts an experiment, --resume continues one: not both")
    if args.candidates < 2 or args.generations < 1:
        fail("--candidates must be at least 2 and --generations at least 1")

    import torch

    from heteroes.coordinator import Coordinator
    from heteroes.dispatch import AdmittedOnly, Greedy, GreedyTail, SpeedBook, StaticProportional, StaticWave
    from heteroes.ledger import Ledger
    from heteroes.model.loading import build_recipe, check_noise_selftest, check_recipe_selftest, load_pinned_model
    from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS
    from heteroes.runtime_info import JsonlLog, code_info, environment_info

    try:
        selftest_seconds = check_noise_selftest()
    except RuntimeError as error:
        fail(str(error))

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    out_dir.mkdir(parents=True, exist_ok=args.resume)
    log = JsonlLog(out_dir / "events.jsonl", append=args.resume)
    started = time.time()
    loaded = load_pinned_model(args.model_path, device)
    if args.init_weights is not None:
        from heteroes.model.weights_io import WeightsFileError, load_weights_
        try:
            load_weights_(loaded.model, loaded.schema, args.init_weights, args.init_weights_sha256)
        except (WeightsFileError, OSError, ValueError) as error:
            fail(f"cannot start from {args.init_weights}: {error}")
    if args.noise_engine == "cuda" and args.chunk_elements:
        fail("--chunk-elements is the chunk of the CPU noise engine: the CUDA engine has a fixed call size")
    recipe = build_recipe(loaded, sigma=args.sigma, chunk_elements=args.chunk_elements or (DEFAULT_CHUNK_ELEMENTS if args.noise_engine == "cpu" else None),
                          eval_dtype=args.eval_dtype, noise_engine=args.noise_engine, workload=args.workload,
                          decode_engine=args.decode_engine)
    try:
        engine_selftest_seconds = check_recipe_selftest(recipe, device)
    except RuntimeError as error:
        fail(str(error))
    ledger = Ledger(out_dir / "ledger.sqlite", max_attempts=args.max_attempts, enforce_chain=True)

    def emit(event: dict) -> None:
        log(event)
        print(json.dumps({key: value for key, value in event.items() if key not in ("rewards", "coefficients")}), flush=True)

    emit({"event": "coordinator_start", "t": time.time(), "environment": environment_info(device), "code": code_info(),
          "args": vars(args), "recipe_hash": recipe.hash, "recipe": recipe.to_dict(), "noise_selftest_seconds": selftest_seconds, "engine_selftest_seconds": engine_selftest_seconds})
    book = SpeedBook(prior=priors)                       # shared by the policies of every generation: a new generation does not start knowing nothing
    base = {"greedy": Greedy, "wave": lambda: StaticWave(args.wave_size), "proportional": lambda: StaticProportional(quotas),
            "tail": lambda: GreedyTail(book, margin=args.tail_margin)}[args.policy]
    admitted = None if args.admit is None else args.admit.split(",")
    policy = base if admitted is None else (lambda: AdmittedOnly(base(), admitted))
    coordinator = Coordinator(
        loaded.model, loaded.schema, recipe, ledger, args.weights_dir, args.experiment_id, args.candidates, args.alpha,
        policy_factory=policy, lease_seconds=args.lease_seconds, host=args.host, port=args.port,
        token=token, allow_unauthenticated=args.allow_unauthenticated, failed_grace_seconds=args.failed_grace_seconds, timeout_seconds=args.timeout_seconds,
        **({} if args.stall_seconds is None else {"stall_seconds": args.stall_seconds or None}), log=emit)
    coordinator.start()
    emit({"event": "listening", "t": time.time(), "url": coordinator.url, "initial_weights_sha256": coordinator.parent_sha256})

    def interrupt(signum, frame):
        raise KeyboardInterrupt(signal.Signals(signum).name)      # ends the run in an orderly way: the summary is written, the workers are told

    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, interrupt)

    outcome, summaries = "ok", []
    try:
        summaries = coordinator.run(args.generations)
    except BaseException as error:                    # noqa: BLE001 - the summary must say how it ended (a Ctrl-C included)
        outcome = f"{type(error).__name__}: {error}"
        emit({"event": "coordinator_error", "t": time.time(), "error": outcome})
    finally:
        time.sleep(args.linger_seconds)
        coordinator.stop()
    summary = {"outcome": outcome, "total_seconds": time.time() - started, "recipe_hash": recipe.hash, "args": vars(args),
               "initial_weights_sha256": summaries[0]["parent_sha256"] if summaries else None,
               "final_weights_sha256": coordinator.parent_sha256, "generations": summaries,
               "internal_errors": coordinator.server.internal_errors, "environment": environment_info(device), "code": code_info()}
    target = out_dir / "summary.json"
    for attempt in range(1, 1000):
        if not target.exists():
            break
        target = out_dir / f"summary-resume{attempt}.json"           # a summary is evidence: never overwritten
    target.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    log.close()
    print(f"wrote {target}: {outcome}", flush=True)
    return 0 if outcome == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
