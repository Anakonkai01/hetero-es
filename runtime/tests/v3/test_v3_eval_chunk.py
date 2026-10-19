"""
`evaluation.chunk` of Recipe v3: prompts per generate() call, part of the recipe because a different batch shape may change
a greedy text. Absent means 16, the chunk of every v3 document written before the key existed (their hashes stay valid).
"""

import copy

import pytest

from heteroes.executor import CandidateExecutor
from heteroes.v3.documents import from_v2, validate_recipe
from heteroes.v3.local import prepare

from test_v3_documents import v2_recipe
from test_v3_local import assets, config_for  # noqa: F401  (assets is a fixture)


def with_chunk(doc, chunk, dtype="float32"):
    changed = copy.deepcopy(doc)
    changed["evaluation"]["evalDtype"] = dtype
    changed["evaluation"]["chunk"] = chunk
    return changed


def test_a_recipe_may_declare_an_exact_chunk_of_its_precision():
    doc, _ = from_v2(v2_recipe().to_dict())
    assert "chunk" not in doc["evaluation"] and validate_recipe(doc)
    for chunk in (16, 32, 64):
        assert validate_recipe(with_chunk(doc, chunk))
    assert validate_recipe(with_chunk(doc, 1, "float16"))
    for bad in (with_chunk(doc, 8), with_chunk(doc, 128), with_chunk(doc, 64.0), with_chunk(doc, True),
                with_chunk(doc, 16, "float16"), with_chunk(doc, None)):  # fmt: skip
        with pytest.raises(ValueError, match="chunk"):
            validate_recipe(bad)


def test_the_chunk_is_written_only_when_chosen_and_the_executor_follows_it(assets, tmp_path):  # noqa: F811
    legacy = prepare(config_for(assets), tmp_path / "legacy")
    assert "chunk" not in legacy["run"].recipe["evaluation"] and legacy["run"].chunk is None
    chosen = prepare(config_for(assets, evalChunk=32), tmp_path / "chosen")
    run = chosen["run"]
    assert run.recipe["evaluation"]["chunk"] == 32 and run.chunk == 32
    assert run.hash != legacy["run"].hash

    def executor(ready, chunk=None):
        return CandidateExecutor(
            ready["model"], ready["tokenizer"], ready["schema"], ready["run"], chunk=chunk, dataset=ready["dataset"]
        )

    assert executor(chosen).chunk == 32 and executor(chosen, 32).chunk == 32
    with pytest.raises(ValueError, match="recipe"):
        executor(chosen, 16)
    assert executor(legacy).chunk == 16 and executor(legacy, 2).chunk == 2  # a worker's choice, as before


def test_a_local_run_may_read_three_given_splits(assets, tmp_path):  # noqa: F811
    import json

    rows = [json.loads(line) for line in (assets / "rows.jsonl").read_text().splitlines()]
    paths = {}
    for name, part in (("train", rows[:12]), ("validation", rows[12:16]), ("test", rows[16:])):
        paths[name] = tmp_path / f"{name}.jsonl"
        paths[name].write_text("".join(json.dumps(r) + "\n" for r in part))
    config = config_for(assets)
    config["data"] = {k: v for k, v in config["data"].items() if k != "path"} | {
        "splits": {k: str(v) for k, v in paths.items()}
    }
    ready = prepare(config, tmp_path / "run")
    assert ready["dataset"]["splitMode"] == "pre-split"
    assert [len(ready["dataset"]["splits"][n]) for n in ("train", "validation", "test")] == [12, 4, len(rows) - 16]


def test_the_command_line_resolves_split_and_rule_paths(tmp_path):
    from heteroes.v3.__main__ import _resolve

    spec = {
        "data": {"splits": {"train": "a.jsonl", "validation": "/abs/b.jsonl", "test": "c.jsonl"}},
        "coefficientRule": {"kind": "python", "path": "rule.py", "function": "f"},
    }
    resolved = _resolve(spec, tmp_path)
    assert resolved["data"]["splits"] == {
        "train": str(tmp_path / "a.jsonl"), "validation": "/abs/b.jsonl", "test": str(tmp_path / "c.jsonl"),
    }  # fmt: skip
    assert resolved["coefficientRule"]["path"] == str(tmp_path / "rule.py")
    assert _resolve({"coefficientRule": "zscore@1"}, tmp_path) == {"coefficientRule": "zscore@1"}
