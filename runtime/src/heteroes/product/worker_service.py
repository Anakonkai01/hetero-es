"""`heteroes-worker` as a systemd user service: it starts when the machine boots (lingering user), restarts after a
crash, and logs to the journal. Stopping it is the same as Ctrl-C on `run`: contribution OFF, owned work drained."""

import getpass
import os
from pathlib import Path
import shlex
import subprocess

UNIT = "heteroes-worker.service"


def unit_name(gpu=None):
    """One service per lent GPU: GPU 0 keeps the plain name (and every existing install)."""
    return UNIT if not gpu else f"heteroes-worker-gpu{gpu}.service"


def unit_path(gpu=None):
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "systemd/user" / unit_name(gpu)


def unit_text(command, home, gpu=None):
    def quoted(value):
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

    return f"""[Unit]
Description=HeteroES Worker (lends this GPU to a HeteroES lab)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart={quoted(command)}{"" if not gpu else f" --gpu {gpu}"} run
Environment={quoted("HETEROES_WORKER_HOME=" + str(home))}{"" if not gpu else chr(10) + f"Environment=CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES={gpu}"}
Restart=on-failure
RestartSec=15
# like Ctrl-C on `run`: contribution OFF, then wait until the work this machine owns has stopped (only the agent gets the
# signal; it stops its own workers and coordinator)
KillSignal=SIGINT
KillMode=mixed
TimeoutStopSec=600

[Install]
WantedBy=default.target
"""


class Service:
    def __init__(self, run=subprocess.run, gpu=None):
        self._run = run
        self.gpu = gpu
        self.unit = unit_name(gpu)

    def systemctl(self, *args, check=True):
        return self._run(["systemctl", "--user", *args], capture_output=True, text=True, check=check)

    def available(self):
        try:
            return self.systemctl("show-environment", check=False).returncode == 0
        except FileNotFoundError:
            return False

    def installed(self):
        return unit_path(self.gpu).is_file()

    def install(self, command, home):
        """Write and enable the unit; returns the shell command the owner still has to run for boot start, or None."""
        path = unit_path(self.gpu)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(unit_text(command, home, self.gpu))
        self.systemctl("daemon-reload")
        self.systemctl("enable", self.unit)
        return self.ensure_linger()

    def ensure_linger(self):
        user = getpass.getuser()
        try:
            shown = self._run(["loginctl", "show-user", user, "-p", "Linger"], capture_output=True, text=True)
            if shown.stdout.strip() == "Linger=yes":
                return None
            if self._run(["loginctl", "enable-linger", user], capture_output=True, text=True).returncode == 0:
                return None
        except FileNotFoundError:
            pass
        # without linger a user service only runs while that user is logged in
        return "sudo loginctl enable-linger " + shlex.quote(user)

    def start(self):
        self.systemctl("start", self.unit)

    def stop(self):
        self.systemctl("stop", self.unit)

    def restart(self):
        self.systemctl("restart", self.unit)

    def active(self):
        try:
            return self.systemctl("is-active", self.unit, check=False).stdout.strip() == "active"
        except FileNotFoundError:
            return False

    def enabled(self):
        try:
            return self.systemctl("is-enabled", self.unit, check=False).stdout.strip() == "enabled"
        except FileNotFoundError:
            return False

    def remove(self):
        if not self.installed():
            return
        self.systemctl("disable", "--now", self.unit, check=False)
        unit_path(self.gpu).unlink()
        self.systemctl("daemon-reload", check=False)

    def logs_command(self, follow=False, lines=200):
        return ["journalctl", "--user", "-u", self.unit, "-n", str(lines), "--no-pager", *(["-f"] if follow else [])]
