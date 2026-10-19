"""
The workloads a recipe can name (`Recipe.workload_name`): what each name asks, how it is scored and its hash.

`arith16` is the 16-prompt workload of the contract (`workload.py`, the default of every recipe); `cot_l3_q32` is the long arithmetic workload of G7
(`cot_workload.py`: word problems with step-by-step reasoning, 32 questions); `cot_l3_q64` is the same with 64 questions (the first 32 are those of `cot_l3_q32`);
`cot_l1_q128` (08/10) is 128 questions of level 1 (two-digit operations): its replies are short (about 96 tokens), so the 256-token limit does not decide the score, unlike level 3
(`artifacts/experiments/2026-10-08-uncut-probe`).
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
    evaluate: Callable                       # (model, tokenizer, chunk[, decode_engine]) -> an object with `.mean_reward`; only the long workloads take a decode engine


WORKLOADS = {
    "arith16": Workload("arith16", workload_hash, evaluate_model),
    "cot_l3_q32": Workload("cot_l3_q32", lambda: workload_hash_of(3, 32), lambda model, tokenizer, chunk, decode_engine="hf_generate": evaluate_cot(model, tokenizer, chunk, level=3, count=32, decode_engine=decode_engine)),
    "cot_l3_q64": Workload("cot_l3_q64", lambda: workload_hash_of(3, 64), lambda model, tokenizer, chunk, decode_engine="hf_generate": evaluate_cot(model, tokenizer, chunk, level=3, count=64, decode_engine=decode_engine)),
    "cot_l1_q128": Workload("cot_l1_q128", lambda: workload_hash_of(1, 128), lambda model, tokenizer, chunk, decode_engine="hf_generate": evaluate_cot(model, tokenizer, chunk, level=1, count=128, decode_engine=decode_engine)),
}


def get_workload(name) -> Workload:
    if not isinstance(name, str) or name not in WORKLOADS:
        raise ValueError(f"unknown workload {name!r}; known: {sorted(WORKLOADS)}")
    return WORKLOADS[name]
