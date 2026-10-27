"""D11: the executor reports stage progress (perturb, every generate() chunk, restore) for the heartbeat."""

from heteroes import progress
from test_v3_product import product_assets, product_config  # noqa: F401 - fixtures


def test_a_candidate_advances_perturb_each_chunk_and_restore(product_assets, tmp_path, monkeypatch):  # noqa: F811
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.executor import CandidateExecutor
    from heteroes.manifest import CandidateDescriptor
    from heteroes.product.v3 import prepare_run

    seen = []
    monkeypatch.setattr(progress, "CURRENT", progress.Progress())
    original = progress.Progress.advance

    def recorded(self, stage):
        seen.append(stage)
        original(self, stage)

    monkeypatch.setattr(progress.Progress, "advance", recorded)
    cfg = product_config(product_assets, tmp_path, evalChunk=16)
    loaded, run, dataset = prepare_run(cfg, tmp_path, device="cpu")
    executor = CandidateExecutor(loaded.model, loaded.tokenizer, loaded.schema, run, dataset=dataset, chunk=16)
    executor.set_generation(0, run.context(dataset, 0))
    parent = model_weights_sha256(loaded.model, loaded.schema)
    executor(CandidateDescriptor(run.hash, parent, "c", 0, 0, 17))
    assert seen == ["perturb", "rollout", "restore"]  # three rows fit one chunk of 16
    assert progress.CURRENT.snapshot() == ("restore", 3)


def test_every_generate_chunk_is_one_unit(product_assets, monkeypatch):  # noqa: F811
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from heteroes.study.evaluation import generate_rows

    monkeypatch.setattr(progress, "CURRENT", progress.Progress())
    model = AutoModelForCausalLM.from_pretrained(product_assets / "model", dtype=torch.float32).eval()
    tokenizer = AutoTokenizer.from_pretrained(product_assets / "model")
    rows = [{"prompt": f"What is {i} plus 2?", "answer": str(i + 2)} for i in range(5)]
    generate_rows(model, tokenizer, rows, {"systemPrompt": None, "maxNewTokens": 2}, chunk=2)
    assert progress.CURRENT.snapshot() == ("rollout", 3)


def test_unknown_stages_are_refused():
    import pytest

    with pytest.raises(ValueError):
        progress.Progress().advance("sleeping")


def test_reload_base_restores_corrupted_live_weights_in_place(product_assets):  # noqa: F811
    import pytest
    import torch

    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.model.schema import build_parameter_schema
    from heteroes.v3.model import file_manifest, load, reload_base_

    files = file_manifest(product_assets / "model")
    model, _ = load(product_assets / "model", files)
    schema = build_parameter_schema(model)
    parent = model_weights_sha256(model, schema)
    pointers = [p.data_ptr() for p in model.parameters()]
    with torch.no_grad():
        for p in model.parameters():
            p.mul_(-3)
    assert model_weights_sha256(model, schema) != parent
    reload_base_(model, product_assets / "model", files)
    assert model_weights_sha256(model, schema) == parent and [p.data_ptr() for p in model.parameters()] == pointers
    with pytest.raises(ValueError):
        reload_base_(model, product_assets / "model", {**files, "config.json": "0" * 64})
