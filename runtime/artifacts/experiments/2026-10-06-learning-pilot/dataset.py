"""Arithmetic questions for the learning experiment: generated with a fixed seed, answers computed by Python.
Not the frozen 16-question workload (its hash must not change); none of its questions is reused."""
import numpy as np
from heteroes.eval.workload import EXAMPLES

TYPES = ["add2", "sub2", "mul1x2", "mul2x2", "add3", "mix3", "paren"]
EXPERIMENT_TYPES = ["sub2", "mul1x2", "mul2x2"]


def make(kind, rng):
    if kind == "add2":
        a, b = rng.integers(10, 100, 2); return f"What is {a} + {b}?", int(a + b)
    if kind == "sub2":
        a, b = sorted(rng.integers(10, 100, 2))[::-1]; return f"What is {a} - {b}?", int(a - b)
    if kind == "mul1x2":
        a, b = rng.integers(2, 13), rng.integers(10, 100); return f"What is {a} * {b}?", int(a * b)
    if kind == "mul2x2":
        a, b = rng.integers(11, 41, 2); return f"What is {a} * {b}?", int(a * b)
    if kind == "add3":
        a, b, c = rng.integers(100, 1000, 3); return f"What is {a} + {b} - {c}?", int(a + b - c)
    if kind == "mix3":
        a, b, c = rng.integers(10, 100), rng.integers(10, 100), rng.integers(10, 100); return f"What is {a} * {b} + {c}?", int(a * b + c)
    if kind == "paren":
        a, b, c = rng.integers(10, 100), rng.integers(10, 100), rng.integers(2, 13); return f"What is ({a} + {b}) * {c}?", int((a + b) * c)
    raise ValueError(kind)


def pool(per_type=40, seed=20261006):
    rng = np.random.default_rng(seed)
    seen = {e.question for e in EXAMPLES}
    out = []
    for kind in TYPES:
        count = 0
        while count < per_type:
            q, a = make(kind, rng)
            if q in seen: continue
            seen.add(q); out.append({"type": kind, "question": q, "answer": a}); count += 1
    return out


def train_heldout(per_type_each=32, seed=20261006):
    """96 train and 96 held-out questions, 32 per type each, disjoint, same generator."""
    rng = np.random.default_rng(seed)
    seen = {e.question for e in EXAMPLES}
    train, held = [], []
    for kind in EXPERIMENT_TYPES:
        items = []
        while len(items) < 2 * per_type_each:
            q, a = make(kind, rng)
            if q in seen: continue
            seen.add(q); items.append({"type": kind, "question": q, "answer": a})
        train += items[:per_type_each]; held += items[per_type_each:]
    assert not {e["question"] for e in train} & {e["question"] for e in held}
    return train, held
