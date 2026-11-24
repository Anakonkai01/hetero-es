"""
A fixed short-answer arithmetic dataset for Recipe v3: seeded multiplication questions whose answer the model must give as
a single `\\boxed{number}`, scored by the declarative `boxed-number@1` scorer (column `answer`).

    python build_arithmetic_dataset.py --out arithmetic.jsonl [--rows 3000] [--seed 20261124]

Kinds (equal shares, in a seeded order): a three-digit by one-digit product (`mul3x1`) and a two-digit by two-digit
product (`mul2x2`). Prompts are distinct. With a short token budget the instruct model must answer at once, so both the
format and the arithmetic leave room to improve. The rows are generated here (no source file); compare `fileSha256` of the
written `.meta.json` to check a rebuild. This script imports nothing of the numerical runtime.
"""

import argparse
import hashlib
import json
import random
from pathlib import Path

PROMPT = "What is {question}? Reply with only the final number inside \\boxed{{}}, no explanation."
KINDS = ("mul3x1", "mul2x2")


def question(kind, rng):
    if kind == "mul3x1":
        a, b = rng.randint(100, 999), rng.randint(2, 9)
    elif kind == "mul2x2":
        a, b = rng.randint(11, 99), rng.randint(11, 99)
    else:
        raise ValueError(f"unknown kind {kind!r}")
    return f"{a} * {b}", a * b


def build_rows(count, seed):
    """`count` rows with distinct prompts, the kinds alternating in a seeded order."""
    rng = random.Random(seed)
    rows, seen = [], set()
    attempts = 0
    while len(rows) < count:
        attempts += 1
        if attempts > 50 * count:
            raise ValueError(f"cannot draw {count} distinct questions")
        kind = KINDS[len(rows) % len(KINDS)]
        text, answer = question(kind, rng)
        prompt = PROMPT.format(question=text)
        if prompt in seen:
            continue
        seen.add(prompt)
        rows.append({"prompt": prompt, "answer": str(answer), "kind": kind})
    rng.shuffle(rows)
    return rows


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(rows, out, seed):
    out = Path(out)
    out.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    meta = {"generator": "build_arithmetic_dataset.py", "seed": seed, "rows": len(rows), "fileSha256": sha256(out)}
    Path(str(out) + ".meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=20261124)
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("choose a fresh output path")
    print(json.dumps(write(build_rows(args.rows, args.seed), args.out, args.seed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
