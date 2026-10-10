#!/usr/bin/env python3
"""Linux coordinator deployment: private config, owned processes, no sudo or autostart."""
import argparse
import io
import json
import os
from pathlib import Path
import secrets
import shlex
import signal
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request

REPO = Path(__file__).resolve().parents[1]
PRIVATE = Path(os.environ.get("HETEROES_PRIVATE_CONFIG", str(Path.home() / ".config/heteroes-integration")))
REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "w") as stream:
        os.chmod(path, 0o600)
        json.dump(body, stream, indent=2)


def birth(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except FileNotFoundError:
        return None


def alive(record):
    return bool(record and record.get("birth") and birth(record["pid"]) == record["birth"])


def request(config, token, path, method="GET"):
    req = urllib.request.Request(f"http://127.0.0.1:{config['controlPort']}" + path,
        headers={"Authorization": "Bearer " + token}, method=method)
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def init():
    if not (PRIVATE / "credentials.json").exists():
        write(PRIVATE / "credentials.json", {"runtime_token": secrets.token_urlsafe(32),
              "users": {name: secrets.token_urlsafe(18) for name in ("admin", "participant")}})
    if (PRIVATE / "config.json").exists():
        print("Private configuration already exists; kept unchanged.")
        return
    runtime = REPO.parent / "hetero-es-integration"
    model = str(Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots" / REVISION)
    state = Path.home() / ".local/share/heteroes-integration"
    ip = os.environ.get("HETEROES_PRIVATE_IP", "100.110.165.40")
    python = str(Path.home() / "miniforge3/envs/heteroes-match/bin/python")
    workers = [{"id": "5070ti", "label": "RTX 5070 Ti", "python": python, "source": str(runtime / "src"),
                "modelPath": model, "stateDirectory": str(state / "workers/5070ti"), "chunk": 16}]
    for worker_id, label, target, username, worker_python, chunk in (
        ("3060", "RTX 3060 (Quang)", "quang@100.99.227.8", "quang", "/home/quang/heteroes-venv/bin/python", 16),
        ("1660s", "GTX 1660 Super", "anakonkai@heteroes-worker-1660s", "anakonkai", "/home/anakonkai/projects/heteroes/.venv/bin/python", 16)):
        home = "/home/" + username
        workers.append({"id": worker_id, "label": label, "ssh": target, "python": worker_python,
            "source": home + "/.local/share/heteroes-integration/runtime/src", "chunk": chunk,
            "modelPath": home + "/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/" + REVISION,
            "stateDirectory": home + "/.local/share/heteroes-integration/workers/" + worker_id})
    write(PRIVATE / "config.json", {"runtimePath": str(runtime), "python": python, "modelPath": model,
        "credentialsFile": str(PRIVATE / "credentials.json"), "stateDirectory": str(state / "runs"),
        "productStateDirectory": str(state / "product"), "processDirectory": str(state / "services"),
        "controlPort": 8766, "workerPort": 8765, "workerHost": ip, "workerUrl": f"http://{ip}:8765",
        "uiHost": ip, "workers": workers})
    print(f"Created {PRIVATE / 'config.json'}. Account credentials: {PRIVATE / 'credentials.json'} (mode 600).")


def start(config):
    runtime = Path(config["runtimePath"])
    root = Path(config["processDirectory"])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backend_port=config.get('backendPort',8000);ui_port=config.get('uiPort',5173)
    env = dict(os.environ, HETEROES_PRIVATE_CONFIG=str(PRIVATE), HETEROES_UI_HOST=config["uiHost"],
               HETEROES_UI_PORT=str(ui_port),HETEROES_BACKEND_PORT=str(backend_port),VITE_DATA_SOURCE="real")
    services = [("runtime", [config["python"], "-m", "heteroes.product.gateway", str(PRIVATE / "config.json")], runtime, {**env, "PYTHONPATH": str(runtime / "src")}, config["controlPort"], "127.0.0.1"),
                ("backend", [str(REPO / ".venv-backend/bin/python"), "-m", "uvicorn", "backend.app:app_from_environment", "--factory", "--host", "127.0.0.1", "--port", str(backend_port)], REPO, env, backend_port, "127.0.0.1"),
                ("frontend", ["npm", "run", "dev"], REPO / "frontend", env, ui_port, config["uiHost"])]
    for name, command, cwd, environment, port, host in services:
        path = root / (name + ".json")
        if alive(read(path)):
            continue
        with socket.socket() as connection:
            if connection.connect_ex((host, port)) == 0:
                raise RuntimeError(f"Port {port} is owned by an untracked process; no process was stopped")
        with open(root / (name + ".log"), "ab") as output:
            process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=output, stderr=output, start_new_session=True)
        record = {"pid": process.pid, "birth": birth(process.pid)}
        write(path, record)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if not alive(record):
                raise RuntimeError(f"{name} failed; inspect {root / (name + '.log')}")
            with socket.socket() as connection:
                if connection.connect_ex((host, port)) == 0:
                    break
            time.sleep(.3)
        else:
            raise RuntimeError(f"{name} startup timed out")
    print(f"UI: http://{config['uiHost']}:{ui_port}")
    print(f"Account credentials are in {PRIVATE / 'credentials.json'}; they are never printed by this command.")


def stop(config):
    root = Path(config["processDirectory"])
    # Stop the dispatcher first so queued experiments cannot start while draining.
    for name in ("frontend", "backend"):
        record = read(root / (name + ".json"))
        if alive(record):
            os.killpg(record["pid"], signal.SIGTERM)
    token = read(PRIVATE / "credentials.json")["runtime_token"]
    if alive(read(root / "runtime.json")):
        deadline = time.monotonic() + 600
        while True:
            active = [run for run in request(config, token, "/runs") if run["status"] not in ("COMPLETED", "CANCELLED", "FAILED")]
            if not active:
                break
            for run in active:
                request(config, token, "/runs/" + run["runId"] + "/cancel", "POST")
            if time.monotonic() > deadline:
                raise RuntimeError("Worker shutdown is unconfirmed. Runtime service was kept running; inspect its logs and retry stop.")
            time.sleep(2)
        record = read(root / "runtime.json")
        if alive(record):
            os.kill(record["pid"], signal.SIGTERM)
    print("Services stopped after confirmed runtime release. Queued experiments remain durable.")


def sync(config, worker_id):
    worker = next((worker for worker in config["workers"] if worker["id"] == worker_id), None)
    if not worker or not worker.get("ssh"):
        raise ValueError("Select a configured SSH worker")
    services = Path(config["processDirectory"])
    if alive(read(services / "runtime.json")):
        token = read(PRIVATE / "credentials.json")["runtime_token"]
        if any(run["status"] not in ("COMPLETED", "CANCELLED", "FAILED") for run in request(config, token, "/runs")):
            raise RuntimeError("Wait for runtime release before deploying source")
    # Deploy an isolated source bundle; never overwrite the friend's existing repo.
    runtime = Path(config["runtimePath"])
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for folder in ("src", "scripts"):
            for path in (runtime / folder).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    archive.add(path, arcname=str(path.relative_to(runtime)))
        metadata = json.dumps({"gitCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=runtime, text=True).strip(),
                               "gitDirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=runtime, text=True).strip()), "deployedAt": time.time()}).encode()
        info = tarfile.TarInfo("deployment.json"); info.size = len(metadata); archive.addfile(info, io.BytesIO(metadata))
    target = str(Path(worker["source"]).parent)
    command = f"mkdir -p {shlex.quote(target)} && tar xzf - -C {shlex.quote(target)}"
    subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", worker["ssh"], command], input=buffer.getvalue(), check=True, timeout=90)
    print(f"Deployed isolated runtime source to {worker_id}: {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "start", "stop", "status", "sync"))
    parser.add_argument("worker", nargs="?")
    args = parser.parse_args()
    try:
        if args.command == "init":
            init()
        else:
            config = read(PRIVATE / "config.json")
            if not config:
                raise RuntimeError("Run scripts/manage-integration.py init first")
            if args.command == "start": start(config)
            elif args.command == "stop": stop(config)
            elif args.command == "sync": sync(config, args.worker)
            else:
                root = Path(config["processDirectory"])
                print(json.dumps({name: alive(read(root / (name + ".json"))) for name in ("runtime", "backend", "frontend")}))
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
