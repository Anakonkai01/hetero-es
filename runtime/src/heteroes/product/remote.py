"""JSON-over-stdin lifecycle helper, invoked only with administrator-owned configuration.

No token is placed in argv. PID identity is checked before every signal; a failed
SSH check is unknown, never confirmation that the GPU has been released.
"""

import filecmp
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys

from .files import events, read_json, write_json
from .platform_process import identity, spawn_options


def alive(record):
    return bool(record and record.get("birth") is not None and identity(record["pid"]) == record["birth"])


def worker_environment(source, token, wsl=Path("/usr/lib/wsl")):
    """Select WSL's mounted Windows driver libraries for this process only.

    A Linux libnvidia-compute package can otherwise shadow the matching PTX JIT
    library and crash CUDA initialization. Match the active gpucomp bytes,
    rather than picking a possibly stale Windows driver directory by name.
    """
    env = dict(os.environ, HETEROES_TOKEN=token, PYTHONPATH=source)
    if sys.platform != "linux":
        return env
    library = wsl / "lib"
    if library.is_dir():
        env["PATH"] = str(library) + ":" + env.get("PATH", "")
        paths = [str(library)]
        gpucomp = library / "libnvidia-gpucomp.so"
        if gpucomp.is_file():
            matching = [
                candidate.parent
                for candidate in (wsl / "drivers").glob("*/libnvidia-gpucomp.so")
                if (candidate.samefile(gpucomp) or filecmp.cmp(candidate, gpucomp, shallow=False))
                and (candidate.parent / "libnvidia-ptxjitcompiler.so.1").is_file()
            ]
            if len(matching) != 1:
                raise RuntimeError("Cannot identify a unique matching WSL Windows PTX JIT driver library")
            paths.append(str(matching[0]))
        if env.get("LD_LIBRARY_PATH"):
            paths.append(env["LD_LIBRARY_PATH"])
        env["LD_LIBRARY_PATH"] = ":".join(paths)
    return env


def handle(request):
    action = request["action"]
    if action == "probe":
        executable = shutil.which("nvidia-smi")
        if not executable:
            candidates = (
                [
                    Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/nvidia-smi.exe",
                    Path(os.environ.get("ProgramFiles", "C:/Program Files"))
                    / "NVIDIA Corporation/NVSMI/nvidia-smi.exe",
                ]
                if sys.platform == "win32"
                else [Path("/usr/lib/wsl/lib/nvidia-smi")]
            )
            executable = next((str(p) for p in candidates if p.is_file()), None)
        if not executable:
            raise RuntimeError("nvidia-smi unavailable")
        completed = subprocess.run(
            [
                executable,
                "--query-gpu=name,memory.total,memory.free,temperature.gpu,utilization.gpu,uuid",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}),
        )
        if completed.returncode:
            raise RuntimeError("nvidia-smi unavailable")
        name, total, free, temperature, utilization, gpu_uuid = completed.stdout.splitlines()[0].split(",")
        return {
            "gpuName": name.strip(),
            "vramTotalMb": int(total),
            "vramFreeMb": int(free),
            "temperatureC": int(temperature),
            "utilizationPercent": int(utilization),
            "gpuUUID": gpu_uuid.strip(),
        }
    root = Path(request["directory"]).expanduser()
    record = read_json(root / "process.json")
    if action == "start":
        if not record:
            intent = root / "launch-intent.json"
            if intent.exists():
                raise RuntimeError("Worker launch ownership is unknown")
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            env = worker_environment(request["source"], request["token"])
            with open(root / "stdout.log", "ab") as output:
                write_json(intent, {"started": True})
                try:
                    process = subprocess.Popen(
                        request["argv"], env=env, stdout=output, stderr=output, **spawn_options()
                    )
                except OSError:
                    # Popen reports a failed OS creation/exec only after its failed child, if any, is reaped. Once it
                    # returns a process, any failure recording identity remains unknown and keeps the intent.
                    intent.unlink(missing_ok=True)
                    raise
            record = {"pid": process.pid, "birth": identity(process.pid)}
            write_json(root / "process.json", record)
    elif action == "stop" and alive(record):
        if sys.platform == "win32":
            write_json(root / "stop-request.json", record)
        else:
            os.kill(record["pid"], signal.SIGTERM)  # worker stops after candidate restore/result
    elif action not in ("poll", "stop"):
        raise ValueError("unknown lifecycle action")
    logs = events(root / "events.jsonl")
    return {
        "alive": alive(record),
        "ready": any(item.get("event") == "executor_ready" for item in logs),
        "events": logs[-200:],
        "process": record,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(handle(json.load(sys.stdin))))
    except Exception as error:
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}))
        sys.exit(1)
