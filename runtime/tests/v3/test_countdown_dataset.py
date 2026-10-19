"""The Countdown dataset builder (runtime/scripts/build_countdown_dataset.py): a fixed, pinned subset in v3 row format."""

import importlib.util
import json
from pathlib import Path

import pytest

from heteroes.v3 import data as v3data
from heteroes.v3.scoring import score


def builder():
    path = Path(__file__).resolve().parents[2] / "scripts" / "build_countdown_dataset.py"
    spec = importlib.util.spec_from_file_location("build_countdown_dataset", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RECORDS = [{"target": 10 + i % 50, "nums": [i % 7 + 1, i % 11 + 2, i % 13 + 3]} for i in range(300)]


def test_rows_are_a_seeded_distinct_subset_with_scalar_columns():
    b = builder()
    rows = b.select_rows(RECORDS, count=40, seed=7)
    assert rows == b.select_rows(RECORDS, count=40, seed=7)
    assert rows != b.select_rows(RECORDS, count=40, seed=8)
    assert len(rows) == 40 and len({r["prompt"] for r in rows}) == 40
    for row in rows:
        assert set(row) == {"prompt", "nums", "target", "sourceIndex"}
        source = RECORDS[row["sourceIndex"]]
        assert row["nums"] == " ".join(map(str, source["nums"])) and row["target"] == source["target"]
        assert str(source["nums"]) in row["prompt"] and f"equals {source['target']}" in row["prompt"]
        assert "<answer>" in row["prompt"]
    # the rows are what a v3 dataset accepts, and the countdown scorer reads their columns
    v3data.build(rows, split_seed=42)
    first = rows[0]
    expression = " + ".join(first["nums"].split())
    spec = {"kind": "declarative", "name": "countdown", "version": 1, "codeSha256": None}
    spec["config"] = {"numbersField": "nums", "targetField": "target"}
    reward = score(spec, [f"<answer>{expression}</answer>"], [first])[0]
    assert reward == (1.0 if sum(map(int, first["nums"].split())) == first["target"] else 0.1)


def test_duplicate_prompts_are_skipped_and_too_few_records_refused():
    b = builder()
    same = [{"target": 5, "nums": [1, 4]}] * 10 + [{"target": 6, "nums": [2, 4]}]
    rows = b.select_rows(same, count=2, seed=1)
    assert len({r["prompt"] for r in rows}) == 2 and 10 in {r["sourceIndex"] for r in rows}
    with pytest.raises(ValueError, match="distinct"):
        b.select_rows(same, count=3, seed=1)


def test_the_source_file_is_checked_before_use(tmp_path):
    b = builder()
    bad = tmp_path / "train.parquet"
    bad.write_bytes(b"not the pinned file")
    with pytest.raises(ValueError, match="SHA-256"):
        b.check_source(bad)


def test_write_gives_jsonl_and_its_identity(tmp_path):
    b = builder()
    rows = b.select_rows(RECORDS, count=20, seed=3)
    meta = b.write(rows, tmp_path / "countdown.jsonl", seed=3)
    assert v3data.read_rows(tmp_path / "countdown.jsonl") == rows
    assert meta["rows"] == 20 and meta["selectionSeed"] == 3 and meta["sourceRevision"] == b.REVISION
    assert meta["fileSha256"] and json.loads((tmp_path / "countdown.jsonl.meta.json").read_text()) == meta
