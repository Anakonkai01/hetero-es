#!/usr/bin/env python3
"""Every runtime Python file in the packaged Linux Worker and in the SDK wheel inside the Server must be the bytes of
`git archive HEAD runtime/src`. Run after `scripts/build-apps.sh --check <dir>` on a clean source tree.
Documentation edits and newly kept acceptance receipts do not change the packaged runtime identity.

    python3 acceptance/probes/package_bytes.py <build dir>
"""

import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from acceptance.core import source_tree  # noqa: E402


def verify_packages(root, repo):
    root, repo = Path(root), Path(repo)
    _, dirty = source_tree(repo)
    if dirty:
        raise ValueError("the source tree is not clean: package bytes would not identify a commit")
    committed = subprocess.check_output(["git", "archive", "HEAD", "runtime/src"], cwd=repo)
    with tarfile.open(fileobj=io.BytesIO(committed)) as t:
        expected = {
            m.name.removeprefix("runtime/src/"): t.extractfile(m).read()
            for m in t.getmembers()
            if m.isfile() and m.name.endswith(".py")
        }
    with tarfile.open(root / "worker/linux-unpacked/resources/worker/runtime.tar.gz") as t:
        worker = {
            m.name.removeprefix("src/"): t.extractfile(m).read()
            for m in t.getmembers()
            if m.isfile() and m.name.startswith("src/") and m.name.endswith(".py")
        }
    with tarfile.open(root / "server/linux-unpacked/resources/server/runtime.tar.gz") as t:
        names = [n for n in t.getnames() if n.startswith("web/notebooks/") and n.endswith(".whl")]
        if len(names) != 1:
            raise ValueError(f"expected one SDK wheel in the Server archive, found {names}")
        wheel = t.extractfile(names[0]).read()
    with zipfile.ZipFile(io.BytesIO(wheel)) as z:
        sdk = {n: z.read(n) for n in z.namelist() if n.startswith("heteroes/") and n.endswith(".py")}
    for label, actual in (("Worker", worker), ("Server SDK", sdk)):
        if actual != expected:
            missing, extra = sorted(set(expected) - set(actual)), sorted(set(actual) - set(expected))
            changed = sorted(n for n in set(expected) & set(actual) if expected[n] != actual[n])
            raise ValueError(f"{label} differs: missing {missing[:5]}, extra {extra[:5]}, changed {changed[:5]}")
    return len(expected)


if __name__ == "__main__":
    try:
        count = verify_packages(sys.argv[1], REPO)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print(f"PACKAGE BYTES OK: {count} runtime Python files in the Worker and the Server SDK")
