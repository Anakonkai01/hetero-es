#!/usr/bin/env python3
"""
Compare a distributed run with its single-process reference.

    python scripts/compare_generation_runs.py <coordinator summary.json> <reference_generations.py output> [--allow-different-environments]

For every generation: the same parent hash, the same rewards (exactly, in index order) and the same child hash. Also the recipe
hash, the initial and the final weights. Prints one line per check and exits 0 only if every one is equal. Exact equality is the
rule: the noise, the perturbation, the evaluation on the tested GPUs and the update are bit-for-bit reproducible
(numerical contract); a difference is a finding to explain, not a tolerance to widen.
"""
import json
import sys
from pathlib import Path


def compare(distributed: dict, reference: dict) -> list[tuple[str, bool, str]]:
    checks = [("recipe hash", distributed["recipe_hash"] == reference["recipe_hash"], distributed["recipe_hash"][:16]),
              ("initial weights", distributed["initial_weights_sha256"] == reference["initial_weights_sha256"],
               str(distributed["initial_weights_sha256"])[:16]),
              ("number of generations", len(distributed["generations"]) == len(reference["generations"]),
               f"{len(distributed['generations'])} and {len(reference['generations'])}")]
    for mine, theirs in zip(distributed["generations"], reference["generations"]):
        g = mine["generation"]
        checks.append((f"g{g} parent", mine["parent_sha256"] == theirs["parent_sha256"], mine["parent_sha256"][:16]))
        checks.append((f"g{g} rewards", mine["rewards"] == theirs["rewards"], f"{mine['rewards']} and {theirs['rewards']}"))
        checks.append((f"g{g} child", mine["child_sha256"] == theirs["child_sha256"],
                       f"{mine['child_sha256'][:16]} and {theirs['child_sha256'][:16]}"))
    checks.append(("final weights", distributed["final_weights_sha256"] == reference["final_weights_sha256"],
                   str(distributed["final_weights_sha256"])[:16]))
    return checks


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    distributed, reference = (json.loads(Path(path).read_text()) for path in argv)
    if distributed.get("outcome") not in (None, "ok"):
        print(f"the distributed run did not end well: {distributed['outcome']}")
        return 1
    checks = compare(distributed, reference)
    for name, equal, detail in checks:
        print(f"{'EQUAL' if equal else 'DIFFERENT':9} {name}: {detail}")
    return 0 if all(equal for _, equal, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
