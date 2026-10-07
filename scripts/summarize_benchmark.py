#!/usr/bin/env python3
"""
Summarize the runs of `scripts/run_benchmark.py` (the numbers of G4/G5 come from this script, not from a scratch one).

    python scripts/summarize_benchmark.py <dir with n<N>-<condition>-r<k> runs> [--prediction prediction-n8.json] [--out summary.json]

Per run: the time of a generation (the coordinator's `total_seconds`: candidates + update + publication) with its three parts, who
ran how many candidates, how long each worker was busy (rollout etc.), synchronizing or idle, and the coordination overhead.
Per condition: the mean and the spread of T over the repeats, ClusterBenefit = T(B0) / T(condition) and DeltaT = T(B0) - T(condition)
(MASTER section 8; B0 is the fastest worker alone). The headline is the STEADY-STATE T: generation 0 is left out because the remote
worker does not synchronize in it (it already holds the parent), so including it flatters a cluster; the figures with generation 0 are
kept as `T_mean` for comparison with G4/G5. The unit of replication is a run, and the intervals are 95 % Student-t intervals over
runs (`heteroes.benchmark_stats`), so with 3 runs they are wide on purpose. The runs of one N must have given exactly the same rewards and weights hashes
(the candidates and their seeds are the same, whoever evaluates them): `consistent` says whether they did.
"""
import argparse
import json
import re
import statistics
import sys
from pathlib import Path

from heteroes.benchmark_stats import mean_ci, ratio_ci

RUN = re.compile(r"n(\d+)-([A-Z0-9]+)-r(\d+)")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize_run(path: Path) -> dict:
    record = json.loads((path / "run.json").read_text(encoding="utf-8"))
    result = {"run": path.name, "outcome": record["outcome"]}
    summary_file = path / "coordinator" / "summary.json"
    if record["outcome"] != "ok" or not summary_file.exists():
        return result
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    generations = summary["generations"]
    totals = [g["total_seconds"] for g in generations]
    result.update({
        "generations": len(generations), "generation_seconds": totals,
        "T_mean": statistics.mean(totals), "T_mean_after_first": statistics.mean(totals[1:]) if len(totals) > 1 else None,
        "wait_mean": statistics.mean(g["wait_seconds"] for g in generations),
        "update_mean": statistics.mean(g["update_seconds"] for g in generations),
        "publish_mean": statistics.mean(g["publish_seconds"] for g in generations),
        "rewards": [g["rewards"] for g in generations], "weights": [g["child_sha256"] for g in generations],
        "final_sha256": summary["final_weights_sha256"], "internal_errors": summary["internal_errors"],
        "policy": summary["args"].get("policy"), "workers": {},
    })
    wait_total = sum(g["wait_seconds"] for g in generations)
    result["first_generation_owner"] = {}                 # candidate index -> the worker that evaluated it, generation 0
    for log in sorted(path.glob("worker-*.jsonl")):
        events = read_jsonl(log)
        steps = [e for e in events if e["event"] == "step" and e["kind"] in ("COMMITTED", "ALREADY_COMMITTED")]
        for e in steps:
            parts = e["candidate_id"].split("/")                      # <experiment>/g<generation>/c<index>
            if parts[-2] == "g0":
                result["first_generation_owner"][int(parts[-1][1:])] = log.stem.removeprefix("worker-")
        busy = sum(e["timing"]["total"] for e in steps if e.get("timing"))
        step_seconds = sum(e["step_seconds"] for e in steps)
        syncs = [e for e in events if e["event"] == "sync"]
        sync = sum(e["transfer_seconds"] + e["load_seconds"] + e["rehash_seconds"] for e in syncs)
        start = next(e for e in events if e["event"] == "worker_start")
        result["workers"][log.stem.removeprefix("worker-")] = {
            "jobs": len(steps), "busy_seconds": busy, "sync_seconds": sync, "syncs": len(syncs),
            "coordination_seconds": step_seconds - busy, "idle_seconds": wait_total - busy - sync,
            "chunk": start["args"].get("chunk"), "gpu": start["environment"]["gpu_name"],
            "failures": sum(1 for e in events if e["event"] == "step" and e["kind"] in ("FAILURE_REPORTED", "REFUSED", "QUARANTINED"))}
    return result


def predicted(prediction: dict | None, condition: str, workers: set) -> float | None:
    if prediction is None:
        return None
    both = len(workers) == 2
    variants = prediction["variants"]
    table = {"B0": ("common_chunk_1", "B3_GREEDY_DYNAMIC", "alone"), "B3": ("common_chunk_1", "B3_GREEDY_DYNAMIC", "both"),
             "B2": ("common_chunk_1", "B2_STATIC_PROPORTIONAL", "both"),
             "H0": ("per_worker_chunk", "B3_GREEDY_DYNAMIC", "both" if both else "alone")}
    if condition not in table:
        return None
    variant, policy, who = table[condition]
    return variants[variant]["predictions"][policy][who]["total_seconds"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory")
    parser.add_argument("--prediction", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--n", type=int, default=None, help="only the runs with this number of candidates (the prediction file is for one N)")
    args = parser.parse_args(argv)
    directory = Path(args.directory)
    prediction = None if args.prediction is None else json.loads(Path(args.prediction).read_text(encoding="utf-8"))

    runs = {}
    for path in sorted(directory.iterdir()):
        match = RUN.fullmatch(path.name)
        if match and path.is_dir() and (path / "run.json").exists() and (args.n is None or int(match.group(1)) == args.n):
            runs[path.name] = (int(match.group(1)), match.group(2), int(match.group(3)), summarize_run(path))

    report = {"directory": str(directory), "runs": {name: run[3] for name, run in runs.items()}, "conditions": {}, "consistent": {}}
    for n in sorted({run[0] for run in runs.values()}):
        good = [(run[1], run[3]) for run in runs.values() if run[0] == n and "T_mean" in run[3]]
        keys = {(json.dumps(run["rewards"]), run["final_sha256"]) for _, run in good}
        report["consistent"][f"n{n}"] = {"runs_compared": len(good), "identical_rewards_and_hashes": len(keys) <= 1, "distinct": len(keys)}
        by_condition = {}
        for condition, run in good:
            by_condition.setdefault(condition, []).append(run)
        reference_run = next((run for condition, run in good if condition == "B0"), None)
        for condition, run in good:
            if reference_run is not None and run is not reference_run:
                # generation 0 has the same parent in every run: a different reward there is a difference in how the candidate was
                # evaluated (which GPU, which chunk), never an effect of an earlier update
                differing = [i for i, (a, b) in enumerate(zip(run["rewards"][0], reference_run["rewards"][0])) if a != b]
                run["first_generation_mismatches"] = [{"candidate": i, "worker": run["first_generation_owner"].get(i), "reward": run["rewards"][0][i],
                                                       "reward_B0": reference_run["rewards"][0][i]} for i in differing]
        baseline = statistics.mean(run["T_mean"] for run in by_condition["B0"]) if "B0" in by_condition else None
        steady = {c: [run["T_mean_after_first"] for run in items if run["T_mean_after_first"] is not None] for c, items in by_condition.items()}
        steady_baseline = steady.get("B0") or None
        for condition, items in sorted(by_condition.items()):
            times = [run["T_mean"] for run in items]
            mean = statistics.mean(times)
            workers = set().union(*[set(run["workers"]) for run in items])
            entry = {"repeats": len(items), "T_mean": mean, "T_min": min(times), "T_max": max(times),
                     "T_stdev": statistics.stdev(times) if len(times) > 1 else None,
                     "T_mean_after_first": statistics.mean([run["T_mean_after_first"] for run in items if run["T_mean_after_first"] is not None] or [float("nan")]),
                     "wait_mean": statistics.mean(run["wait_mean"] for run in items), "update_mean": statistics.mean(run["update_mean"] for run in items),
                     "publish_mean": statistics.mean(run["publish_mean"] for run in items), "workers": sorted(workers),
                     "cluster_benefit_vs_B0": None if baseline is None else baseline / mean,
                     "delta_T_vs_B0": None if baseline is None else baseline - mean, "predicted_T": predicted(prediction, condition, workers)}
            steady_values = steady[condition]
            if steady_values:
                entry["T_steady"], entry["T_steady_ci95"] = mean_ci(steady_values)
                entry["T_steady_runs"] = steady_values
                if steady_baseline:
                    entry["cluster_benefit_steady"], entry["cluster_benefit_steady_ci95"] = ratio_ci(steady_baseline, steady_values)
                    entry["delta_T_steady_vs_B0"] = statistics.mean(steady_baseline) - entry["T_steady"]
            if entry["predicted_T"] is not None:
                entry["prediction_error_percent"] = 100 * (entry["predicted_T"] - mean) / mean
            report["conditions"][f"n{n}-{condition}"] = entry

    cell = lambda value, fmt: "-" if value is None else format(value, fmt)
    print(f"{'condition':<10}{'rep':>4}{'T steady':>10}{'+-95%':>7}{'CB steady':>10}{'+-95%':>7}{'T all':>8}{'CB all':>8}{'wait':>7}{'update':>8}{'pred':>8}{'err%':>7}")
    for name, e in report["conditions"].items():
        print(f"{name:<10}{e['repeats']:>4}{cell(e.get('T_steady'), '.1f'):>10}{cell(e.get('T_steady_ci95'), '.1f'):>7}"
              f"{cell(e.get('cluster_benefit_steady'), '.3f'):>10}{cell(e.get('cluster_benefit_steady_ci95'), '.3f'):>7}"
              f"{e['T_mean']:>8.1f}{cell(e['cluster_benefit_vs_B0'], '.3f'):>8}{e['wait_mean']:>7.1f}{e['update_mean']:>8.1f}"
              f"{cell(e['predicted_T'], '.1f'):>8}{cell(e.get('prediction_error_percent'), '.1f'):>7}")
    for key, value in report["consistent"].items():
        print(key, value)
    for name, (n, condition, repeat, run) in runs.items():
        if run.get("first_generation_mismatches"):
            print(f"{name}: generation 0 differs from B0 at", [(m["candidate"], m["worker"]) for m in run["first_generation_mismatches"]])
        if run["outcome"] != "ok":
            print("NOT OK:", name, run["outcome"])
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
