"""The rows of the experiment notebooks' tasks: GSM8K, multiplication and Countdown.

Every builder is deterministic (fixed files, fixed seeds), so a rerun of a notebook gives the same rows and the lab the
same dataset hash. Rows are dicts with a `prompt` and the columns the reward reads.
"""

import importlib.util
import json
import random
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

GSM8K_REPO, GSM8K_REVISION = "openai/gsm8k", "740312add88f781978c0658806c59bc2815b9866"
GSM8K_INSTRUCTION = "Solve the problem step by step. Put only the final number inside \\boxed{}, for example \\boxed{42}."
GSM8K_VALIDATION, GSM8K_SEED = 500, 20261125


def _gsm8k_rows(table):
    rows = []
    for item in table.to_pylist():
        answer = item["answer"].rsplit("####", 1)[1].strip().replace(",", "")
        rows.append({"prompt": f"{item['question'].strip()}\n\n{GSM8K_INSTRUCTION}", "answer": answer})
    return rows


def gsm8k():
    """GSM8K (main): its train split less 500 seeded rows for validation; the official test split (1319) as test."""
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    def split(name):
        path = hf_hub_download(GSM8K_REPO, f"main/{name}-00000-of-00001.parquet", repo_type="dataset",
                               revision=GSM8K_REVISION)
        return _gsm8k_rows(pq.read_table(path))

    train, test = split("train"), split("test")
    order = list(range(len(train)))
    random.Random(GSM8K_SEED).shuffle(order)
    held = set(order[:GSM8K_VALIDATION])
    validation = [train[i] for i in sorted(held)]
    train = [r for i, r in enumerate(train) if i not in held]
    return {"train": train, "validation": validation, "test": test}


def arithmetic(count=3000, seed=20261124):
    """The multiplication questions of the demo notebook (seeded; the lab splits them 80/10/10)."""
    spec = importlib.util.spec_from_file_location("arith", REPO / "runtime/scripts/build_arithmetic_dataset.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_rows(count, seed=seed)


def countdown():
    """The 2500 Countdown rows of the Qwen2.5-0.5B campaign (Jiayi-Pan/Countdown-Tasks-3to4, seeded selection)."""
    path = REPO / ".scratch/countdown/countdown.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def boxed(text):
    """The last \\boxed{...} of an answer (for showing examples; the reward itself is the lab's boxed-number scorer)."""
    found = re.findall(r"\\boxed\{([^{}]*)\}", text)
    return found[-1].strip() if found else None


def countdown_solution(numbers, target):
    """One expression over all the given numbers (each once, + - * /) that equals `target`, or None (for showing the scorer)."""
    from fractions import Fraction
    from itertools import permutations

    def build(items):
        if len(items) == 1:
            yield items[0]
            return
        for i in range(1, len(items)):
            for (lv, ls) in build(items[:i]):
                for (rv, rs) in build(items[i:]):
                    yield lv + rv, f"({ls} + {rs})"
                    yield lv - rv, f"({ls} - {rs})"
                    yield lv * rv, f"({ls} * {rs})"
                    if rv != 0:
                        yield lv / rv, f"({ls} / {rs})"

    for order in permutations(int(n) for n in str(numbers).replace(",", " ").split()):
        for value, text in build([(Fraction(n), str(n)) for n in order]):
            if value == target:
                return text[1:-1] if text.startswith("(") else text
    return None
