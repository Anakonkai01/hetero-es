#!/usr/bin/env python3
"""
Run the learning experiment on the two machines (experiment code): coordinator + three worker processes (two on the 5070 Ti, one on the 1660S, policy B4 as the
best configuration of G7), CUDA noise engine, workload cot_l3_q64, chunk 64, FP32 evaluation. It keeps the checkpoints (`learnlib.CheckpointKeeper`), restarts a worker
or the coordinator (`--resume`) that dies, and stops at --stop-at. Run it with the `heteroes-match` python from the repository root:

    PYTHONPATH=src ~/miniforge3/envs/heteroes-match/bin/python artifacts/experiments/2026-10-07-learning-runtime/run_learning.py \
        --out-dir artifacts/experiments/2026-10-07-learning-runtime/runA --experiment-id lrtA --generations 100 --local-python ~/miniforge3/envs/heteroes-match/bin/python
"""
import argparse
import json
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(HERE))
from cluster_runner import FAST, SLOW, Cluster, add_cluster_arguments  # noqa: E402
from learnlib import CheckpointKeeper  # noqa: E402
from run_benchmark import plan  # noqa: E402

PROFILES = REPO / "artifacts/experiments/2026-10-07-g7-bigchunk/profiles-derived"


def worker_keys(cluster, worker: str) -> list[str]:
    return [key for key in cluster.processes if key == worker or key.startswith(f"{worker}-restart")]


def main(argv) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--generations", type=int, default=100)
    parser.add_argument("--candidates", type=int, default=24)
    parser.add_argument("--condition", default="B4x2")
    parser.add_argument("--ckpt-dir", default=None, help="default: ~/.cache/heteroes/learn-ckpt/<experiment id> (on the disk of the published weights, so that they are hard links)")
    parser.add_argument("--ckpt-every", type=int, default=5)
    parser.add_argument("--stop-at", default=None, help="local time 'YYYY-MM-DD HH:MM': end the run in an orderly way when it is reached")
    parser.add_argument("--max-coordinator-restarts", type=int, default=3)
    parser.add_argument("--max-worker-restarts", type=int, default=5)
    parser.add_argument("--run-timeout", type=float, default=6 * 3600.0)
    add_cluster_arguments(parser)
    parser.set_defaults(noise_engine="cuda", workload="cot_l3_q64", coordinator_noise_threads=28)
    args = parser.parse_args(argv)
    chunk = 64
    reference = json.loads((PROFILES / "profile-5070ti-cot_l3_q64.json").read_text())
    candidate = json.loads((PROFILES / "profile-1660s-cot_l3_q64.json").read_text())
    spec = plan(args.condition, args.candidates, reference, candidate, None, chunk)
    stop_at = None if args.stop_at is None else datetime.strptime(args.stop_at, "%Y-%m-%d %H:%M").timestamp()
    run_dir = Path(args.out_dir)
    run_dir.mkdir(parents=True)
    ckpt_dir = Path(args.ckpt_dir) if args.ckpt_dir else Path.home() / ".cache/heteroes/learn-ckpt" / args.experiment_id
    cluster = Cluster(args, args.experiment_id, run_dir)
    keeper = CheckpointKeeper(run_dir / "coordinator/events.jsonl", cluster.published, ckpt_dir, args.generations, args.ckpt_every)
    started = time.time()
    outcome, restarts = "ok", {"coordinator": 0}
    (run_dir / "run-spec.json").write_text(json.dumps({"args": vars(args), "spec": spec, "ckpt_dir": str(ckpt_dir), "started": started}, indent=2) + "\n")
    try:
        coordinator = cluster.start_coordinator(spec["policy"], spec["args"], args.candidates, args.generations)
        for worker, w_chunk in spec["workers"].items():
            cluster.start_worker(worker, w_chunk)
            restarts[worker] = 0
        while True:
            keeper.poll()
            code = coordinator.poll()
            if code is not None:
                if code == 0:
                    break
                if restarts["coordinator"] >= args.max_coordinator_restarts:
                    outcome = f"coordinator exit {code} after {restarts['coordinator']} restarts"
                    break
                restarts["coordinator"] += 1
                print(f"[{time.strftime('%H:%M:%S')}] coordinator exited with {code}: restart {restarts['coordinator']} with --resume", flush=True)
                coordinator = cluster.start_coordinator(spec["policy"], spec["args"], args.candidates, args.generations, resume=True,
                                                        label=f"coordinator-resume{restarts['coordinator']}")
            else:
                for worker, w_chunk in spec["workers"].items():
                    latest = cluster.processes[worker_keys(cluster, worker)[-1]]
                    if latest.poll() is not None and latest.returncode != 0 and not keeper.finished and restarts[worker] < args.max_worker_restarts:
                        restarts[worker] += 1
                        print(f"[{time.strftime('%H:%M:%S')}] worker {worker} exited with {latest.returncode}: restart {restarts[worker]}", flush=True)
                        cluster.start_worker(worker, w_chunk)
            if stop_at is not None and time.time() > stop_at:
                outcome = "stopped at --stop-at (deadline)"
                coordinator.send_signal(signal.SIGTERM)
                coordinator.wait(timeout=120)
                break
            if time.time() - started > args.run_timeout:
                outcome = f"timeout after {args.run_timeout} s"
                coordinator.send_signal(signal.SIGTERM)
                coordinator.wait(timeout=120)
                break
            time.sleep(2)
        for worker in spec["workers"]:
            for key in worker_keys(cluster, worker):
                try:
                    cluster.processes[key].wait(timeout=60)
                except subprocess.TimeoutExpired:
                    pass
    except BaseException as error:                    # noqa: BLE001 - the run must say how it ended
        outcome = f"{type(error).__name__}: {error}"
    finally:
        keeper.poll()
        cluster.collect_and_clean(spec["workers"])
    record = {"experiment_id": args.experiment_id, "outcome": outcome, "wall_seconds": time.time() - started, "restarts": restarts,
              "checkpoints": {str(g): sha for g, sha in sorted(keeper.kept.items())}, "pending_unlinked": keeper.pending, "ckpt_dir": str(ckpt_dir), "spec": spec}
    (run_dir / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: v for k, v in record.items() if k not in ("spec", "checkpoints")}), flush=True)
    return 0 if outcome == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
