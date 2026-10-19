"""
CommonsenseQA for Recipe v3, used to look for forgetting (a model trained on another task is scored on it): train and
validation are drawn (seeded, disjoint) from the official train split, the labelled official validation split is kept
whole as the held-out test (the official test split has no labels). Rows have `prompt`, `question` and `answer` (the
correct letter A-E), the columns the `choice-letter@1` scorer compares.

    python build_commonsense_qa_dataset.py --source-dir DIR --out-dir OUT [--train 2000] [--validation 500] \
        [--seed 20261020]

DIR holds `train.parquet` and `validation.parquet` of the pinned revision below (license MIT); reading them needs pyarrow.
OUT receives train.jsonl, validation.jsonl, test.jsonl and meta.json.
"""

import argparse
import hashlib
import json
import random
from pathlib import Path

DATASET = "tau/commonsense_qa"
REVISION = "94630fe30dad47192a8546eb75f094926d47e155"
SOURCES = {
    "train": ("data/train-00000-of-00001.parquet", "b0449767ed986bfc2ca52b1244a46ef12f732756727f3cb0a4ab69ac8b3d282b"),
    "validation": (
        "data/validation-00000-of-00001.parquet",
        "bdbd9bf9cc4d2349b24901038b2ab2f58e10e4e507ad2fd425dca55cd3cb6660",
    ),
}
LETTERS = list("ABCDE")
PROMPT = "{question}\n{choices}\nAnswer with the letter of the correct choice only: end with a final line of the form 'Answer: <single letter A-E>'."


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_source(path, split):
    name, digest = SOURCES[split]
    if sha256(path) != digest:
        url = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{name}"
        raise ValueError(f"{path} is not the pinned {split} file (SHA-256 differs); download {url}")
    return path


def row(record):
    choices, key = record["choices"], record["answerKey"]
    if list(choices["label"]) != LETTERS or len(choices["text"]) != 5 or key not in LETTERS:
        raise ValueError(f"a CommonsenseQA record has five choices A-E and a labelled answer: {record['id']}")
    question = record["question"].strip()
    lines = "\n".join(f"{letter}. {text}" for letter, text in zip(LETTERS, choices["text"]))
    return {"prompt": PROMPT.format(question=question, choices=lines), "question": question, "answer": key}


def splits(train_records, held_out_records, train, validation, seed):
    """{"train", "validation", "test"} rows: a seeded disjoint draw from the official train, the official validation whole."""
    if train + validation > len(train_records):
        raise ValueError("the official train split is smaller than train + validation")
    order = list(range(len(train_records)))
    random.Random(seed).shuffle(order)
    drawn = [row(train_records[i]) for i in order[: train + validation]]
    return {"train": drawn[:train], "validation": drawn[train:], "test": [row(r) for r in held_out_records]}


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
    result = splits(records["train"], records["validation"], args.train, args.validation, args.seed)
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
