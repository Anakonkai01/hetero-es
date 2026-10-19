"""Recipe v3 datasets (any columns, a prompt) and the run object the coordinator and executor read."""

import json

import pytest

from heteroes.canonical import canonical_json_hash
from heteroes.study import data as v2data
from heteroes.v3 import data as v3data
from heteroes.v3.documents import from_v1
from heteroes.v3.run import RecipeV3Run, build_documents, make_scorer

ROWS = [{"question": f"Q{i}?", "answer": f"A{i}", "level": i % 3, "ok": i % 2 == 0, "note": None} for i in range(20)]


def test_rows_are_read_from_json_jsonl_and_csv_with_their_columns(tmp_path):
    (tmp_path / "r.jsonl").write_text("\n".join(json.dumps(r) for r in ROWS))
    (tmp_path / "r.json").write_text(json.dumps(ROWS))
    (tmp_path / "r.csv").write_text("question,answer\n" + "\n".join(f"{r['question']},{r['answer']}" for r in ROWS))
    for name in ("r.jsonl", "r.json"):
        rows = v3data.read_rows(tmp_path / name, "question")
        assert rows[3] == {**ROWS[3], "prompt": "Q3?"}
    assert v3data.read_rows(tmp_path / "r.csv", "question")[0] == {"question": "Q0?", "answer": "A0", "prompt": "Q0?"}
    with pytest.raises(ValueError):
        v3data.read_rows(tmp_path / "r.jsonl", "missing")
    (tmp_path / "r.txt").write_text("x")
    with pytest.raises(ValueError):
        v3data.read_rows(tmp_path / "r.txt")


@pytest.mark.parametrize(
    "bad", [{"prompt": "  "}, {"prompt": "x", "nested": {"a": 1}}, {"prompt": "x", "v": float("nan")}]
)
def test_rows_hold_only_plain_values_and_a_real_prompt(bad):
    with pytest.raises(ValueError):
        v3data.build([bad] + [{"prompt": f"p{i}"} for i in range(10)])


def test_a_file_with_a_nan_cell_is_refused_when_read(tmp_path):
    (tmp_path / "r.jsonl").write_text(
        '{"prompt": "x", "score": NaN}\n'
    )  # Python's json reads NaN: the reader must refuse it
    with pytest.raises(ValueError):
        v3data.read_rows(tmp_path / "r.jsonl")


def test_a_dataset_is_split_hashed_and_refuses_leaked_prompts():
    rows = [{**r, "prompt": r["question"]} for r in ROWS]
    value = v3data.build(rows, split_seed=7)
    assert [len(value["splits"][s]) for s in ("train", "validation", "test")] == [16, 2, 2]
    assert v3data.verify(value) is value and v3data.build(rows, split_seed=7) == value
    assert v3data.build(rows, split_seed=8)["contentHash"] != value["contentHash"]
    tampered = json.loads(json.dumps(value))
    tampered["splits"]["train"][0]["answer"] = "changed"
    with pytest.raises(ValueError):
        v3data.verify(tampered)
    with pytest.raises(ValueError, match="twice"):
        v3data.build(rows + [{"prompt": "Q1?   "}])
    with pytest.raises(ValueError):
        v3data.build(rows[:9])


def test_the_batch_sampler_is_the_recipe_v2_one():
    v3 = v3data.build([{"prompt": f"p{i}", "answer": str(i)} for i in range(30)])
    for generation in range(3):
        selected = v3data.batch(v3, generation, 5, 11)
        # the same rule as Recipe v2, over this dataset's content hash
        digest = v2data.sha(
            {"dataset": v3["contentHash"], "generation": generation, "seed": 11, "sampler": v3data.SAMPLER}
        )
        import random

        assert selected["indices"] == random.Random(int(digest, 16)).sample(range(len(v3["splits"]["train"])), 5)
        assert selected["hash"] == canonical_json_hash(selected["rows"])
    with pytest.raises(ValueError):
        v3data.batch(v3, 0, 0, 11)


def documents(scorer=None, **config):
    dataset = v3data.build([{"prompt": f"p{i}", "answer": str(i)} for i in range(30)])
    scorer = scorer or {"kind": "declarative", "name": "exact-string", "version": 1, "codeSha256": None,
                        "config": {"answerField": "answer", "strip": True, "casefold": False}}  # fmt: skip
    base = {"model": {"id": "tiny"}, "sigma": {"initial": 0.01}, "population": 4, "generations": 3, "alpha": 0.1,
            "batchSize": 3, "scorerSpec": scorer}  # fmt: skip
    recipe, plan = build_documents(
        {**base, **config},
        model_files={"config.json": "a" * 64, "model.safetensors": "b" * 64},
        revision="c" * 40,
        schema_hash="d" * 64,
        generation_config_sha256="e" * 64,
        dataset=dataset,
    )
    return recipe, plan, dataset


def test_the_generation_context_freezes_sigma_batch_scorer_and_rule():
    recipe, plan, dataset = documents(sigma={"kind": "cosine", "initial": 0.01, "minimum": 0.001})
    run = RecipeV3Run(recipe, plan)
    first, last = run.context(dataset, 0), run.context(dataset, 2)
    assert first["scorer"] == plan["scorer"] and first["coefficientRule"] == plan["coefficientRule"]
    assert first["recipeHash"] == run.hash and first["planHash"] == canonical_json_hash(plan)
    assert first["sigmaFloat32"] > last["sigmaFloat32"] and first["batchIndices"] != last["batchIndices"]
    assert first["contextHash"] == canonical_json_hash({k: v for k, v in first.items() if k != "contextHash"})
    other = v3data.build([{"prompt": f"q{i}"} for i in range(30)])
    with pytest.raises(ValueError, match="differs"):
        run.context(other, 0)


def test_the_scorer_of_a_run_reads_the_rows_of_its_generation():
    recipe, plan, dataset = documents()
    run = RecipeV3Run(recipe, plan)
    rows = run.batch(dataset, 1)["rows"]
    score = make_scorer(run, dataset)
    assert score(1, None, [row["answer"] for row in rows]) == 1.0
    assert score(1, None, ["wrong"] * len(rows)) == 0.0


def test_a_run_needs_an_imported_dataset_and_a_loaded_python_scorer():
    import copy

    golden = json.loads(open(__file__.replace("v3/test_v3_data_run.py", "fixtures/golden-identities.json")).read())
    translated, fixed = from_v1(golden["recipes"][0]["recipe"])
    translated = copy.deepcopy(translated)
    translated["model"]["files"] = {"config.json": "a" * 64}
    plan = {"formatVersion": 1, "recipeHash": canonical_json_hash(translated), "population": 4, "generations": 1,
            "alpha": 0.1, **fixed}  # fmt: skip
    with pytest.raises(ValueError, match="imported dataset"):
        RecipeV3Run(translated, plan)
    python = {"kind": "python", "name": "mine", "version": 1, "codeSha256": "f" * 64, "config": {}}
    recipe, plan, dataset = documents(scorer=python)
    with pytest.raises(ValueError, match="loaded"):
        make_scorer(RecipeV3Run(recipe, plan), dataset)
