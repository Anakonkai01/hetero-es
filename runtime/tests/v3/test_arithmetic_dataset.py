"""The arithmetic dataset builder (runtime/scripts/build_arithmetic_dataset.py): seeded, distinct, boxed-number rows."""

import importlib.util
import json
from pathlib import Path

import pytest

from heteroes.v3 import data as v3data
from heteroes.v3.scoring import score


def builder():
    path = Path(__file__).resolve().parents[2] / "scripts" / "build_arithmetic_dataset.py"
    spec = importlib.util.spec_from_file_location("build_arithmetic_dataset", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCORER = {
    "kind": "declarative",
    "name": "boxed-number",
    "version": 1,
    "codeSha256": None,
    "config": {"answerField": "answer", "formatReward": 0.1},
}


def test_rows_are_seeded_distinct_balanced_and_correct():
    b = builder()
    rows = b.build_rows(200, seed=5)
    assert rows == b.build_rows(200, seed=5) and rows != b.build_rows(200, seed=6)
    assert len({r["prompt"] for r in rows}) == 200
    assert sum(r["kind"] == "mul3x1" for r in rows) == sum(r["kind"] == "mul2x2" for r in rows) == 100
    for row in rows:
        left, right = row["prompt"].removeprefix("What is ").split("?")[0].split(" * ")
        assert int(left) * int(right) == int(row["answer"])
        low, high = (100, 999) if row["kind"] == "mul3x1" else (11, 99)
        assert low <= int(left) <= high
        assert (2 <= int(right) <= 9) if row["kind"] == "mul3x1" else (11 <= int(right) <= 99)
        assert row["prompt"].endswith("Reply with only the final number inside \\boxed{}, no explanation.")


def test_the_boxed_number_scorer_reads_the_rows():
    rows = builder().build_rows(3, seed=1)
    answers = [f"\\boxed{{{rows[0]['answer']}}}", "\\boxed{1}", "no box"]
    mean, per_row = score(SCORER, answers, rows)
    assert per_row == [1.0, 0.1, 0.0] and mean == pytest.approx(1.1 / 3)


def test_written_file_imports_as_a_v3_dataset_with_its_meta(tmp_path):
    b = builder()
    meta = b.write(b.build_rows(40, seed=3), tmp_path / "a.jsonl", 3)
    assert meta == json.loads((tmp_path / "a.jsonl.meta.json").read_text())
    assert meta["fileSha256"] == b.sha256(tmp_path / "a.jsonl") and meta["rows"] == 40
    rows = [json.loads(line) for line in (tmp_path / "a.jsonl").read_text().splitlines()]
    document = v3data.build(rows, split_seed=42)
    assert sum(len(document["splits"][name]) for name in v3data.SPLITS) == 40
    assert b.main(["--out", str(tmp_path / "b.jsonl"), "--rows", "10", "--seed", "3"]) == 0
    with pytest.raises(SystemExit):
        b.main(["--out", str(tmp_path / "b.jsonl")])
