#!/usr/bin/env python3
"""
Run benchmark conditions on the two machines, one after the other, and keep the raw logs of every run (G4 and G5 of MASTER).

    python scripts/run_benchmark.py --out-dir artifacts/experiments/<dir> --candidates 8 --generations 3 --repeats 1 \
        --conditions B0,B3,B2 --profile-reference <profile-5070ti.json> --profile-candidate <profile-1660s.json>

Run on the coordinator's machine (the 5070 Ti). For each condition and repeat it starts a coordinator, a local worker and (if the
condition uses it) a worker on the 1660S through SSH, waits until the experiment is finished, copies the remote log back, and
deletes the published and cached weights (1 GB per generation) so that the disk never fills. Every run has the same experiment id,
so every candidate has the same seed in every run: the rewards and weights hashes of the runs must be identical (summarize_benchmark.py checks).

Conditions (MASTER policy ids; a worker is "fast" = the 5070 Ti, "slow" = the 1660S):
  B0  the fast worker alone, one prompt per generate() call            B1  waves of two, both workers, chunk 1
  Any condition can end in xK (B0x2, B3x2): K worker processes share the fast GPU (default 1).
  B2  quotas by measured speed (largest remainder), both, chunk 1      B3  greedy, both, chunk 1
  B4  greedy that keeps the slow worker away from the end of a generation (starts from the profiles' speeds, then learns)
  H0  the integrated system: the admission of `--prediction` (variant per_worker_chunk) decides who works, each worker uses
      the safe chunk of its profile, dynamic dispatch. If the admission leaves only the fast worker, H0 is "the fast worker alone with
      its safe chunk": it is NOT B0 (the chunk differs) and it is not a new scheduler.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cluster_runner import FAST, SLOW, Cluster, add_cluster_arguments, wait_health  # noqa: E402,F401

REPO = Path(__file__).resolve().parents[1]


def parse_condition(condition: str) -> tuple[str, int]:
    """"B3" -> ("B3", 1); "B0x2" -> ("B0", 2): the number after x is how many worker PROCESSES share the fast GPU (a 5070 Ti is idle most of a candidate: its CPU noise and its GPU rollout overlap across processes)."""
    match = re.fullmatch(r"([A-Z]\d)(?:x(\d+))?", condition)
    if match is None:
        raise ValueError(f"unknown condition {condition!r}")
    k = int(match.group(2) or 1)
    if k < 1:
        raise ValueError(f"unknown condition {condition!r}")
    return match.group(1), k


def seconds_at(profile: dict, chunk: int) -> float:
    """The median candidate time of a profile at `chunk` if it was timed there, else at chunk 1 (what the profiles of G4/G5 have)."""
    times = profile.get("candidate_times", {}).get(str(chunk))
    if times is not None and times.get("total_median"):
        return times["total_median"]
    return profile["candidate_seconds_at_chunk_1"]


def fast_worker_ids(k: int) -> list[str]:
    return [FAST] + [f"{FAST}-{i}" for i in range(2, k + 1)]


def plan(condition: str, candidates: int, reference: dict, candidate: dict, prediction: dict | None, chunk: int = 1) -> dict:
    """Who works, with which chunk, under which policy: pure, so that it can be tested."""
    from heteroes.dispatch import proportional_quotas

    base, k = parse_condition(condition)
    fast = fast_worker_ids(k)
    fast1 = seconds_at(reference, chunk)
    slow1 = seconds_at(candidate, chunk)
    alone = {worker: chunk for worker in fast}
    both = {**alone, SLOW: chunk}
    if base == "B0":
        return {"workers": alone, "policy": "greedy", "args": []}
    if base == "B1":
        return {"workers": both, "policy": "wave", "args": ["--wave-size", str(len(both))]}
    if base == "B2":
        speeds = {**{worker: 1.0 / fast1 for worker in fast}, SLOW: 1.0 / slow1}
        quotas = proportional_quotas(candidates, speeds)
        return {"workers": both, "policy": "proportional", "args": [a for w, q in sorted(quotas.items()) for a in ("--quota", f"{w}={q}")],
                "quotas": quotas}
    if base == "B3":
        return {"workers": both, "policy": "greedy", "args": []}
    if base == "B4":
        return {"workers": both, "policy": "tail", "args": [a for w, seconds in sorted({**{f: fast1 for f in fast}, SLOW: slow1}.items())
                                                            for a in ("--speed-prior", f"{w}={seconds}")]}
    if base == "H0":
        if k != 1:
            raise ValueError("H0 is defined for one process on the fast GPU")
        if prediction is None:
            raise ValueError("H0 needs --prediction")
        state = prediction["variants"]["per_worker_chunk"]["decision_b3"]["state"]
        workers = {FAST: reference["safe_chunk"]}
        if state in ("ADMITTED", "ADMITTED_LIMITED"):
            workers[SLOW] = candidate["safe_chunk"]
        return {"workers": workers, "policy": "greedy", "args": ["--admit", ",".join(sorted(workers))], "admission_state": state}
    raise ValueError(f"unknown condition {condition!r}")


def existing_run_state(run_dir: Path) -> str:
    """"ok" (a finished run to keep), "failed" (a run that ended badly or never finished: it is set aside and redone) or "new"."""
    if not run_dir.exists():
        return "new"
    record = run_dir / "run.json"
    if record.is_file():
        try:
            if json.loads(record.read_text(encoding="utf-8")).get("outcome") == "ok":
                return "ok"
        except ValueError:
            pass
    return "failed"


def set_aside(run_dir: Path) -> Path:
    """Evidence is never overwritten and never deleted: a failed attempt is renamed, and the run is made again in a clean directory."""
    for number in range(1, 1000):
        target = run_dir.with_name(f"{run_dir.name}.failed-attempt{number}")
        if not target.exists():
            run_dir.rename(target)
            return target
    raise RuntimeError(f"too many failed attempts of {run_dir.name}")


def run_one(name: str, spec: dict, args, run_dir: Path) -> dict:
    run_dir.mkdir(parents=True)
    cluster = Cluster(args, name, run_dir)
    started = time.time()
    try:
        coordinator = cluster.start_coordinator(spec["policy"], spec["args"], args.candidates, args.generations)
        for worker, chunk in spec["workers"].items():
            cluster.start_worker(worker, chunk)
        deadline = time.time() + args.run_timeout
        while coordinator.poll() is None:
            if time.time() > deadline:
                raise TimeoutError(f"{name} did not finish in {args.run_timeout} s")
            time.sleep(2)
        for worker in spec["workers"]:
            try:
                cluster.processes[worker].wait(timeout=120)
            except subprocess.TimeoutExpired:
                pass
        outcome = "ok" if coordinator.returncode == 0 else f"coordinator exit {coordinator.returncode}"
    except BaseException as error:                    # noqa: BLE001 - the run must say how it ended
        outcome = f"{type(error).__name__}: {error}"
    finally:
        cluster.collect_and_clean(spec["workers"])
    record = {"name": name, "outcome": outcome, "wall_seconds": time.time() - started, "spec": spec}
    (run_dir / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--candidates", type=int, required=True)
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--conditions", required=True)
    parser.add_argument("--profile-reference", required=True)
    parser.add_argument("--profile-candidate", required=True)
    parser.add_argument("--prediction", default=None)
    parser.add_argument("--chunk", type=int, default=None, help="prompts per generate() call for every worker of the B conditions "
                                                                "(default: the exact size of --eval-dtype, 16 for float32 and 1 for float16; see the cross-GPU evidence)")
    parser.add_argument("--first-repeat", type=int, default=1, help="number the repeats from this (to add repeats later)")
    add_cluster_arguments(parser)
    parser.add_argument("--run-timeout", type=float, default=3600.0)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(REPO / "src"))

    reference = json.loads(Path(args.profile_reference).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.profile_candidate).read_text(encoding="utf-8"))
    prediction = None if args.prediction is None else json.loads(Path(args.prediction).read_text(encoding="utf-8"))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    conditions = args.conditions.split(",")
    from heteroes.eval.precision import default_chunk

    if args.chunk is None:
        args.chunk = default_chunk(args.eval_dtype)
    specs = {name: plan(name, args.candidates, reference, candidate, prediction, args.chunk) for name in conditions}
    (out / f"plan-n{args.candidates}.json").write_text(json.dumps({"args": vars(args), "specs": specs}, indent=2) + "\n", encoding="utf-8")
    failed = 0
    for repeat in range(args.first_repeat, args.first_repeat + args.repeats):
        for name in conditions:                           # repeats go round the conditions, so a drift in the machines is spread
            run_name = f"n{args.candidates}-{name}-r{repeat}"
            state = existing_run_state(out / run_name)
            if state == "ok":
                print(f"skip {run_name}: it ran", flush=True)
                continue
            if state == "failed":
                print(f"{run_name}: a failed attempt exists, set aside as {set_aside(out / run_name).name}", flush=True)
            print(f"=== {run_name}: {specs[name]['workers']} {specs[name]['policy']}", flush=True)
            record = run_one(run_name, specs[name], args, out / run_name)
            print(f"    {record['outcome']} in {record['wall_seconds']:.0f} s", flush=True)
            failed += record["outcome"] != "ok"
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
