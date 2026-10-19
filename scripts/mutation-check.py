#!/usr/bin/env python3
"""Mutation check on a scratch copy: break the code on purpose and confirm that a test notices.

    mutation-check.py --repo runtime --copy src --copy tests/ledger/test_x.py \\
        --env PYTHONPATH=src --test "python -m pytest -q tests/ledger/test_x.py" --mutants mutants.json

mutants.json is a list of {"name": "...", "file": "src/x.py", "old": "exact text, once", "new": "replacement"}.
A control run (no change) must pass; every mutant must make the test command fail (KILLED). A mutant that
passes (SURVIVED) is either an equivalent mutant (say why) or a gap in the tests (add a test). The repository
itself is never modified: each run uses a fresh copy of the listed paths under --scratch (default /tmp; copies
are removed afterwards, /tmp may be a small RAM disk). Exit status 1 if the control fails or any mutant survives.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


def run_one(repo, copies, env, command, scratch, change=None, timeout=900):
    work = Path(tempfile.mkdtemp(prefix='mutation-', dir=scratch))
    try:
        for item in copies:
            source, target = repo / item, work / item
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, symlinks=True, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
            else:
                shutil.copy2(source, target)
        if change:
            path = work / change['file']
            text = path.read_text()
            if text.count(change['old']) != 1:
                raise ValueError(f"{change['name']}: the old text must appear exactly once in {change['file']} (found {text.count(change['old'])})")
            path.write_text(text.replace(change['old'], change['new'], 1))
        result = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=timeout,
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', **env})
        tail = (result.stdout.strip().splitlines() or result.stderr.strip().splitlines() or [''])[-1]
        return result.returncode == 0, tail
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--copy', action='append', required=True, help='path inside the repository to copy (repeatable)')
    parser.add_argument('--env', action='append', default=[], help='KEY=VALUE for the test command (repeatable)')
    parser.add_argument('--test', required=True, help='the test command, run inside the copy')
    parser.add_argument('--mutants', type=Path, required=True)
    parser.add_argument('--scratch', default='/tmp')
    args = parser.parse_args(argv)
    env = dict(item.split('=', 1) for item in args.env)
    command = shlex.split(args.test)
    mutants = json.loads(args.mutants.read_text())
    ok, tail = run_one(args.repo.resolve(), args.copy, env, command, args.scratch)
    print(('control ok   ' if ok else 'CONTROL FAILED'), '|', tail)
    if not ok:
        return 1
    survived = 0
    for mutant in mutants:
        passed, tail = run_one(args.repo.resolve(), args.copy, env, command, args.scratch, change=mutant)
        survived += passed
        print(('SURVIVED    ' if passed else 'killed      '), mutant['name'], '|', tail)
    print(f'\n{len(mutants) - survived} of {len(mutants)} mutants killed.')
    return 1 if survived else 0


if __name__ == '__main__':
    sys.exit(main())
