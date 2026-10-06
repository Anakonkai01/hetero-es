"""
The scripts, end to end, on this machine: a coordinator process and two worker processes (real Qwen model, real HTTP on the loopback
interface, full synchronization between two generations) against the single-process reference, compared bit for bit.

Slow (about 3 minutes) and heavy (three processes on the GPU): it runs only with HETEROES_E2E=1, HETEROES_QWEN_PINNED_PATH=<snapshot
dir> and a CUDA GPU. The evidence of 06/10 (artifacts/experiments/2026-10-06-g3-local-two-process) was made the same way.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import torch

PINNED_PATH = os.environ.get("HETEROES_QWEN_PINNED_PATH")
pytestmark = pytest.mark.skipif(
    os.environ.get("HETEROES_E2E") != "1" or PINNED_PATH is None or not torch.cuda.is_available(),
    reason="set HETEROES_E2E=1 and HETEROES_QWEN_PINNED_PATH and use a CUDA GPU to run the end-to-end check",
)
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
CANDIDATES, GENERATIONS = 3, 2


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def run(args, **kwargs):
    return subprocess.Popen([sys.executable, *map(str, args)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kwargs)


@pytest.mark.parametrize("policy", ["greedy", "wave"])
def test_two_worker_processes_give_the_bits_of_the_single_process_reference(policy):
    base = Path.home() / ".cache" / "heteroes" / "e2e-test"        # a real disk: the weights are 1 GB per generation and /tmp may be RAM
    base.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(tempfile.mkdtemp(dir=base))
    port = free_port()
    common = ["--model-path", PINNED_PATH]
    coordinator = run([SCRIPTS / "run_coordinator.py", *common, "--out-dir", tmp_path / "coordinator", "--weights-dir", tmp_path / "published",
                       "--experiment-id", "e2e", "--candidates", CANDIDATES, "--generations", GENERATIONS, "--alpha", "1e-3",
                       "--sigma", "1e-3", "--policy", policy, "--wave-size", "2", "--port", port, "--timeout-seconds", "600",
                       "--linger-seconds", "10"])
    workers = [run([SCRIPTS / "run_worker.py", *common, "--coordinator-url", f"http://127.0.0.1:{port}", "--worker-id", f"worker-{name}",
                    "--log", tmp_path / f"worker-{name}.jsonl", "--cache-dir", tmp_path / f"cache-{name}", "--poll-seconds", "0.5",
                    "--give-up-after-seconds", "60"]) for name in "ab"]
    try:
        output, _ = coordinator.communicate(timeout=900)
        worker_outputs = [worker.communicate(timeout=120)[0] for worker in workers]
    finally:
        for process in [coordinator, *workers]:
            if process.poll() is None:
                process.kill()
    assert coordinator.returncode == 0, output[-2000:]
    assert [worker.returncode for worker in workers] == [0, 0], worker_outputs

    reference = subprocess.run([sys.executable, SCRIPTS / "reference_generations.py", *common, "--output", tmp_path / "reference.json",
                                "--experiment-id", "e2e", "--candidates", str(CANDIDATES), "--generations", str(GENERATIONS),
                                "--alpha", "1e-3", "--sigma", "1e-3"], capture_output=True, text=True)
    assert reference.returncode == 0, reference.stderr[-2000:]
    comparison = subprocess.run([sys.executable, SCRIPTS / "compare_generation_runs.py", tmp_path / "coordinator" / "summary.json",
                                 tmp_path / "reference.json"], capture_output=True, text=True)
    assert comparison.returncode == 0, comparison.stdout
    summary = json.loads((tmp_path / "coordinator" / "summary.json").read_text())
    assert summary["outcome"] == "ok" and len(summary["generations"]) == GENERATIONS and summary["internal_errors"] == []
    for name in "ab":
        events = [json.loads(line) for line in (tmp_path / f"worker-{name}.jsonl").read_text().splitlines()]
        assert events[-1]["event"] == "exit" and events[-1]["reason"] == "finished"
        assert sum(e["event"] == "sync" for e in events) == 1                        # the weights of generation 1 were downloaded
    shutil.rmtree(tmp_path)                                                             # only if everything held: otherwise the files stay to be looked at
