"""
Start, watch, disturb and stop the processes of one experiment on the two machines (shared by `run_benchmark.py` and
`failure_campaign.py`). The coordinator and the fast worker run on this machine, the slow worker over SSH on the other one.

Nothing here is a general cluster manager: it knows the two machines of the project, takes every address and path from the
arguments of the calling script (see `add_cluster_arguments`) and keeps what it starts in `self.processes`. The remote worker is
started with `exec` after writing its pid to a file, so that it is signalled by pid and never by a name pattern (a `pkill -f` pattern
matches the shell that runs it).
"""
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
FAST, SLOW, THIRD = "worker-5070ti", "worker-1660s", "worker-3060"
MODEL = "7ae557604adf67be50417f59c2c2f167def9a775"
LOCAL_MODEL = str(Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots" / MODEL)
DEFAULTS = {"remote": "anakonkai@10.10.10.2", "remote_repo": "~/projects/heteroes/hetero-es",
            "remote_python": "~/projects/heteroes/.venv/bin/python", "host": "10.10.10.1", "port": 8765}


def add_cluster_arguments(parser) -> None:
    parser.add_argument("--lease-seconds", type=float, default=60.0)
    parser.add_argument("--noise-threads", type=int, default=None, help="HETEROES_NOISE_THREADS for every process (default: the library default)")
    parser.add_argument("--coordinator-noise-threads", type=int, default=None,
                        help="HETEROES_NOISE_THREADS for the coordinator only (its update runs while the workers are idle: it can use every CPU thread)")
    parser.add_argument("--worker-http-timeout", type=float, default=None, help="--http-timeout-seconds of every worker (default: the worker's own, 60 s)")
    parser.add_argument("--local-python", default=None, help="the interpreter of the coordinator and the local worker (default: this one)")
    parser.add_argument("--scratch-dir", default=str(Path.home() / ".cache" / "heteroes" / "bench-scratch"),
                        help="where each run keeps its published weights and worker cache (about 1 GB per generation; deleted after the run)")
    parser.add_argument("--replay", choices=["never", "always", "auto"], default="never",
                        help="how the REMOTE worker catches up with a new parent: download (never), apply the update records (always), or whichever its profile says is faster (auto)")
    parser.add_argument("--replay-profile", default=None, help="the remote worker's profile JSON, as a path ON THE REMOTE MACHINE (needed by --replay auto)")
    parser.add_argument("--replay-verify-every", type=int, default=1)
    parser.add_argument("--third", default=None, help="a THIRD worker machine as an ssh target (08/10: the 3060 in WSL2), started like the remote worker; none by default")
    parser.add_argument("--third-repo", default="~/projects/heteroes/hetero-es")
    parser.add_argument("--third-python", default="~/heteroes-venv/bin/python")
    parser.add_argument("--third-model-path", default=f"~/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/{MODEL}")
    parser.add_argument("--third-env", default="", help="environment assignments put in front of the third worker's command, e.g. 'LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers/<nv_dispi dir>' (WSL2 where the Ubuntu NVIDIA 580 libraries shadow the Windows driver's)")
    parser.add_argument("--third-url", default=None, help="the coordinator's address as the THIRD worker sees it (default: --host)")
    parser.add_argument("--third-replay", choices=["never", "always", "auto"], default="never", help="how the third worker catches up (see --replay)")
    parser.add_argument("--third-replay-profile", default=None, help="the third worker's profile JSON, as a path on the third machine (for --third-replay auto)")
    parser.add_argument("--bind-host", default=None, help="the address the coordinator listens on (default: --host); 0.0.0.0 to serve the cable and another network at once (the firewall decides who may connect)")
    parser.add_argument("--remote", default=DEFAULTS["remote"])
    parser.add_argument("--remote-repo", default=DEFAULTS["remote_repo"])
    parser.add_argument("--remote-python", default=DEFAULTS["remote_python"])
    parser.add_argument("--host", default=DEFAULTS["host"], help="the coordinator's address as the workers see it")
    parser.add_argument("--port", type=int, default=DEFAULTS["port"])
    parser.add_argument("--experiment-id", default="bench")
    parser.add_argument("--alpha", type=float, default=1e-3, help="the step of the update (the coordinator's --alpha)")
    parser.add_argument("--sigma", type=float, default=1e-3, help="the size of the perturbation (the recipe's sigma)")
    parser.add_argument("--eval-dtype", choices=["float16", "float32"], default="float32", help="precision of the forward pass of the evaluation (the recipe's; the workers read it from the job)")
    parser.add_argument("--noise-engine", choices=["cpu", "cuda"], default="cpu", help="the noise engine of the recipe (the workers read it from the job)")
    parser.add_argument("--workload", choices=["arith16", "cot_l3_q32", "cot_l3_q64", "cot_l1_q128"], default="arith16", help="the workload of the recipe (the workers read it from the job)")
    parser.add_argument("--generation-timeout", type=float, default=1200.0)


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


class Cluster:
    def __init__(self, args, name: str, run_dir: Path):
        self.args, self.name, self.run_dir = args, name, run_dir
        self.env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONPATH": str(REPO / "src")}
        if args.noise_threads is not None:
            self.env["HETEROES_NOISE_THREADS"] = str(args.noise_threads)
        self.python = args.local_python or sys.executable
        self.url = f"http://{args.host}:{args.port}"
        self.scratch = Path(args.scratch_dir) / name
        self.published, self.local_cache = self.scratch / "published", self.scratch / "worker-cache"
        self.remotes: list[dict] = []        # every remote worker process started: its directory, pid file and the name of its log here
        self.processes: dict[str, subprocess.Popen] = {}
        shutil.rmtree(self.scratch, ignore_errors=True)
        self.scratch.mkdir(parents=True)

    # ---- starting --------------------------------------------------------------------------------------------------------

    def start_coordinator(self, policy: str, policy_args: list[str], candidates: int, generations: int, resume: bool = False,
                          label: str = "coordinator") -> subprocess.Popen:
        a = self.args
        cmd = [self.python, str(REPO / "scripts/run_coordinator.py"), "--model-path", LOCAL_MODEL, "--out-dir", str(self.run_dir / "coordinator"),
               "--weights-dir", str(self.published), "--experiment-id", a.experiment_id, "--candidates", str(candidates),
               "--generations", str(generations), "--alpha", repr(a.alpha), "--sigma", repr(a.sigma), "--policy", policy,
               "--host", a.bind_host or a.host, "--port", str(a.port), "--linger-seconds", "10", "--lease-seconds", str(a.lease_seconds),
               "--allow-unauthenticated", "--timeout-seconds", str(a.generation_timeout), "--eval-dtype", a.eval_dtype,
               "--noise-engine", a.noise_engine, "--workload", a.workload] + policy_args + (["--resume"] if resume else [])
        env = self.env if a.coordinator_noise_threads is None else {**self.env, "HETEROES_NOISE_THREADS": str(a.coordinator_noise_threads)}
        process = subprocess.Popen(cmd, stdout=open(self.run_dir / f"{label}.out", "a"), stderr=subprocess.STDOUT, env=env)
        self.processes[label] = process
        wait_health(self.url, 300)
        return process

    def remote_settings(self, worker: str) -> dict:
        """Where a non-local worker runs and how it reaches the coordinator: the 1660S (SLOW) or the third machine (THIRD)."""
        a = self.args
        if worker == THIRD:
            if not a.third:
                raise ValueError("a worker on the third machine needs --third")
            return {"target": a.third, "repo": a.third_repo, "python": a.third_python, "model": a.third_model_path,
                    "url": a.third_url or self.url, "pythonpath": True, "env": a.third_env,
                    "replay": a.third_replay, "replay_profile": a.third_replay_profile}
        return {"target": a.remote, "repo": a.remote_repo, "python": a.remote_python,
                "model": f"~/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/{MODEL}",
                "url": self.url, "pythonpath": False, "env": "", "replay": a.replay, "replay_profile": a.replay_profile}

    def start_worker(self, worker: str, chunk: int) -> subprocess.Popen:
        """Start a worker. Starting the remote worker a second time (after it was killed) keeps the first one's log: other directory, other file."""
        a = self.args
        local = worker.startswith(FAST)
        number = 0 if local else sum(1 for r in self.remotes if r["worker"] == worker)
        tag = "" if number == 0 else f"-restart{number}"
        log = self.run_dir / f"{worker}{tag}.out"
        suffix = "" if worker == SLOW else f"-{worker}"                      # the 1660S keeps the directory name of the earlier campaigns
        remote_dir = f"/tmp/bench-{self.name}{tag}{suffix}"
        pidfile = f"{remote_dir}/worker.pid"
        extra = [] if a.worker_http_timeout is None else ["--http-timeout-seconds", str(a.worker_http_timeout)]
        if local:
            cmd = [self.python, str(REPO / "scripts/run_worker.py"), "--model-path", LOCAL_MODEL, "--coordinator-url", self.url, "--worker-id", worker,
                   "--log", str(self.run_dir / f"{worker}.jsonl"), "--cache-dir", str(self.local_cache / worker), "--chunk", str(chunk)] + extra
        else:
            r = self.remote_settings(worker)
            replay = ([] if r["replay"] == "never" else ["--replay", r["replay"], "--replay-verify-every", str(a.replay_verify_every)]
                      + ([] if r["replay_profile"] is None else ["--profile", r["replay_profile"]]))     # the local worker downloads from this machine's disk
            noise = "" if a.noise_threads is None else f"HETEROES_NOISE_THREADS={a.noise_threads} "
            path = ("PYTHONPATH=src " if r["pythonpath"] else "") + (r["env"] + " " if r["env"] else "")
            remote = (f"rm -rf {remote_dir}; mkdir -p {remote_dir}; echo $$ > {pidfile}; cd {r['repo']} && {noise}{path}exec {r['python']} "
                      f"scripts/run_worker.py --model-path {r['model']} "
                      f"--coordinator-url {r['url']} --worker-id {worker} --log {remote_dir}/{worker}.jsonl --cache-dir {remote_dir}/cache --chunk {chunk} "
                      + " ".join(extra + replay))
            cmd = ["ssh", "-o", "ServerAliveInterval=15", r["target"], remote]
            self.remotes.append({"worker": worker, "dir": remote_dir, "pidfile": pidfile, "log": f"{worker}{tag}.jsonl", "target": r["target"]})
        process = subprocess.Popen(cmd, stdout=open(log, "a"), stderr=subprocess.STDOUT, env=self.env)
        self.processes[f"{worker}{tag}"] = process
        return process

    # ---- disturbing ------------------------------------------------------------------------------------------------------

    def signal_remote_worker(self, name: str, worker: str | None = None) -> None:
        """Send a signal (KILL, STOP, CONT, TERM) to the latest remote worker (of the given worker id, if any) by its pid."""
        remote = [r for r in self.remotes if worker is None or r["worker"] == worker][-1]
        subprocess.run(["ssh", remote["target"], f"test -f {remote['pidfile']} && kill -{name} $(cat {remote['pidfile']}) 2>/dev/null; true"], timeout=60)

    def signal_local(self, label: str, sig) -> None:
        process = self.processes[label]
        if process.poll() is None:
            process.send_signal(sig)

    # ---- finishing -------------------------------------------------------------------------------------------------------

    def collect_and_clean(self, workers) -> None:
        for process in self.processes.values():
            if process.poll() is None:
                process.terminate()
        for process in self.processes.values():
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
        a = self.args
        for remote in self.remotes:
            target = remote.get("target", a.remote)
            subprocess.run(["ssh", target, f"test -f {remote['pidfile']} && kill -CONT $(cat {remote['pidfile']}) 2>/dev/null; "
                                           f"test -f {remote['pidfile']} && kill $(cat {remote['pidfile']}) 2>/dev/null; true"], timeout=60)
            subprocess.run(["scp", "-q", f"{target}:{remote['dir']}/{remote['worker']}.jsonl", str(self.run_dir / remote["log"])], timeout=120)
            subprocess.run(["ssh", target, f"rm -rf {remote['dir']}"], timeout=60)
        shutil.rmtree(self.scratch, ignore_errors=True)
