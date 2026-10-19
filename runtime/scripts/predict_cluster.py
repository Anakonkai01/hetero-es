#!/usr/bin/env python3
"""
Write, BEFORE the benchmark, the predicted time of one generation for a cluster of any number of machines (`predict_admission.py` knows one reference and one candidate).

    python scripts/predict_cluster.py --candidates 24 --chunk 64 --update-from <reference profile> --out prediction.json \
        --worker <profile of the local worker>  --worker <profile of a remote worker>[:replay]  --worker <another remote>[:replay] ...

The first --worker is local to the coordinator (no synchronization). For each remote worker `:replay` says that it catches up by replaying the update records (the time of one replay =
update cost per candidate x N + fixed + the check of the hash) instead of downloading the weights; without it the measured full synchronization is used. A profile that lacks the
`sync` block can be completed with `--sync-for <worker id>=<json of scripts/measure_sync.py>` (say so in the README of the experiment). Every subset of the workers that contains the
first one is predicted under B3 (greedy) and B2 (quotas by speed). The file records the time and the git commit; it is never overwritten.
"""
import argparse
import itertools
import json
import sys
import time
from pathlib import Path


def build_models(specs, sync_files, chunk, candidates, replay_hash_seconds=None):
    """[(WorkerModel, update dict)] from the profiles; the first is local. A remote worker's `sync` is the download or, with :replay, the estimate of a replay."""
    from heteroes.admission import worker_model_from_profile
    from heteroes.replay import ReplayPolicy

    models = []
    for index, spec in enumerate(specs):
        path, _, mode = spec.partition(":")
        profile = json.loads(Path(path).read_text(encoding="utf-8"))
        extra = sync_files.get(profile["worker_id"])
        if extra is not None:
            profile = {**profile, "sync": extra["sync"]}
        if index == 0:
            models.append((worker_model_from_profile(profile, chunk, remote=False), profile.get("update")))
            continue
        if mode == "replay":
            update = profile.get("update")
            if update is None:
                raise ValueError(f"{profile['worker_id']}: a replay estimate needs the update cost in its profile (--measure-update)")
            policy = ReplayPolicy.from_profile(profile, mode="always")
            seconds = policy.estimate_replay_seconds(1, candidates, verified=True)
            model = worker_model_from_profile({**profile, "sync": {"total_seconds": seconds}}, chunk, remote=True)
        elif mode == "":
            model = worker_model_from_profile(profile, chunk, remote=True)
        else:
            raise ValueError(f"unknown option {mode!r} after the profile; only ':replay' exists")
        models.append((model, profile.get("update")))
    return models


def predict(models, candidates, delta_fraction):
    from heteroes.admission import predict_generation_seconds

    reference_update = models[0][1]
    if reference_update is None:
        raise ValueError("the first (local) profile needs the update cost (--measure-update)")
    per_candidate, publish = reference_update["seconds_per_candidate_median"], reference_update["publish_seconds"]
    fixed = max(0.0, reference_update.get("fixed_seconds", 0.0))
    workers = [m for m, _ in models]
    out = {}
    for size in range(1, len(workers) + 1):
        for others in itertools.combinations(workers[1:], size - 1):
            members = [workers[0], *others]
            key = "+".join(w.worker_id for w in members)
            out[key] = {}
            for policy in ("B3_GREEDY_DYNAMIC", "B2_STATIC_PROPORTIONAL"):
                result = predict_generation_seconds(policy, members, candidates, per_candidate, publish, fixed)
                out[key][policy] = result
    for key, policies in out.items():
        for policy, result in policies.items():
            alone = out[workers[0].worker_id][policy]["total_seconds"]
            result["cluster_benefit_against_local_alone"] = alone / result["total_seconds"]
            result["admit_by_the_threshold"] = result["total_seconds"] < alone * (1.0 - delta_fraction)
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--worker", action="append", required=True, help="profile JSON, optionally followed by :replay (repeat; the first is local)")
    parser.add_argument("--sync-for", action="append", default=[], help="<worker id>=<json of measure_sync.py> for a profile without `sync`")
    parser.add_argument("--candidates", type=int, required=True)
    parser.add_argument("--chunk", type=int, required=True)
    parser.add_argument("--delta-fraction", type=float, default=0.05)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if Path(args.out).exists():
        print(f"error: {args.out} already exists; a prediction is never overwritten", file=sys.stderr)
        return 2
    sync_files = {}
    for item in args.sync_for:
        worker_id, _, path = item.partition("=")
        sync_files[worker_id] = json.loads(Path(path).read_text(encoding="utf-8"))

    from heteroes.runtime_info import code_info

    models = build_models(args.worker, sync_files, args.chunk, args.candidates)
    result = {"written_at_unix": time.time(), "written_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "code": code_info(),
              "inputs": {"workers": args.worker, "sync_for": args.sync_for, "candidates": args.candidates, "chunk": args.chunk, "delta_fraction": args.delta_fraction},
              "catch_up_seconds": {m.worker_id: m.sync_seconds for m, _ in models},
              "predictions": predict(models, args.candidates, args.delta_fraction)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "x", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
        file.write("\n")
    for key, policies in result["predictions"].items():
        print(key, {p.split("_")[0]: (round(r["total_seconds"], 1), round(r["cluster_benefit_against_local_alone"], 3)) for p, r in policies.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
