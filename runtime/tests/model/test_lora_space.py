"""
The LoRA weight space (ADR-008 section 4) on a tiny Qwen2 built from a config (no download): FP16 adapters as a subset
schema, the base never moving under the unchanged ES code, a deterministic initial adapter file, and a PEFT export that
PeftModel.from_pretrained loads to the same outputs.
"""

import copy

import numpy as np
import pytest
import torch

transformers = pytest.importorskip("transformers")
peft = pytest.importorskip("peft")

from heteroes.es.perturb import perturb_model_  # noqa: E402
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot  # noqa: E402
from heteroes.es.update import apply_coefficients_  # noqa: E402
from heteroes.model.lora import (  # noqa: E402
    attach_lora,
    create_initial_adapter,
    export_peft,
    load_adapter_,
    trainable_schema,
)
from heteroes.model.weights_io import WeightsFileError  # noqa: E402

SPACE = {"kind": "lora", "rank": 4, "alpha": 8, "targetModules": ["v_proj", "q_proj"], "initialAdapterSha256": "f" * 64}
CHUNK = 64


def tiny():
    config = transformers.Qwen2Config(
        vocab_size=64,
        hidden_size=32,
        intermediate_size=64,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        max_position_embeddings=64,
        tie_word_embeddings=True,
    )
    torch.manual_seed(0)
    return transformers.Qwen2ForCausalLM(config).half().eval()


def base_bits(model):
    return {n: p.detach().clone().view(torch.int16) for n, p in model.named_parameters() if ".lora_" not in n}


def logits(model, ids=((1, 2, 3, 4, 5),)):
    with torch.no_grad():
        return copy.deepcopy(model).float()(torch.tensor(ids)).logits


def test_adapters_are_fp16_a_subset_and_start_as_the_identity():
    model = tiny()
    before = logits(model)
    attach_lora(model, SPACE, seed=7)
    schema = trainable_schema(model)
    names = [entry.canonical_name for entry in schema.entries]
    assert len(names) == 2 * 2 * 2 and all(".lora_" in n for n in names)  # layers x modules x (A, B)
    assert {entry.dtype for entry in schema.entries} == {"torch.float16"}
    parameters = dict(model.named_parameters())
    assert all(parameters[n].abs().sum() == 0 for n in names if ".lora_B." in n)
    assert all(parameters[n].abs().sum() > 0 for n in names if ".lora_A." in n)
    assert torch.equal(logits(model), before)  # B = 0: the adapted model starts as the base model


def test_the_es_code_moves_only_the_adapters_and_the_first_perturbation_changes_the_output():
    model = attach_lora(tiny(), SPACE, seed=7)
    schema = trainable_schema(model)
    base, before = base_bits(model), logits(model)
    snapshot = take_snapshot(model, schema)
    perturb_model_(model, schema, 11, 1e-1, CHUNK)
    assert base_bits(model).keys() == base.keys() and all(torch.equal(base[n], base_bits(model)[n]) for n in base)
    assert not torch.equal(logits(model), before)  # sigma * eps_B * A is first order: learning can start from B = 0
    restore_from_snapshot_(model, schema, snapshot)
    assert torch.equal(logits(model), before)
    apply_coefficients_(model, schema, [3, 4], np.array([1.0, -0.5], dtype=np.float32), 0.1, CHUNK)
    assert all(torch.equal(base[n], base_bits(model)[n]) for n in base)


def test_the_initial_adapter_file_is_deterministic_and_leaves_the_callers_random_state(tmp_path):
    model = tiny()  # tiny() seeds the generator itself: build it before taking the caller's state
    torch.manual_seed(123)
    state = torch.random.get_rng_state()
    first = create_initial_adapter(model, SPACE, 7, tmp_path / "a.bin")
    assert torch.equal(torch.random.get_rng_state(), state)
    assert create_initial_adapter(tiny(), SPACE, 7, tmp_path / "b.bin") == first
    assert create_initial_adapter(tiny(), SPACE, 8, tmp_path / "c.bin") != first


def test_a_worker_loads_the_pinned_initial_adapter_and_refuses_another(tmp_path):
    sha = create_initial_adapter(tiny(), SPACE, 7, tmp_path / "init.bin")
    worker = attach_lora(tiny(), SPACE, seed=999)  # whatever its own initialization, the file decides
    load_adapter_(worker, tmp_path / "init.bin", sha)
    reference = attach_lora(tiny(), SPACE, seed=7)
    assert torch.equal(logits(worker), logits(reference))
    worker_bits = {n: p.view(torch.int16) for n, p in worker.named_parameters()}
    assert all(torch.equal(worker_bits[n], p.view(torch.int16)) for n, p in reference.named_parameters())
    with pytest.raises(WeightsFileError):
        load_adapter_(attach_lora(tiny(), SPACE, seed=1), tmp_path / "init.bin", "0" * 64)


def test_the_peft_export_loads_back_to_the_same_outputs(tmp_path):
    model = attach_lora(tiny(), SPACE, seed=7)
    perturb_model_(model, trainable_schema(model), 5, 1e-1, CHUNK)  # nonzero B, so the adapter matters
    export_peft(model, SPACE, tmp_path / "adapter", "tiny/qwen2", "1" * 40)
    loaded = peft.PeftModel.from_pretrained(tiny().float(), tmp_path / "adapter")
    with torch.no_grad():
        theirs = loaded(torch.tensor(((1, 2, 3, 4, 5),))).logits
    assert not torch.equal(theirs, logits(tiny()))  # premise: the adapter changes the outputs
    assert torch.allclose(theirs, logits(model), atol=1e-5)
    assert peft.PeftConfig.from_pretrained(tmp_path / "adapter").base_model_name_or_path == "tiny/qwen2"


def test_attach_refuses_what_it_cannot_do_exactly():
    with pytest.raises(TypeError):
        attach_lora(tiny().float(), SPACE, seed=1)
    model = attach_lora(tiny(), SPACE, seed=1)
    with pytest.raises(ValueError, match="already"):
        attach_lora(model, SPACE, seed=1)
    with pytest.raises(ValueError):
        attach_lora(tiny(), {"kind": "subset", "include": ["x"]}, seed=1)


def test_an_export_without_adapters_writes_nothing(tmp_path):
    with pytest.raises(ValueError, match="no LoRA"):
        export_peft(tiny(), SPACE, tmp_path / "adapter", "x", "1" * 40)
    assert not (tmp_path / "adapter").exists()
