"""
The workloads a recipe can name (`Recipe.workload_name`): what each name asks, how it is scored and its hash.

`arith16` is the 16-prompt workload of the contract (`workload.py`, the default of every recipe); `cot_l3_q32` is the long arithmetic workload of G7
(`cot_workload.py`: word problems with step-by-step reasoning, 32 questions).
"""
from dataclasses import dataclass
from typing import Callable

from heteroes.eval.cot_workload import evaluate_cot, workload_hash_of
from heteroes.eval.generate import evaluate_model
from heteroes.eval.workload import workload_hash


@dataclass(frozen=True)
class Workload:
    name: str
    hash: Callable[[], str]
    evaluate: Callable                       # (model, tokenizer, chunk) -> an object with `.mean_reward`


WORKLOADS = {
    "arith16": Workload("arith16", workload_hash, evaluate_model),
    "cot_l3_q32": Workload("cot_l3_q32", lambda: workload_hash_of(3, 32), lambda model, tokenizer, chunk: evaluate_cot(model, tokenizer, chunk, level=3, count=32)),
}


def get_workload(name) -> Workload:
    if not isinstance(name, str) or name not in WORKLOADS:
        raise ValueError(f"unknown workload {name!r}; known: {sorted(WORKLOADS)}")
    return WORKLOADS[name]
