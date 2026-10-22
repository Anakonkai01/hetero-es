"""Headless Linux Worker: lends this machine's NVIDIA GPU to a HeteroES lab, without a window.

    curl -fsSL https://lab.heteroes.site/downloads/install-worker.sh | bash    # installs, then runs `setup`

    heteroes-worker setup [--lab URL]      checks the machine, installs, self-tests, pairs, starts the service, waits for
                                           approval and asks to turn contribution ON; run again to resume where it stopped
    heteroes-worker status [--json]        what this machine is doing now
    heteroes-worker on [--keep-after-reboot] | off [--no-keep]
    heteroes-worker start | stop | restart | logs [-f]
    heteroes-worker doctor | update | clean | rename NAME | forget | uninstall
    heteroes-worker install | selftest | join LAB | run      the single steps that `setup` runs

`install-worker.sh` puts the pinned Python, this runtime and the bundle (profile.json, lock file, reference) under
HETEROES_WORKER_HOME (default ~/.local/share/heteroes-worker). The device token is kept in a 0600 file there and is never
printed or passed as an argument; the pairing code is read from the terminal, never from the command line.
"""

import argparse
import datetime
import email.utils
import getpass
import hashlib
import http.client
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from heteroes.http_transport import USER_AGENT
from .files import read_json, write_json
from .worker_service import Service

WORKER_PORT = 8765
DEFAULT_LAB = "https://lab.heteroes.site"
DOWNLOAD_ATTEMPTS = 6
TRANSIENT = (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, socket.timeout)


def home():
    return Path(os.environ.get("HETEROES_WORKER_HOME") or Path.home() / ".local/share/heteroes-worker")


SHARED = ("bundle", "runtimes", "models", "downloads")


def gpu_home(gpu=None):
    """GPU 0 lives in the main home. Another lent GPU of the same machine is its own device (pairing, token, agent state,
    service) in `gpu<N>` beside it, sharing the main home's runtime, model and downloads through links."""
    main = home()
    if not gpu:
        return main
    root = main / f"gpu{gpu}"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in SHARED:
        link = root / name
        if not link.exists() and not link.is_symlink():
            (main / name).mkdir(parents=True, exist_ok=True, mode=0o700)
            link.symlink_to(main / name)
    return root


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class Progress:
    """One line per download: redrawn in place on a terminal, every quarter otherwise (logs, pipes)."""

    def __init__(self, name, total, stream=None):
        self.name, self.total, self.stream = name, total, stream or sys.stderr
        self.tty = self.stream.isatty()
        self.started, self.shown, self.quarter = time.monotonic(), 0.0, 0

    def __call__(self, done):
        now = time.monotonic()
        rate = done / max(now - self.started, 1e-3) / 1e6
        line = f"  {self.name[:40]:40} {100 * done / self.total:5.1f}%  {done / 1e6:8.1f}/{self.total / 1e6:.1f} MB  {rate:6.1f} MB/s"
        if self.tty and (now - self.shown >= 0.2 or done >= self.total):
            self.stream.write("\r" + line + ("\n" if done >= self.total else ""))
            self.stream.flush()
            self.shown = now
        elif not self.tty and 4 * done // self.total > self.quarter:
            self.quarter = 4 * done // self.total
            print(line, file=self.stream, flush=True)


def _fetch(item, partial, progress):
    """Continue `partial` from where it stopped (HTTP Range); a server that ignores the range sends it all again."""
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > item["sizeBytes"]:
        partial.unlink()
        offset = 0
    headers = {"User-Agent": USER_AGENT, **({"Range": f"bytes={offset}-"} if offset else {})}
    with urllib.request.urlopen(urllib.request.Request(item["url"], headers=headers), timeout=60) as response:
        if offset and getattr(response, "status", None) != 206:
            offset = 0
        with open(partial, "ab" if offset else "wb") as output:
            size = offset
            for block in iter(lambda: response.read(1 << 20), b""):
                size += len(block)
                if size > item["sizeBytes"]:
                    break
                output.write(block)
                if progress:
                    progress(size)


def verified_download(item, directory, say=print, attempts=DOWNLOAD_ATTEMPTS, sleep=time.sleep, progress=None):
    """Fetch `item` (name, url, sha256, sizeBytes) into `directory` once; a file that does not match is never kept.
    Network failures are retried with growing pauses and the download resumes where it stopped."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / item["name"]
    if target.is_file() and target.stat().st_size == item["sizeBytes"] and sha256_file(target) == item["sha256"]:
        return target
    partial = target.with_name(target.name + ".part")
    say(f"downloading {item['name']} ({item['sizeBytes'] / 1e6:.1f} MB)")
    for attempt in range(1, attempts + 1):
        try:
            _fetch(item, partial, progress)
            break
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == attempts:
                raise RuntimeError(f"DOWNLOAD_FAILED: {item['name']} (HTTP {error.code})") from None
        except TRANSIENT as error:
            if attempt == attempts:
                raise RuntimeError(f"DOWNLOAD_FAILED: {item['name']} ({type(error).__name__})") from None
        delay = min(60, 2**attempt)
        say(f"  network problem; retrying in {delay} s (attempt {attempt + 1} of {attempts})")
        sleep(delay)
    if partial.stat().st_size != item["sizeBytes"] or sha256_file(partial) != item["sha256"]:
        partial.unlink()
        raise RuntimeError("CHECKSUM_MISMATCH: " + item["name"])
    partial.rename(target)
    return target


SELFTEST_STAGES = {
    "model": "loading the model",
    "candidate": "checking candidate scores",
    "recipe_v2": "checking recipe v2",
    "recipe_v3": "checking recipe v3",
    "update_speed": "measuring update speed",
}


def describe_stage(progress):
    text = SELFTEST_STAGES.get(progress.get("stage"), str(progress.get("stage")))
    if progress.get("weightSpace"):
        text += f" ({progress['weightSpace']}, sign {progress['sign']:+d})"
    if progress.get("total"):
        text += f" {progress['iteration']}/{progress['total']}"
    return text


class Streamed:
    def __init__(self, stdout):
        self.stdout = stdout


def streamed_run(argv, input, env, on_row, log):
    """Run the self-test process and report each progress row as it comes; stderr goes to `log`."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w") as errors:
        process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True, env=env
        )
        process.stdin.write(input)
        process.stdin.close()
        lines = []
        for line in process.stdout:
            lines.append(line)
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and "progress" in row:
                on_row(row["progress"])
        process.wait()
    return Streamed("".join(lines))


class Worker:
    def __init__(self, root=None, say=print, service=None):
        self.root = Path(root or home())
        self.bundle = self.root / "bundle"
        self.say = say
        self.service = service or Service()

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
            "logs": self.root / "logs",
        }

    def settings(self):
        return read_json(self.paths()["settings"], {})

    def save_settings(self, value):
        write_json(self.paths()["settings"], value)

    def needed_bytes(self):
        profile = self.profile()
        return sum(w["sizeBytes"] for w in profile["selected"]["wheels"]) * 3 + sum(
            m["sizeBytes"] for m in profile["modelFiles"]
        )

    # --- install ----------------------------------------------------------------------------------------------------
    def install(self, run=subprocess.run, progress=None):
        profile, p = self.profile(), self.paths()
        if sha256_file(self.bundle / "runtime.tar.gz") != profile["runtimeSha256"]:
            raise RuntimeError("RUNTIME_CHECKSUM_MISMATCH")
        selected = profile["selected"]
        lock = sha256_file(self.bundle / selected["lockFile"])
        marker = p["runtime"] / "LOCK_SHA256"
        if self.installed() and marker.is_file() and marker.read_text().strip() == lock:
            # install-worker.sh linked the same pinned Python and packages from the previous runtime: nothing to fetch
            shutil.rmtree(p["wheels"], ignore_errors=True)
            self.say("installed (pinned packages reused from the previous runtime)")
            return
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if shutil.disk_usage(self.root).free < self.needed_bytes():
            raise RuntimeError("INSUFFICIENT_DISK_SPACE")
        progress = progress or (lambda item: None)
        for wheel in selected["wheels"]:
            verified_download(wheel, p["wheels"], self.say, progress=progress(wheel))
        self.say("installing pinned packages")
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--quiet",
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
            verified_download(model, p["model"], self.say, progress=progress(model))
        write_json(
            p["ready"],
            {
                "profile": profile["profile"],
                "platform": "linux",
                "lockSha256": lock,
                "verifiedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        )
        marker.write_text(lock + "\n")  # the next runtime with the same lock file reuses these packages
        # the packages are inside the runtime now: the wheel files (gigabytes of CUDA) are not needed any more
        shutil.rmtree(p["wheels"], ignore_errors=True)
        self.say("installed")

    def installed(self):
        p = self.paths()
        return p["ready"].is_file() and all(
            (p["model"] / m["name"]).is_file() and (p["model"] / m["name"]).stat().st_size == m["sizeBytes"]
            for m in self.profile()["modelFiles"]
        )

    # --- self-test --------------------------------------------------------------------------------------------------
    def selftest(self, run=None, device="cuda"):
        from .remote import worker_environment

        if device not in ("cpu", "cuda"):
            raise ValueError("Choose cpu or cuda")
        if not self.installed():
            raise RuntimeError("RUNTIME_NOT_INSTALLED")
        p = self.paths()
        argv = [sys.executable, "-m", "heteroes.product.qualification"]
        request = json.dumps(
            {"modelPath": str(p["model"]), "referencePath": str(self.bundle / "reference.json"), "device": device}
        )
        env = {
            **worker_environment(str(p["runtime"] / "src"), "self-test-no-network"),
            "PYTHONNOUSERSITE": "1",
            **({"CUDA_VISIBLE_DEVICES": ""} if device == "cpu" else {}),
        }
        started = time.monotonic()

        def show(progress):
            self.say(f"  [{time.monotonic() - started:5.0f} s] {describe_stage(progress)}")

        self.say("self-test: running the pinned reference on this GPU (a few minutes)")
        if run is None:
            completed = streamed_run(argv, request, env, show, p["logs"] / "selftest.log")
        else:
            completed = run(argv, input=request, capture_output=True, text=True, env=env)
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
        self.say(f"self-test passed on {result.get('gpuName')}")
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
            raise RuntimeError("SELF_TEST_REQUIRED")
        if settings.get("device"):
            raise RuntimeError("ALREADY_PAIRED")
        server_url = server_url.rstrip("/")
        if not call(server_url, "/api/v1/health", None, None).get("agentMode"):
            raise RuntimeError("LAB_AGENT_MODE_REQUIRED")
        settings = {**settings, "serverUrl": server_url, "compute": self.compute(coordinator, host)}
        worker_id = "cli-" + secrets.token_hex(6)
        try:
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
        except LabError as error:
            if error.status in (400, 401, 403, 404, 409, 422):
                raise RuntimeError("PAIRING_REFUSED") from None
            raise
        token_file = self.paths()["token"]
        descriptor = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(device["deviceToken"])
        public = {k: v for k, v in device.items() if k != "deviceToken"}
        self.save_settings({**settings, "device": public})
        self.say(f"paired with {server_url} as '{name}'")
        return public

    # --- talking to the lab as this device --------------------------------------------------------------------------
    def lab(self, path, body=None, method=None, call=None):
        settings = self.settings()
        if not settings.get("device"):
            raise RuntimeError("DEVICE_NOT_PAIRED")
        return (call or lab_request)(settings["serverUrl"], path, self.paths()["token"].read_text(), body, method)

    def summary(self, call=None):
        return self.lab("/api/v1/device/summary", call=call)

    def contribution(self, enabled, keep=None, call=None):
        body = {"enabled": enabled, **({} if keep is None else {"keepAfterReboot": keep})}
        try:
            return self.lab("/api/v1/device/contribution", body, call=call)
        except LabError as error:
            if error.status == 409:
                raise RuntimeError("NOT_READY_FOR_CONTRIBUTION") from None
            raise

    def rename(self, name, call=None):
        result = self.lab("/api/v1/device/name", {"displayName": name}, "PATCH", call=call)
        settings = self.settings()
        self.save_settings({**settings, "device": {**settings["device"], "displayName": result["displayName"]}})
        return result

    def forget(self, call=None):
        """Leave the lab: the lab revokes this device's token, then the local pairing is removed."""
        try:
            self.lab("/api/v1/device", method="DELETE", call=call)
        except LabError as error:
            if error.status == 409:
                raise RuntimeError("FORGET_BUSY") from None
            if error.status != 401:  # 401: the lab had already removed it
                raise
        p = self.paths()
        p["token"].unlink(missing_ok=True)
        p["agentConfig"].unlink(missing_ok=True)
        settings = self.settings()
        self.save_settings({k: v for k, v in settings.items() if k not in ("device", "serverUrl", "compute")})

    # --- agent ------------------------------------------------------------------------------------------------------
    def agent_config(self):
        """The same agent configuration the desktop Worker writes (desktop/worker/electron/service.cjs)."""
        from .cpu_coordinator import coordinator_only

        settings, p = self.settings(), self.paths()
        if not settings.get("device"):
            raise RuntimeError("DEVICE_NOT_PAIRED")
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
            # ADR-010: the owner's cap on prompts per generate() call (else the agent picks one from the GPU memory)
            **({"maxChunk": settings["limits"]["maxChunk"]} if (settings.get("limits") or {}).get("maxChunk") else {}),
            # the owner's contribution hours and GPU temperature ceiling (the agent leaves runs while one holds)
            "limits": {k: v for k, v in (settings.get("limits") or {}).items() if k in ("hours", "maxTemperatureC")},
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
        self.say("online; contribution follows the lab (heteroes-worker on/off). Ctrl-C stops after work is drained.")
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

    def agent_online(self, within=60):
        connection = read_json(self.paths()["agentState"] / "connection.json", None) or {}
        return connection.get("status") == "ONLINE" and time.time() - connection.get("t", 0) < within

    # --- status -----------------------------------------------------------------------------------------------------
    def status(self, call=None):
        settings, p = self.settings(), self.paths()
        result = {
            "home": str(self.root),
            "installed": self.installed(),
            "runtime": p["runtime"].name,
            "selfTestPassed": bool((settings.get("selfTest") or {}).get("passed")),
            "gpuName": (settings.get("selfTest") or {}).get("gpuName"),
            "serverUrl": settings.get("serverUrl"),
            "device": settings.get("device"),
            "compute": settings.get("compute"),
            "service": {
                "installed": self.service.installed(),
                "active": self.service.active(),
                "startsAtBoot": self.service.enabled(),
            },
            "connection": read_json(p["agentState"] / "connection.json", None),
            "boot": read_json(p["agentState"] / "boot.json", None),
            "gpu": (read_json(p["agentState"] / "telemetry.json", None) or {}).get("gpu"),
            "lab": None,
        }
        if settings.get("device"):
            try:
                result["lab"] = self.summary(call=call)
            except (LabError, OSError, RuntimeError) as error:
                result["lab"] = {"error": error_code(error)}
        return result

    # --- doctor -----------------------------------------------------------------------------------------------------
    def doctor(self, lab=None, run=subprocess.run, call=None):
        """Checks that explain most failures before they happen. Each row: (level, check, detail, fix)."""
        rows = []

        def row(level, check, detail, fix=""):
            rows.append({"level": level, "check": check, "detail": detail, "fix": fix})

        machine = f"{platform.system()} {platform.machine()}"
        if machine != "Linux x86_64":
            row("fail", "system", machine, "Only Linux x86_64 is supported; use the Windows app on Windows.")
        elif "microsoft" in platform.release().lower():
            row("fail", "system", "WSL", "WSL is no longer supported: install the HeteroES Worker app on Windows.")
        else:
            row("ok", "system", f"{machine}, {platform.release()}")
        try:
            gpus = run(
                ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            lines = [line.strip() for line in gpus.stdout.splitlines() if line.strip()]
            if gpus.returncode == 0 and lines:
                row("ok", "GPU", "; ".join(lines))
            else:
                row("fail", "GPU", "nvidia-smi found no GPU", "Install or repair the NVIDIA driver, then reboot.")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            row(
                "fail",
                "GPU",
                "nvidia-smi is missing",
                "Install the NVIDIA driver (sudo ubuntu-drivers install), reboot.",
            )
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        free = shutil.disk_usage(self.root).free
        if self.installed():
            row("ok", "disk", f"{free / 1e9:.1f} GB free in {self.root}")
        else:
            need = self.needed_bytes() if (self.bundle / "profile.json").exists() else 0
            row(
                "ok" if free >= need else "fail",
                "disk",
                f"{free / 1e9:.1f} GB free in {self.root}, {need / 1e9:.1f} GB needed",
                "" if free >= need else "Free space, or install with HETEROES_WORKER_HOME on a larger disk.",
            )
        if self.service.available():
            fix = self.service.ensure_linger()
            row(
                "ok" if fix is None else "warn",
                "service",
                "systemd user services available" + ("" if fix is None else "; not started at boot"),
                "" if fix is None else f"Run: {fix}",
            )
        else:
            row("warn", "service", "no systemd user session", "Run `heteroes-worker run` inside tmux or screen.")
        # no Tailscale by default (owner 2026-10-22): a worker reaches the lab and its runs over the public address
        private = tailscale_ip(run)
        row(
            "ok",
            "network",
            "the lab's public address" + (f"; private route {private} (Tailscale) too" if private else ""),
            "",
        )
        url = (lab or self.settings().get("serverUrl") or "").rstrip("/")
        if url:
            try:
                health, skew = lab_health(url, call)
                if not health.get("agentMode"):
                    row("fail", "lab", f"{url} is not a HeteroES lab that accepts devices", "Check the address.")
                else:
                    row("ok", "lab", f"{url} answers (lab {health.get('uiUrl') or url})")
                if skew is not None and abs(skew) > 120:
                    row(
                        "warn",
                        "clock",
                        f"{skew:+.0f} s from the lab",
                        "Turn on time sync: sudo timedatectl set-ntp true",
                    )
            except (LabError, OSError) as error:
                row("fail", "lab", f"{url}: {error_code(error)}", "Check the address and the network.")
        settings = self.settings()
        row(
            "ok" if self.installed() else "warn",
            "installed",
            "yes" if self.installed() else "no",
            "" if self.installed() else "Run `heteroes-worker setup`.",
        )
        passed = (settings.get("selfTest") or {}).get("passed")
        row(
            "ok" if passed else "warn",
            "self-test",
            "passed" if passed else "not passed",
            "" if passed else "Run `heteroes-worker selftest`.",
        )
        return rows

    # --- maintenance ------------------------------------------------------------------------------------------------
    def clean(self):
        """Remove what is never needed again: leftover wheel files and runtimes other than the current one. Run data
        (a coordinator's ledger and weights under artifacts/coordinators) is the only copy and is never removed here."""
        p, freed = self.paths(), 0

        def size(path):  # a file linked into several places (runtimes, checkpoints) counts once
            files = {(f.stat().st_dev, f.stat().st_ino): f.stat().st_size for f in Path(path).rglob("*") if f.is_file()}
            return sum(files.values())

        if p["wheels"].exists():
            freed += size(p["wheels"])
            shutil.rmtree(p["wheels"])
        keep = {p["runtime"].resolve(), *Path(sys.executable).resolve().parents}  # the current one and this process's
        for runtime in (self.root / "runtimes").glob("*"):
            if runtime.resolve() not in keep:
                freed += size(runtime)
                shutil.rmtree(runtime)
        for partial in (self.root / "downloads").rglob("*.part"):
            freed += partial.stat().st_size
            partial.unlink()
        kept = size(p["artifacts"] / "coordinators") if (p["artifacts"] / "coordinators").exists() else 0
        return {"freedBytes": freed, "runDataBytes": kept}


def tailscale_ip(run=subprocess.run):
    try:
        shown = run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    lines = shown.stdout.split()
    return lines[0] if shown.returncode == 0 and lines else None


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
            data = response.read()
            return json.loads(data) if data else None
    except urllib.error.HTTPError as error:
        raise LabError(error.code) from None
    except TRANSIENT:
        raise RuntimeError("LAB_UNREACHABLE") from None


def lab_health(url, call=None):
    """The lab's health and, when the lab is reached directly, this machine's clock offset from it (seconds)."""
    if call:
        return call(url, "/api/v1/health", None, None), None
    request = urllib.request.Request(url + "/api/v1/health", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            date = response.headers.get("Date")
            skew = time.time() - email.utils.parsedate_to_datetime(date).timestamp() if date else None
            return json.load(response), skew
    except urllib.error.HTTPError as error:
        raise LabError(error.code) from None
    except TRANSIENT:
        raise RuntimeError("LAB_UNREACHABLE") from None


# --- words for people ------------------------------------------------------------------------------------------------
EXPLAIN = {
    "RUNTIME_CHECKSUM_MISMATCH": (
        "The downloaded runtime does not match its pinned checksum.",
        "Run the install command again; if it repeats, the download is being altered on the way.",
    ),
    "INSUFFICIENT_DISK_SPACE": (
        "Not enough free disk space for the packages and the model.",
        "Free space (see `heteroes-worker doctor`), or install with HETEROES_WORKER_HOME on a larger disk.",
    ),
    "CHECKSUM_MISMATCH": ("A downloaded file does not match its pinned checksum.", "Run the command again."),
    "DOWNLOAD_FAILED": (
        "A download kept failing.",
        "Check the internet connection and run the command again: finished files are kept, the rest resumes.",
    ),
    "PIP_INSTALL_FAILED": (
        "Installing the pinned Python packages failed.",
        "Read the output above (free disk space is the usual cause), then run `heteroes-worker setup` again.",
    ),
    "RUNTIME_NOT_INSTALLED": ("The worker is not installed yet.", "Run `heteroes-worker setup`."),
    "COMPATIBILITY_FAILED": (
        "This GPU did not reproduce the pinned reference results, so it cannot take part in exact runs.",
        "Check the driver with `heteroes-worker doctor` and run `heteroes-worker selftest` again; if it fails again,"
        " send logs/selftest.log to the lab administrator.",
    ),
    "SELF_TEST_REQUIRED": ("The self-test has not passed on this machine.", "Run `heteroes-worker selftest`."),
    "ALREADY_PAIRED": (
        "This machine is already paired with a lab.",
        "`heteroes-worker status` shows which; `heteroes-worker forget` unpairs it.",
    ),
    "LAB_AGENT_MODE_REQUIRED": (
        "That address answers, but it is not a HeteroES lab that accepts devices.",
        f"Check the address; the HeteroES lab is {DEFAULT_LAB}.",
    ),
    "PAIRING_REFUSED": (
        "The lab refused the pairing code.",
        "A code works once and expires after 10 minutes: make a new one on the lab's Devices page. Also check the"
        f" address is the lab you mean (the HeteroES lab is {DEFAULT_LAB}, not a test lab).",
    ),
    "LAB_UNREACHABLE": (
        "The lab does not answer.",
        "Check the address and this machine's network; `heteroes-worker doctor` tests the connection.",
    ),
    "DEVICE_NOT_PAIRED": ("This machine is not paired with a lab.", "Run `heteroes-worker setup`."),
    "NOT_READY_FOR_CONTRIBUTION": (
        "The lab cannot turn this machine ON yet.",
        "It must be approved by an administrator and its service must be running (`heteroes-worker status`).",
    ),
    "FORGET_BUSY": (
        "This machine still has work in a run.",
        "Turn it OFF (`heteroes-worker off`), wait until `heteroes-worker status` shows no run, then try again.",
    ),
    "UPDATE_BUSY": (
        "This machine is taking part in a running experiment.",
        "Wait until it ends, or use --force: the run continues without this machine.",
    ),
    "SERVICE_UNAVAILABLE": (
        "This system has no systemd user session, so the worker cannot run as a service.",
        "Run `heteroes-worker run` inside tmux or screen instead.",
    ),
    "LAB_HTTP_401": (
        "The lab no longer accepts this machine's key (it was revoked or removed).",
        "Run `heteroes-worker forget`, then `heteroes-worker setup` with a new pairing code.",
    ),
    "LAB_HTTP_403": ("The lab refused this action for this machine.", "Ask the lab administrator."),
    "LAB_HTTP_404": (
        "The lab does not know this request; the address may be another service or an older lab.",
        f"Check the address (the HeteroES lab is {DEFAULT_LAB}) or update the worker: `heteroes-worker update`.",
    ),
    "LAB_HTTP_409": ("The lab refused in its current state.", "`heteroes-worker status` shows the machine's state."),
    "LAB_HTTP_422": ("The lab rejected what this machine sent.", "Update the worker: `heteroes-worker update`."),
    "LAB_HTTP_5XX": ("The lab had a problem or is busy.", "Wait a minute and try again."),
}


def error_code(error):
    if isinstance(error, LabError):
        return f"LAB_HTTP_{error.status}"
    if isinstance(error, subprocess.CalledProcessError):
        return "PIP_INSTALL_FAILED"
    if isinstance(error, urllib.error.URLError):
        return "LAB_UNREACHABLE"
    return str(error).split(":")[0].strip() or type(error).__name__


def explain(error):
    code = error_code(error)
    key = "LAB_HTTP_5XX" if code.startswith("LAB_HTTP_5") else code
    if key in EXPLAIN:
        message, fix = EXPLAIN[key]
        detail = str(error).split(":", 1)[1].strip() if ":" in str(error) and not isinstance(error, LabError) else ""
        return f"error: {message}{' (' + detail + ')' if detail else ''}\n  what to do: {fix}\n  [{code}]"
    return f"error: {error}"


def ago(t):
    seconds = max(0, time.time() - t)
    return (
        f"{seconds:.0f} s ago"
        if seconds < 120
        else f"{seconds / 60:.0f} min ago"
        if seconds < 7200
        else (f"{seconds / 3600:.1f} h ago")
    )


def render_status(s):
    device = s.get("device") or {}
    lab = s.get("lab") or {}
    name = lab.get("displayName") or device.get("displayName") or "(not paired)"
    lines = [f"{name}  ·  {s.get('serverUrl') or 'no lab yet'}"]

    def line(label, value):
        lines.append(f"  {label:<13} {value}")

    if not s["installed"]:
        line("Install", "not installed: run `heteroes-worker setup`")
    elif not s["selfTestPassed"]:
        line("Self-test", "not passed: run `heteroes-worker selftest`")
    if lab.get("error"):
        line("Lab", f"cannot read ({lab['error']}): {EXPLAIN.get(lab['error'], ('', ''))[0]}")
    elif lab:
        line(
            "Approval",
            {"APPROVED": "approved", "PENDING": "waiting for an administrator"}.get(
                lab["approvalStatus"], lab["approvalStatus"].lower()
            ),
        )
        on = "ON" if lab["contributionEnabled"] else ("turning ON" if lab["contributionDesired"] else "OFF")
        line("Contribution", on + (" (stays ON after restart)" if lab["keepContributionAfterReboot"] else ""))
        for run in lab.get("runs", []):
            progress = (
                f", generation {run['completedGenerations']}/{run['maxGenerations']}"
                if run.get("completedGenerations") is not None and run.get("maxGenerations")
                else ""
            )
            line("Run", f"{run.get('name') or run['experimentId']} ({run['role']}{progress}, {run.get('status')})")
        if not lab.get("runs"):
            line("Run", "none")
    service = s["service"]
    line(
        "Service",
        ("running" if service["active"] else "stopped")
        + (
            ", starts at boot"
            if service["startsAtBoot"]
            else ", not started at boot"
            if service["installed"]
            else " (no service: started by hand)"
        ),
    )
    connection = s.get("connection") or {}
    if connection.get("t"):
        stale = time.time() - connection["t"] > 60  # the agent writes it every ~10 s while it runs
        line(
            "Lab contact",
            f"none for {ago(connection['t'])[:-4]}"
            if stale
            else f"{connection['status'].lower()}, {ago(connection['t'])}",
        )
    gpu = s.get("gpu")
    if gpu:
        parts = [gpu.get("name") or s.get("gpuName") or "GPU"]
        if gpu.get("vramTotalMb"):
            parts.append(f"{gpu.get('vramUsedMb', 0) / 1024:.1f}/{gpu['vramTotalMb'] / 1024:.1f} GB")
        if gpu.get("temperatureC") is not None:
            parts.append(f"{gpu['temperatureC']:.0f} °C")
        if gpu.get("powerDrawW") is not None:
            parts.append(f"{gpu['powerDrawW']:.0f} W")
        if gpu.get("utilizationPercent") is not None:
            parts.append(f"{gpu['utilizationPercent']:.0f}% busy")
        line("GPU", " · ".join(parts))
    elif s.get("gpuName"):
        line("GPU", s["gpuName"])
    line("Runtime", s["runtime"])
    return "\n".join(lines)


def watch(worker, every=2.0, log_lines=8, run=subprocess.run):
    """A screen that refreshes itself (like htop): the status, then the newest lines of the service's log. q quits."""
    import curses

    def lines():
        text = render_status(worker.status()).splitlines()
        if worker.service.installed():
            command = worker.service.logs_command(lines=log_lines)
            logged = run(command, capture_output=True, text=True).stdout.splitlines()
            text += ["", "Log:"] + ["  " + line[-200:] for line in logged[-log_lines:]]
        return text + ["", f"refreshes every {every:.0f} s · q quits"]

    def screen(window):
        curses.curs_set(0)
        window.timeout(int(every * 1000))
        while True:
            window.erase()
            height, width = window.getmaxyx()
            for row, line in enumerate(lines()[: height - 1]):
                window.addnstr(row, 0, line, width - 1)
            window.refresh()
            if window.getch() in (ord("q"), ord("Q"), 27):
                return

    curses.wrapper(screen)


# --- terminal ----------------------------------------------------------------------------------------------------------
def terminal():
    """Where questions go: the terminal even when stdin is the piped install script (`curl ... | bash`)."""
    if sys.stdin.isatty():
        return sys.stdin
    try:
        return open("/dev/tty")
    except OSError:
        return None


def ask(question, default=None, tty=None):
    tty = tty or terminal()
    if tty is None:
        if default is None:
            raise RuntimeError("NO_TERMINAL: run this command in a terminal or pass the answer as an option")
        return default
    suffix = f" [{default}]" if default not in (None, "") else ""
    print(f"{question}{suffix}: ", end="", flush=True)
    answer = tty.readline().strip()
    return answer or (default or "")


def confirm(question, default=True, tty=None):
    answer = ask(question + (" (Y/n)" if default else " (y/N)"), "", tty).lower()
    return default if not answer else answer in ("y", "yes", "c", "co", "có")


def read_code():
    if sys.stdin.isatty() or terminal() is not None:
        try:
            return getpass.getpass("Pairing code from the lab's Devices page (hidden): ").strip()
        except (EOFError, OSError):
            pass
    return sys.stdin.readline().strip()


def launcher():
    """The `heteroes-worker` command that install-worker.sh wrote (the service starts it)."""
    configured = os.environ.get("HETEROES_WORKER_COMMAND")
    found = configured or shutil.which("heteroes-worker") or str(Path.home() / ".local/bin/heteroes-worker")
    return str(Path(found).resolve()) if Path(found).exists() else found


# --- commands --------------------------------------------------------------------------------------------------------
def confirm_lab(url, call=None, yes=False):
    url = url.rstrip("/")
    if not url.startswith(("https://", "http://")):
        url = "https://" + url
    health, _ = lab_health(url, call)
    if not health.get("agentMode"):
        raise RuntimeError("LAB_AGENT_MODE_REQUIRED")
    home_page = (health.get("uiUrl") or url).rstrip("/")
    print(f"Lab: {home_page}" + ("" if home_page == url else f"  (reached at {url})"))
    if home_page != url and home_page.startswith("https://"):
        print(f"  note: this lab calls itself {home_page}; pairing at that address is usually what you want.")
    if not yes and not confirm("Pair this machine with that lab?"):
        raise RuntimeError("CANCELLED")
    return url


def start_service(worker):
    if not worker.service.available():
        raise RuntimeError("SERVICE_UNAVAILABLE")
    hint = worker.service.install(launcher(), home())  # the unit adds --gpu N for another GPU
    if worker.service.active():
        worker.service.restart()
    else:
        worker.service.start()
    worker.say("service started (heteroes-worker.service)" + ("" if hint else ", starts at boot"))
    if hint:
        worker.say(f"  to start it at boot without logging in, run once: {hint}")


def wait_until(check, timeout, every=5, sleep=time.sleep):
    end = time.monotonic() + timeout
    while True:
        value = check()
        if value or time.monotonic() >= end:
            return value
        sleep(every)


def setup(worker, args, call=None, sleep=time.sleep):
    """Every step that is not done yet, in order; a step already done is skipped, so running it again resumes."""
    worker.say("1/6 checking this machine")
    rows = worker.doctor(args.lab, call=call)
    for row in rows:
        if row["level"] != "ok":
            worker.say(
                f"  {row['level']}: {row['check']}: {row['detail']}" + (f"\n    {row['fix']}" if row["fix"] else "")
            )
    if any(r["level"] == "fail" and r["check"] in ("system", "GPU", "disk") for r in rows) and not args.cpu:
        raise RuntimeError("MACHINE_NOT_READY: see the checks above")
    gpus = next((r["detail"].count(";") + 1 for r in rows if r["check"] == "GPU" and r["level"] == "ok"), 1)
    if gpus > 1 and not getattr(args, "gpu", None):
        worker.say(
            f"  this machine has {gpus} GPUs; this setup lends GPU 0. Lend another one with:"
            " heteroes-worker --gpu 1 setup"
        )
    worker.say("2/6 installing" if not worker.installed() else "2/6 installed already")
    if not worker.installed():
        worker.install(progress=lambda item: Progress(item["name"], item["sizeBytes"]))
    settings = worker.settings()
    if (settings.get("selfTest") or {}).get("passed"):
        worker.say("3/6 self-test passed already")
    else:
        worker.say("3/6 self-test")
        worker.selftest(device="cpu" if args.cpu else "cuda")
    if worker.settings().get("device"):
        worker.say(f"4/6 paired already with {worker.settings()['serverUrl']}")
    else:
        worker.say("4/6 pairing")
        url = confirm_lab(args.lab or ask("Lab address", DEFAULT_LAB), call, args.yes)
        gpu = getattr(args, "gpu", None)
        name = args.name or ask("Name for this GPU", socket.gethostname() + (f"-gpu{gpu}" if gpu else ""))
        host = args.host
        if args.coordinator and not host:
            # a coordinator outside the lab machine is reached on a private network (LAN or Tailscale), never by default
            host = ask("Address other machines reach this one at (LAN or Tailscale IP)", tailscale_ip())
        print(f"Make a pairing code on {url}/devices (it works once, for 10 minutes).")
        worker.join(url, read_code(), name, args.coordinator, host, call=call)
    worker.say("5/6 starting the service")
    try:
        start_service(worker)
    except RuntimeError as error:
        if error_code(error) != "SERVICE_UNAVAILABLE":
            raise
        worker.say("  " + EXPLAIN["SERVICE_UNAVAILABLE"][1])
        return
    worker.say("6/6 approval and contribution")
    try:
        summary = worker.summary(call=call)
    except LabError as error:
        if error.status != 404:
            raise
        worker.say("  this lab is older than this worker: approve and turn it ON on the lab's Devices page")
        return
    if summary["approvalStatus"] == "PENDING":
        worker.say(
            f"  waiting for an administrator to approve '{summary['displayName']}' on {worker.settings()['serverUrl']}"
            "/devices (Ctrl-C stops waiting; the service keeps running)"
        )
        try:
            summary = (
                wait_until(
                    lambda: (lambda s: s if s["approvalStatus"] != "PENDING" else None)(worker.summary(call=call)),
                    args.approval_timeout,
                    sleep=sleep,
                )
                or summary
            )
        except KeyboardInterrupt:
            worker.say("  stopped waiting; run `heteroes-worker on` once it is approved")
            return
    if summary["approvalStatus"] != "APPROVED":
        worker.say(f"  not approved yet ({summary['approvalStatus']}); run `heteroes-worker on` once it is")
        return
    if summary["contributionEnabled"]:
        worker.say("  contribution is ON")
        return
    on = args.on if args.on is not None else confirm("Turn contribution ON now (lend this GPU to the lab's runs)?")
    if not on:
        worker.say("  left OFF; `heteroes-worker on` turns it ON")
        return
    keep = args.keep if args.keep is not None else confirm("Keep it ON after this machine restarts?", default=False)
    if not wait_until(worker.agent_online, 90, every=3, sleep=sleep):
        raise RuntimeError("NOT_READY_FOR_CONTRIBUTION: the service has not reached the lab yet")
    worker.contribution(True, keep, call=call)
    worker.say("  contribution ON" + (", kept after restart" if keep else ""))


def update(worker, args, call=None, run=subprocess.run):
    settings = worker.settings()
    lab = (settings.get("serverUrl") or DEFAULT_LAB).rstrip("/")
    if settings.get("device") and not args.force:
        if (worker.summary(call=call) or {}).get("runs"):
            raise RuntimeError("UPDATE_BUSY")
    before = worker.paths()["runtime"].name
    with tempfile.TemporaryDirectory() as scratch:
        script = Path(scratch) / "install-worker.sh"
        request = urllib.request.Request(lab + "/downloads/install-worker.sh", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            script.write_bytes(response.read())
        run(
            ["bash", str(script)],
            check=True,
            env={**os.environ, "HETEROES_WORKER_HOME": str(worker.root), "HETEROES_SKIP_SETUP": "1"},
        )
    after = Worker(worker.root, worker.say, worker.service).paths()["runtime"].name
    if after == before:
        worker.say(f"already the newest runtime ({after})")
    else:
        worker.say(f"runtime {before} -> {after}; checking this GPU against the new runtime")
        # the new runtime has its own Python: the self-test runs in it, through the new launcher
        run([launcher(), "selftest"], check=True)
    if worker.service.installed():
        worker.service.restart()
        worker.say("service restarted")


def uninstall(worker, args, call=None):
    if not args.yes and not confirm(f"Remove the worker and everything in {worker.root}?", default=False):
        raise RuntimeError("CANCELLED")
    worker.service.remove()
    if worker.settings().get("device"):
        try:
            worker.forget(call=call)
        except (LabError, RuntimeError) as error:
            worker.say(f"  could not tell the lab ({error_code(error)}); an administrator can remove the device")
    keep = worker.root / "artifacts" / "coordinators"
    if args.keep_run_data and keep.exists():
        for child in worker.root.iterdir():
            if child.name != "artifacts":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
        worker.say(f"kept run data in {keep}")
    else:
        shutil.rmtree(worker.root, ignore_errors=True)
    command = Path(launcher())
    if worker.root == home() and command.is_file() and "HETEROES_WORKER_HOME" in command.read_text(errors="ignore"):
        command.unlink()  # another GPU's uninstall keeps the command the others use
    worker.say("removed")


def show_doctor(rows):
    marks = {"ok": "ok  ", "warn": "warn", "fail": "FAIL"}
    for row in rows:
        print(f"  {marks[row['level']]}  {row['check']:<10} {row['detail']}")
        if row["fix"]:
            print(f"        -> {row['fix']}")
    return 1 if any(r["level"] == "fail" for r in rows) else 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="heteroes-worker", description=__doc__.split("\n")[0])
    parser.add_argument(
        "--gpu", type=int, default=None, help="act on another GPU of this machine (each lent GPU is its own device)"
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    s = commands.add_parser("setup", help="set this machine up from scratch, or resume where setup stopped")
    s.add_argument("--lab", help=f"lab address (default: ask, suggesting {DEFAULT_LAB})")
    s.add_argument("--name", help="name shown on the lab (default: ask, suggesting the host name)")
    s.add_argument("--coordinator", action="store_true", help="also offer this machine as a coordinator")
    s.add_argument(
        "--host",
        help="with --coordinator: the LAN or Tailscale address other machines reach this one at (default: ask)",
    )
    s.add_argument("--cpu", action="store_true", help="a CPU-only coordinator (no GPU work)")
    s.add_argument("--on", action=argparse.BooleanOptionalAction, default=None, help="turn contribution ON at the end")
    s.add_argument("--keep", action=argparse.BooleanOptionalAction, default=None, help="keep it ON after restarts")
    s.add_argument("--yes", action="store_true", help="do not ask to confirm the lab")
    s.add_argument("--approval-timeout", type=int, default=1800, help="seconds to wait for approval (default 1800)")
    status = commands.add_parser("status", help="what this machine is doing now")
    status.add_argument("--json", action="store_true", help="machine-readable output")
    on = commands.add_parser("on", help="lend this GPU to the lab's runs")
    on.add_argument(
        "--keep-after-reboot",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="stay ON after this machine restarts (--no-keep-after-reboot clears it)",
    )
    off = commands.add_parser("off", help="stop lending this GPU (a run in progress continues on the other machines)")
    off.add_argument("--no-keep", action="store_true", help="also stop turning ON after restarts")
    w = commands.add_parser("watch", help="a live screen: run, generation, GPU, newest log lines (q quits)")
    w.add_argument("--every", type=float, default=2.0, help="seconds between refreshes")
    commands.add_parser("start", help="start the background service")
    commands.add_parser("stop", help="stop the background service (contribution OFF first, work drained)")
    commands.add_parser("restart", help="restart the background service")
    logs = commands.add_parser("logs", help="show the service's log")
    logs.add_argument("-f", "--follow", action="store_true", help="keep showing new lines")
    doctor = commands.add_parser("doctor", help="check driver, disk, service, network, lab and clock")
    doctor.add_argument("--lab", help="check this lab address instead of the paired one")
    u = commands.add_parser("update", help="install the lab's newest worker and restart the service")
    u.add_argument("--force", action="store_true", help="update even while this machine is in a run")
    commands.add_parser("clean", help="delete leftover downloads and old runtimes (never run data)")
    limits = commands.add_parser("limits", help="show or set this machine's limits (taken at the next service start)")
    limits.add_argument(
        "--max-chunk", type=int, choices=(16, 32, 64), help="largest prompts per generate() call this GPU may use"
    )
    limits.add_argument("--hours", help="contribute only between these local hours, e.g. 22-7 (past midnight is fine)")
    limits.add_argument("--max-temp", type=int, help="leave runs while the GPU is hotter than this (degrees C)")
    limits.add_argument("--clear", action="store_true", help="remove every limit")
    rename = commands.add_parser("rename", help="change the name shown on the lab")
    rename.add_argument("name")
    commands.add_parser("forget", help="unpair this machine from its lab")
    un = commands.add_parser("uninstall", help="remove the service, the pairing and the installed files")
    un.add_argument("--yes", action="store_true", help="do not ask to confirm")
    un.add_argument(
        "--keep-run-data", action="store_true", help="keep artifacts/ (a coordinator's ledgers and weights)"
    )
    commands.add_parser("install", help="step: download and install the pinned packages and model")
    selftest = commands.add_parser("selftest", help="step: run the numerical admission test")
    selftest.add_argument(
        "--device", choices=("cpu", "cuda"), default="cuda", help="cpu admits coordination only; cuda admits GPU work"
    )
    join = commands.add_parser("join", help="step: pair this machine with a lab (asks for the pairing code)")
    join.add_argument("lab", help=f"lab address, for example {DEFAULT_LAB}")
    join.add_argument("--name", default=os.uname().nodename, help="name shown on the lab")
    join.add_argument("--coordinator", action="store_true", help="also offer this machine as a coordinator")
    join.add_argument("--host", help="with --coordinator: the address other workers reach this machine at")
    join.add_argument("--yes", action="store_true", help="do not ask to confirm the lab")
    commands.add_parser("run", help="step: keep this device online in the foreground until Ctrl-C")
    args = parser.parse_args(argv)
    if args.gpu:
        if args.gpu < 0:
            parser.error("--gpu is a GPU index, 1 or more (GPU 0 needs no option)")
        # the self-test and the agent see only that GPU, numbered as nvidia-smi numbers it
        os.environ.update(CUDA_DEVICE_ORDER="PCI_BUS_ID", CUDA_VISIBLE_DEVICES=str(args.gpu))
    worker = Worker(  # `run` is often logged to a file
        gpu_home(args.gpu), say=lambda *values: print(*values, flush=True), service=Service(gpu=args.gpu)
    )
    try:
        if args.command == "setup":
            setup(worker, args)
            print()
            print(render_status(worker.status()))
        elif args.command == "status":
            value = worker.status()
            print(json.dumps(value, indent=2) if args.json else render_status(value))
        elif args.command == "watch":
            watch(worker, args.every)
        elif args.command == "on":
            worker.contribution(True, args.keep_after_reboot)
            print(
                "contribution ON requested"
                + {True: ", kept after restart", False: ", not kept after restart", None: ""}[args.keep_after_reboot]
            )
        elif args.command == "off":
            worker.contribution(False, False if args.no_keep else None)
            print("contribution OFF requested: a run in progress continues on the other machines")
        elif args.command in ("start", "stop", "restart"):
            if not worker.service.installed():
                if args.command == "stop":
                    raise RuntimeError("SERVICE_UNAVAILABLE")
                start_service(worker)
            else:
                getattr(worker.service, args.command)()
                print(
                    {"start": "service started", "stop": "service stopped", "restart": "service restarted"}[
                        args.command
                    ]
                )
        elif args.command == "logs":
            command = worker.service.logs_command(args.follow)
            os.execvp(command[0], command)
        elif args.command == "doctor":
            return show_doctor(worker.doctor(args.lab))
        elif args.command == "update":
            update(worker, args)
        elif args.command == "clean":
            result = worker.clean()
            print(
                f"freed {result['freedBytes'] / 1e9:.2f} GB; run data kept: {result['runDataBytes'] / 1e9:.2f} GB in"
                f" {worker.paths()['artifacts'] / 'coordinators'}"
            )
        elif args.command == "limits":
            settings = worker.settings()
            current = {} if args.clear else dict(settings.get("limits") or {})
            if args.max_chunk:
                current["maxChunk"] = args.max_chunk
            if args.hours:
                start, _, end = args.hours.partition("-")
                if not (start.isdigit() and end.isdigit() and 0 <= int(start) < 24 and 0 <= int(end) < 24):
                    raise ValueError("--hours is START-END in whole hours, for example 22-7")
                current["hours"] = [int(start), int(end)]
            if args.max_temp:
                if not 50 <= args.max_temp <= 100:
                    raise ValueError("--max-temp is between 50 and 100 degrees C")
                current["maxTemperatureC"] = args.max_temp
            worker.save_settings({**settings, "limits": current})
            print(
                json.dumps(current) if current else "no limits",
                "(restart the service to apply: heteroes-worker restart)",
            )
        elif args.command == "rename":
            print("renamed to " + worker.rename(args.name)["displayName"])
        elif args.command == "forget":
            if worker.service.installed():
                worker.service.stop()
            worker.forget()
            print("unpaired; `heteroes-worker setup` pairs it again")
        elif args.command == "uninstall":
            uninstall(worker, args)
        elif args.command == "install":
            worker.install(progress=lambda item: Progress(item["name"], item["sizeBytes"]))
            print("next: heteroes-worker selftest (or heteroes-worker setup)")
        elif args.command == "selftest":
            worker.selftest(device=args.device)
        elif args.command == "join":
            url = confirm_lab(args.lab, yes=args.yes)
            worker.join(url, read_code(), args.name, args.coordinator, args.host)
            print("an administrator must approve it; then `heteroes-worker start` and `heteroes-worker on`")
        elif args.command == "run":
            worker.run()
    except KeyboardInterrupt:
        print("\ninterrupted; `heteroes-worker setup` continues from here", file=sys.stderr)
        return 130
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        if error_code(error) == "CANCELLED":
            print("cancelled", file=sys.stderr)
            return 1
        print(explain(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
