#!/usr/bin/env python3
"""
HeteroES acceptance: run the checks of milestones M0-M6 and report every gate as PASS / FAIL / NOT_RUN / DEFERRED / OPEN.

    scripts/accept.py list                         # checks, gates and their hosts
    scripts/accept.py run cpu gpu                  # run these profiles here (host "local"), write a receipt
    scripts/accept.py run gpu --only strict-parity-qwen
    scripts/accept.py remote 3060-wsl gpu          # stage this commit on a remote host, run there, fetch the receipt
    scripts/accept.py report --write               # merge the committed receipts, write docs/acceptance/STATUS.md

Profiles: cpu, gpu, perf, faults, package, mutation (`all` = every profile). GPU checks need HETEROES_GPU_ACCEPTANCE=1
set by the caller, as every GPU run in this repository does. A run writes `<out>/receipt.json` and one log per check;
`--keep` also copies the receipt into docs/acceptance/receipts/ for the report. Receipts of a dirty source tree are
kept but never make a gate pass. See acceptance/core.py for the rules.
"""

import argparse
import base64
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from acceptance import core  # noqa: E402
from acceptance.hosts import HOSTS, POWERSHELL, REMOTE_ROOT, SSH, WINDOWS_ROOT  # noqa: E402
from acceptance.registry import CHECKS, GATES  # noqa: E402

RECEIPTS = REPO / "docs" / "acceptance" / "receipts"
STATUS = REPO / "docs" / "acceptance" / "STATUS.md"
# What a remote host needs: the runtime and its tests, the acceptance system itself and this script.
STAGED = [
    "runtime/src",
    "runtime/tests",
    "runtime/scripts",
    "runtime/pyproject.toml",
    "acceptance",
    "scripts/accept.py",
]
STAGED += ["scripts/mutation-check.py"]


def profiles(names):
    chosen = core.PROFILES if "all" in names else tuple(names)
    unknown = set(chosen) - set(core.PROFILES)
    if unknown:
        raise SystemExit(f"unknown profiles {sorted(unknown)}; choose from {core.PROFILES} or all")
    return chosen


def command_list(_):
    for check in CHECKS:
        print(f"{check.profile:9} {check.name:28} hosts={','.join(check.hosts)}")
    print()
    for gate in GATES:
        kind = "checks: " + ", ".join(gate.checks) if gate.checks else ("DEFERRED: " if gate.deferred else "OPEN: ")
        print(f"{gate.id:22} {kind}{gate.deferred or gate.open}")


def command_run(args):
    host = HOSTS[args.host]
    chosen = profiles(args.profiles)
    selected = [c for c in CHECKS if c.profile in chosen and host.label in c.hosts]
    if args.only:
        selected = [c for c in selected if c.name in args.only]
        missing = set(args.only) - {c.name for c in selected}
        if missing:
            raise SystemExit(f"not runnable here with these profiles: {sorted(missing)}")
    if any(c.gpu for c in selected) and os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        raise SystemExit("GPU checks selected: set HETEROES_GPU_ACCEPTANCE=1 (explicit GPU opt-in)")
    tree, dirty = core.source_tree(REPO)
    out = Path(args.out or REPO / ".scratch" / "accept" / time.strftime(f"%Y%m%d-%H%M%S-{host.label}")).resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    print(f"source {tree}{' (DIRTY: results will not count)' if dirty else ''}; host {host.label}; out {out}")
    results = []
    for check in selected:
        print(f"=== {check.name}", flush=True)
        result = core.run_check(check, host, out, REPO)
        results.append(result)
        print(f"{result.status} {check.name} ({result.seconds:.0f} s){' — ' + result.detail if result.detail else ''}")
    commit = (
        (REPO / "SOURCE_COMMIT").read_text().strip() if (REPO / "SOURCE_COMMIT").exists() else git("rev-parse", "HEAD")
    )
    receipt = core.write_receipt(
        out / "receipt.json",
        tree=tree,
        dirty=dirty,
        commit=commit,
        host=host.label,
        profiles=chosen,
        results=results,
        started=started,
    )
    if args.keep:
        keep(out / "receipt.json", receipt)
    failed = [r.name for r in results if r.status != core.PASS]
    print(
        f"{len(results) - len(failed)}/{len(results)} checks passed"
        + (f"; failed: {', '.join(failed)}" if failed else "")
    )
    return 1 if failed else 0


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()


def keep(path, receipt):
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    stamp = receipt["finished"].replace(":", "")[:15]
    target = RECEIPTS / f"{stamp}-{receipt['host']}-{'-'.join(receipt['profiles'])}.json"
    shutil.copyfile(path, target)
    print(f"kept {target.relative_to(REPO)}")


def stage_archive(tree):
    """The committed bytes of the staged paths (git archive HEAD), plus the identity files."""
    data = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", *STAGED], cwd=REPO, capture_output=True, check=True
    )
    buffer = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(data.stdout)) as source, tarfile.open(fileobj=buffer, mode="w:gz") as target:
        for member in source.getmembers():
            target.addfile(member, source.extractfile(member) if member.isfile() else None)
        for name, text in (("SOURCE_TREE", tree), ("SOURCE_COMMIT", git("rev-parse", "HEAD"))):
            item = tarfile.TarInfo(name)
            item.size = len(text.encode()) + 1
            target.addfile(item, io.BytesIO(text.encode() + b"\n"))
    return buffer.getvalue()


def command_remote(args):
    if args.host == "local":
        raise SystemExit("use `run` for the local host")
    tree, dirty = core.source_tree(REPO)
    if dirty:
        raise SystemExit("commit first: a remote host runs the committed sources (git archive HEAD)")
    chosen = profiles(args.profiles)
    name = f"heteroes-accept-{tree[4:16]}-{time.strftime('%Y%m%d-%H%M%S')}"
    root = f"{REMOTE_ROOT[args.host]}/{name}"
    subprocess.run(
        [*SSH, f"mkdir -p {shlex.quote(root)} && tar -xzf - -C {shlex.quote(root)}"],
        input=stage_archive(tree),
        check=True,
    )
    host = HOSTS[args.host]
    run = ["run", *chosen, "--host", args.host, "--out", "results"] + sum((["--only", o] for o in args.only or []), [])
    if args.host == "3060-native":
        windows = WINDOWS_ROOT + "\\" + name
        script = (
            '$env:HETEROES_GPU_ACCEPTANCE="1"; $ProgressPreference="SilentlyContinue"; '
            f"Set-Location '{windows}'; $env:ACCEPT_PYTHON='{host.runtime_python}'; "
            f"& '{host.runtime_python}' -B scripts\\accept.py {' '.join(run)}; exit $LASTEXITCODE"
        )
        remote = (
            f"{POWERSHELL} -NoProfile -NonInteractive -EncodedCommand "
            + base64.b64encode(script.encode("utf-16-le")).decode()
        )
    else:
        env = " ".join(f"{k}={shlex.quote(v)}" for k, v in host.env.items())
        remote = (
            f"cd {shlex.quote(root)} && HETEROES_GPU_ACCEPTANCE=1 ACCEPT_PYTHON={shlex.quote(host.runtime_python)} {env} "
            f"{shlex.quote(host.runtime_python)} -B scripts/accept.py {shlex.join(run)}"
        )
    print(f"staged {tree} at {args.host}:{root}", flush=True)
    status = subprocess.run([*SSH, remote]).returncode
    out = Path(args.out or REPO / ".scratch" / "accept" / f"{name}-{args.host}").resolve()
    out.mkdir(parents=True, exist_ok=False)
    fetched = subprocess.run([*SSH, f"cd {shlex.quote(root)} && tar -czf - results"], capture_output=True, check=True)
    with tarfile.open(fileobj=io.BytesIO(fetched.stdout)) as archive:
        archive.extractall(out, filter="data")
    receipt = json.loads((out / "results" / "receipt.json").read_text())
    if receipt["tree"] != tree:
        raise SystemExit("the remote receipt is for another source tree")
    print(f"fetched {out}")
    if args.keep:
        keep(out / "results" / "receipt.json", receipt)
    return status


def command_report(args):
    paths = args.receipts or sorted(RECEIPTS.glob("*.json"))
    receipts = core.load_receipts(paths)
    tree = args.tree or core.source_tree(REPO)[0]
    rows = core.evaluate(GATES, core.merge(receipts, tree))
    text = core.report(rows, tree, receipts)
    if args.write:
        STATUS.parent.mkdir(parents=True, exist_ok=True)
        STATUS.write_text(text)
        print(f"wrote {STATUS.relative_to(REPO)}")
    else:
        print(text)
    return 0


def main():
    core.validate(CHECKS, GATES)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list").set_defaults(func=command_list)
    run = commands.add_parser("run")
    run.add_argument("profiles", nargs="+")
    run.add_argument("--host", default="local", choices=sorted(HOSTS))
    run.add_argument("--only", action="append")
    run.add_argument("--out")
    run.add_argument("--keep", action="store_true")
    run.set_defaults(func=command_run)
    remote = commands.add_parser("remote")
    remote.add_argument("host", choices=sorted(h for h in HOSTS if h != "local"))
    remote.add_argument("profiles", nargs="+")
    remote.add_argument("--only", action="append")
    remote.add_argument("--out")
    remote.add_argument("--keep", action="store_true")
    remote.set_defaults(func=command_remote)
    report = commands.add_parser("report")
    report.add_argument("receipts", nargs="*", type=Path)
    report.add_argument("--tree")
    report.add_argument("--write", action="store_true")
    report.set_defaults(func=command_report)
    args = parser.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
