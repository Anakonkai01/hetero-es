"""
The mapping table of ADR-008 section 9: every recorded Recipe v1 (from the golden fixture) with its recorded hash, its
Recipe v3 translation and the plan fields v1 fixed (coefficient rule, scorer). Reads only the fixture; writes --out.

    PYTHONPATH=runtime/src python runtime/scripts/translate_recipes_v3.py --out <evidence>/v3-mapping.json
"""

import argparse
import json
from pathlib import Path

from heteroes.v3.documents import from_v1, recipe_hash

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/golden-identities.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    golden = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = []
    for entry in golden["recipes"]:
        doc, fixed = from_v1(entry["recipe"])
        rows.append(
            {
                "v1Hash": entry["recorded_hashes"][0],
                "v3Hash": recipe_hash(doc, translated=True),
                "workload": doc["data"]["name"],
                "recipeV3": doc,
                "planFields": fixed,
                "sources": entry["sources"],
            }
        )
    rows.sort(key=lambda row: row["v1Hash"])
    args.out.write_text(json.dumps({"formatVersion": 1, "mappings": rows}, indent=1, sort_keys=True) + "\n")
    for row in rows:
        print(row["v1Hash"][:12], "->", row["v3Hash"][:12], row["workload"], f"({len(row['sources'])} sources)")


if __name__ == "__main__":
    main()
