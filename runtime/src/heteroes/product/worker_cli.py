"""Headless Linux Worker: the desktop Worker's setup, self-test, pairing and agent, without a window.

    heteroes-worker install                       # pinned wheels and model, each verified by SHA-256
    heteroes-worker selftest                      # the desktop app's numerical admission on this GPU
    heteroes-worker join https://lab.example      # asks for the code from the lab's Devices page
    heteroes-worker run                           # keeps the device online; turn it ON/OFF on the Devices page
    heteroes-worker status

`install-worker.sh` puts the pinned Python, this runtime and the bundle (profile.json, lock file, reference) under
HETEROES_WORKER_HOME (default ~/.local/share/heteroes-worker) and then runs `install`. The device token is kept in a
0600 file there and is never printed or passed as an argument.
"""

import argparse
import datetime
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

from heteroes.http_transport import USER_AGENT
from .files import read_json, write_json

WORKER_PORT = 8765


def home():
    return Path(os.environ.get("HETEROES_WORKER_HOME") or Path.home() / ".local/share/heteroes-worker")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verified_download(item, directory, say=print):
    """Fetch `item` (name, url, sha256, sizeBytes) into `directory` once; a file that does not match is never kept."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / item["name"]
    if target.is_file() and target.stat().st_size == item["sizeBytes"] and sha256_file(target) == item["sha256"]:
        return target
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    size = 0
    say(f"downloading {item['name']} ({item['sizeBytes'] / 1e6:.1f} MB)")
    request = urllib.request.Request(item["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response, open(partial, "wb") as output:
        for block in iter(lambda: response.read(1 << 20), b""):
            size += len(block)
            if size > item["sizeBytes"]:
                break
            digest.update(block)
            output.write(block)
    if size != item["sizeBytes"] or digest.hexdigest() != item["sha256"]:
        partial.unlink()
        raise RuntimeError("CHECKSUM_MISMATCH: " + item["name"])
    partial.rename(target)
    return target


class Worker:
    def __init__(self, root=None, say=print):
        self.root = Path(root or home())
        self.bundle = self.root / "bundle"
        self.say = say

    # --- layout ---------------------------------------------------------------------------------------------------
    def profile(self):
        profile = json.loads((self.bundle / "profile.json").read_text())
        return {**profile, "platform": "linux", "selected": profile["platforms"]["linux"]}

    def paths(self):
        profile = self.profile()
        return {
            "runtime": self.root / "runtimes" / profile["runtimeSha256"][:12],
            "model": self.root / "models" / profile["modelRevision"],
            "wheels": self.root / "downloads" / "linux",
            "ready": self.root / "runtimes" / profile["runtimeSha256"][:12] / "READY.json",
            "settings": self.root / "settings.json",
            "token": self.root / "device-token",
            "agentConfig": self.root / "agent-config.json",
            "agentState": self.root / "agent-state",
            "artifacts": self.root / "artifacts",
        }

    def settings(self):
        return read_json(self.paths()["settings"], {})

    def save_settings(self, value):
        write_json(self.paths()["settings"], value)

    # --- install ----------------------------------------------------------------------------------------------------
    def install(self, run=subprocess.run):
        profile, p = self.profile(), self.paths()
        if sha256_file(self.bundle / "runtime.tar.gz") != profile["runtimeSha256"]:
            raise RuntimeError("RUNTIME_CHECKSUM_MISMATCH")
        selected = profile["selected"]
        needed = sum(w["sizeBytes"] for w in selected["wheels"]) * 3 + sum(
            m["sizeBytes"] for m in profile["modelFiles"]
        )
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if shutil.disk_usage(self.root).free < needed:
            raise RuntimeError("INSUFFICIENT_DISK_SPACE")
        for wheel in selected["wheels"]:
            verified_download(wheel, p["wheels"], self.say)
        self.say("installing pinned packages")
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(p["wheels"]),
                "--require-hashes",
                "-r",
                str(self.bundle / selected["lockFile"]),
            ],
            check=True,
            env={**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1"},
        )
        for model in profile["modelFiles"]:
            verified_download(model, p["model"], self.say)
        write_json(
            p["ready"],
            {
                "profile": profile["profile"],
                "platform": "linux",
                "verifiedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        )
        self.say("installed; next: heteroes-worker selftest")

    def installed(self):
        p = self.paths()
        return p["ready"].is_file() and all(
            (p["model"] / m["name"]).is_file() and (p["model"] / m["name"]).stat().st_size == m["sizeBytes"]
            for m in self.profile()["modelFiles"]
        )

    # --- self-test --------------------------------------------------------------------------------------------------
    def selftest(self, run=subprocess.run, device="cuda"):
        from .remote import worker_environment

        if device not in ("cpu", "cuda"):
            raise ValueError("Choose cpu or cuda")
        if not self.installed():
            raise RuntimeError("RUNTIME_NOT_INSTALLED: run heteroes-worker install")
        p = self.paths()
        completed = run(
            [sys.executable, "-m", "heteroes.product.qualification"],
            input=json.dumps(
                {"modelPath": str(p["model"]), "referencePath": str(self.bundle / "reference.json"), "device": device}
            ),
            capture_output=True,
            text=True,
            env={
                **worker_environment(str(p["runtime"] / "src"), "self-test-no-network"),
                "PYTHONNOUSERSITE": "1",
                **({"CUDA_VISIBLE_DEVICES": ""} if device == "cpu" else {}),
            },
        )
        result = error = None
        for line in completed.stdout.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            result = row.get("result", result)
            error = row.get("code", error)
        if error or not result or not result.get("passed"):
            raise RuntimeError(error or "COMPATIBILITY_FAILED")
        self.save_settings({**self.settings(), "selfTest": result})
        self.say(f"self-test passed on {result.get('gpuName')}; next: heteroes-worker join <lab address>")
        return result

    # --- pairing ----------------------------------------------------------------------------------------------------
    def compute(self, coordinator=False, host=None):
        if coordinator and not host:
            raise ValueError("A coordinator needs --host: the address other workers reach this machine at")
        return {"coordinator": bool(coordinator), "host": host if coordinator else "127.0.0.1"}

    def advertised(self, settings):
        from .cpu_coordinator import coordinator_only

        if coordinator_only(settings["selfTest"]) and not settings["compute"]["coordinator"]:
            raise ValueError("A CPU coordinator-only profile must join with --coordinator and --host")
        return {**settings["selfTest"], "coordinator": settings["compute"]["coordinator"]}

    def join(self, server_url, code, name, coordinator=False, host=None, call=None):
        call = call or lab_request
        settings = self.settings()
        if not (settings.get("selfTest") or {}).get("passed"):
            raise RuntimeError("SELF_TEST_REQUIRED: run heteroes-worker selftest")
        if settings.get("device"):
            raise RuntimeError("ALREADY_PAIRED")
        server_url = server_url.rstrip("/")
        if not call(server_url, "/api/v1/health", None, None).get("agentMode"):
            raise RuntimeError("LAB_AGENT_MODE_REQUIRED")
        settings = {**settings, "serverUrl": server_url, "compute": self.compute(coordinator, host)}
        worker_id = "cli-" + secrets.token_hex(6)
        device = call(
            server_url,
            "/api/v1/device/enroll",
            None,
            {
                "code": code,
                "workerId": worker_id,
                "displayName": name,
                "computeUrl": f"http://{settings['compute']['host']}:{WORKER_PORT}",
                "selfTest": self.advertised(settings),
            },
        )
        token_file = self.paths()["token"]
        descriptor = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(device["deviceToken"])
        public = {k: v for k, v in device.items() if k != "deviceToken"}
        self.save_settings({**settings, "device": public})
        self.say("paired; an administrator must approve it. Then: heteroes-worker run, and turn it ON on the lab.")
        return public

    # --- agent ------------------------------------------------------------------------------------------------------
    def agent_config(self):
        """The same agent configuration the desktop Worker writes (desktop/worker/electron/service.cjs)."""
        from .cpu_coordinator import coordinator_only

        settings, p = self.settings(), self.paths()
        if not settings.get("device"):
            raise RuntimeError("DEVICE_NOT_PAIRED: run heteroes-worker join")
        compute = settings["compute"]
        config = {
            "serverUrl": settings["serverUrl"],
            "deviceId": settings["device"]["deviceId"],
            "workerId": settings["device"]["workerId"],
            "stateDirectory": str(p["agentState"]),
            "modelPath": str(p["model"]),
            "computeUrl": f"http://{compute['host']}:{WORKER_PORT}",
            "workerHost": compute["host"],
            "workerPort": WORKER_PORT,
            "workerOnly": not compute["coordinator"],
            "device": "cpu" if coordinator_only(settings["selfTest"]) else "cuda",
            "largeDataDirectory": str(p["artifacts"]),
            "selfTest": self.advertised(settings),
        }
        write_json(p["agentConfig"], config)
        return p["agentConfig"]

    def run(self, call=None, bridge_class=None):
        call = call or lab_request
        if bridge_class is None:
            from .desktop_bridge import Bridge as bridge_class
        config = self.agent_config()
        settings, token = self.settings(), self.paths()["token"].read_text()
        bridge = bridge_class(config, token)
        self.declare_qualification(bridge, settings, token, call)
        stop = []
        for number in (signal.SIGINT, signal.SIGTERM):
            signal.signal(number, lambda *_: stop.append(True))
        self.say("online; turn contribution ON on the lab's Devices page. Ctrl-C stops after running work is drained.")
        while not stop:
            time.sleep(1)
        self.say("stopping: contribution OFF, waiting for owned processes to end")
        while not bridge.call("quit")["drained"]:
            time.sleep(2)
        self.say("stopped")

    def declare_qualification(self, bridge, settings, token, call):
        """Bind recipe v2/v3 admission evidence to this boot, as the desktop Worker does after starting its agent."""
        evidenced = [v for v in settings["selfTest"].get("recipeVersions", []) if v >= 2]
        if not evidenced:
            return
        health = call(settings["serverUrl"], "/api/v1/health", None, None)
        if not any(v in health.get("recipeVersions", []) for v in evidenced):
            return
        for attempt in range(20):
            try:
                call(
                    settings["serverUrl"],
                    "/api/v1/device/qualification",
                    token,
                    {"bootId": bridge.call("status")["bootId"], "selfTest": self.advertised(settings)},
                    "PATCH",
                )
                return
            except LabError as error:
                if error.status != 409 or attempt == 19:
                    raise
                time.sleep(0.2)

    def status(self):
        settings, p = self.settings(), self.paths()
        return {
            "home": str(self.root),
            "installed": self.installed(),
            "selfTestPassed": bool((settings.get("selfTest") or {}).get("passed")),
            "serverUrl": settings.get("serverUrl"),
            "device": settings.get("device"),
            "compute": settings.get("compute"),
            "connection": read_json(p["agentState"] / "connection.json", None),
            "boot": read_json(p["agentState"] / "boot.json", None),
        }


class LabError(RuntimeError):
    def __init__(self, status):
        super().__init__(f"LAB_HTTP_{status}")
        self.status = status


def lab_request(server_url, path, token, body, method=None):
    """One JSON request to the lab. Errors carry only the status: never URLs, tokens or server text."""
    request = urllib.request.Request(
        server_url + path,
        data=None if body is None else json.dumps(body, allow_nan=False).encode(),
        method=method,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            **({"Authorization": "Bearer " + token} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise LabError(error.code) from None


def read_code():
    if sys.stdin.isatty():
        return getpass.getpass("Pairing code from the lab's Devices page: ").strip()
    return sys.stdin.readline().strip()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="heteroes-worker", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("install", help="download and install the pinned packages and model")
    selftest = commands.add_parser("selftest", help="run the numerical admission test")
    selftest.add_argument(
        "--device", choices=("cpu", "cuda"), default="cuda", help="cpu admits coordination only; cuda admits GPU work"
    )
    join = commands.add_parser("join", help="pair this machine with a lab (asks for the pairing code)")
    join.add_argument("lab", help="lab address, for example https://lab.heteroes.site")
    join.add_argument("--name", default=os.uname().nodename, help="name shown on the lab")
    join.add_argument("--coordinator", action="store_true", help="also offer this machine as a coordinator")
    join.add_argument("--host", help="with --coordinator: the address other workers reach this machine at")
    commands.add_parser("run", help="keep this device online until Ctrl-C")
    commands.add_parser("status", help="show installation, pairing and connection state")
    args = parser.parse_args(argv)
    worker = Worker(say=lambda *values: print(*values, flush=True))  # `run` is often logged to a file
    try:
        if args.command == "install":
            worker.install()
        elif args.command == "selftest":
            worker.selftest(device=args.device)
        elif args.command == "join":
            worker.join(args.lab, read_code(), args.name, args.coordinator, args.host)
        elif args.command == "run":
            worker.run()
        else:
            print(json.dumps(worker.status(), indent=2))
    except subprocess.CalledProcessError:
        print("error: PIP_INSTALL_FAILED", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, OSError) as error:
        print("error:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
