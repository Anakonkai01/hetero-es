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
  B2  quotas by measured speed (largest remainder), both, chunk 1      B3  greedy, both, chunk 1
  H0  the integrated system: the admission of `--prediction` (variant per_worker_chunk) decides who works, each worker uses
      the safe chunk of its profile, dynamic dispatch. If the admission leaves only the fast worker, H0 is "the fast worker alone with
      its safe chunk": it is NOT B0 (the chunk differs) and it is not a new scheduler.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FAST, SLOW = "worker-5070ti", "worker-1660s"
MODEL = "7ae557604adf67be50417f59c2c2f167def9a775"
LOCAL_MODEL = str(Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots" / MODEL)
# the defaults are the two machines of the project (a direct cable between them); every one can be changed on the command line
DEFAULTS = {"remote": "anakonkai@10.10.10.2", "remote_repo": "~/projects/heteroes/hetero-es",
            "remote_python": "~/projects/heteroes/.venv/bin/python", "host": "10.10.10.1", "port": 8765}


def plan(condition: str, candidates: int, reference: dict, candidate: dict, prediction: dict | None) -> dict:
    """Who works, with which chunk, under which policy: pure, so that it can be tested."""
    from heteroes.dispatch import proportional_quotas

    fast1 = reference["candidate_seconds_at_chunk_1"]
    slow1 = candidate["candidate_seconds_at_chunk_1"]
    both = {FAST: 1, SLOW: 1}
    if condition == "B0":
        return {"workers": {FAST: 1}, "policy": "greedy", "args": []}
    if condition == "B1":
        return {"workers": both, "policy": "wave", "args": ["--wave-size", "2"]}
    if condition == "B2":
        quotas = proportional_quotas(candidates, {FAST: 1.0 / fast1, SLOW: 1.0 / slow1})
        return {"workers": both, "policy": "proportional", "args": [a for w, q in sorted(quotas.items()) for a in ("--quota", f"{w}={q}")],
                "quotas": quotas}
    if condition == "B3":
        return {"workers": both, "policy": "greedy", "args": []}
    if condition == "H0":
        if prediction is None:
            raise ValueError("H0 needs --prediction")
        state = prediction["variants"]["per_worker_chunk"]["decision_b3"]["state"]
        workers = {FAST: reference["safe_chunk"]}
        if state in ("ADMITTED", "ADMITTED_LIMITED"):
            workers[SLOW] = candidate["safe_chunk"]
        return {"workers": workers, "policy": "greedy", "args": ["--admit", ",".join(sorted(workers))], "admission_state": state}
    raise ValueError(f"unknown condition {condition!r}")


def wait_health(url: str, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            with urllib.request.urlopen(url + "/v1/health", timeout=2) as reply:
                if reply.status == 200:
                    return
        except OSError:
            time.sleep(1)
    raise TimeoutError(f"no answer from {url}")


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
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONPATH": str(REPO / "src")}
    if args.noise_threads is not None:
        env["HETEROES_NOISE_THREADS"] = str(args.noise_threads)
    local_python = args.local_python or sys.executable
    HOST, PORT = args.host, args.port
    REMOTE, REMOTE_REPO, REMOTE_PYTHON = args.remote, args.remote_repo, args.remote_python
    url = f"http://{HOST}:{PORT}"
    processes = {}
    started = time.time()
    # this run's own scratch space (published weights, worker cache): only it is deleted afterwards, never a shared cache directory
    scratch = Path(args.scratch_dir) / name
    PUBLISHED, LOCAL_CACHE = scratch / "published", scratch / "worker-cache"
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)
    remote_dir = f"/tmp/bench-{name}"
    pidfile = f"{remote_dir}/worker.pid"
    try:
        coordinator_cmd = [local_python, str(REPO / "scripts/run_coordinator.py"), "--model-path", LOCAL_MODEL, "--out-dir", str(run_dir / "coordinator"),
                           "--weights-dir", str(PUBLISHED), "--experiment-id", args.experiment_id, "--candidates", str(args.candidates),
                           "--generations", str(args.generations), "--alpha", "1e-3", "--sigma", "1e-3", "--policy", spec["policy"],
                           "--host", HOST, "--port", str(PORT), "--linger-seconds", "10", "--lease-seconds", str(args.lease_seconds),
                           "--allow-unauthenticated", "--timeout-seconds", str(args.generation_timeout)] + spec["args"]
        processes["coordinator"] = subprocess.Popen(coordinator_cmd, stdout=open(run_dir / "coordinator.out", "w"), stderr=subprocess.STDOUT, env=env)
        wait_health(url, 300)
        for worker, chunk in spec["workers"].items():
            if worker == FAST:
                cmd = [local_python, str(REPO / "scripts/run_worker.py"), "--model-path", LOCAL_MODEL, "--coordinator-url", url, "--worker-id", worker,
                       "--log", str(run_dir / f"{worker}.jsonl"), "--cache-dir", str(LOCAL_CACHE), "--chunk", str(chunk)]
            else:
                # `exec` replaces the shell, so the pid in the file is the worker's: it can be killed by pid, never by a name pattern
                noise = "" if args.noise_threads is None else f"HETEROES_NOISE_THREADS={args.noise_threads} "
                remote = (f"rm -rf {remote_dir}; mkdir -p {remote_dir}; echo $$ > {pidfile}; cd {REMOTE_REPO} && {noise}exec {REMOTE_PYTHON} scripts/run_worker.py "
                          f"--model-path ~/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/{MODEL} --coordinator-url {url} "
                          f"--worker-id {worker} --log {remote_dir}/{worker}.jsonl --cache-dir {remote_dir}/cache --chunk {chunk}")
                cmd = ["ssh", "-o", "ServerAliveInterval=15", REMOTE, remote]
            processes[worker] = subprocess.Popen(cmd, stdout=open(run_dir / f"{worker}.out", "w"), stderr=subprocess.STDOUT, env=env)
        deadline = time.time() + args.run_timeout
        while processes["coordinator"].poll() is None:
            if time.time() > deadline:
                raise TimeoutError(f"{name} did not finish in {args.run_timeout} s")
            time.sleep(2)
        for worker in spec["workers"]:
            try:
                processes[worker].wait(timeout=120)
            except subprocess.TimeoutExpired:
                pass
        outcome = "ok" if processes["coordinator"].returncode == 0 else f"coordinator exit {processes['coordinator'].returncode}"
    except BaseException as error:                    # noqa: BLE001 - the run must say how it ended
        outcome = f"{type(error).__name__}: {error}"
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
        for process in processes.values():
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
        if SLOW in spec["workers"]:
            subprocess.run(["ssh", REMOTE, f"test -f {pidfile} && kill $(cat {pidfile}) 2>/dev/null; true"], timeout=60)
            subprocess.run(["scp", "-q", f"{REMOTE}:{remote_dir}/{SLOW}.jsonl", str(run_dir / f"{SLOW}.jsonl")], timeout=120)
            subprocess.run(["ssh", REMOTE, f"rm -rf {remote_dir}"], timeout=60)
        shutil.rmtree(scratch, ignore_errors=True)
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
    parser.add_argument("--experiment-id", default="bench")
    parser.add_argument("--first-repeat", type=int, default=1, help="number the repeats from this (to add repeats later)")
    parser.add_argument("--lease-seconds", type=float, default=60.0)
    parser.add_argument("--noise-threads", type=int, default=None, help="HETEROES_NOISE_THREADS for every process (default: the library default)")
    parser.add_argument("--local-python", default=None, help="the interpreter of the coordinator and the local worker (default: this one)")
    parser.add_argument("--scratch-dir", default=str(Path.home() / ".cache" / "heteroes" / "bench-scratch"),
                        help="where each run keeps its published weights and worker cache (about 1 GB per generation; deleted after the run)")
    parser.add_argument("--remote", default=DEFAULTS["remote"])
    parser.add_argument("--remote-repo", default=DEFAULTS["remote_repo"])
    parser.add_argument("--remote-python", default=DEFAULTS["remote_python"])
    parser.add_argument("--host", default=DEFAULTS["host"], help="the coordinator's address as the workers see it")
    parser.add_argument("--port", type=int, default=DEFAULTS["port"])
    parser.add_argument("--run-timeout", type=float, default=3600.0)
    parser.add_argument("--generation-timeout", type=float, default=1200.0)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(REPO / "src"))

    reference = json.loads(Path(args.profile_reference).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.profile_candidate).read_text(encoding="utf-8"))
    prediction = None if args.prediction is None else json.loads(Path(args.prediction).read_text(encoding="utf-8"))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    conditions = args.conditions.split(",")
    specs = {name: plan(name, args.candidates, reference, candidate, prediction) for name in conditions}
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
