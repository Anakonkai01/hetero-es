#!/usr/bin/env python3
"""
Write the admission prediction BEFORE the benchmark (MASTER section 8: "log the prediction before knowing the actual outcome").

    python scripts/predict_admission.py --reference artifacts/.../profile-5070ti.json --candidate artifacts/.../profile-1660s.json \
        --candidates 8 --out artifacts/experiments/<dir>/prediction.json

The reference worker is on the coordinator's machine (no synchronization, and its profile holds the update cost). It predicts the
time of one generation for every combination that the benchmark will run, with the decision for the candidate worker, from the
profiles alone. The file records the time of the prediction and the git commit: it is written first and never edited.
"""
import argparse
import json
import sys
import time
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--candidates", type=int, required=True, help="candidates per generation (N)")
    parser.add_argument("--delta-fraction", type=float, default=0.05)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if Path(args.out).exists():
        print(f"error: {args.out} already exists; a prediction is never overwritten", file=sys.stderr)
        return 2

    from heteroes.admission import capability_gate, decide, predict_generation_seconds, worker_model_from_profile
    from heteroes.runtime_info import code_info

    reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    if reference["update"] is None:
        print("error: the reference profile has no update measurement (--measure-update)", file=sys.stderr)
        return 2
    update, publish = reference["update"]["seconds_per_candidate_median"], reference["update"]["publish_seconds"]
    ref_key = reference["key"]
    expected = {**candidate["key"], "recipe_hash": ref_key["recipe_hash"], "schema_hash": ref_key["schema_hash"],
                "workload_hash": ref_key["workload_hash"], "device": "cuda"}
    reasons = capability_gate(candidate, expected)

    variants = {"common_chunk_1": (1, 1), "per_worker_chunk": (reference["safe_chunk"], candidate["safe_chunk"])}
    out = {"written_at_unix": time.time(), "written_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "code": code_info(),
           "inputs": {"reference": args.reference, "candidate": args.candidate, "candidates": args.candidates,
                      "update_per_candidate_seconds": update, "publish_seconds": publish, "delta_fraction": args.delta_fraction},
           "capability_gate": [reason.value for reason in reasons], "variants": {}}
    for name, (ref_chunk, cand_chunk) in variants.items():
        fast = worker_model_from_profile(reference, ref_chunk, remote=False)
        slow = worker_model_from_profile(candidate, cand_chunk, remote=True)
        entry = {"chunks": {reference["worker_id"]: ref_chunk, candidate["worker_id"]: cand_chunk}, "predictions": {}}
        for policy in ("B3_GREEDY_DYNAMIC", "B2_STATIC_PROPORTIONAL"):
            entry["predictions"][policy] = {
                "alone": predict_generation_seconds(policy, [fast], args.candidates, update, publish),
                "both": predict_generation_seconds(policy, [fast, slow], args.candidates, update, publish)}
            alone, both = entry["predictions"][policy]["alone"]["total_seconds"], entry["predictions"][policy]["both"]["total_seconds"]
            entry["predictions"][policy]["predicted_cluster_benefit"] = alone / both
            entry["predictions"][policy]["predicted_delta_seconds"] = alone - both
        entry["decision_b3"] = decide(slow, [fast], reasons, "B3_GREEDY_DYNAMIC", args.candidates, update, publish,
                                      args.delta_fraction, limited=cand_chunk < ref_chunk).to_dict()
        out["variants"][name] = entry
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "x", encoding="utf-8") as file:
        json.dump(out, file, indent=2)
        file.write("\n")
    for name, entry in out["variants"].items():
        print(name, entry["decision_b3"]["state"], {policy: (round(v["alone"]["total_seconds"], 1), round(v["both"]["total_seconds"], 1),
                                                             round(v["predicted_cluster_benefit"], 3)) for policy, v in entry["predictions"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
