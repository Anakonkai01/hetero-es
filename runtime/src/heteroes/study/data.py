"""Bounded text imports, exact math answers, immutable splits and batches."""

import csv
import hashlib
import io
import json
import random
import re
from decimal import Decimal, InvalidOperation

MAX_IMPORT_BYTES = 3_000_000
MAX_ROWS = 100_000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def answer(value, adapter="exact-number-v1"):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("Answers must be finite numbers or numeric strings")
    text = str(value).strip()
    if adapter == "gsm8k-v1":
        if "####" not in text:
            raise ValueError("GSM8K answers require the official #### marker")
        text = text.rsplit("####", 1)[1].strip()
    elif adapter != "exact-number-v1":
        raise ValueError("Unsupported answer adapter")
    text = text.replace(",", "")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        raise ValueError("Answer is not an exact number")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("Invalid number") from None
    if not value.is_finite():
        raise ValueError("Answer must be finite")
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def parse(content, format_name, mapping=None, adapter="exact-number-v1"):
    payload = content.encode() if isinstance(content, str) else content
    if len(payload) > MAX_IMPORT_BYTES:
        raise ValueError("Dataset file exceeds 3 MB")
    text = payload.decode("utf-8-sig")
    if format_name == "json":
        rows = json.loads(text)
    elif format_name == "jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif format_name == "csv":
        rows = list(csv.DictReader(io.StringIO(text)))
    else:
        raise ValueError("Use JSON, JSONL or CSV")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError("Expected a bounded nonempty row array")
    mapping = mapping or {"prompt": "prompt", "answer": "answer"}
    if set(mapping) != {"prompt", "answer"} or any(not isinstance(v, str) for v in mapping.values()):
        raise ValueError("Map prompt and answer fields")
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each row must be an object")
        prompt = row.get(mapping["prompt"])
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20000:
            raise ValueError("Missing or oversized prompt")
        result.append({"prompt": prompt.strip(), "answer": answer(row.get(mapping["answer"]), adapter)})
    return result


def dataset(files, *, seed=42, mapping=None, adapter="exact-number-v1"):
    if type(seed) is not int or not 0 <= seed < 2**53:
        raise ValueError("Invalid split seed")
    if not isinstance(files, dict) or set(files) not in ({"all"}, {"train", "validation", "test"}):
        raise ValueError("Provide one file or three named splits")
    splits = {name: parse(file["content"], file["format"], mapping, adapter) for name, file in files.items()}
    seen = set()
    for rows in splits.values():
        for row in rows:
            # Whitespace differences must not permit prompt leakage.
            prompt = " ".join(row["prompt"].split())
            if prompt in seen:
                raise ValueError("Duplicate prompt across or within splits")
            seen.add(prompt)
    if "all" in splits:
        rows = splits["all"][:]
        if len(rows) < 10:
            raise ValueError("Seeded 80/10/10 requires at least ten examples")
        random.Random(seed).shuffle(rows)
        n = len(rows)
        train = int(n * 0.8)
        validation = max(1, int(n * 0.1))
        splits = {
            "train": rows[:train],
            "validation": rows[train : train + validation],
            "test": rows[train + validation :],
        }
    if any(not rows for rows in splits.values()):
        raise ValueError("Every split must be nonempty")
    body = {
        "formatVersion": 1,
        "adapter": adapter,
        "splitSeed": seed,
        "splitMode": "seeded-80-10-10" if "all" in files else "pre-split",
        "splits": splits,
    }
    body["splitHashes"] = {name: sha(rows) for name, rows in splits.items()}
    return {**body, "contentHash": sha(body)}


def verify(value):
    body = {k: v for k, v in value.items() if k != "contentHash"}
    if sha(body) != value.get("contentHash"):
        raise ValueError("Dataset content hash mismatch")
    if (
        set(body) != {"formatVersion", "adapter", "splitSeed", "splitMode", "splits", "splitHashes"}
        or body["formatVersion"] != 1
    ):
        raise ValueError("Invalid dataset manifest")
    if set(body["splits"]) != {"train", "validation", "test"}:
        raise ValueError("Invalid splits")
    for name, rows in body["splits"].items():
        if sha(rows) != body["splitHashes"][name]:
            raise ValueError("Split hash mismatch")
    return value


def batch(value, generation, size, seed):
    verify(value)
    if (
        type(generation) is not int
        or generation < 0
        or type(size) is not int
        or size < 1
        or size > len(value["splits"]["train"])
    ):
        raise ValueError("Invalid training batch")
    if type(seed) is not int or not 0 <= seed < 2**53:
        raise ValueError("Invalid batch seed")
    rows = value["splits"]["train"]
    digest = sha(
        {
            "dataset": value["contentHash"],
            "generation": generation,
            "seed": seed,
            "sampler": "sha256-python-random-sample-v1",
        }
    )
    indices = random.Random(int(digest, 16)).sample(range(len(rows)), size)
    selected = [rows[i] for i in indices]
    return {"indices": indices, "rows": selected, "hash": sha(selected)}
