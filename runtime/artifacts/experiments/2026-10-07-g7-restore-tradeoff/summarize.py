"""Print the tables of the G7 restore trade-off from the JSON files (no numbers are typed by hand into the README).
Usage: python summarize.py tradeoff-5070ti.json [tradeoff-1660s.json ...]"""
import json, statistics, sys


def main():
    by_gpu = {}                                   # the files of one GPU (the arms may have been run in several files) are one table
    for path in sys.argv[1:]:
        d = json.load(open(path))
        if d["gpu"] in by_gpu:
            by_gpu[d["gpu"]][0]["arms"].update(d["arms"])
            by_gpu[d["gpu"]][1].append(path)
        else:
            by_gpu[d["gpu"]] = [d, [path]]
    for d, paths in by_gpu.values():
        path = ", ".join(paths)
        arms = dict(sorted(d["arms"].items()))
        print(f"\n## {d['gpu']}  ({path}; {d['candidates']} candidates, {d['questions']} questions of level {d['level']}, chunk {d['chunk']}, noise threads {d['noise_threads']}, {d['cpu_count']} CPUs)\n")
        print("| arm | perturb s | rollout s | back s | candidate s | back as % | peak GPU GiB | drift after 1 / 8 / last (elements) | relative L2 (last) | max abs diff | base reward before -> after (answers changed) |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for name, a in arms.items():
            m = a["median_seconds"]
            c = a["candidates"]
            idx = [0, min(7, len(c) - 1), len(c) - 1]
            dr = " / ".join(f"{c[i]['drift']['elements_differing']:,}" for i in idx)
            print(f"| {name} | {m['perturb']:.3f} | {m['rollout']:.2f} | {m['back']:.3f} | {m['total']:.2f} | {100 * m['back'] / m['total']:.1f} | {a['peak_gpu_bytes'] / 2**30:.2f} | {dr} | "
                  f"{a['final_drift']['relative_l2']:.2e} | {a['final_drift']['max_abs_diff']:.2e} | {a['base_reward_before']:.3f} -> {a['base_reward_after']:.3f} ({a['base_answers_changed']}) |")
        print(f"\nsnapshot kept by arm A in host memory: {d['snapshot_host_bytes'] / 2**30:.2f} GiB (arms A and D keep it, B and C keep none)")
        if "A" in arms and "B" in arms:
            ra = [r["reward"] for r in arms["A"]["candidates"]]
            rb = [r["reward"] for r in arms["B"]["candidates"]]
            diff = [abs(x - y) for x, y in zip(ra, rb)]
            same = sum(1 for x in diff if x == 0)
            print(f"A vs B (same seeds, same noise, only the revert differs): {same} of {len(ra)} candidate rewards equal; mean |diff| {statistics.mean(diff):.4f}, max {max(diff):.4f}")
            qa = sum(sum(x != y for x, y in zip(a["rewards"], b["rewards"])) for a, b in zip(arms["A"]["candidates"], arms["B"]["candidates"]))
            print(f"                                                           {qa} of {len(ra) * d['questions']} per-question outcomes differ")


if __name__ == "__main__":
    main()
