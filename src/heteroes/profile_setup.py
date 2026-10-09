"""
What `scripts/profile_worker.py` chooses by the recipe: the questions to time and compare (by workload name) and the noise functions (by engine version).

The profile of a worker is measured for ONE workload and ONE recipe (`profile.py`); before 08/10 the script knew only the 16 prompts of the contract and the CPU engine,
so a worker running the CUDA engine on a long workload had no profile of the thing it actually does.
"""
from heteroes.es.cuda_ops import apply_coefficients_cuda_, perturb_model_cuda_
from heteroes.es.perturb import perturb_model_
from heteroes.es.update import apply_coefficients_
from heteroes.eval.cot_workload import generate as cot_generate
from heteroes.eval.cot_workload import make_questions
from heteroes.eval.generate import generate_answer, generate_answers
from heteroes.eval.workload import EXAMPLES
from heteroes.noise.contracts import CUDA_ENGINE_VERSION, ENGINE_VERSION

# (level, count) of each long workload; the names are those of `heteroes.eval.workloads`
_COT = {"cot_l3_q32": (3, 32), "cot_l3_q64": (3, 64), "cot_l1_q128": (1, 128)}


def profile_questions(workload_name: str) -> list[str]:
    if workload_name == "arith16":
        return [example.question for example in EXAMPLES]
    if workload_name in _COT:
        level, count = _COT[workload_name]
        return [question for question, _ in make_questions(count, level)]
    raise ValueError(f"unknown workload {workload_name!r}; known: {['arith16', *sorted(_COT)]}")


def profile_texts(workload_name: str, model, tokenizer, chunk: int, decode_engine: str = "hf_generate") -> list[str]:
    """The answers of the workload's questions with `chunk` prompts per generate() call (chunk 1: one call per question), made by the decode engine (long workloads only)."""
    questions = profile_questions(workload_name)
    if workload_name == "arith16":
        if decode_engine != "hf_generate":
            raise ValueError(f"the decode engine {decode_engine!r} is for the long workloads; arith16 has its own code")
        if chunk == 1:
            return [generate_answer(model, tokenizer, question) for question in questions]
        out = []
        for start in range(0, len(questions), chunk):
            out += generate_answers(model, tokenizer, questions[start:start + chunk])
        return out
    return cot_generate(model, tokenizer, questions, chunk, decode_engine)[0]


def reference_check_applies(workload_name: str) -> bool:
    """The answers recorded on 2026-09-29 (`artifacts/probes`) are those of the 16 prompts only."""
    return workload_name == "arith16"


def _tagged(function):
    def call(*args, **kwargs):
        return function(*args, **kwargs)
    call.__wrapped_by__ = function
    return call


def noise_ops(engine_version: str, chunk_elements: int | None):
    """(perturb(model, schema, seed, sigma), update(model, schema, seeds, coefficients, alpha)) of the engine, as the executor and the coordinator use them."""
    if engine_version == ENGINE_VERSION:
        return _cpu(chunk_elements)
    if engine_version == CUDA_ENGINE_VERSION:
        perturb, update = _tagged(perturb_model_cuda_), _tagged(apply_coefficients_cuda_)
        return perturb, update
    raise ValueError(f"unknown noise engine version {engine_version!r}")


def _cpu(chunk_elements):
    def perturb(model, schema, seed, sigma):
        return perturb_model_(model, schema, seed, sigma, chunk_elements)

    def update(model, schema, seeds, coefficients, alpha):
        return apply_coefficients_(model, schema, seeds, coefficients, alpha, chunk_elements)
    perturb.__wrapped_by__, update.__wrapped_by__ = perturb_model_, apply_coefficients_
    return perturb, update
