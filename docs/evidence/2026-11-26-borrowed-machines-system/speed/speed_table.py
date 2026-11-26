import collections, json, statistics, sys
from pathlib import Path
RUNS = Path.home() / ".local/share/heteroes-worker/agent-state/runs"
CFG = [("1 GPU (5070 Ti)", "6131a0ade3834556b9051407c0516bd3"), ("2 GPU (2×5070 Ti)", "bc2b12ef39024a3f8e41ae96f0323b0f"),
       ("3 GPU (2×5070 Ti + 3060)", "9ce75c6f88ae49039e31ec46402e0874")]
out = {}
for label, run in CFG:
    first = collections.defaultdict(dict)
    for line in (RUNS / run / "events.jsonl").read_text().splitlines():
        e = json.loads(line)
        if "generation" in e:
            first[e["generation"]].setdefault(e["event"], e["t"])
    steps = collections.defaultdict(list)
    for g, at in first.items():
        after = first.get(g + 1, {})
        need = ("generation_open", "generation_complete", "update_applied", "generation_done")
        if "validation_completed" in at or "generation_open" not in after or not all(k in at for k in need):
            continue
        steps["score"].append(at["generation_complete"] - at["generation_open"])
        steps["update"].append(at["update_applied"] - at["generation_complete"])
        steps["publish"].append(at["generation_done"] - at["update_applied"])
        steps["backup_open"].append(after["generation_open"] - at["generation_done"])
        steps["total"].append(after["generation_open"] - at["generation_open"])
    out[label] = {"run": run, "generations": len(steps["total"]),
                  **{k: {"median": round(statistics.median(v), 1), "mean": round(statistics.mean(v), 1),
                         "min": round(min(v), 1), "max": round(max(v), 1)} for k, v in steps.items()}}
one = out[CFG[0][0]]["total"]
for label in out:
    t = out[label]["total"]
    out[label]["speedupMedian"] = round(one["median"] / t["median"], 2)
    out[label]["speedupMean"] = round(one["mean"] / t["mean"], 2)
print(json.dumps(out, indent=1, ensure_ascii=False))
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
