"""
GSM8K for Recipe v3: train and validation drawn (seeded, disjoint) from the official train split, the official test
split kept whole as the held-out test (docs/es-literature-local-recipe.md). Rows have `prompt`, `question` and `answer`
(the normalized number after `####`), the columns the `answer-line-last-number@1` scorer compares.

    python build_gsm8k_dataset.py --source-dir DIR --out-dir OUT [--train 2000] [--validation 500] [--seed 20261020]

DIR holds `train.parquet` and `test.parquet` of the pinned revision below (license MIT); reading them needs pyarrow.
OUT receives train.jsonl, validation.jsonl, test.jsonl and meta.json.
"""

import argparse
import hashlib
import json
import random
import re
from decimal import Decimal
from pathlib import Path

DATASET = "openai/gsm8k"
REVISION = "740312add88f781978c0658806c59bc2815b9866"
SOURCES = {
    "train": ("main/train-00000-of-00001.parquet", "ea82612ea9582142387730c793eb67d3b12849002bc0b7fa6f8efafa7351419d"),
    "test": ("main/test-00000-of-00001.parquet", "ee7b8da9e381df27b9e3f7758a159ab2bdaa4dbaa910546cbbc47e0cb44e4f59"),
}
PROMPT = "{question}\nSolve the problem step by step, then end with a final line of the form 'Answer: <number>'."


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_source(path, split):
    name, digest = SOURCES[split]
    if sha256(path) != digest:
        url = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{name}"
        raise ValueError(f"{path} is not the pinned {split} file (SHA-256 differs); download {url}")
    return path


def number(answer):
    # the normalization of heteroes.study.data.answer(text, "gsm8k-v1"), kept here so the script needs no runtime
    text = answer.rsplit("####", 1)[1].strip().replace(",", "")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        raise ValueError(f"not an exact number: {text!r}")
    value = Decimal(text)
    return "0" if value == 0 else format(value.normalize(), "f")


def row(record):
    question = record["question"].strip()
    return {"prompt": PROMPT.format(question=question), "question": question, "answer": number(record["answer"])}


def splits(train_records, test_records, train, validation, seed):
    """{"train", "validation", "test"} rows: a seeded disjoint draw from the official train, the official test whole."""
    if train + validation > len(train_records):
        raise ValueError("the official train split is smaller than train + validation")
    order = list(range(len(train_records)))
    random.Random(seed).shuffle(order)
    drawn = [row(train_records[i]) for i in order[: train + validation]]
    return {"train": drawn[:train], "validation": drawn[train:], "test": [row(r) for r in test_records]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--train", type=int, default=2000)
    parser.add_argument("--validation", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20261020)
    args = parser.parse_args(argv)
    import pyarrow.parquet as pq

    records = {s: pq.read_table(check_source(args.source_dir / f"{s}.parquet", s)).to_pylist() for s in SOURCES}
    result = splits(records["train"], records["test"], args.train, args.validation, args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=False)
    meta = {"source": DATASET, "sourceRevision": REVISION, "seed": args.seed, "files": {}}
    for name, rows in result.items():
        path = args.out_dir / f"{name}.jsonl"
        path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
        meta["files"][name] = {"rows": len(rows), "sha256": sha256(path)}
    (args.out_dir / "meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
