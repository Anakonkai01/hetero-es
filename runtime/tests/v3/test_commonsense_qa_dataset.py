"""The CommonsenseQA builder (runtime/scripts/build_commonsense_qa_dataset.py): a seeded draw from the official train
split, the labelled official validation split kept whole as the held-out set, rows the choice-letter scorer compares."""

import importlib.util
from pathlib import Path

import pytest

from heteroes.v3 import data as v3data
from heteroes.v3.scoring import score


def builder():
    path = Path(__file__).resolve().parents[2] / "scripts" / "build_commonsense_qa_dataset.py"
    spec = importlib.util.spec_from_file_location("build_commonsense_qa_dataset", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(name, key):
    return {
        "id": name,
        "question": f"Where is {name}?",
        "choices": {"label": list("ABCDE"), "text": [f"{name}-{c}" for c in "abcde"]},
        "answerKey": key,
    }


TRAIN = [record(f"t{i}", "ABCDE"[i % 5]) for i in range(60)]
HELD_OUT = [record(f"v{i}", "ABCDE"[i % 5]) for i in range(10)]


def test_splits_draw_from_train_and_keep_the_official_validation_whole():
    b = builder()
    splits = b.splits(TRAIN, HELD_OUT, train=40, validation=10, seed=5)
    assert splits == b.splits(TRAIN, HELD_OUT, train=40, validation=10, seed=5)
    assert splits["validation"] != b.splits(TRAIN, HELD_OUT, train=40, validation=10, seed=6)["validation"]
    assert [len(splits[n]) for n in ("train", "validation", "test")] == [40, 10, 10]
    assert [r["question"] for r in splits["test"]] == [f"Where is v{i}?" for i in range(10)]  # whole, in order
    assert not {r["prompt"] for r in splits["train"]} & {r["prompt"] for r in splits["validation"]}
    row = splits["test"][4]
    assert set(row) == {"prompt", "question", "answer"} and row["answer"] == "E"
    for letter in "ABCDE":
        assert f"{letter}. v4-{letter.lower()}" in row["prompt"]
    assert "single letter" in row["prompt"]
    assert v3data.build([], splits=splits)["splitMode"] == "pre-split"
    spec = {
        "kind": "declarative",
        "name": "choice-letter",
        "version": 1,
        "codeSha256": None,
        "config": {"answerField": "answer"},
    }
    assert score(spec, [f"Answer: {row['answer']}", "Answer: A"], [row, row])[1] == [1.0, 0.0]
    with pytest.raises(ValueError):
        b.splits(TRAIN, HELD_OUT, train=55, validation=10, seed=5)


def test_a_record_that_is_not_five_labelled_choices_is_refused():
    b = builder()
    for bad in (
        {**HELD_OUT[0], "answerKey": ""},
        {**HELD_OUT[0], "answerKey": "F"},
        {**HELD_OUT[0], "choices": {"label": list("ABCD"), "text": list("abcd")}},
        {**HELD_OUT[0], "choices": {"label": list("ABCDF"), "text": list("abcde")}},
        {**HELD_OUT[0], "choices": {"label": list("ABCDE"), "text": list("abcd")}},
    ):
        with pytest.raises(ValueError):
            b.row(bad)


def test_the_source_files_are_checked(tmp_path):
    b = builder()
    bad = tmp_path / "train.parquet"
    bad.write_bytes(b"x")
    with pytest.raises(ValueError, match="SHA-256"):
        b.check_source(bad, "train")
