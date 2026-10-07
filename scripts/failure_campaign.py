#!/usr/bin/env python3
"""
Failures on the two real machines (C3/E6 of MASTER): disturb a running experiment in four ways and check that it still ends with
exactly the weights of an undisturbed run.

    python scripts/failure_campaign.py --out-dir artifacts/experiments/<dir> --candidates 8 --generations 3 \
        [--scenarios kill-worker,pause-worker,cut-link,kill-coordinator] [--reference-final <sha256>]

Every scenario starts a coordinator and a worker on this machine and a worker on the other one (like `run_benchmark.py` B3, with a short
lease so that a lost lease is noticed in seconds), waits for a condition, does one thing to the system and lets it finish:

  kill-worker       SIGKILL the remote worker while it holds a candidate (found in the ledger): the lease runs out, the other worker retries the
                    candidate; the remote worker is then started again by the campaign and rejoins (it synchronizes).
  pause-worker      SIGSTOP the remote worker while it holds a candidate for longer than the lease, then SIGCONT: its late result must be
                    refused (the candidate was retaken), the worker carries on afterwards.
  cut-link          drop the packets from the other machine for a few seconds right after a generation was published (so during its download of
                    the new weights), then restore them: the download is resumed or repeated, the worker rejoins. Needs root for iptables:
                    the password is read from the environment variable named by --sudo-password-env, never from a file or the command line.
  kill-coordinator  SIGKILL the coordinator in the middle of a generation and start it again with --resume: the ledger and the published
                    weights say where it was; the workers wait and come back.

The reference is the same experiment (same experiment id, candidates and generations) with the fast worker alone; the final weights hash of
every scenario must be that one. (The 1660S can in principle give another reward than the 5070 Ti for a candidate, see G4/G5: a scenario
that ends with another hash is then compared with the cross-GPU sweep before it is called a failure.) The raw logs of every run are kept.
"""
import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cluster_runner import FAST, SLOW, Cluster, add_cluster_arguments  # noqa: E402

SCENARIOS = ["kill-worker", "pause-worker", "cut-link", "kill-coordinator"]


def open_leases(ledger_path: Path, worker: str) -> int:
    """How many attempts of `worker` are open (leased, not ended) according to the coordinator's ledger (read-only)."""
    try:
        connection = sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return 0
    try:
        return connection.execute("SELECT COUNT(*) FROM attempt WHERE worker_id = ? AND ended_at IS NULL", (worker,)).fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        connection.close()


def committed_count(ledger_path: Path) -> int:
    try:
        connection = sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return 0
    try:
        return connection.execute("SELECT COUNT(*) FROM result").fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        connection.close()


def events_of(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    return events


def wait_until(condition, seconds: float, what: str, poll: float = 0.2):
    end = time.time() + seconds
    while time.time() < end:
        value = condition()
        if value:
            return value
        time.sleep(poll)
    raise TimeoutError(f"timed out after {seconds} s waiting for: {what}")


def sudo_run(command: list[str], password: str) -> None:
    subprocess.run(["sudo", "-S", "-p", ""] + command, input=password + "\n", text=True, check=True, timeout=60, capture_output=True)


def final_hash(run_dir: Path) -> str | None:
    for name in sorted(run_dir.glob("coordinator/summary*.json")):
        record = json.loads(name.read_text(encoding="utf-8"))
        if record.get("outcome") == "ok":
            return record["final_weights_sha256"]
    return None


def run_scenario(name: str, args, out: Path, password: str | None) -> dict:
    run_dir = out / name
    run_dir.mkdir(parents=True)
    cluster = Cluster(args, f"campaign-{name}", run_dir)
    ledger_path = run_dir / "coordinator" / "ledger.sqlite"
    started = time.time()
    notes: list[str] = []
    both = {FAST: args.chunk, SLOW: args.chunk}
    peer, port = args.remote.split("@")[-1], str(args.port)
    drop_rule = ["iptables", "-I", "INPUT", "1", "-s", peer, "-p", "tcp", "--dport", port, "-j", "DROP"]
    undrop_rule = ["iptables", "-D", "INPUT", "-s", peer, "-p", "tcp", "--dport", port, "-j", "DROP"]
    dropped = False
    try:
        coordinator = cluster.start_coordinator("greedy", [], args.candidates, args.generations)
        for worker, chunk in both.items():
            cluster.start_worker(worker, chunk)

        if name == "kill-worker":
            wait_until(lambda: open_leases(ledger_path, SLOW) > 0, 600, "the remote worker to hold a candidate")
            time.sleep(2.0)
            cluster.signal_remote_worker("KILL")
            notes.append("remote worker killed while it held a candidate")
            time.sleep(1.0)
            cluster.start_worker(SLOW, args.chunk)              # a new process with the same worker id: it must rejoin
            notes.append("remote worker started again")

        elif name == "pause-worker":
            wait_until(lambda: open_leases(ledger_path, SLOW) > 0, 600, "the remote worker to hold a candidate")
            time.sleep(1.0)
            cluster.signal_remote_worker("STOP")
            notes.append(f"remote worker stopped for {args.lease_seconds + 15:.0f} s (the lease is {args.lease_seconds:.0f} s)")
            time.sleep(args.lease_seconds + 15)
            cluster.signal_remote_worker("CONT")
            notes.append("remote worker continued")

        elif name == "cut-link":
            if password is None:
                raise RuntimeError("cut-link needs the sudo password in the environment variable named by --sudo-password-env")
            wait_until(lambda: any(e.get("event") == "weights_published" and e.get("generation") == 0 for e in events_of(run_dir / "coordinator" / "events.jsonl")),
                       900, "generation 0 to be published")
            time.sleep(args.cut_delay)                          # the download of the new weights (about 9 s) has begun when the packets are dropped
            sudo_run(drop_rule, password)
            dropped = True
            notes.append(f"packets from {args.remote} dropped for {args.cut_seconds:.0f} s")
            time.sleep(args.cut_seconds)
            sudo_run(undrop_rule, password)
            dropped = False
            notes.append("packets accepted again")

        elif name == "kill-coordinator":
            wait_until(lambda: committed_count(ledger_path) >= max(2, args.candidates // 2 + args.candidates), 900,
                       "half of generation 1 to be committed")
            coordinator.send_signal(signal.SIGKILL)
            coordinator.wait(timeout=30)
            notes.append(f"coordinator killed with {committed_count(ledger_path)} results committed")
            time.sleep(args.restart_after)
            coordinator = cluster.start_coordinator("greedy", [], args.candidates, args.generations, resume=True, label="coordinator-resumed")
            notes.append("coordinator started again with --resume")

        deadline = time.time() + args.run_timeout
        while coordinator.poll() is None:
            if time.time() > deadline:
                raise TimeoutError(f"{name} did not finish in {args.run_timeout} s")
            time.sleep(2)
        for worker in both:
            try:
                cluster.processes[worker].wait(timeout=120)
            except subprocess.TimeoutExpired:
                pass
        outcome = "ok" if coordinator.returncode == 0 else f"coordinator exit {coordinator.returncode}"
    except BaseException as error:                    # noqa: BLE001 - the run must say how it ended
        outcome = f"{type(error).__name__}: {error}"
    finally:
        if dropped and password is not None:
            try:
                sudo_run(undrop_rule, password)
            except Exception:                         # noqa: BLE001
                notes.append("WARNING: the iptables rule may still be there")
        cluster.collect_and_clean(both)
    record = {"name": name, "outcome": outcome, "wall_seconds": time.time() - started, "notes": notes, "final_weights_sha256": final_hash(run_dir)}
    (run_dir / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def run_reference(args, out: Path) -> str:
    run_dir = out / "reference"
    run_dir.mkdir(parents=True)
    cluster = Cluster(args, "campaign-reference", run_dir)
    try:
        coordinator = cluster.start_coordinator("greedy", [], args.candidates, args.generations)
        cluster.start_worker(FAST, args.chunk)
        deadline = time.time() + args.run_timeout
        while coordinator.poll() is None and time.time() < deadline:
            time.sleep(2)
        outcome = "ok" if coordinator.returncode == 0 else f"coordinator exit {coordinator.returncode}"
    finally:
        cluster.collect_and_clean([FAST])
    digest = final_hash(run_dir)
    (run_dir / "run.json").write_text(json.dumps({"name": "reference", "outcome": outcome, "final_weights_sha256": digest}, indent=2) + "\n", encoding="utf-8")
    if digest is None:
        raise RuntimeError(f"the reference run failed: {outcome}")
    return digest


def verdict(record: dict, reference: str) -> dict:
    """Pure: did the scenario end well and with the reference weights?"""
    ended = record["outcome"] == "ok"
    same = record["final_weights_sha256"] == reference
    return {"scenario": record["name"], "ended_ok": ended, "same_final_weights_as_reference": same, "passed": ended and same}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--reference-final", default=None, help="the final weights hash of the undisturbed run (default: run it first)")
    parser.add_argument("--chunk", type=int, default=1, help="prompts per generate() call of every worker (more than 1 only with --eval-dtype float32)")
    parser.add_argument("--cut-seconds", type=float, default=8.0)
    parser.add_argument("--cut-delay", type=float, default=0.0, help="cut-link: seconds after the publication of generation 0 before the packets are dropped (3 s puts the cut in the middle of the download)")
    parser.add_argument("--restart-after", type=float, default=5.0)
    parser.add_argument("--run-timeout", type=float, default=1800.0)
    parser.add_argument("--sudo-password-env", default="HETEROES_SUDO_PASSWORD")
    add_cluster_arguments(parser)
    parser.set_defaults(experiment_id="campaign", lease_seconds=20.0)
    args = parser.parse_args(argv)
    unknown = [name for name in args.scenarios.split(",") if name not in SCENARIOS]
    if unknown:
        parser.error(f"unknown scenarios {unknown}; known: {SCENARIOS}")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    password = os.environ.get(args.sudo_password_env)
    reference = args.reference_final or (out / "reference" / "run.json").exists() and json.loads((out / "reference" / "run.json").read_text())["final_weights_sha256"]
    if not reference:
        print("=== reference (the fast worker alone)", flush=True)
        reference = run_reference(args, out)
    print(f"reference final weights {reference}", flush=True)
    results = []
    for name in args.scenarios.split(","):
        if (out / name / "run.json").exists():
            print(f"skip {name}: it ran", flush=True)
            continue
        print(f"=== {name}", flush=True)
        record = run_scenario(name, args, out, password)
        results.append(verdict(record, reference))
        print("   ", record["outcome"], record["notes"], results[-1], flush=True)
    (out / "verdicts.json").write_text(json.dumps({"reference_final_weights_sha256": reference, "verdicts": results}, indent=2) + "\n", encoding="utf-8")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
