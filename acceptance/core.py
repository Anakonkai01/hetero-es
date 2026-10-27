"""
The acceptance model: checks (commands that pass or fail), gates (what a milestone needs) and receipts (what ran where).

A check is one command with a pass/fail outcome, run on a named host ("local", "3060-wsl", "3060-native"). A gate of a
milestone M0-M6 is exactly one of:

- checked: it names the checks it needs, as "check" (local) or "check@host". It PASSES only when every one of them has
  passed on the same source tree, FAILS when any of them failed, and is NOT_RUN while some result is missing;
- DEFERRED: it cannot be done with the available hardware or conditions; the reason is stated and printed;
- OPEN: the work it needs is not done yet; what is missing is stated and printed.

Nothing is skipped silently: a gate without a result is NOT_RUN, never PASS. Results of different runs and hosts are
merged only when they were made from the same source tree (git tree id); a run from a dirty working tree is recorded
but never makes a gate pass. This module uses the standard library only, so the same code runs on every host.
"""

from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import time

RECEIPT_FORMAT = "heteroes-acceptance-receipt-v1"
MILESTONES = ("M0", "M1", "M2", "M3", "M4", "M5", "M6")
PROFILES = ("cpu", "gpu", "perf", "faults", "package", "mutation")
PASS, FAIL, NOT_RUN, DEFERRED, OPEN = "PASS", "FAIL", "NOT_RUN", "DEFERRED", "OPEN"
MIN_REASON = 12  # a reason is a sentence, not a placeholder like "todo"


@dataclass(frozen=True)
class Check:
    name: str
    profile: str
    command: tuple[str, ...]  # placeholders: {python} {runtime_python} {out} {repo} {models} {sep} {extra}
    hosts: tuple[str, ...] = ("local",)
    env: tuple[tuple[str, str], ...] = ()
    cwd: str = "."
    timeout: int = 3600
    expect: str = ""  # if set, this text must appear in the command's output for the check to pass
    gpu: bool = False


@dataclass(frozen=True)
class Gate:
    id: str
    milestone: str
    title: str
    checks: tuple[str, ...] = ()
    deferred: str = ""
    open: str = ""


@dataclass
class Result:
    name: str
    host: str
    status: str
    returncode: int | None
    seconds: float
    log: str
    log_sha256: str
    detail: str = ""


@dataclass
class Host:
    label: str
    runtime_python: str
    models: str = ""
    env: dict = field(default_factory=dict)
    extra_path: str = ""  # appended to PYTHONPATH through {extra}: test dependencies installed outside the runtime


def validate(checks, gates):
    """Refuse an inconsistent registry before anything runs."""
    names = [c.name for c in checks]
    if len(set(names)) != len(names):
        raise ValueError("duplicate check names")
    by_name = {c.name: c for c in checks}
    for check in checks:
        if check.profile not in PROFILES:
            raise ValueError(f"{check.name}: unknown profile {check.profile!r}")
        if not check.command or not check.hosts:
            raise ValueError(f"{check.name}: a check needs a command and at least one host")
    ids = [g.id for g in gates]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate gate ids")
    for gate in gates:
        if gate.milestone not in MILESTONES or not gate.id.startswith(gate.milestone + "."):
            raise ValueError(f"{gate.id}: gate id must start with its milestone M0..M6")
        kinds = [bool(gate.checks), bool(gate.deferred), bool(gate.open)]
        if sum(kinds) != 1:
            raise ValueError(f"{gate.id}: a gate is exactly one of checked, deferred or open")
        for reason in (gate.deferred, gate.open):
            if reason and len(reason.strip()) < MIN_REASON:
                raise ValueError(f"{gate.id}: a deferred or open gate states its reason in a sentence")
        for item in gate.checks:
            name, host = split_ref(item)
            if name not in by_name:
                raise ValueError(f"{gate.id}: unknown check {name!r}")
            if host not in by_name[name].hosts:
                raise ValueError(f"{gate.id}: check {name!r} does not run on {host!r}")
    missing = set(MILESTONES) - {g.milestone for g in gates}
    if missing:
        raise ValueError(f"milestones without gates: {sorted(missing)}")


def split_ref(item):
    name, _, host = item.partition("@")
    return name, host or "local"


SOURCE_PATHS = (".", ":(exclude)docs")  # documentation and committed receipts do not change what was accepted


def source_tree(repo):
    """(source id, dirty): a hash of every tracked file outside docs/ at HEAD, and whether any of them is modified or
    untracked. On a staged copy without git, the controller writes SOURCE_TREE next to the sources."""
    staged = Path(repo) / "SOURCE_TREE"
    if staged.exists():
        return staged.read_text().strip(), False
    listing = b"".join(
        line + b"\n"
        for line in subprocess.run(
            ["git", "ls-tree", "-r", "HEAD"], cwd=repo, capture_output=True, check=True
        ).stdout.splitlines()
        if not line.split(b"\t", 1)[1].startswith(b"docs/")
    )
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *SOURCE_PATHS], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    return "src-" + hashlib.sha256(listing).hexdigest(), bool(status.strip())


def expand(text, host, out, repo):
    return text.format(
        python=os.environ.get("ACCEPT_PYTHON", "python3"),
        runtime_python=host.runtime_python,
        out=str(out),
        repo=str(repo),
        models=host.models,
        sep=os.pathsep,
        extra=os.pathsep + host.extra_path if host.extra_path else "",
    )


def run_check(check, host, out, repo, runner=subprocess.run):
    """Run one check; its whole output is kept in a log file, hashed in the result."""
    folder = Path(out) / check.name
    folder.mkdir(parents=True, exist_ok=False)
    log = folder / "output.log"
    command = [expand(part, host, folder, repo) for part in check.command]
    env = {**os.environ, **host.env, **{k: expand(v, host, folder, repo) for k, v in check.env}}
    if not check.gpu:
        env["CUDA_VISIBLE_DEVICES"] = ""
    started = time.monotonic()
    detail = ""
    with log.open("w") as handle:
        handle.write("$ " + shlex.join(command) + "\n")
        handle.flush()
        try:
            completed = runner(
                command,
                cwd=Path(repo) / check.cwd,
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=check.timeout,
            )
            returncode = completed.returncode
        except subprocess.TimeoutExpired:
            returncode, detail = None, f"timed out after {check.timeout} s"
        except OSError as error:
            returncode, detail = None, f"could not start: {error}"
    text = log.read_text(errors="replace")
    ok = returncode == 0 and (not check.expect or check.expect in text)
    if returncode == 0 and not ok:
        detail = f"expected output {check.expect!r} not found"
    elif returncode not in (0, None):
        detail = f"exit status {returncode}"
    return Result(
        check.name,
        host.label,
        PASS if ok else FAIL,
        returncode,
        round(time.monotonic() - started, 3),
        str(log),
        hashlib.sha256(log.read_bytes()).hexdigest(),
        detail,
    )


def machine():
    info = {"platform": platform.platform(), "python": platform.python_version(), "node": platform.node()}
    try:
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        info["gpus"] = [line.strip() for line in gpu.stdout.splitlines() if line.strip()] if gpu.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        info["gpus"] = []
    return info


def write_receipt(path, *, tree, dirty, commit, host, profiles, results, started):
    receipt = {
        "format": RECEIPT_FORMAT,
        "tree": tree,
        "dirty": dirty,
        "commit": commit,
        "host": host,
        "profiles": list(profiles),
        "machine": machine(),
        "started": started,
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "results": [asdict(r) for r in results],
    }
    Path(path).write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def load_receipts(paths):
    receipts = []
    for path in paths:
        receipt = json.loads(Path(path).read_text())
        if receipt.get("format") != RECEIPT_FORMAT:
            raise ValueError(f"{path}: not an acceptance receipt")
        receipts.append(receipt)
    return receipts


def merge(receipts, tree):
    """Results of `tree` by (check, host); a later receipt replaces an earlier one. Dirty runs never count."""
    merged = {}
    for receipt in sorted(receipts, key=lambda r: r["finished"]):
        if receipt["tree"] != tree or receipt["dirty"]:
            continue
        for result in receipt["results"]:
            merged[(result["name"], result["host"])] = result
    return merged


def evaluate(gates, merged):
    """Status of every gate, with the evidence it rests on."""
    rows = []
    for gate in gates:
        if gate.deferred:
            rows.append((gate, DEFERRED, gate.deferred, []))
            continue
        if gate.open:
            rows.append((gate, OPEN, gate.open, []))
            continue
        evidence, statuses = [], []
        for item in gate.checks:
            result = merged.get(split_ref(item))
            statuses.append(NOT_RUN if result is None else result["status"])
            evidence.append((item, NOT_RUN if result is None else result["status"]))
        status = FAIL if FAIL in statuses else NOT_RUN if NOT_RUN in statuses else PASS
        rows.append((gate, status, "", evidence))
    return rows


def milestone_status(rows):
    """FAIL > NOT_RUN > OPEN > PASS; deferred gates do not block, but are always listed."""
    result = {}
    for milestone in MILESTONES:
        statuses = [status for gate, status, _, _ in rows if gate.milestone == milestone]
        for candidate in (FAIL, NOT_RUN, OPEN):
            if candidate in statuses:
                result[milestone] = candidate
                break
        else:
            result[milestone] = PASS + (" (with deferred gates)" if DEFERRED in statuses else "")
    return result


def report(rows, tree, receipts):
    lines = [
        "# Acceptance status",
        "",
        f"Source tree `{tree}`. Generated by `scripts/accept.py report`; do not edit by hand.",
        "",
        "| Milestone | Status |",
        "| --- | --- |",
    ]
    lines += [f"| {m} | {s} |" for m, s in milestone_status(rows).items()]
    for milestone in MILESTONES:
        lines += ["", f"## {milestone}", "", "| Gate | Status | Evidence or reason |", "| --- | --- | --- |"]
        for gate, status, reason, evidence in rows:
            if gate.milestone != milestone:
                continue
            what = reason or ", ".join(f"`{item}` {result}" for item, result in evidence)
            lines.append(f"| {gate.id} — {gate.title} | **{status}** | {what} |")
    used = [r for r in receipts if r["tree"] == tree and not r["dirty"]]
    lines += ["", "## Receipts", ""]
    lines += [f"- {r['host']} {'/'.join(r['profiles'])}, finished {r['finished']}" for r in used] or ["- none"]
    return "\n".join(lines) + "\n"
