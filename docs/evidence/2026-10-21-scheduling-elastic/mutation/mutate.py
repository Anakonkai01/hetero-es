"""Apply one textual mutant at a time to a scratch copy of runtime/, run the given tests, restore the file.

Usage: mutate.py ROOT MUTANTS.json TESTS...   (ROOT is a full copy of runtime/: tests start subprocesses from scripts/)
A mutant whose tests do not finish in TIMEOUT seconds is reported as a hang; it is not counted as killed.
"""

import json
import os
import pathlib
import subprocess
import sys

TIMEOUT = 1200
root = pathlib.Path(sys.argv[1])
mutants = json.load(open(sys.argv[2]))
tests = sys.argv[3:]
env = dict(os.environ, CUDA_VISIBLE_DEVICES="", PYTHONPATH=str(root / "src"))
python = os.path.expanduser("~/miniforge3/envs/heteroes-match/bin/python")
results = []
for mutant in mutants:
    path = root / mutant["file"]
    original = path.read_text()
    assert original.count(mutant["old"]) == 1, (mutant["name"], original.count(mutant["old"]))
    path.write_text(original.replace(mutant["old"], mutant["new"]))
    try:
        run = subprocess.run(
            [python, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        outcome = "KILLED" if run.returncode else "SURVIVED"
    except subprocess.TimeoutExpired:
        outcome = "HANG"
    finally:
        path.write_text(original)
    results.append({"name": mutant["name"], "outcome": outcome, "killed": outcome == "KILLED"})
    print(mutant["name"], outcome, flush=True)
json.dump(results, open(sys.argv[2].replace(".json", "-results.json"), "w"), indent=1)
