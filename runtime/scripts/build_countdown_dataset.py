"""
A fixed Countdown dataset for Recipe v3: a seeded subset of the pinned `Jiayi-Pan/Countdown-Tasks-3to4` file (the task of
TinyZero and "Evolution Strategies at Scale", arXiv 2509.24372), as JSON Lines rows with the columns the `countdown@1`
scorer reads.

    python build_countdown_dataset.py --source train.parquet --out countdown.jsonl [--rows 2500] [--seed 20261019]

The source file is downloaded by the operator from the pinned revision below and checked by its SHA-256; reading it needs
pyarrow (any environment: this script imports nothing of the numerical runtime). The dataset card declares no license, so
the rows are not committed: rebuild them from the pinned file, and compare `fileSha256` of the written `.meta.json`.
"""

import argparse
import hashlib
import json
import random
from pathlib import Path

DATASET = "Jiayi-Pan/Countdown-Tasks-3to4"
REVISION = "408f70d177020686d34a56bba5952feb45aaaee4"
SOURCE_FILE = "data/train-00000-of-00001.parquet"
SOURCE_SHA256 = "a1b37bea0f439c858b11b908daa682e521f13f9592f1866b08650f58b730d126"
SOURCE_URL = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{SOURCE_FILE}"

# The instruct-model prompt of TinyZero's Countdown task.
PROMPT = (
    "Using the numbers {nums}, create an equation that equals {target}. You can use basic arithmetic operations "
    "(+, -, *, /) and each number can only be used once. Show your work in <think> </think> tags. And return the final "
    "answer in <answer> </answer> tags, for example <answer> (1 + 2) / 3 </answer>."
)


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_source(path):
    if sha256(path) != SOURCE_SHA256:
        raise ValueError(f"{path} is not the pinned source file (SHA-256 differs); download {SOURCE_URL}")
    return path


def read_records(path):
    import pyarrow.parquet as pq

    return pq.read_table(check_source(path)).to_pylist()


def select_rows(records, count, seed):
    """`count` rows with distinct prompts, drawn in a seeded order from `records` ({"target", "nums"})."""
    order = list(range(len(records)))
    random.Random(seed).shuffle(order)
    rows, seen = [], set()
    for index in order:
        record = records[index]
        nums = [int(n) for n in record["nums"]]
        prompt = PROMPT.format(nums=nums, target=int(record["target"]))
        if prompt in seen:
            continue
        seen.add(prompt)
        rows.append(
            {"prompt": prompt, "nums": " ".join(map(str, nums)), "target": int(record["target"]), "sourceIndex": index}
        )
        if len(rows) == count:
            return rows
    raise ValueError(f"the source has fewer than {count} distinct prompts")


def write(rows, out, seed):
    out = Path(out)
    out.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    meta = {
        "source": DATASET,
        "sourceRevision": REVISION,
        "sourceFile": SOURCE_FILE,
        "sourceSha256": SOURCE_SHA256,
        "selectionSeed": seed,
        "rows": len(rows),
        "fileSha256": sha256(out),
    }
    Path(f"{out}.meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=2500)
    parser.add_argument("--seed", type=int, default=20261019)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; choose a fresh path")
    print(json.dumps(write(select_rows(read_records(args.source), args.rows, args.seed), args.out, args.seed)))


if __name__ == "__main__":
    main()
