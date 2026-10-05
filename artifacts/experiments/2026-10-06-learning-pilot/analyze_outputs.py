import json, re, sys
from heteroes.eval.workload import extract_integer
d = json.load(open(sys.argv[1])); held, a, b = d["held"], d["start"], d["end"]
ok = lambda t, e: int(extract_integer(t) == e["answer"])
only_int = lambda t: bool(re.fullmatch(r"-?\d+", t.strip()))
n = len(held)
print(f"outputs that are only an integer: start {sum(only_int(t) for t in a)}/{n}, end {sum(only_int(t) for t in b)}/{n}")
print(f"mean length of the output text (characters): start {sum(len(t) for t in a)/n:.1f}, end {sum(len(t) for t in b)/n:.1f}")
print(f"correct: start {sum(ok(t,e) for t,e in zip(a,held))}/{n}, end {sum(ok(t,e) for t,e in zip(b,held))}/{n}")
gained = [(e, x, y) for e, x, y in zip(held, a, b) if not ok(x, e) and ok(y, e)]
lost = [(e, x, y) for e, x, y in zip(held, a, b) if ok(x, e) and not ok(y, e)]
fmt_only = [g for g in gained if extract_integer(g[1]) == g[0]["answer"]]
print(f"gained {len(gained)}, lost {len(lost)}")
# a gained question where the START text was already 'wrong number' means the arithmetic changed; if the start text had no integer or extra trailing numbers it may be format
no_int = sum(extract_integer(g[1]) is None for g in gained); wrong_int = len(gained) - no_int
print(f"of the gained questions, the start output had NO integer in {no_int} and a WRONG integer in {wrong_int}")
print("examples gained (question | expected | start -> end):")
for e, x, y in gained[:8]: print(f"  {e['question']:28} | {e['answer']:6} | {x!r} -> {y!r}")
print("examples lost:")
for e, x, y in lost[:5]: print(f"  {e['question']:28} | {e['answer']:6} | {x!r} -> {y!r}")
changed = sum(1 for x, y in zip(a, b) if x != y)
print(f"output texts that changed at all: {changed}/{n}")
