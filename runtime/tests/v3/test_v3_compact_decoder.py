"""Recipe v3 with the compacting greedy decoder (`hf_compact`): the same texts as `generate()`, or a loud refusal."""

import pytest

from heteroes.study.evaluation import generate_rows
from tinylm import build_tiny_lm

ROWS = [{"prompt": p, "answer": "1"} for p in ("What is 17 plus 24?", "Solve", "Step by step: 2 plus 3", "41", "What")]


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    import torch
    import transformers

    directory = build_tiny_lm(tmp_path_factory.mktemp("tiny"), seed=3)
    tokenizer = transformers.AutoTokenizer.from_pretrained(directory)
    model = transformers.AutoModelForCausalLM.from_pretrained(directory, dtype=torch.float32).eval()
    torch.manual_seed(5)
    with torch.no_grad():  # larger random weights than the default: varied texts instead of one repeated token
        for parameter in model.parameters():
            parameter.normal_(0, 1.0)
    model.generation_config.eos_token_id = 71  # first produced at steps 2 to 8 of these rows: staggered ends
    return model, tokenizer


@pytest.mark.parametrize("system", [None, "Solve the problem step by step."])
def test_compact_gives_the_texts_of_generate_for_v3_rows(tiny, system, monkeypatch):
    from heteroes.eval import compact_decode

    model, tokenizer = tiny
    evaluation = {"systemPrompt": system, "maxNewTokens": 24}
    original, compactions = compact_decode.compact_generate_ids, []

    def counted(*args, **kwargs):
        ids, stats = original(*args, **kwargs)
        compactions.append(stats["compactions"])
        return ids, stats

    monkeypatch.setattr(compact_decode, "compact_generate_ids", counted)
    generated = generate_rows(model, tokenizer, ROWS, {**evaluation, "decoder": "hf_generate"}, chunk=8)
    assert compactions == []
    compact = generate_rows(model, tokenizer, ROWS, {**evaluation, "decoder": "hf_compact"}, chunk=8)

    assert sum(compactions) > 0  # finished rows really were dropped

    assert len({len(r["output"]) for r in generated}) > 1 and not all(r["truncated"] for r in generated)  # premise
    assert compact == generated


def test_compact_refuses_sampling_and_settings_it_does_not_reproduce(tiny):
    from heteroes.eval.compact_decode import UnsupportedDecode

    model, tokenizer = tiny
    evaluation = {"systemPrompt": None, "maxNewTokens": 8, "decoder": "hf_compact"}
    with pytest.raises(ValueError, match="greedy"):
        generate_rows(model, tokenizer, ROWS, evaluation, sample=True)
    model.generation_config.no_repeat_ngram_size = 2
    try:
        with pytest.raises(UnsupportedDecode):
            generate_rows(model, tokenizer, ROWS, evaluation)
    finally:
        model.generation_config.no_repeat_ngram_size = 0
    with pytest.raises(ValueError, match="decoder"):
        generate_rows(model, tokenizer, ROWS, {**evaluation, "decoder": "vllm"})


def test_a_v3_configuration_may_choose_the_compacting_decoder_and_the_run_passes_it_on():
    from heteroes.v3.options import validate_options
    from heteroes.v3.run import RecipeV3Run
    from test_v3_data_run import documents

    scorer = {"kind": "declarative", "name": "exact-string", "version": 1, "codeSha256": None,
              "config": {"answerField": "answer", "strip": True, "casefold": False}}  # fmt: skip
    base = {"weightSpace": {"kind": "full"}, "scorer": scorer, "coefficientRule": "zscore@1", "antithetic": False,
            "candidatesPerGeneration": 4, "decodeEngine": "hf_compact", "systemPrompt": None, "alpha": 0.001}  # fmt: skip
    validate_options(base)
    with pytest.raises(ValueError, match="decoder"):
        validate_options({**base, "decodeEngine": "vllm"})
    recipe, plan, _ = documents(decoder="hf_compact")
    assert RecipeV3Run(recipe, plan).evaluation["decoder"] == "hf_compact"
    recipe, plan, _ = documents()
    assert RecipeV3Run(recipe, plan).evaluation["decoder"] == "hf_generate"
