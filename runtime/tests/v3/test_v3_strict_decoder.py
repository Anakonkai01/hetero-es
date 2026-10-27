"""`strict_b22_v1` (ADR-013): a new Recipe v3 decoder value over the live FP16 weights, through the candidate executor."""

import copy
import os

import pytest
import torch

from heteroes.eval import strict_backend
from heteroes.eval.reference_ops import ReferenceArithmeticError, StrictMemoryBudget, StrictTransportError
from test_v3_product import product_assets, product_config  # noqa: F401 - fixtures


def test_strict_decoder_is_a_new_v3_only_value():
    from heteroes.catalog import DECODE_ENGINES, STRICT_B22_DECODER, V3_DECODE_ENGINES

    assert STRICT_B22_DECODER == "strict_b22_v1"
    assert STRICT_B22_DECODER in V3_DECODE_ENGINES and STRICT_B22_DECODER not in DECODE_ENGINES


def test_strict_documents_need_fp16_and_accept_batch_chunks():
    from heteroes.catalog import STRICT_B22_DECODER
    from heteroes.v3.documents import recipe_hash, validate_recipe
    from test_v3_data_run import documents

    old, _, _ = documents()
    new = copy.deepcopy(old)
    new["evaluation"].update(decoder=STRICT_B22_DECODER, evalDtype="float16", chunk=8, chunks=[1, 8, 32])
    assert validate_recipe(new) == new and recipe_hash(new) != recipe_hash(old)
    fp32 = copy.deepcopy(new)
    fp32["evaluation"].update(evalDtype="float32", chunk=16, chunks=[16])
    with pytest.raises(ValueError, match="FP16"):
        validate_recipe(fp32)
    for chunk in (3, 128):
        wrong = copy.deepcopy(new)
        wrong["evaluation"].update(chunk=chunk, chunks=[chunk])
        with pytest.raises(ValueError, match="chunk"):
            validate_recipe(wrong)
    plain = copy.deepcopy(old)  # the earlier FP16 decoders keep their exact chunk of 1
    plain["evaluation"].update(evalDtype="float16", chunk=8)
    with pytest.raises(ValueError, match="chunk"):
        validate_recipe(plain)


def test_strict_run_options_need_fp16(product_assets, tmp_path):  # noqa: F811
    from heteroes.catalog import STRICT_B22_DECODER
    from heteroes.v3.options import validate_options

    config = product_config(product_assets, tmp_path, decodeEngine=STRICT_B22_DECODER, evalDtype="float16")
    validate_options(config, with_code=False)
    validate_options({**config, "evalChunk": 8, "evalChunks": [1, 8]}, with_code=False)
    with pytest.raises(ValueError, match="FP16"):
        validate_options({**config, "evalDtype": "float32"}, with_code=False)
    with pytest.raises(ValueError, match="generate"):
        validate_options({**config, "evalChunk": 5}, with_code=False)


@pytest.mark.parametrize("tokens, context", [(1, 512), (512, 512), (513, 1024), (4096, 4096)])
def test_engine_context_buckets(tokens, context):
    assert strict_backend.context_for(tokens) == context


def test_contexts_beyond_the_largest_bucket_or_the_model_are_refused():
    with pytest.raises(ReferenceArithmeticError, match="4096"):
        strict_backend.context_for(4097)
    assert strict_backend.context_for(100, 256) == 256 and strict_backend.context_for(600, 32768) == 1024
    with pytest.raises(ReferenceArithmeticError, match="256"):
        strict_backend.context_for(257, 256)


def test_memory_budget_can_be_set_explicitly(monkeypatch):
    monkeypatch.setenv("HETEROES_STRICT_GRAPH_BYTES", "123456")
    assert strict_backend.graph_budget("cuda") == 123456
    for bad in ("0", "-1", "lots"):
        monkeypatch.setenv("HETEROES_STRICT_GRAPH_BYTES", bad)
        with pytest.raises(ValueError):
            strict_backend.graph_budget("cuda")


def test_cpu_models_are_refused():
    with pytest.raises(ReferenceArithmeticError, match="GPU"):
        strict_backend.engine_for(torch.nn.Linear(2, 2))


def test_generate_rows_routes_the_strict_decoder_and_refuses_sampling(product_assets, monkeypatch):  # noqa: F811
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from heteroes.catalog import STRICT_B22_DECODER
    from heteroes.study.evaluation import generate_rows

    model = AutoModelForCausalLM.from_pretrained(product_assets / "model", dtype=torch.float16).eval()
    tokenizer = AutoTokenizer.from_pretrained(product_assets / "model")
    model.generation_config.repetition_penalty = 1.1
    calls = []

    def fake(model, input_ids, attention_mask, max_new_tokens, eos_ids, pad_id, processors):
        calls.append(([type(p).__name__ for p in processors], list(eos_ids), pad_id, max_new_tokens))
        return torch.full((input_ids.shape[0], max_new_tokens), int(eos_ids[0]))

    monkeypatch.setattr(strict_backend, "generate_ids", fake)
    rows = [{"prompt": "What is 1 plus 2?", "answer": "3"}, {"prompt": "Solve", "answer": "1"}]
    evaluation = {"systemPrompt": None, "maxNewTokens": 3, "decoder": STRICT_B22_DECODER}
    out = generate_rows(model, tokenizer, rows, evaluation, chunk=2, count_tokens=True)
    assert len(out) == 2 and calls == [
        (["RepetitionPenaltyLogitsProcessor"], [tokenizer.eos_token_id], tokenizer.pad_token_id, 3)
    ]
    assert all(row["generatedTokens"] == 1 and not row["truncated"] for row in out)
    with pytest.raises(ValueError, match="greedy"):
        generate_rows(model, tokenizer, rows, evaluation, sample=True)
    model.generation_config.no_repeat_ngram_size = 2
    from heteroes.eval.compact_decode import UnsupportedDecode

    with pytest.raises(UnsupportedDecode):
        generate_rows(model, tokenizer, rows, evaluation)


@pytest.mark.parametrize(
    "error, kind, text",
    [
        (StrictMemoryBudget("Captured decode exceeds its explicit memory budget"), "OUT_OF_MEMORY", "budget"),
        (StrictTransportError("Strict kernel data transport timed out"), "OTHER", "infrastructure"),
        (ReferenceArithmeticError("Nonfinite reference arithmetic"), "OTHER", "strict arithmetic"),
    ],
)
def test_executor_maps_strict_failures_after_an_exact_restore(product_assets, tmp_path, monkeypatch, error, kind, text):  # noqa: F811
    from heteroes import executor as module
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.manifest import CandidateDescriptor
    from heteroes.product.v3 import prepare_run
    from heteroes.worker import CandidateFailed

    cfg = product_config(product_assets, tmp_path)
    loaded, run, dataset = prepare_run(cfg, tmp_path, device="cpu")
    executor = module.CandidateExecutor(loaded.model, loaded.tokenizer, loaded.schema, run, dataset=dataset)
    executor.set_generation(0, run.context(dataset, 0))
    parent = model_weights_sha256(loaded.model, loaded.schema)

    def failing(*args, **kwargs):
        raise error

    monkeypatch.setattr(module, "evaluate_task", failing)
    with pytest.raises(CandidateFailed) as caught:
        executor._run(CandidateDescriptor(run.hash, parent, "c", 0, 0, 17), executor.chunk)
    assert caught.value.kind.value == kind and text in str(caught.value)
    assert model_weights_sha256(loaded.model, loaded.schema) == parent


gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@gpu
def test_executor_candidates_use_live_weights_restore_exactly_and_do_not_depend_on_chunk(
    product_assets,  # noqa: F811
    tmp_path,
    monkeypatch,
):
    from heteroes.catalog import STRICT_B22_DECODER
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.executor import CandidateExecutor
    from heteroes.manifest import CandidateDescriptor
    from heteroes.product.v3 import prepare_run

    monkeypatch.delenv("HETEROES_GPU_ACCEPTANCE")  # a strict recipe is the opt-in in a managed worker
    cfg = product_config(
        product_assets, tmp_path, decodeEngine=STRICT_B22_DECODER, evalDtype="float16", evalChunk=1, evalChunks=[1, 4]
    )
    loaded, run, dataset = prepare_run(cfg, tmp_path, device="cuda")
    texts = {}
    for chunk in (1, 4):
        executor = CandidateExecutor(
            loaded.model, loaded.tokenizer, loaded.schema, run, dataset=dataset, return_completions=True, chunk=chunk
        )
        executor.set_generation(0, run.context(dataset, 0))
        parent = model_weights_sha256(loaded.model, loaded.schema)
        for sign in (1, -1):
            descriptor = CandidateDescriptor(run.hash, parent, f"c{sign}", 0, 0, 17, sign=sign)
            texts[chunk, sign] = tuple(executor(descriptor))
            assert model_weights_sha256(loaded.model, loaded.schema) == parent
    assert texts[1, 1] == texts[4, 1] and texts[1, -1] == texts[4, -1]
    engine = strict_backend.engine_for(loaded.model)
    assert engine.model is loaded.model and engine.identity["operators"]["linear"]["magnitudeBits"] == 22
    assert sum(1 for _ in engine.buffers()) and not any(p.dtype == torch.float32 for p in loaded.model.parameters())


@gpu
def test_unsupported_graphs_are_refused_before_decoding():
    from transformers import LlamaConfig, LlamaForCausalLM

    config = LlamaConfig(hidden_size=32, intermediate_size=64, num_attention_heads=4, num_key_value_heads=2,
                         num_hidden_layers=1, vocab_size=50, rope_scaling={"rope_type": "linear", "factor": 2.0})  # fmt: skip
    model = LlamaForCausalLM(config).half().cuda()
    with pytest.raises(ReferenceArithmeticError):
        strict_backend.engine_for(model)


@gpu
def test_generation_settings_follow_the_pinned_config_against_the_cpu_oracle(product_assets):  # noqa: F811
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from heteroes.eval.compact_decode import decode_settings
    from heteroes.eval.integer_decoder import IntegerDecoderReference

    tokenizer = AutoTokenizer.from_pretrained(product_assets / "model")
    cpu = AutoModelForCausalLM.from_pretrained(product_assets / "model", dtype=torch.float16).eval()
    model = AutoModelForCausalLM.from_pretrained(product_assets / "model", dtype=torch.float16).eval().cuda()
    for m in (cpu, model):
        m.generation_config.repetition_penalty = 20.0
    tokenizer.padding_side = "left"
    batch = tokenizer(["What is 17 plus 24?", "Solve"], return_tensors="pt", padding=True)
    eos_ids, pad_id, processors = decode_settings(model, 6, tokenizer.pad_token_id)
    actual = strict_backend.generate_ids(
        model, batch["input_ids"].cuda(), batch["attention_mask"].cuda(), 6, eos_ids, pad_id, processors
    )
    oracle = IntegerDecoderReference(cpu, max_context=256, magnitude_bits=22)
    expected = oracle.generate(
        batch["input_ids"],
        attention_mask=batch["attention_mask"],
        max_new_tokens=6,
        eos_token_id=eos_ids,
        pad_token_id=pad_id,
        repetition_penalty=20.0,
    )[:, batch["input_ids"].shape[1] :]
    plain = oracle.generate(
        batch["input_ids"], attention_mask=batch["attention_mask"], max_new_tokens=6, eos_token_id=eos_ids,
        pad_token_id=pad_id, repetition_penalty=1.0,
    )[:, batch["input_ids"].shape[1] :]  # fmt: skip
    assert torch.equal(actual.cpu(), expected) and not torch.equal(expected, plain)
    assert strict_backend.engine_for(model) is strict_backend.engine_for(model, 200)  # one cached engine per model


def test_executor_checks_the_strict_graph_when_it_is_built(product_assets, tmp_path, monkeypatch):  # noqa: F811
    from heteroes.catalog import STRICT_B22_DECODER
    from heteroes.executor import CandidateExecutor
    from heteroes.product.v3 import prepare_run

    cfg = product_config(product_assets, tmp_path, decodeEngine=STRICT_B22_DECODER, evalDtype="float16", evalChunk=1)
    loaded, run, dataset = prepare_run(cfg, tmp_path, device="cpu")

    def refuse(model, tokens=1):
        raise ReferenceArithmeticError("Unsupported graph family, attention, RoPE or activation")

    monkeypatch.setattr(strict_backend, "engine_for", refuse)
    with pytest.raises(ReferenceArithmeticError, match="Unsupported graph"):
        CandidateExecutor(loaded.model, loaded.tokenizer, loaded.schema, run, dataset=dataset, return_completions=True)
