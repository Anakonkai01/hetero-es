"""
`heteroes.profile_setup`: what `scripts/profile_worker.py` needs to profile ANY workload and ANY noise engine, not only the 16 prompts with the CPU engine.
No model and no GPU: the questions come from the generators and the engine is chosen by the recipe's engine version.
"""
import pytest

from heteroes.es.cuda_ops import apply_coefficients_cuda_, perturb_model_cuda_
from heteroes.es.perturb import perturb_model_
from heteroes.es.update import apply_coefficients_
from heteroes.eval.cot_workload import make_questions
from heteroes.eval.workload import EXAMPLES
from heteroes.manifest import WORKLOAD_NAMES
from heteroes.noise.contracts import CUDA_ENGINE_VERSION, ENGINE_VERSION
from heteroes.profile_setup import noise_ops, profile_questions, reference_check_applies


def test_arith16_questions_are_the_contract_examples():
    assert profile_questions("arith16") == [example.question for example in EXAMPLES]


@pytest.mark.parametrize("name,level,count", [("cot_l3_q32", 3, 32), ("cot_l3_q64", 3, 64), ("cot_l1_q128", 1, 128)])
def test_cot_questions_are_the_generated_ones(name, level, count):
    assert profile_questions(name) == [question for question, _ in make_questions(count, level)]


def test_every_known_workload_has_questions():
    for name in WORKLOAD_NAMES:
        assert len(profile_questions(name)) >= 16


def test_unknown_workload_is_refused():
    with pytest.raises(ValueError):
        profile_questions("nope")


def test_cpu_engine_uses_the_cpu_functions():
    perturb, update = noise_ops(ENGINE_VERSION, chunk_elements=2 ** 18)
    assert perturb.__wrapped_by__ is perturb_model_ and update.__wrapped_by__ is apply_coefficients_


def test_cuda_engine_uses_the_cuda_functions():
    perturb, update = noise_ops(CUDA_ENGINE_VERSION, chunk_elements=None)
    assert perturb.__wrapped_by__ is perturb_model_cuda_ and update.__wrapped_by__ is apply_coefficients_cuda_


def test_unknown_engine_is_refused():
    with pytest.raises(ValueError):
        noise_ops("v0", chunk_elements=None)


def test_the_stored_reference_answers_exist_only_for_arith16():
    assert reference_check_applies("arith16") is True
    assert all(reference_check_applies(name) is False for name in WORKLOAD_NAMES if name != "arith16")


def test_the_texts_of_a_profile_pass_the_decode_engine_to_the_long_workloads(monkeypatch):
    from heteroes import profile_setup
    seen = []
    monkeypatch.setattr(profile_setup, "cot_generate", lambda model, tokenizer, questions, chunk, decode_engine="hf_generate": seen.append((chunk, decode_engine)) or (["t"], 0))
    profile_setup.profile_texts("cot_l1_q128", None, None, 64)
    profile_setup.profile_texts("cot_l1_q128", None, None, 64, "hf_compact")
    assert seen == [(64, "hf_generate"), (64, "hf_compact")]


def test_the_16_prompt_workload_has_no_other_decode_engine():
    from heteroes import profile_setup
    with pytest.raises(ValueError, match="arith16"):
        profile_setup.profile_texts("arith16", None, None, 4, "hf_compact")
