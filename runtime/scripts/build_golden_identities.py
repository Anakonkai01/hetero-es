"""
Collect the identities that past runs recorded, so that a refactor can be checked against the hashes those runs really had.

    python3 -I runtime/scripts/build_golden_identities.py --out runtime/tests/fixtures/golden-identities.json

Reads (never writes) `runtime/artifacts/` and `docs/evidence/`:
  - every recipe document stored next to its `recipe_hash` (coordinator events, regression references);
  - every generation record in a ledger (`generation_update.record_json`, `record_hash`) and the recipe hash of its generation.

Duplicates are kept once, with every file they came from. The hashes in the output are the RECORDED ones; this script computes
no hash, so the fixture cannot agree with the code by construction. Standard library only.
"""

import argparse
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ("runtime/artifacts", "docs/evidence")
RECIPE_KEYS = {"manifest_version", "model", "noise", "perturbation", "update", "workload"}


def json_objects(path):
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        return [json.loads(text)]
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []  # not every file under evidence is JSON of ours (logs, truncated captures)


def recipe_pairs(value):
    """Every (recipe document, recorded hash or None) inside a JSON value."""
    if isinstance(value, dict):
        recipe = value.get("recipe")
        if isinstance(recipe, dict) and set(recipe) == RECIPE_KEYS:
            yield recipe, value.get("recipe_hash")
        for child in value.values():
            yield from recipe_pairs(child)
    elif isinstance(value, list):
        for child in value:
            yield from recipe_pairs(child)


def ledger_records(path):
    # Read a COPY: opening a WAL ledger, even with mode=ro, creates or rewrites its -shm/-wal files, and evidence is immutable.
    # The -wal file is copied too, since some recorded ledgers hold their rows only there (immutable=1 would not see them).
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / path.name
        for suffix in ("", "-wal"):
            if Path(f"{path}{suffix}").exists():
                shutil.copyfile(f"{path}{suffix}", f"{copy}{suffix}")
        connection = sqlite3.connect(copy)
        try:
            return connection.execute(
                "SELECT u.record_json, u.record_hash, g.recipe_hash FROM generation_update u "
                "JOIN generation g USING (experiment_id, generation) ORDER BY u.experiment_id, u.generation"
            ).fetchall()
        finally:
            connection.close()


def collect():
    recipes, records = {}, {}
    for source in SOURCES:
        for path in sorted((ROOT / source).rglob("*")):
            relative = path.relative_to(ROOT).as_posix()
            if path.suffix in (".json", ".jsonl"):
                for value in json_objects(path):
                    for recipe, recorded in recipe_pairs(value):
                        key = json.dumps(recipe, sort_keys=True)
                        entry = recipes.setdefault(key, {"recipe": recipe, "recorded_hashes": set(), "sources": set()})
                        if recorded is not None:
                            entry["recorded_hashes"].add(recorded)
                        entry["sources"].add(relative)
            elif path.suffix == ".sqlite":
                for record_json, record_hash, recipe_hash in ledger_records(path):
                    entry = records.setdefault(
                        record_hash,
                        {
                            "record_json": record_json,
                            "record_hash": record_hash,
                            "recipe_hash": recipe_hash,
                            "sources": set(),
                        },
                    )
                    if entry["record_json"] != record_json or entry["recipe_hash"] != recipe_hash:
                        raise SystemExit(f"{relative}: record {record_hash} differs from an earlier copy")
                    entry["sources"].add(relative)
    return (
        [
            {"recipe": e["recipe"], "recorded_hashes": sorted(e["recorded_hashes"]), "sources": sorted(e["sources"])}
            for e in sorted(recipes.values(), key=lambda e: json.dumps(e["recipe"], sort_keys=True))
        ],
        [{**e, "sources": sorted(e["sources"])} for _, e in sorted(records.items())],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    recipes, records = collect()
    document = {
        "formatVersion": 1,
        "builtBy": "runtime/scripts/build_golden_identities.py",
        "sources": list(SOURCES),
        "recipes": recipes,
        "records": records,
    }
    args.out.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"{len(recipes)} distinct recipes "
        f"({sum(1 for r in recipes if r['recorded_hashes'])} with a recorded hash), {len(records)} distinct records"
    )


if __name__ == "__main__":
    main()
