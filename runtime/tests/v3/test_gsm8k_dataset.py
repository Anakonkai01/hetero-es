"""The GSM8K dataset builder (runtime/scripts/build_gsm8k_dataset.py): validation from the official train split, the
official test split kept whole and held out, answers in the form the answer-line-last-number scorer compares."""

import importlib.util
from pathlib import Path

import pytest

from heteroes.v3 import data as v3data
from heteroes.v3.scoring import score


def builder():
    path = Path(__file__).resolve().parents[2] / "scripts" / "build_gsm8k_dataset.py"
    spec = importlib.util.spec_from_file_location("build_gsm8k_dataset", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TRAIN = [
    {"question": f"Tom has {i} apples. How many?", "answer": f"He has {i}.\n#### {i:,}"} for i in range(1000, 1060)
]
TEST = [{"question": f"Ann has {i} pears. How many?", "answer": f"#### {i}"} for i in range(10)]


def test_splits_keep_the_official_test_and_draw_validation_from_train():
    b = builder()
    splits = b.splits(TRAIN, TEST, train=40, validation=10, seed=5)
    assert splits == b.splits(TRAIN, TEST, train=40, validation=10, seed=5)
    assert splits["validation"] != b.splits(TRAIN, TEST, train=40, validation=10, seed=6)["validation"]
    assert [r["question"] for r in splits["train"]] != [r["question"] for r in TRAIN[:40]]  # a draw, not the head
    assert [len(splits[name]) for name in ("train", "validation", "test")] == [40, 10, 10]
    assert [r["question"] for r in splits["test"]] == [r["question"] for r in TEST]  # whole, in order
    train_questions = {r["question"] for r in TRAIN}
    assert all(r["question"] in train_questions for r in splits["train"] + splits["validation"])
    assert not {r["prompt"] for r in splits["train"]} & {r["prompt"] for r in splits["validation"]}
    row = splits["train"][0]
    assert set(row) == {"prompt", "question", "answer"} and row["question"] in row["prompt"]
    assert "Answer:" in row["prompt"] and "," not in row["answer"]  # "1,0xx" normalized to "10xx"
    document = v3data.build([], splits=splits)
    assert document["splitMode"] == "pre-split"
    spec = {"kind": "declarative", "name": "answer-line-last-number", "version": 1, "codeSha256": None, "config": {}}
    assert score(spec, [f"so...\nAnswer: {row['answer']}"], [row])[0] == 1.0
    with pytest.raises(ValueError):
        b.splits(TRAIN, TEST, train=55, validation=10, seed=5)


def test_the_source_files_are_checked(tmp_path):
    b = builder()
    bad = tmp_path / "train.parquet"
    bad.write_bytes(b"x")
    with pytest.raises(ValueError, match="SHA-256"):
        b.check_source(bad, "train")


def test_answers_are_normalized_like_the_runtime():
    from heteroes.study.data import answer

    b = builder()
    for text in ("#### 1,234", "#### 0", "#### -7", "#### 3.50", "#### 007", "x\n#### 12"):
        assert b.number(text) == answer(text, "gsm8k-v1")
