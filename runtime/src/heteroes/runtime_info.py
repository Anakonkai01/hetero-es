"""Where and with what a run happened (for the records of an experiment), and the append-only JSONL log the processes write."""
import json
import platform
import socket
import subprocess
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(arguments: list[str]) -> str | None:
    try:
        completed = subprocess.run(arguments, capture_output=True, text=True, cwd=REPO_ROOT, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def code_info() -> dict:
    commit = _run(["git", "rev-parse", "HEAD"])
    status = _run(["git", "status", "--porcelain"])
    return {"git_commit": commit, "git_dirty": None if status is None else bool(status)}      # untracked files count as dirty


def environment_info(device: str) -> dict:
    import numpy
    import torch
    import transformers

    info = {
        "hostname": socket.gethostname(), "platform": platform.platform(), "python": platform.python_version(),
        "torch": torch.__version__, "torch_cuda": torch.version.cuda, "numpy": numpy.__version__,
        "transformers": transformers.__version__, "device": device, "gpu_name": None, "gpu_capability": None,
        "gpu_total_memory_bytes": None, "nvidia_driver": None,
    }
    if device == "cuda":
        properties = torch.cuda.get_device_properties(0)
        info["gpu_name"] = properties.name
        info["gpu_capability"] = [properties.major, properties.minor]
        info["gpu_total_memory_bytes"] = properties.total_memory
        info["nvidia_driver"] = _run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"])
    return info


class JsonlLog:
    """
    One JSON object per line, flushed at once, safe to call from several threads. Never overwrites a file (evidence is not
    overwritten); `append=True` continues an existing log (a coordinator that was restarted writes after what the first one wrote).
    """

    def __init__(self, path, append: bool = False):
        self._file = open(path, "a" if append else "x", encoding="utf-8")
        self._lock = threading.Lock()

    def __call__(self, event: dict) -> None:
        line = json.dumps(event)                # may raise TypeError: nothing is written then
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()

    def close(self) -> None:
        with self._lock:
            self._file.close()
