"""Apply one textual mutant to a scratch copy, run the given tests, restore. Usage: mutate.py ROOT MUTANTS.json TESTS..."""
import json, pathlib, subprocess, sys, os
root = pathlib.Path(sys.argv[1]); mutants = json.load(open(sys.argv[2])); tests = sys.argv[3:]
env = dict(os.environ, CUDA_VISIBLE_DEVICES="", PYTHONPATH=str(root / "src"))
py = os.path.expanduser("~/miniforge3/envs/heteroes-match/bin/python")
results = []
for m in mutants:
    f = root / m["file"]; original = f.read_text()
    assert original.count(m["old"]) == 1, (m["name"], original.count(m["old"]))
    f.write_text(original.replace(m["old"], m["new"]))
    try:
        r = subprocess.run([py, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests], cwd=root, env=env, capture_output=True, text=True)
    finally:
        f.write_text(original)
    results.append({"name": m["name"], "killed": r.returncode != 0})
    print(m["name"], "KILLED" if r.returncode else "SURVIVED", flush=True)
json.dump(results, open(sys.argv[2].replace(".json", "-results.json"), "w"), indent=1)
