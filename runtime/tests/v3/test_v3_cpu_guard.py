"""Owner-approved FP32 GPU / selective CPU-reference decoder, without acquiring a GPU."""

import copy

import pytest
import torch

from heteroes.eval import cpu_guard
from heteroes.study.evaluation import generate_rows
from tinylm import build_tiny_lm
from test_v3_product import product_assets, product_config


@pytest.fixture
def tiny(tmp_path):
    from transformers import AutoModelForCausalLM, AutoTokenizer

    directory = build_tiny_lm(tmp_path / "tiny", seed=3)
    model = AutoModelForCausalLM.from_pretrained(directory, dtype=torch.float32).eval()
    model.generation_config.repetition_penalty = 1.1
    return model, AutoTokenizer.from_pretrained(directory)


def test_margin_guard_uses_only_ambiguous_active_rows_and_exact_prefix():
    calls = []

    def reference(row, ids):
        calls.append((row, ids.tolist()))
        return torch.tensor([0.0, 4.0, 1.0])

    guard = cpu_guard.MarginProcessor(reference, prompt_length=2, eos_ids=[9])
    ids = torch.tensor([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    scores = torch.tensor([[3.0, 0.0, 1.0], [2.0, 1.999, 0.0], [2.0, 1.999, 0.0]])
    before = scores.clone()
    result = guard(ids, scores)
    assert calls == [(1, [[4, 5, 6]])]
    assert result.argmax(-1).tolist() == [0, 1, 0]
    assert torch.equal(result[0], before[0]) and torch.equal(result[2], before[2])
    assert torch.equal(scores, before)
    assert guard.reference_calls == 1


def test_multiple_ties_reference_failure_and_nonfinite_scores():
    calls = []

    def reference(row, ids):
        calls.append(row)
        return torch.tensor([0.0, 0.0, 1.0])

    guard = cpu_guard.MarginProcessor(reference, prompt_length=1, eos_ids=[9])
    result = guard(torch.tensor([[1], [2]]), torch.ones((2, 3)))
    assert calls == [0, 1] and result.argmax(-1).tolist() == [2, 2]
    with pytest.raises(cpu_guard.ReferenceUnavailable, match="finite"):
        guard(torch.tensor([[1]]), torch.tensor([[float("nan"), 0.0, 1.0]]))

    def broken(*args):
        raise cpu_guard.ReferenceUnavailable("CPU unavailable")

    with pytest.raises(cpu_guard.ReferenceUnavailable, match="CPU unavailable"):
        cpu_guard.MarginProcessor(broken, 1, [9])(torch.tensor([[1]]), torch.ones((1, 3)))
    with pytest.raises(cpu_guard.ReferenceUnavailable, match="finite"):
        bad = lambda *args: torch.tensor([0.0, float("nan"), 1.0])
        cpu_guard.MarginProcessor(bad, 1, [9])(torch.tensor([[1]]), torch.ones((1, 3)))


def test_reference_stays_cpu_float64_preserves_ties_and_refreshes_weights(monkeypatch):
    monkeypatch.setattr(cpu_guard, "available_memory_bytes", lambda: 2**40)
    model = torch.nn.Module()
    model.a = torch.nn.Linear(2, 2, bias=False)
    model.b = torch.nn.Linear(2, 2, bias=False)
    model.b.weight = model.a.weight
    model.register_buffer("counter", torch.tensor([7], dtype=torch.int64))
    first = cpu_guard.cpu_reference(model)
    assert first.a is not first.b and first.a.weight is first.b.weight
    assert first.a.weight.device.type == "cpu" and first.a.weight.dtype == torch.float64
    assert first.counter.dtype == torch.int64
    original = first.a.weight.clone()
    with torch.no_grad():
        model.a.weight.add_(1)
    second = cpu_guard.cpu_reference(model)
    assert torch.equal(first.a.weight, original)
    assert torch.equal(second.a.weight, model.a.weight.double())
    assert not torch.equal(first.a.weight, second.a.weight)


def test_reference_memory_checks_fail_before_copy(monkeypatch):
    model = torch.nn.Linear(4, 4).eval()
    monkeypatch.setattr(cpu_guard, "available_memory_bytes", lambda: 0)
    with pytest.raises(cpu_guard.ReferenceUnavailable, match="RAM"):
        cpu_guard.cpu_reference(model)
    monkeypatch.setattr(cpu_guard, "available_memory_bytes", lambda: 2**40)
    monkeypatch.setattr(cpu_guard, "MAX_REFERENCE_BYTES", 1)
    with pytest.raises(cpu_guard.ReferenceUnavailable, match="limit"):
        cpu_guard.cpu_reference(model)


def test_cpu_reference_is_freed_without_waiting_for_cyclic_garbage_collection(monkeypatch):
    import weakref

    monkeypatch.setattr(cpu_guard, "available_memory_bytes", lambda: 2**40)
    reference = cpu_guard.cpu_reference(torch.nn.Linear(4, 4).eval())
    alive = weakref.ref(reference)
    del reference
    assert alive() is None, "A multi-GB reference must not survive until a later GC cycle"


def test_forward_precision_mode_is_scoped_to_cpu_reference():
    value = torch.tensor([1.0], dtype=torch.float64)
    with cpu_guard.FullPrecision():
        assert value.float().dtype == torch.float64
    assert value.float().dtype == torch.float32


def test_guarded_generation_uses_repetition_processor_and_left_padded_prefixes(tiny, monkeypatch):
    model, tokenizer = tiny
    monkeypatch.setattr(cpu_guard, "MARGIN", 1000.0)  # force the independently checked reference path
    monkeypatch.setattr(cpu_guard, "available_memory_bytes", lambda: 2**40)
    tokenizer.padding_side = "left"
    inputs = tokenizer(["What is 17 plus 24?", "Solve"], padding=True, return_tensors="pt")
    reference = cpu_guard.cpu_reference(model)
    with torch.no_grad():
        expected = reference.generate(**inputs, max_new_tokens=5, do_sample=False)
        actual, stats = cpu_guard.guarded_generate_ids(model, **inputs, max_new_tokens=5)
    assert torch.equal(actual, expected)
    assert stats["referenceCalls"] > 0 and stats["referenceBytes"] > 0
    assert all(p.dtype == torch.float32 for p in model.parameters())


def test_no_cpu_copy_is_created_when_all_primary_scores_are_unambiguous(tiny, monkeypatch):
    model, tokenizer = tiny
    monkeypatch.setattr(cpu_guard, "MARGIN", 0.0)

    def forbidden(*args):
        pytest.fail("An unambiguous token must not allocate a CPU reference")

    monkeypatch.setattr(cpu_guard, "cpu_reference", forbidden)
    inputs = tokenizer("Solve", return_tensors="pt")
    with torch.no_grad():
        expected = model.generate(**inputs, max_new_tokens=3, do_sample=False)
        actual, stats = cpu_guard.guarded_generate_ids(model, **inputs, max_new_tokens=3)
    assert torch.equal(actual, expected) and stats["referenceCalls"] == stats["referenceBytes"] == 0


def test_generate_rows_routes_new_decoder_and_refuses_sampling_or_unsupported_config(tiny, monkeypatch):
    from heteroes.catalog import CPU_GUARD_DECODER
    from heteroes.eval.compact_decode import UnsupportedDecode

    model, tokenizer = tiny
    seen = []
    original = cpu_guard.guarded_generate_ids

    def counted(*args, **kwargs):
        seen.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(cpu_guard, "guarded_generate_ids", counted)
    rows = [{"prompt": "Solve", "answer": "1"}]
    evaluation = {"systemPrompt": None, "maxNewTokens": 2, "decoder": CPU_GUARD_DECODER}
    assert len(generate_rows(model, tokenizer, rows, evaluation)) == 1
    assert seen == [True]
    with pytest.raises(ValueError, match="greedy"):
        generate_rows(model, tokenizer, rows, evaluation, sample=True)
    model.generation_config.no_repeat_ngram_size = 2
    with pytest.raises(UnsupportedDecode):
        generate_rows(model, tokenizer, rows, evaluation)
    model.generation_config.no_repeat_ngram_size = 0
    model.half()
    with pytest.raises(ValueError, match="FP32"):
        generate_rows(model, tokenizer, rows, evaluation)


@pytest.mark.parametrize(
    "setting,value",
    [
        ("num_beams", 2),
        ("num_return_sequences", 2),
        ("max_time", 0.1),
        ("stop_strings", ["stop"]),
        ("token_healing", True),
        ("cache_implementation", "static"),
    ],
)
def test_unsupported_generation_modes_are_refused_before_generating(tiny, monkeypatch, setting, value):
    from heteroes.eval.compact_decode import UnsupportedDecode

    model, tokenizer = tiny
    setattr(model.generation_config, setting, value)

    def forbidden(*args, **kwargs):
        pytest.fail("Unsupported settings must be rejected before GPU generation")

    monkeypatch.setattr(model, "generate", forbidden)
    with pytest.raises(UnsupportedDecode):
        cpu_guard.guarded_generate_ids(model, **tokenizer("Solve", return_tensors="pt"), max_new_tokens=2)


def test_new_identity_is_v3_only_fp32_and_dataset_only():
    from heteroes.catalog import CPU_GUARD_DECODER, DECODE_ENGINES
    from heteroes.v3.documents import recipe_hash, validate_recipe
    from test_v3_data_run import documents

    old, _, _ = documents()
    new = copy.deepcopy(old)
    new["evaluation"]["decoder"] = CPU_GUARD_DECODER
    assert validate_recipe(new) == new and recipe_hash(new) != recipe_hash(old)
    assert CPU_GUARD_DECODER not in DECODE_ENGINES
    half = copy.deepcopy(new)
    half["evaluation"]["evalDtype"] = "float16"
    with pytest.raises(ValueError, match="FP32"):
        validate_recipe(half)
    builtin = copy.deepcopy(new)
    builtin["data"] = {"kind": "builtin", "name": "arith16", "hash": "a" * 64}
    builtin["evaluation"].update(maxNewTokens=None, systemPrompt=None)
    with pytest.raises(ValueError, match="dataset"):
        validate_recipe(builtin)


def test_supervisor_admits_new_v3_decoder_but_legacy_does_not():
    from heteroes.catalog import CPU_GUARD_DECODER
    from heteroes.product.run_supervisor import validate

    config = {
        "runId": "a" * 32,
        "maxGenerations": 2,
        "candidatesPerGeneration": 4,
        "alpha": 0.001,
        "sigma": 0.001,
        "workload": "text_v3",
        "decodeEngine": CPU_GUARD_DECODER,
        "recipeVersion": 3,
        "workerIds": ["w"],
        "schedulerPolicy": "greedy",
        "syncMode": "synchronous",
        "weightSpace": {"kind": "full"},
        "coefficientRule": "zscore@1",
        "antithetic": False,
        "systemPrompt": None,
        "scorer": {
            "kind": "declarative",
            "name": "exact-string",
            "version": 1,
            "codeSha256": None,
            "config": {"answerField": "answer", "strip": True, "casefold": False},
        },
    }
    validate(config, {"w": {}})
    with pytest.raises(ValueError, match="decoder"):
        validate({**config, "recipeVersion": 1, "workload": "arith16"}, {"w": {}})


def test_sampled_checkpoint_evaluation_refuses_guard_before_loading_model(tmp_path):
    import json
    from heteroes.catalog import CPU_GUARD_DECODER
    from heteroes.v3.evaluation import evaluate
    from test_v3_data_run import documents

    recipe, plan, _ = documents(decoder=CPU_GUARD_DECODER)
    (tmp_path / "recipe.json").write_text(json.dumps(recipe))
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="greedy"):
        evaluate(tmp_path, "/does-not-exist", [-1], "validation", samples=1)


def test_reference_failure_restores_candidate_and_never_returns_completions(product_assets, tmp_path, monkeypatch):
    from heteroes.catalog import CPU_GUARD_DECODER
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.executor import CandidateExecutor
    from heteroes.manifest import CandidateDescriptor
    from heteroes.product.v3 import prepare_run

    cfg = product_config(product_assets, tmp_path, decodeEngine=CPU_GUARD_DECODER)
    loaded, run, dataset = prepare_run(cfg, tmp_path, device="cpu")
    executor = CandidateExecutor(
        loaded.model, loaded.tokenizer, loaded.schema, run, dataset=dataset, return_completions=True
    )
    executor.set_generation(0, run.context(dataset, 0))
    parent = model_weights_sha256(loaded.model, loaded.schema)
    descriptor = CandidateDescriptor(run.hash, parent, "guard-failure", 0, 0, 17)
    monkeypatch.setattr(cpu_guard, "MARGIN", 1000.0)
    monkeypatch.setattr(cpu_guard, "available_memory_bytes", lambda: 0)
    with pytest.raises(cpu_guard.ReferenceUnavailable, match="RAM"):
        executor(descriptor)
    assert model_weights_sha256(loaded.model, loaded.schema) == parent
    assert executor.last_completions is None
