"""Batch samplers of Recipe v3 (owner 2026-10-20): the original seeded sample per generation stays, so recorded runs
replay; `epoch-shuffle@1` walks the train split in shuffled epochs like the reference ES implementations."""

import pytest

from heteroes.canonical import canonical_json_hash
from heteroes.v3 import data as v3data
from heteroes.v3.documents import validate_recipe
from test_v3_data_run import documents

DATASET = v3data.build([{"prompt": f"p{i}", "answer": str(i)} for i in range(50)])  # 40 train rows


def test_the_original_sampler_is_unchanged_and_stays_the_default():
    selected = v3data.batch(DATASET, 3, 7, 11)
    assert selected == v3data.batch(DATASET, 3, 7, 11, v3data.SAMPLER)
    # recorded before the sampler became a choice (2026-10-20): any edit of the old rule changes these indices
    assert selected["indices"] == [19, 7, 16, 5, 2, 6, 36]
    recipe, _, _ = documents()
    assert recipe["data"]["batch"]["sampler"] == "sha256-python-random-sample-v1"


def test_an_epoch_visits_every_train_row_exactly_once_with_a_short_last_batch():
    batches = [v3data.batch(DATASET, g, 16, 11, "epoch-shuffle@1")["indices"] for g in range(3)]
    assert [len(b) for b in batches] == [16, 16, 8]  # 40 rows: two full batches and a short one
    assert sorted(i for b in batches for i in b) == list(range(40))
    second = [v3data.batch(DATASET, g, 16, 11, "epoch-shuffle@1")["indices"] for g in range(3, 6)]
    assert sorted(i for b in second for i in b) == list(range(40))
    assert second != batches  # a new shuffle every epoch
    assert batches[0] != list(range(16))  # shuffled, not in file order


def test_the_epoch_order_depends_only_on_dataset_epoch_and_seed():
    first = v3data.batch(DATASET, 4, 16, 11, "epoch-shuffle@1")
    assert first == v3data.batch(DATASET, 4, 16, 11, "epoch-shuffle@1")
    assert first["indices"] != v3data.batch(DATASET, 4, 16, 12, "epoch-shuffle@1")["indices"]
    assert first["hash"] == canonical_json_hash(first["rows"])
    other = v3data.build([{"prompt": f"q{i}", "answer": str(i)} for i in range(50)])
    assert v3data.batch(other, 4, 16, 11, "epoch-shuffle@1")["indices"] != first["indices"]


def test_unknown_samplers_are_refused_everywhere():
    with pytest.raises(ValueError, match="sampler"):
        v3data.batch(DATASET, 0, 4, 11, "random@9")
    recipe, _, _ = documents(sampler="epoch-shuffle@1")
    assert recipe["data"]["batch"]["sampler"] == "epoch-shuffle@1"
    validate_recipe(recipe)
    recipe["data"]["batch"]["sampler"] = "random@9"
    with pytest.raises(ValueError, match="sampler"):
        validate_recipe(recipe)


def test_a_managed_configuration_chooses_its_sampler(tmp_path):
    from heteroes.v3.options import validate_options

    base = {
        "weightSpace": {"kind": "full"},
        "scorer": {
            "kind": "declarative",
            "name": "exact-string",
            "version": 1,
            "codeSha256": None,
            "config": {"answerField": "answer", "strip": True, "casefold": False},
        },  # fmt: skip
        "coefficientRule": "zscore@1",
        "antithetic": False,
        "candidatesPerGeneration": 4,
        "decodeEngine": "hf_generate",
        "systemPrompt": None,
        "alpha": 0.001,
    }
    validate_options(base)  # the default sampler
    validate_options({**base, "sampler": "epoch-shuffle@1"})
    with pytest.raises(ValueError, match="sampler"):
        validate_options({**base, "sampler": "random@9"})


def test_the_sdk_writes_the_chosen_sampler_into_the_run_configuration():
    from heteroes.sdk import ESConfig

    args = ESConfig(model_path="m", model_id="m", train_dataset="d.jsonl", sampler="epoch-shuffle@1")
    assert args.to_config({"kind": "declarative"})["data"]["sampler"] == "epoch-shuffle@1"
    assert ESConfig(model_path="m", model_id="m", train_dataset="d.jsonl").to_config({})["data"]["sampler"] == (
        "sha256-python-random-sample-v1"
    )
