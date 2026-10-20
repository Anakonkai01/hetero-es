"""Optional prompt format preserves old identities; boxed answers have explicit versioned scoring."""

import copy

import pytest

from test_v3_local import assets, config_for


def test_prompt_format_is_optional_and_changes_the_recipe_only_when_chosen(assets, tmp_path):
    from heteroes.v3.local import prepare
    from heteroes.v3.documents import validate_recipe
    from heteroes.v3.run import RecipeV3Run

    config = config_for(assets, generations=1)
    original = prepare(config, tmp_path / "original")
    assert "promptFormat" not in original["run"].recipe["evaluation"]
    raw = prepare({**config, "promptFormat": "raw", "systemPrompt": None}, tmp_path / "raw")
    assert raw["run"].recipe["evaluation"]["promptFormat"] == "raw"
    assert raw["run"].hash != original["run"].hash
    assert raw["run"].evaluation["promptFormat"] == "raw"
    old = RecipeV3Run(original["run"].recipe, original["run"].plan)
    assert old.hash == original["run"].hash and "promptFormat" not in old.recipe["evaluation"]
    invalid = copy.deepcopy(raw["run"].recipe)
    invalid["evaluation"]["promptFormat"] = "unknown"
    with pytest.raises(ValueError, match="prompt"):
        validate_recipe(invalid)
    with pytest.raises(ValueError, match="system"):
        prepare({**config, "promptFormat": "raw", "systemPrompt": "Silently ignoring this is wrong"}, tmp_path / "bad")


def test_raw_generation_uses_the_dataset_prompt_verbatim(assets, monkeypatch):
    import torch
    from heteroes.v3.model import file_manifest, load
    from heteroes.study.evaluation import generate_rows

    model, tokenizer = load(assets / "model", file_manifest(assets / "model"), "cpu")
    rows = [{"prompt": "What is 17 plus 24? Answer:"}]
    inputs = tokenizer([rows[0]["prompt"]], return_tensors="pt", padding=True)
    with torch.no_grad():
        tokens = model.float().generate(**inputs, do_sample=False, max_new_tokens=4)
    expected = tokenizer.batch_decode(tokens[:, inputs["input_ids"].shape[1] :], skip_special_tokens=True)
    monkeypatch.setattr(
        tokenizer, "apply_chat_template", lambda *a, **k: (_ for _ in ()).throw(AssertionError("raw is verbatim"))
    )
    evaluation = {"promptFormat": "raw", "systemPrompt": None, "maxNewTokens": 4}
    assert [r["output"] for r in generate_rows(model, tokenizer, rows, evaluation)] == expected
    with pytest.raises(ValueError, match="system"):
        generate_rows(model, tokenizer, rows, {**evaluation, "systemPrompt": "ignored"})
    with pytest.raises(ValueError, match="prompt"):
        generate_rows(model, tokenizer, rows, {**evaluation, "promptFormat": "unknown"})


@pytest.mark.parametrize(
    "text,expected",
    [
        (r"Reasoning \boxed{42}", 1.0),
        (r"\boxed{1,234.00}", 1.0),
        (r"\boxed{-2.5}", 1.0),
        (r"\boxed{0.5}", 1.0),
    ],
)
def test_boxed_number_parses_exact_decimal_answers(text, expected):
    from heteroes.v3.scoring import score, validate_spec

    answer = {
        r"Reasoning \boxed{42}": "42",
        r"\boxed{1,234.00}": "1234",
        r"\boxed{-2.5}": "-2.500",
        r"\boxed{0.5}": "0.50",
    }[text]
    spec = {"kind": "declarative", "name": "boxed-number", "version": 1, "codeSha256": None, "config": {}}
    validate_spec(spec)
    assert score(spec, [text], [{"answer": answer}])[0] == expected


def test_boxed_format_reward_is_optional_and_never_awarded_for_malformed_output():
    from heteroes.v3.scoring import score, validate_spec

    spec = {
        "kind": "declarative",
        "name": "boxed-number",
        "version": 1,
        "codeSha256": None,
        "config": {"answerField": "target", "formatReward": 0.1},
    }
    validate_spec(spec)
    texts = [
        r"\boxed{2}",
        "2",
        r"\boxed{2",
        r"\boxed{nonsense}",
        r"\boxed{1} then \boxed{2}",
        r"\boxed{2} then \boxed{1}",
        r"\boxed{2} then \boxed{broken}",
    ]
    assert score(spec, texts, [{"target": 2}] * len(texts))[1] == [1.0, 0.0, 0.0, 0.0, 1.0, 0.1, 0.0]
    for value in (True, -0.1, 1, float("nan"), "0.1"):
        with pytest.raises(ValueError):
            validate_spec({**spec, "config": {"formatReward": value}})


def test_sdk_prompt_format_defaults_to_absence():
    from heteroes.sdk import ESConfig

    common = dict(model_path="m", model_id="m/id", train_dataset="rows.jsonl")
    assert "promptFormat" not in ESConfig(**common).to_config({"name": "exact-string"})
    assert ESConfig(**common, prompt_format="raw").to_config({"name": "exact-string"})["promptFormat"] == "raw"


def test_boxed_comparison_does_not_round_large_integer_answers():
    from heteroes.v3.scoring import score

    spec = {"kind": "declarative", "name": "boxed-number", "version": 1, "codeSha256": None, "config": {}}
    assert (
        score(spec, [r"\boxed{1234567890123456789012345678901}"], [{"answer": "1234567890123456789012345678902"}])[0]
        == 0
    )
