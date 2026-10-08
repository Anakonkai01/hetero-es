#!/usr/bin/env python3
"""
Measure the profile of THIS machine's GPU for the pinned model, ONE workload and ONE noise engine (C1, MASTER section 8) and write it as JSON.

    python scripts/profile_worker.py --model-path <snapshot dir> --worker-id worker-5070ti --out artifacts/experiments/<dir>/profile-5070ti.json
        [--workload arith16|cot_l3_q32|cot_l3_q64|cot_l1_q128] [--noise-engine cpu|cuda]   # default: the 16 prompts and the CPU engine, as before 08/10
        [--chunks 1,2,4,8,16] [--candidates 5] [--probe-candidates 32] [--sigma 1e-3]
        [--sync-url http://10.10.10.1:8765 --sync-sha256 <hash printed by scripts/serve_weights.py>]   # (the server's token is read from HETEROES_TOKEN) the link and the sync of a remote worker
        [--measure-update [--update-sizes 1,2,4,8]]   # the coordinator's update cost at several numbers of candidates, fitted as fixed + per candidate x N (run it on the coordinator's host)

What it checks and records:
  * the noise self-test (of the chosen engine), and that the restore after a perturbation is bit-exact (`checks`);
  * for each number of prompts per generate() call (chunk), on the parent weights and on --probe-candidates perturbed candidates: did it fit in
    memory, were the answers the same TEXT as one prompt at a time, how long did the whole prompt set take (`chunk_probes`);
    the safe chunk is the largest exact one; for the 16 prompts chunk 1 must also give the answers recorded by the probe of 2026-09-29; for the other workloads
    no such record exists, so chunk 1 is run twice and must give the same text both times (`reference_kind` says which check was made);
    a long workload takes minutes per condition: lower --probe-candidates and --candidates for it;
  * the duration of real candidates (perturb + rollout + restore) at chunk 1 and at the safe chunk (`candidate_times`);
  * optionally the round trip to a server and the time of a full synchronization (`sync`), and the update cost per candidate (`update`).
The output file must not exist (evidence is never overwritten).
"""
import argparse
import contextlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_FILE = REPO_ROOT / "artifacts" / "probes" / "2026-09-29" / "probe_5070ti.json"
PROFILE_SEED_BASE = 7001                 # the perturbed candidates on which the chunks are compared: seeds 7001, 7002, ...


def fail(message: str, code: int = 2) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(code)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--chunks", default="1,2,4,8,16")
    parser.add_argument("--candidates", type=int, default=5, help="real candidates to time at each chunk")
    parser.add_argument("--probe-candidates", type=int, default=32,
                        help="perturbed candidates on which every chunk is compared with chunk 1 (a rare difference needs many: with a "
                             "4 percent rate, 2 candidates see it 8 percent of the time, 32 see it 73 percent)")
    parser.add_argument("--sigma", type=float, default=1e-3)
    parser.add_argument("--workload", default="arith16", help="the workload of the recipe (heteroes.manifest.WORKLOAD_NAMES)")
    parser.add_argument("--noise-engine", choices=["cpu", "cuda"], default="cpu", help="the engine of the recipe; cuda needs --device cuda")
    parser.add_argument("--eval-dtype", choices=["float16", "float32"], default="float32",
                        help="precision of the forward pass of the evaluation (part of the recipe): the chunks are compared and the candidates timed with it")
    parser.add_argument("--sync-url", default=None)
    parser.add_argument("--sync-sha256", default=None)
    parser.add_argument("--sync-dir", default=str(Path.home() / ".cache" / "heteroes" / "profile-sync"))
    parser.add_argument("--measure-update", action="store_true")
    parser.add_argument("--update-sizes", default="1,2,4,8", help="numbers of candidates at which the update is timed (at least two different)")
    parser.add_argument("--update-repeats", type=int, default=2, help="timings per size (the fit uses their median)")
    parser.add_argument("--device", choices=["cuda", "cpu"], default=None)
    args = parser.parse_args(argv)
    if Path(args.out).exists():
        fail(f"{args.out} already exists; evidence is never overwritten")
    if bool(args.sync_url) != bool(args.sync_sha256):
        fail("--sync-url and --sync-sha256 go together")
    chunks = sorted({int(value) for value in args.chunks.split(",")})
    from heteroes.manifest import WORKLOAD_NAMES
    if args.workload not in WORKLOAD_NAMES:
        fail(f"--workload must be one of {WORKLOAD_NAMES}")

    import torch

    from heteroes.es.snapshot import RestoreError, restore_from_snapshot_, take_snapshot
    from heteroes.eval.workloads import get_workload
    from heteroes.executor import CandidateExecutor
    from heteroes.http_transport import HttpClient
    from heteroes.manifest import CandidateDescriptor
    from heteroes.model.loading import build_recipe, check_noise_selftest, check_recipe_selftest, load_pinned_model
    from heteroes.model.weights_io import load_weights_, publish_weights
    from heteroes.noise.parallel import noise_threads
    from heteroes.profile import PROFILE_FORMAT, fit_affine, key_hash, probe_chunks, profile_key, safe_chunk, summarize_times
    from heteroes.profile_setup import noise_ops, profile_texts, reference_check_applies
    from heteroes.runtime_info import code_info, environment_info
    from heteroes.worker import CandidateFailed
    from heteroes.worker_runtime import download_weights

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    cuda = device == "cuda"
    if args.noise_engine == "cuda" and not cuda:
        fail("--noise-engine cuda needs a CUDA device")
    checks = {"noise_selftest": True, "restore_exact": True, "chunk1_reproduces_reference": False}

    loaded = load_pinned_model(args.model_path, device)
    model, tokenizer, schema = loaded.model, loaded.tokenizer, loaded.schema
    recipe = build_recipe(loaded, sigma=args.sigma, eval_dtype=args.eval_dtype, noise_engine=args.noise_engine, workload=args.workload)
    try:
        selftest_seconds = check_recipe_selftest(recipe, device)      # the self-test of the engine the recipe names
    except RuntimeError:
        checks["noise_selftest"], selftest_seconds = False, None
    perturb_op, update_op = noise_ops(recipe.engine_version, recipe.chunk_elements if args.noise_engine == "cpu" else None)
    from heteroes.eval.precision import EvalModel
    evaluation = EvalModel(model, args.eval_dtype)
    evaluation.refresh()
    snapshot = take_snapshot(model, schema)

    def texts_at(chunk: int) -> list[str]:
        evaluation.refresh()                                       # an FP32 copy takes the weights of the state the model is in
        return profile_texts(args.workload, evaluation.model, tokenizer, chunk)

    state = {"restore_ok": True}

    @contextlib.contextmanager
    def parent():
        yield

    def perturbed(seed: int):
        @contextlib.contextmanager
        def condition():
            perturb_op(model, schema, seed, recipe.sigma)
            try:
                yield
            finally:
                try:
                    restore_from_snapshot_(model, schema, snapshot)
                except RestoreError:
                    state["restore_ok"] = False
                    raise
        return condition

    def is_oom(error: BaseException) -> bool:
        return isinstance(error, torch.cuda.OutOfMemoryError)

    probes = probe_chunks([parent] + [perturbed(PROFILE_SEED_BASE + index) for index in range(args.probe_candidates)], texts_at, chunks, is_oom, time.perf_counter,
                          reset_peak=(torch.cuda.reset_peak_memory_stats if cuda else (lambda: None)),
                          peak_bytes=(torch.cuda.max_memory_allocated if cuda else (lambda: None)))
    if cuda:
        torch.cuda.empty_cache()
    checks["restore_exact"] = state["restore_ok"]
    if reference_check_applies(args.workload):
        reference_kind = "recorded_probe_2026-09-29"
        recorded = json.loads(PROBE_FILE.read_text(encoding="utf-8"))["base_evaluation"]["records"]
        checks["chunk1_reproduces_reference"] = texts_at(1) == [record["output_text"].strip() for record in recorded]
    else:
        reference_kind = "chunk1_twice_equal"                         # no recorded answers exist for this workload: the weaker check that the parent's text is repeatable
        checks["chunk1_reproduces_reference"] = texts_at(1) == texts_at(1)
    chosen = safe_chunk(probes)
    evaluation = None                                              # the FP32 copy of the probes is freed: each executor below makes its own, and two would double the measured peak
    if cuda:
        torch.cuda.empty_cache()

    def time_candidates(chunk: int) -> dict:
        executor = CandidateExecutor(model, tokenizer, schema, recipe, chunk=chunk)
        if cuda:
            torch.cuda.reset_peak_memory_stats()
        samples = []
        for index in range(args.candidates):
            descriptor = CandidateDescriptor(recipe_hash=recipe.hash, parent_weights_sha256=executor.parent_sha256, experiment_id="profile",
                                             generation=0, index=index, seed=9000 + index)
            try:
                executor(descriptor)
            except CandidateFailed as failed:
                fail(f"a candidate failed at chunk {chunk} while it was timed: {failed.kind.value} ({failed}); a profile with a failed candidate is not written", 3)
            samples.append(executor.last_timing)
        return {"chunk": chunk, "raw": samples, **summarize_times(samples),
                "peak_bytes": torch.cuda.max_memory_allocated() if cuda else None}

    candidate_times = {"1": time_candidates(1)}
    if chosen != 1:
        candidate_times[str(chosen)] = time_candidates(chosen)
    reference_times = candidate_times[str(chosen)]
    sync_executor = CandidateExecutor(model, tokenizer, schema, recipe)         # made before the timing, as in a running worker
    parent_sha256 = sync_executor.parent_sha256

    sync = None
    if args.sync_url:
        client = HttpClient(args.sync_url, token=os.environ.get("HETEROES_TOKEN") or None, timeout=60.0)     # the token of serve_weights.py, from the environment
        rtts = []
        for _ in range(20):
            start = time.perf_counter()
            client.get_json("/v1/health")
            rtts.append(time.perf_counter() - start)
        directory = Path(args.sync_dir)
        start = time.perf_counter()
        path = download_weights(client, args.sync_sha256, directory)
        transferred = time.perf_counter()
        load_weights_(model, schema, path, args.sync_sha256, already_verified=True)      # what WorkerRuntime.sync does
        loaded_at = time.perf_counter()
        sync_executor.reset_parent(args.sync_sha256, verified_file=path)
        done = time.perf_counter()
        size_on_disk = path.stat().st_size
        path.unlink()
        sync = {"url": args.sync_url, "rtt_median_seconds": statistics.median(rtts), "rtt_max_seconds": max(rtts),
                "weights_sha256": args.sync_sha256, "transfer_seconds": transferred - start, "load_seconds": loaded_at - transferred,
                "rehash_seconds": done - loaded_at, "total_seconds": done - start,
                "same_as_parent": args.sync_sha256 == parent_sha256, "weights_bytes": size_on_disk}
        sync["throughput_mb_per_second"] = sync["weights_bytes"] / 1e6 / sync["transfer_seconds"]

    update = None
    if args.measure_update:
        sizes = sorted({int(value) for value in args.update_sizes.split(",")})
        if len(sizes) < 2:
            fail("--update-sizes needs at least two different sizes")
        raw, medians = {}, []
        for size in sizes:
            seeds = [11 + index for index in range(size)]
            coefficients = [1.0 if index % 2 == 0 else -0.5 for index in range(size)]       # not all equal: an update that does something
            raw[str(size)] = []
            for _ in range(args.update_repeats):
                start = time.perf_counter()
                update_op(model, schema, seeds, coefficients, 1e-3)
                if cuda:
                    torch.cuda.synchronize()
                raw[str(size)].append(time.perf_counter() - start)
                restore_from_snapshot_(model, schema, snapshot)
            medians.append(statistics.median(raw[str(size)]))
        fit = fit_affine(sizes, medians)
        timings = raw[str(sizes[0])]
        directory = Path(args.sync_dir)
        start = time.perf_counter()
        published = publish_weights(model, schema, directory)
        publish_seconds = time.perf_counter() - start
        (directory / f"{published}.bin").unlink()
        from heteroes.eval.candidate import model_weights_sha256
        start = time.perf_counter()
        model_weights_sha256(model, schema)
        hash_seconds = time.perf_counter() - start                                  # what a replay pays to check the weights it made
        update = {"seconds_per_candidate_median": fit["per_candidate_seconds"], "fixed_seconds": fit["fixed_seconds"], "fit": fit, "raw": raw,
                  "publish_seconds": publish_seconds, "hash_seconds": hash_seconds, "noise_threads": noise_threads()}

    environment = environment_info(device)
    key = profile_key(environment, recipe.hash, schema.hash, get_workload(args.workload).hash(), device)
    profile = {
        "format": PROFILE_FORMAT, "worker_id": args.worker_id, "measured_at_unix": time.time(),
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "key": key, "key_hash": key_hash(key), "environment": environment, "code": code_info(),
        "recipe_hash": recipe.hash, "parent_weights_sha256": parent_sha256, "sigma": recipe.sigma,
        "checks": checks, "reference_kind": reference_kind, "workload": args.workload, "noise_engine": recipe.engine_version, "noise_selftest_seconds": selftest_seconds,
        "chunk_probes": [probe.to_dict() for probe in probes], "safe_chunk": chosen,
        "candidate_times": candidate_times, "candidate_seconds_at_safe_chunk": reference_times.get("total_median"),
        "candidate_seconds_at_chunk_1": candidate_times["1"].get("total_median"),
        "peak_bytes_candidate": reference_times.get("peak_bytes"), "sync": sync, "update": update, "args": vars(args),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "x", encoding="utf-8") as file:
        json.dump(profile, file, indent=2)
        file.write("\n")
    print(json.dumps({key_: profile[key_] for key_ in ("worker_id", "safe_chunk", "checks", "candidate_seconds_at_chunk_1",
                                                         "candidate_seconds_at_safe_chunk", "peak_bytes_candidate")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
