#!/usr/bin/env python3
"""Prove that the test fixtures copied from the evidence archive are byte-identical to the archived files.

    python3 scripts/check-archive-fixtures.py

`runtime/tests/fixtures/archive/<path>` and `backend/tests/fixtures/archive/<path>` are copies of `<path>` on the
`evidence-archive` branch; COPIES maps the few copies kept elsewhere. Exit 1 on any difference or missing source.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRANCH = "evidence-archive"
ROOTS = ["runtime/tests/fixtures/archive", "backend/tests/fixtures/archive"]
COPIES = {
    "runtime/references/desktop-v1-reference.json": "runtime/artifacts/regression/2026-10-10-m3-native-profile/reference.json"
}


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


def main():
    pairs = dict(COPIES)
    for root in ROOTS:
        for file in sorted((REPO / root).rglob("*")):
            if file.is_file():
                pairs[file.relative_to(REPO).as_posix()] = file.relative_to(REPO / root).as_posix()
    bad = 0
    for copy, source in pairs.items():
        archived = git("rev-parse", f"{BRANCH}:{source}")
        local = git("hash-object", copy)
        same = archived.returncode == 0 and archived.stdout.strip() == local.stdout.strip()
        bad += not same
        print(("OK   " if same else "DIFF ") + f"{copy} <- {BRANCH}:{source}")
    print(f"{len(pairs) - bad}/{len(pairs)} fixtures identical to the archive")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
