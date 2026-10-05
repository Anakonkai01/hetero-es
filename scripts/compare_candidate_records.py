#!/usr/bin/env python3
"""
Compare two JSON records written by scripts/run_one_candidate.py (the cross-machine same-candidate regression, step 7).

    python scripts/compare_candidate_records.py artifacts/regression/<date>/5070ti.json artifacts/regression/<date>/1660s.json

Two kinds of line:
  MUST BE EQUAL  identity of the candidate and of the weights (hashes, seed, sigma, recipe, model revision, generation
                 config). A difference here means the two machines did NOT run the same candidate.
  MEASURED       outputs, predictions and rewards of the three evaluations. A difference is not hidden and not an error
                 by itself: it is listed question by question, to be measured and explained (numerical contract, section 9).

Exit code 0: every MUST BE EQUAL line is equal. Exit code 1: at least one differs. Exit code 2: unusable input.
"""
import argparse
import json
import sys
from pathlib import Path

from heteroes.manifest import Recipe, effective_generation_config, generation_config_sha256
from heteroes.noise.selftest import EXPECTED_NOISE_FINGERPRINT

EVALUATIONS = ("base", "candidate", "restored")


def first_run(record: dict) -> dict:
    return record["runs"][0]


def recipe_hash_of(record: dict) -> str:
    """
    The recipe hash of a record. A record of format 2 carries it; a record of format 1 (the evidence of
    2026-10-05 and 2026-10-06) is rebuilt from its own fields, which is what the format-2 script would have stored.
    """
    if "recipe_hash" in record:
        return record["recipe_hash"]
    run = first_run(record)
    try:
        return Recipe(
            model_id="Qwen/Qwen2.5-0.5B-Instruct",
            model_revision=record["model"]["revision"],
            tokenizer_revision=record["model"]["tokenizer_revision"],
            dtype=record["model"]["dtype"],
            schema_hash=run["schema_hash"],
            engine_version=run["engine_version"],
            chunk_elements=run["chunk_elements"],
            noise_fingerprint=EXPECTED_NOISE_FINGERPRINT,
            sigma=run["sigma"],
            reward_eta=1e-9,
            workload_hash=run["workload_hash"],
            generation_config_sha256=generation_config_sha256(record["model"]["generation_config"]),
        ).hash
    except (ValueError, TypeError) as error:
        # a record that does not make a valid recipe is reported as a difference, not as a crash
        return f"no valid recipe: {error}"


def must_be_equal_checks(a: dict, b: dict) -> list[tuple[str, object, object]]:
    """(name, value in a, value in b) for everything that has to be identical on both machines."""
    run_a, run_b = first_run(a), first_run(b)
    checks = [
        ("recipe hash (manifest v1)", recipe_hash_of(a), recipe_hash_of(b)),
        ("model revision", a["model"]["revision"], b["model"]["revision"]),
        ("tokenizer revision", a["model"]["tokenizer_revision"], b["model"]["tokenizer_revision"]),
        ("model dtype", a["model"]["dtype"], b["model"]["dtype"]),
        ("generation config (set values, no library version)", effective_generation_config(a["model"]["generation_config"]), effective_generation_config(b["model"]["generation_config"])),
    ]
    for key in ("schema_hash", "workload_hash", "engine_version", "chunk_elements", "seed", "sigma", "sigma_float32"):
        checks.append((key, run_a[key], run_b[key]))
    for key in ("original", "perturbed", "restored"):
        checks.append((f"weights sha256 {key}", run_a["weights_sha256"][key], run_b["weights_sha256"][key]))
    return checks


def own_checks(record: dict, label: str) -> list[tuple[str, bool]]:
    """Things that have to hold on each machine by itself (they are not a comparison)."""
    return [
        (f"{label}: restore gives back the original weights (every run)", all(r["restored_equals_original"] for r in record["runs"])),
        (f"{label}: restored outputs equal base outputs (every run)", all(r["evaluation"]["restored"] == r["evaluation"]["base"] for r in record["runs"])),
        (f"{label}: the runs of this file are identical ({len(record['runs'])} runs)", bool(record["repeat_identical"])),
    ]


def measured_differences(a: dict, b: dict) -> dict:
    """For each evaluation: the rewards and the questions whose output text differs between the machines."""
    run_a, run_b = first_run(a), first_run(b)
    result = {}
    for name in EVALUATIONS:
        records_a, records_b = run_a["evaluation"][name]["records"], run_b["evaluation"][name]["records"]
        different = [
            {
                "index": index,
                "question": left["question"],
                "output_a": left["output_text"],
                "output_b": right["output_text"],
                "prediction_a": left["prediction"],
                "prediction_b": right["prediction"],
            }
            for index, (left, right) in enumerate(zip(records_a, records_b, strict=True))
            if left["output_text"] != right["output_text"]
        ]
        result[name] = {
            "reward_a": run_a["evaluation"][name]["mean_reward"],
            "reward_b": run_b["evaluation"][name]["mean_reward"],
            "questions": len(records_a),
            "different": different,
        }
    return result


def environment_lines(a: dict, b: dict) -> list[str]:
    keys = ("hostname", "gpu_name", "gpu_capability", "python", "torch", "torch_cuda", "numpy", "transformers", "nvidia_driver")
    return [f"  {key:<16} {a['environment'].get(key)!s:<34} {b['environment'].get(key)!s}" for key in keys]


def compare(a: dict, b: dict, label_a: str = "A", label_b: str = "B") -> tuple[str, bool]:
    """The report and whether every MUST BE EQUAL line is equal."""
    lines = [f"A = {label_a}", f"B = {label_b}", "", "ENVIRONMENT (information)"]
    lines += environment_lines(a, b)
    raw_a, raw_b = a["model"]["generation_config_sha256"], b["model"]["generation_config_sha256"]
    lines += ["", "raw generation config sha256 " + ("equal" if raw_a == raw_b else f"differs (A {raw_a[:16]}... | B {raw_b[:16]}...): see the line 'generation config' below, which compares the set values only")]
    lines += ["", f"code: A {a['code']['git_commit']} (dirty {a['code']['git_dirty']}), B {b['code']['git_commit']} (dirty {b['code']['git_dirty']})"]

    ok = True
    lines += ["", "MUST BE EQUAL"]
    for name, value_a, value_b in must_be_equal_checks(a, b):
        equal = value_a == value_b
        ok = ok and equal
        shown = f"{value_a}" if equal else f"A {value_a} | B {value_b}"
        lines.append(f"  {'EQUAL    ' if equal else 'DIFFERENT'} {name}: {shown}")

    lines += ["", "HOLDS ON EACH MACHINE"]
    for label, record in (("A", a), ("B", b)):
        for name, holds in own_checks(record, label):
            ok = ok and holds
            lines.append(f"  {'YES' if holds else 'NO '} {name}")

    lines += ["", "MEASURED (a difference is listed, not hidden)"]
    for name, info in measured_differences(a, b).items():
        count = len(info["different"])
        lines.append(f"  {name}: reward A {info['reward_a']} | B {info['reward_b']}; {count} of {info['questions']} output texts differ")
        for item in info["different"]:
            lines.append(f"      question {item['index']}: A {item['output_a']!r} | B {item['output_b']!r}")

    lines += ["", "RESULT: " + ("every MUST BE EQUAL line is equal" if ok else "AT LEAST ONE MUST-BE-EQUAL LINE DIFFERS")]
    return "\n".join(lines), ok


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("record_a")
    parser.add_argument("record_b")
    args = parser.parse_args(argv)
    try:
        a = json.loads(Path(args.record_a).read_text(encoding="utf-8"))
        b = json.loads(Path(args.record_b).read_text(encoding="utf-8"))
        report, ok = compare(a, b, args.record_a, args.record_b)
    except (OSError, ValueError, KeyError, IndexError) as error:
        print(f"error: unusable input: {error!r}", file=sys.stderr)
        return 2
    print(report)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
