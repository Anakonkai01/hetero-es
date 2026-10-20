"""
A researcher's Python function (a scorer or a coefficient rule) in a child process with a time limit, on the coordinator.

The owner opened Python rewards on the web lab (2026-10-20, ADR-008 "Owner answers"): the code runs with the
permissions of the coordinator's user, so this is NOT a security boundary. What the child process gives: a hang or a
crash of the researcher's code becomes a loud failure (`error`, for example `ScorerError`), never a reward, and it
cannot corrupt the coordinator's memory. Workers never run researcher code.

Protocol: one JSON line per call on the child's stdin ({"args": [...]}), one JSON line back ({"ok": value} or
{"error": text}) on a private copy of its stdout; what the code prints goes to stderr.
"""

import json
import os
from pathlib import Path
import selectors
import subprocess
import sys


class ChildFunction:
    def __init__(self, path, function, *, timeout=300.0, error=RuntimeError):
        self.path, self.function, self.timeout, self.error = Path(path), function, timeout, error
        self.process = None

    def _start(self):
        self.process = subprocess.Popen(
            [sys.executable, "-m", "heteroes.v3.sandbox", str(self.path), self.function],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,  # the coordinator's log
            cwd=self.path.parent,
            # this runtime, by absolute path: the child runs in the code's folder
            # without the coordinator's credentials (HETEROES_TOKEN and the like)
            env={k: v for k, v in os.environ.items() if not k.startswith("HETEROES_")}
            | {"PYTHONPATH": str(Path(__file__).resolve().parents[2])},
            text=True,
        )

    def _fail(self, message):
        self.close()
        raise self.error(f"{self.path.name}:{self.function} {message}")

    def __call__(self, *args):
        if self.process is None or self.process.poll() is not None:
            self._start()
        try:
            self.process.stdin.write(json.dumps({"args": list(args)}) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError):
            self._fail("ended before it was called")
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            if not selector.select(self.timeout):
                self._fail(f"took more than {self.timeout:g} s")
        line = self.process.stdout.readline()
        if not line:
            self._fail(f"ended (exit code {self.process.wait()})")
        reply = json.loads(line)
        if "error" in reply:
            raise self.error(f"{self.path.name}:{self.function} failed: {reply['error']}")
        return reply["ok"]

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait()
            self.process = None


def _plain(value):
    """Numbers and sequences of numbers as JSON can carry them (a numpy array becomes a list of Python floats)."""
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def main():
    path, function = sys.argv[1], sys.argv[2]
    replies = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)  # the researcher's prints go to stderr, never into the replies
    sys.stdout = sys.stderr
    from heteroes.v3.run import load_python_scorer

    loaded, _ = load_python_scorer(path, function)
    for line in sys.stdin:
        try:
            reply = {"ok": _plain(loaded(*json.loads(line)["args"]))}
            text = json.dumps(reply)
        except Exception as error:  # noqa: BLE001 - any failure of the researcher's code is reported, not raised here
            text = json.dumps({"error": f"{type(error).__name__}: {error}"})
        replies.write(text + "\n")
        replies.flush()


if __name__ == "__main__":
    main()
