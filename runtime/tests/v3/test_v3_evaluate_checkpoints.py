"""runtime/scripts/v3_evaluate_checkpoints.py: rebuild checkpoints of a local v3 run by replay and score a split."""

import importlib.util
import json
from pathlib import Path

import pytest

from heteroes.study.evaluation import generate_rows
from heteroes.v3.local import run_local
from heteroes.v3.model import file_manifest, load
from heteroes.v3.scoring import score

from test_v3_local import assets, config_for  # noqa: F401  (assets is a fixture)
from test_v3_product import product_assets, product_config, run_product


def tool():
    path = Path(__file__).resolve().parents[2] / "scripts" / "v3_evaluate_checkpoints.py"
    spec = importlib.util.spec_from_file_location("v3_evaluate_checkpoints", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCORER = {
    "kind": "declarative",
    "name": "exact-string",
    "config": {"answerField": "answer", "strip": True, "casefold": True},
}


def test_managed_file_dataset_is_evaluated_and_bound_to_the_recipe(product_assets, tmp_path):
    from heteroes.canonical import canonical_json_hash
    from heteroes.product.files import write_json
    from heteroes.v3.data import build_file_dataset, build

    root = tmp_path / "run"
    root.mkdir()
    cfg = product_config(product_assets, root)
    source = tmp_path / "rows.jsonl"
    source.write_text("".join(json.dumps({"prompt": f"Question {i}?", "label": str(i)}) + "\n" for i in range(20)))
    data_dir = tmp_path / "data"
    document = build_file_dataset({"all": (source, "jsonl")}, data_dir)
    import shutil

    for file in data_dir.iterdir():
        shutil.copyfile(file, root / file.name)
    cfg.update(
        datasetPath=str(root / "dataset.json"), datasetIdentity={k: document[k] for k in ("contentHash", "splitHashes")}
    )
    run_product(cfg, root)
    report = tool().evaluate(root, product_assets / "model", [-1, 0], "validation")
    expected = [
        json.loads(line) for line in (root / f"{document['splitHashes']['validation']}.jsonl").read_text().splitlines()
    ]
    assert report["rowsHash"] == canonical_json_hash(expected)
    assert all(c["count"] == len(expected) for c in report["checkpoints"])
    # A valid but unrelated dataset must not silently become this run's evaluation data.
    replacement = build([{"prompt": f"Unrelated {i}?"} for i in range(20)])
    write_json(root / "dataset.json", replacement)
    with pytest.raises(ValueError, match="dataset identity"):
        tool().evaluate(root, product_assets / "model", [0], "validation")
    # Same split files, different recorded provenance: still not the recipe's dataset.
    body = {key: value for key, value in document.items() if key != "contentHash"}
    body["splitSeed"] += 1
    write_json(root / "dataset.json", {**body, "contentHash": canonical_json_hash(body)})
    with pytest.raises(ValueError, match="dataset identity"):
        tool().evaluate(root, product_assets / "model", [0], "validation")


def test_checkpoints_are_rebuilt_by_replay_and_scored(assets, tmp_path):  # noqa: F811
    out = tmp_path / "run"
    summaries = run_local(config_for(assets, generations=3), out, workers=1, timeout_seconds=30)
    assert any(not s["noop"] for s in summaries)
    module = tool()
    with pytest.raises(ValueError, match="scorer"):
        module.evaluate(out, assets / "model", [0], "validation", device="cpu")
    report = module.evaluate(
        out, assets / "model", [-1, 0, 2], "validation", "cpu", assets / "scorer.py", "distinct_characters"
    )
    assert [r["generation"] for r in report["checkpoints"]] == [-1, 0, 2]
    assert [r["weightsSha256"] for r in report["checkpoints"][1:]] == [
        summaries[0]["child_sha256"],
        summaries[2]["child_sha256"],
    ]
    # the base checkpoint is the untouched model, evaluated the same way
    dataset = json.loads((out / "dataset.json").read_text())
    rows = dataset["splits"]["validation"]
    model, tokenizer = load(assets / "model", file_manifest(assets / "model"))
    raw = generate_rows(model.float(), tokenizer, rows, {"systemPrompt": None, "maxNewTokens": 8}, 16)
    plan = json.loads((out / "plan.json").read_text())
    base = report["checkpoints"][0]
    namespace = {}
    exec((assets / "scorer.py").read_text(), namespace)
    expected = score(plan["scorer"], [r["output"] for r in raw], rows, namespace["distinct_characters"])[0]
    assert base["meanReward"] == expected
    assert report["checkpoints"][2]["outputs"] != base["outputs"]  # premise: the weights changed the answers
    assert base["outputs"] == [r["output"] for r in raw] and base["count"] == len(rows)
    assert set(base) >= {"scoreCounts", "truncated", "meanCharacters"}


def test_a_wrong_record_chain_is_refused(assets, tmp_path):  # noqa: F811
    out = tmp_path / "run"
    run_local(config_for(assets, scorer=SCORER, generations=1), out, workers=1, timeout_seconds=30)
    module = tool()
    with pytest.raises(ValueError, match="generation"):
        module.evaluate(out, assets / "model", [3], "validation", device="cpu")
    with pytest.raises(ValueError, match="split"):
        module.evaluate(out, assets / "model", [0], "everything", device="cpu")


def test_a_replay_that_does_not_reach_the_recorded_child_is_refused(assets, tmp_path, monkeypatch):  # noqa: F811
    out = tmp_path / "run"
    summaries = run_local(config_for(assets, generations=1), out, workers=1, timeout_seconds=30)
    assert not summaries[0]["noop"]  # premise: the recorded child differs from the base
    monkeypatch.setattr("heteroes.es.update.apply_coefficients_", lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match="does not hash"):
        tool().evaluate(out, assets / "model", [0], "validation", "cpu", assets / "scorer.py", "distinct_characters")


def test_a_checkpoint_is_scored_on_other_rows_with_another_scorer(assets, tmp_path):  # noqa: F811
    out = tmp_path / "run"
    run_local(config_for(assets, scorer=SCORER, generations=2), out, workers=1, timeout_seconds=30)
    module = tool()
    other = [
        {"prompt": "Pick a letter.", "label": "A"},
        {"prompt": "Pick again.", "label": "B"},
        {"prompt": "Q", "label": "E"},
    ]
    letter = {
        "kind": "declarative",
        "name": "choice-letter",
        "version": 1,
        "codeSha256": None,
        "config": {"answerField": "label"},
    }
    report = module.evaluate(out, assets / "model", [-1, 1], "validation", "cpu", rows=other, rows_scorer=letter)
    base, trained = report["checkpoints"]
    assert (base["split"], base["count"]) == ("external", 3) and len(trained["outputs"]) == 3
    assert report["externalScorer"] == letter
    model, tokenizer = load(assets / "model", file_manifest(assets / "model"))
    raw = generate_rows(model.float(), tokenizer, other, {"systemPrompt": None, "maxNewTokens": 8}, 16)
    assert base["outputs"] == [r["output"] for r in raw]  # the run's decoding, on the other rows
    assert base["meanReward"] == score(letter, base["outputs"], other)[0]
    with pytest.raises(ValueError, match="together"):
        module.evaluate(out, assets / "model", [0], "validation", "cpu", rows=other)
    with pytest.raises(ValueError, match="unknown declarative"):
        module.evaluate(
            out, assets / "model", [0], "validation", "cpu", rows=other, rows_scorer={**letter, "name": "nope"}
        )
    with pytest.raises(ValueError, match="only declarative"):
        module.evaluate(
            out,
            assets / "model",
            [0],
            "validation",
            "cpu",
            rows=other,
            rows_scorer={**letter, "kind": "python", "codeSha256": "0" * 64},
        )
    path = tmp_path / "rows.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in other), encoding="utf-8")
    (tmp_path / "scorer.json").write_text(json.dumps(letter), encoding="utf-8")
    target = tmp_path / "report.json"
    module.main(
        [
            str(out),
            "--model-path",
            str(assets / "model"),
            "--generations",
            "-1",
            "--rows",
            str(path),
            "--rows-scorer",
            str(tmp_path / "scorer.json"),
            "--out",
            str(target),
        ]
    )
    assert json.loads(target.read_text())["checkpoints"][0]["meanReward"] == base["meanReward"]
