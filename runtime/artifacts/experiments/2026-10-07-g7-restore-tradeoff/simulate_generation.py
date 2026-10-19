"""
Trace-driven estimate of one generation on the two machines with the long workload (G7). NOT a measurement of the runtime: it replays the
MEASURED duration of every candidate (arm A of restore_tradeoff.py, seeds 0..23, on each GPU) through three dispatch rules and adds the costs
that the profiles of G6 measured. Everything is a parameter and is printed.

  B0  the fast machine alone
  B3  greedy: whoever is free takes the next candidate
  B4  tail-aware: a machine takes the next candidate only if it would finish before the fast machine could finish ALL the remaining ones alone
      (the idea of GreedyTail; here with the true durations of the trace as the estimate, so it is an optimistic version)

The slow machine can start only after its synchronization (SYNC seconds from the start of a generation). The coordinator's update costs
UPDATE_PER_CANDIDATE seconds per candidate after the last result (2.4 s for 8 candidates in G6). For N above 24 the trace is repeated.
Usage: python simulate_generation.py FAST.json SLOW.json [--arm A|D] [--update SECONDS_PER_CANDIDATE]
  --arm D with --update 0.08 describes the CUDA noise engine (arm D traces; 0.64 s measured for the update of 8 candidates on the 5070 Ti)
"""
import json, sys

SYNC = 10.0
UPDATE_PER_CANDIDATE = 0.3


def trace(paths, arm):
    arms = {}
    for path in paths:
        arms.update(json.load(open(path))["arms"])
    return [c["timing"]["total"] for c in arms[arm]["candidates"]]


def makespan(n, fast, slow, rule):
    dur = lambda w, i: (fast if w == 0 else slow)[i % len(fast)]
    free = [0.0, SYNC if rule != "B0" else float("inf")]
    nxt = 0
    end = 0.0
    mean = [sum(fast) / len(fast), sum(slow) / len(slow)]
    while nxt < n:
        w = 0 if free[0] <= free[1] else 1
        t = free[w]
        if rule == "B4" and w == 1:
            remaining = n - nxt
            if t + mean[1] > free[0] + remaining * mean[0]:       # the fast machine alone would finish everything sooner
                free[1] = float("inf")
                continue
        free[w] = t + dur(w, nxt)
        end = max(end, free[w])
        nxt += 1
    return end + UPDATE_PER_CANDIDATE * n


def main():
    global UPDATE_PER_CANDIDATE
    args = sys.argv[1:]
    arm = args[args.index("--arm") + 1] if "--arm" in args else "A"
    if "--update" in args:
        UPDATE_PER_CANDIDATE = float(args[args.index("--update") + 1])
    files = [a for i, a in enumerate(args) if a.endswith(".json")]
    fast, slow = trace([f for f in files if "5070" in f], arm), trace([f for f in files if "1660" in f], arm)
    print(f"arm {arm}")
    print(f"median candidate: fast {sorted(fast)[len(fast) // 2]:.2f} s, slow {sorted(slow)[len(slow) // 2]:.2f} s; sync {SYNC} s; update {UPDATE_PER_CANDIDATE} s per candidate")
    print("| N | B0 s | B3 s | B4 s | B3/B0 | B4/B0 |\n|---|---|---|---|---|---|")
    for n in (8, 24, 48, 96, 192):
        b0, b3, b4 = (makespan(n, fast, slow, r) for r in ("B0", "B3", "B4"))
        print(f"| {n} | {b0:.1f} | {b3:.1f} | {b4:.1f} | {b0 / b3:.3f} | {b0 / b4:.3f} |")


if __name__ == "__main__":
    main()
