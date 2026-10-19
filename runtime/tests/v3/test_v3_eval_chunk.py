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
