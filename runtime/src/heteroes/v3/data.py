"""
Datasets of Recipe v3 (ADR-008 section 2): rows with a prompt and any other columns the experiment's scorer reads.

Unlike Recipe v2 (`study/data.py`, numeric answers only) a row keeps every column as given (strings, numbers, booleans,
null); only the prompt column is required. The identity is the same kind of document: splits, their hashes and a content
hash, and the per-generation batch uses the same sampler (`sha256-python-random-sample-v1`).
"""

import csv
import hashlib
import io
import json
import math
import random
from pathlib import Path

from heteroes.canonical import canonical_json_bytes, canonical_json_hash

FORMAT_VERSION = 2  # 1 is the numeric-answer format of Recipe v2
SAMPLER = "sha256-python-random-sample-v1"
MAX_ROWS = 100_000
MAX_PROMPT = 20_000
SPLITS = ("train", "validation", "test")


def _row(row, prompt_field):
    if not isinstance(row, dict):
        raise ValueError("each row is an object")
    prompt = row.get(prompt_field)
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT:
        raise ValueError(f"every row needs a nonempty {prompt_field!r} of at most {MAX_PROMPT} characters")
    for key, value in row.items():
        if not isinstance(key, str) or not (
            value is None or isinstance(value, (str, bool, int)) or (isinstance(value, float) and math.isfinite(value))
        ):
            raise ValueError(f"column {key!r} must hold a string, a number, a boolean or null")
    return {**row, "prompt": prompt.strip()}  # the prompt column is also available as `prompt`


def read_rows(path, prompt_field="prompt"):
    """Rows of a JSON array, JSON Lines or CSV file; the prompt column is copied to `prompt`."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif path.suffix == ".json":
        rows = json.loads(text)
    elif path.suffix == ".csv":
        rows = list(csv.DictReader(io.StringIO(text)))
    else:
        raise ValueError("use a .json, .jsonl or .csv file")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError(f"expected between 1 and {MAX_ROWS} rows")
    return [_row(row, prompt_field) for row in rows]


def build(rows, *, split_seed=42, splits=None):
    """The dataset document of `rows` (seeded 80/10/10) or of given `splits` ({"train", "validation", "test"} -> rows)."""
    if type(split_seed) is not int or not 0 <= split_seed < 2**53:
        raise ValueError("invalid split seed")
    if splits is None:
        rows = [_row(row, "prompt") for row in rows]
        if len(rows) < 10:
            raise ValueError("a seeded 80/10/10 split needs at least ten rows")
        shuffled = rows[:]
        random.Random(split_seed).shuffle(shuffled)
        n = len(shuffled)
        train, validation = int(n * 0.8), max(1, int(n * 0.1))
        splits = {
            "train": shuffled[:train],
            "validation": shuffled[train : train + validation],
            "test": shuffled[train + validation :],
        }
        mode = "seeded-80-10-10"
    else:
        if set(splits) != set(SPLITS):
            raise ValueError("give the splits train, validation and test")
        splits = {name: [_row(row, "prompt") for row in splits[name]] for name in SPLITS}
        mode = "pre-split"
    if any(not splits[name] for name in SPLITS):
        raise ValueError("every split must be nonempty")
    seen = set()
    for name in SPLITS:
        for row in splits[name]:
            prompt = " ".join(row["prompt"].split())  # whitespace differences must not let a prompt leak
            if prompt in seen:
                raise ValueError("a prompt appears twice (within or across splits)")
            seen.add(prompt)
    body = {
        "formatVersion": FORMAT_VERSION,
        "splitSeed": split_seed,
        "splitMode": mode,
        "splits": splits,
        "splitHashes": {name: canonical_json_hash(splits[name]) for name in SPLITS},
    }
    return {**body, "contentHash": canonical_json_hash(body)}


def verify(value):
    body = {key: item for key, item in value.items() if key != "contentHash"}
    if set(body) != {"formatVersion", "splitSeed", "splitMode", "splits", "splitHashes"} or body["formatVersion"] != 2:
        raise ValueError("not a Recipe v3 dataset document")
    if canonical_json_hash(body) != value.get("contentHash"):
        raise ValueError("dataset content hash mismatch")
    if any(canonical_json_hash(body["splits"][name]) != body["splitHashes"][name] for name in SPLITS):
        raise ValueError("split hash mismatch")
    return value


def batch(value, generation, size, seed):
    """The training rows of a generation: the Recipe v2 sampler over this dataset's train split."""
    verify(value)
    rows = value["splits"]["train"]
    if type(generation) is not int or generation < 0 or type(size) is not int or not 1 <= size <= len(rows):
        raise ValueError("invalid training batch")
    if type(seed) is not int or not 0 <= seed < 2**53:
        raise ValueError("invalid batch seed")
    digest = hashlib.sha256(
        canonical_json_bytes(
            {"dataset": value["contentHash"], "generation": generation, "seed": seed, "sampler": SAMPLER}
        )
    ).hexdigest()
    indices = random.Random(int(digest, 16)).sample(range(len(rows)), size)
    selected = [rows[i] for i in indices]
    return {"indices": indices, "rows": selected, "hash": canonical_json_hash(selected)}
