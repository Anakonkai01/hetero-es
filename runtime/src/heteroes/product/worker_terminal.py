"""What the Linux worker shows and asks in a terminal: error explanations, the status screen and prompts."""

import getpass
import subprocess
import sys
import time
import urllib.error

from .worker_lab import DEFAULT_LAB, LabError


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
