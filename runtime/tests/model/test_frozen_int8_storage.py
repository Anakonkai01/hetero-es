"""Typed frozen-int8 storage, pinned artifacts and FP16 LoRA-only trainable schema."""

import copy

import pytest
import torch
from transformers import Qwen2Config, Qwen2ForCausalLM

from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.eval import frozen_int8
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.model.frozen_int8 import (
    FrozenInt8LoraLinear,
    create_initial_frozen_adapter,
    freeze_linear,
    freeze_projections,
    frozen_modules,
    load_frozen_adapter_,
    require_frozen_projections,
)
from heteroes.model.lora import trainable_schema


def tiny():
    config = Qwen2Config(
        vocab_size=53,
        hidden_size=24,
        intermediate_size=47,
        num_hidden_layers=2,
        num_attention_heads=6,
        num_key_value_heads=2,
        max_position_embeddings=64,
        tie_word_embeddings=True,
        attention_bias=True,
        mlp_bias=True,
    )
    config._attn_implementation = "eager"
    torch.manual_seed(47)
    return Qwen2ForCausalLM(config).half().eval()


def bits(value):
    return value.contiguous().view(torch.int32)


def test_freeze_keeps_typed_base_buffers_and_only_adapters_trainable():
    model = tiny()
    embed = model.model.embed_tokens.weight
    head = model.lm_head.weight
    digests = freeze_projections(model, rank=2, alpha=4, seed=7, target_modules=("q_proj", "v_proj"))
    assert set(digests) == {
        f"model.layers.{layer}.self_attn.{name}" for layer in range(2) for name in ("q_proj", "v_proj")
    }
    assert model.model.embed_tokens.weight is embed and model.lm_head.weight is head
    assert model.lm_head.weight is model.model.embed_tokens.weight
    schema = trainable_schema(model)
    names = [entry.canonical_name for entry in schema.entries]
    assert len(names) == 4 * 2 and all(".lora_" in name for name in names)
    parameters = dict(model.named_parameters())
    assert all(parameters[name].dtype == torch.float16 for name in names)
    assert not any(name.endswith(".weight") and ".lora_" not in name for name in parameters if "q_proj" in name)
    for name, module in frozen_modules(model):
        assert isinstance(module, FrozenInt8LoraLinear)
        assert module.weight_q.dtype == torch.int8 and module.weight_scale.dtype == torch.float32
        assert module.weight_q.shape == module.weight_scale.shape[:1] + (module.in_features,)
        assert not hasattr(module, "weight")
        assert module.artifact_sha256 == digests[name]
        assert module.bias is not None and module.bias.dtype == torch.float16


def test_zero_adapter_preserves_the_base_and_es_moves_only_the_adapter():
    model = tiny()
    freeze_projections(model, rank=4, alpha=8, seed=11, target_modules=("q_proj",))
    module = model.model.layers[0].self_attn.q_proj
    value = torch.randn(5, module.in_features, generator=torch.Generator().manual_seed(3)).half().float()
    base = module.base_linear_cpu(value)
    assert torch.equal(bits(module(value)), bits(base))

    schema = trainable_schema(model)
    before_base = (module.weight_q.clone(), module.weight_scale.clone(), module.bias.clone())
    before_output = module(value).clone()
    snapshot = take_snapshot(model, schema)
    perturb_model_(model, schema, 13, 1e-1, 64)
    assert torch.equal(module.weight_q, before_base[0])
    assert torch.equal(module.weight_scale, before_base[1])
    assert torch.equal(module.bias, before_base[2])
    assert not torch.equal(bits(module(value)), bits(before_output))
    restore_from_snapshot_(model, schema, snapshot)
    assert torch.equal(bits(module(value)), bits(before_output))


def test_cpu_forward_matches_explicit_base_plus_fp32_adapter_delta(tmp_path):
    model = tiny()
    freeze_projections(model, rank=3, alpha=5, seed=17, target_modules=("down_proj",))
    module = model.model.layers[1].mlp.down_proj
    with torch.no_grad():
        module.lora_B["default"].weight.normal_(generator=torch.Generator().manual_seed(19))
    value = torch.randn(7, module.in_features, generator=torch.Generator().manual_seed(23)).half().float()
    base = module.base_linear_cpu(value)
    adapter_a = module.lora_A["default"].weight.float()
    adapter_b = module.lora_B["default"].weight.float()
    delta = (value @ adapter_a.T) @ adapter_b.T * module.scaling
    expected = torch.where(delta == 0, base, torch.add(base, delta))
    assert torch.equal(bits(module(value)), bits(expected))
    assert not torch.equal(bits(base), bits(expected))


def test_pinned_artifact_is_reused_and_mismatch_is_refused(tmp_path):
    model = tiny()
    source = model.model.layers[0].self_attn.q_proj
    weight_q, weight_scale = frozen_int8.quantize_weight(source.weight.detach().cpu())
    path = tmp_path / "q.fint8"
    digest = frozen_int8.write_artifact(path, weight_q, weight_scale, metadata={"module": "q"})
    frozen, used = freeze_linear(
        source,
        rank=2,
        alpha=4,
        seed=5,
        artifact_path=path,
        expected_sha256=digest,
    )
    assert used == digest and frozen.artifact_sha256 == digest
    assert torch.equal(frozen.weight_q.cpu(), weight_q)
    assert torch.equal(frozen.weight_scale.cpu(), weight_scale)

    with pytest.raises(ReferenceArithmeticError, match="[Hh]ash"):
        freeze_linear(
            source,
            rank=2,
            alpha=4,
            seed=5,
            artifact_path=path,
            expected_sha256="0" * 64,
        )
    wrong = torch.ones((source.weight.shape[0] + 1, source.weight.shape[1]), dtype=torch.int8)
    wrong_scale = torch.ones((source.weight.shape[0] + 1,), dtype=torch.float32)
    wrong_path = tmp_path / "wrong.fint8"
    wrong_digest = frozen_int8.write_artifact(wrong_path, wrong, wrong_scale)
    with pytest.raises(ReferenceArithmeticError, match="shape"):
        freeze_linear(
            source,
            rank=2,
            alpha=4,
            seed=5,
            artifact_path=wrong_path,
            expected_sha256=wrong_digest,
        )


def test_adapter_initialization_is_deterministic_and_leaves_caller_rng_untouched():
    first, second = tiny(), tiny()
    torch.manual_seed(123)
    state = torch.random.get_rng_state()
    one = freeze_projections(first, rank=4, alpha=8, seed=29, target_modules=("q_proj",))
    assert torch.equal(torch.random.get_rng_state(), state)
    two = freeze_projections(second, rank=4, alpha=8, seed=29, target_modules=("q_proj",))
    assert one == two
    for (name, left), (_, right) in zip(frozen_modules(first), frozen_modules(second), strict=True):
        assert name in one
        assert torch.equal(left.lora_A["default"].weight, right.lora_A["default"].weight)
        assert torch.equal(left.lora_B["default"].weight, right.lora_B["default"].weight)


def test_initial_adapter_file_is_pinned_and_loadable(tmp_path):
    first = tiny()
    freeze_projections(first, rank=2, alpha=4, seed=31, target_modules=("q_proj", "v_proj"))
    hash_one = create_initial_frozen_adapter(first, tmp_path / "one.bin")
    second = tiny()
    freeze_projections(second, rank=2, alpha=4, seed=31, target_modules=("q_proj", "v_proj"))
    hash_two = create_initial_frozen_adapter(second, tmp_path / "two.bin")
    assert hash_one == hash_two
    third = tiny()
    freeze_projections(third, rank=2, alpha=4, seed=99, target_modules=("q_proj", "v_proj"))
    load_frozen_adapter_(third, tmp_path / "one.bin", hash_one)
    for (name, left), (_, right) in zip(frozen_modules(first), frozen_modules(third), strict=True):
        assert torch.equal(left.lora_A["default"].weight, right.lora_A["default"].weight)
        assert torch.equal(left.lora_B["default"].weight, right.lora_B["default"].weight)
    from heteroes.model.weights_io import WeightsFileError

    wrong = tiny()
    freeze_projections(wrong, rank=2, alpha=4, seed=99, target_modules=("q_proj", "v_proj"))
    with pytest.raises(WeightsFileError):
        load_frozen_adapter_(wrong, tmp_path / "one.bin", "0" * 64)


def test_require_frozen_projections_and_tied_head_guard(tmp_path):
    model = tiny()
    names = freeze_projections(model, rank=2, alpha=4, seed=37, target_modules=("q_proj",))
    assert set(require_frozen_projections(model, names)) == set(names)
    with pytest.raises(ReferenceArithmeticError, match="set"):
        require_frozen_projections(model, ())
    with pytest.raises(ReferenceArithmeticError, match="set"):
        require_frozen_projections(model, (*names, "model.layers.0.mlp.down_proj"))
    with pytest.raises(ReferenceArithmeticError, match="tied"):
        freeze_projections(model, rank=2, alpha=4, seed=37, target_modules=("lm_head",))
    with pytest.raises(ReferenceArithmeticError, match="selects no projection"):
        freeze_projections(model, rank=2, alpha=4, seed=37, target_modules=("q_proj",))
    for bad_rank, bad_alpha, bad_name in ((0, 1, "default"), (2, 0, "default"), (2, 1, "a.b")):
        with pytest.raises(ReferenceArithmeticError):
            FrozenInt8LoraLinear(
                torch.ones((1, 1), dtype=torch.int8),
                torch.ones((1,), dtype=torch.float32),
                rank=bad_rank,
                alpha=bad_alpha,
                seed=1,
                adapter_name=bad_name,
            )


def test_constructor_refuses_bytes_that_do_not_match_the_pinned_digest():
    weight_q = torch.ones((2, 3), dtype=torch.int8)
    weight_scale = torch.ones((2,), dtype=torch.float32)
    with pytest.raises(ReferenceArithmeticError, match="pinned"):
        FrozenInt8LoraLinear(
            weight_q,
            weight_scale,
            rank=1,
            alpha=1,
            seed=1,
            artifact_sha256="0" * 64,
        )


def test_fresh_quantization_must_match_the_expected_digest(tmp_path):
    model = tiny()
    source = model.model.layers[0].self_attn.q_proj
    with pytest.raises(ReferenceArithmeticError, match="hash"):
        freeze_linear(source, rank=2, alpha=4, seed=5, expected_sha256="0" * 64)
    path = tmp_path / "fresh.fint8"
    with pytest.raises(ReferenceArithmeticError, match="hash"):
        freeze_linear(source, rank=2, alpha=4, seed=5, artifact_path=path, expected_sha256="0" * 64)
    assert not path.exists()
