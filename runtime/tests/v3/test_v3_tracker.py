"""Validation uses the frozen scorer; test is read only after selection is complete."""

import pytest

from heteroes.product.files import read_json
from heteroes.v3.tracker import Tracker
from heteroes.product.v3 import prepare_run
from heteroes.model.weights_io import publish_weights
from test_v3_product import product_assets, product_config


def test_validation_interval_ties_and_test_lock(product_assets, tmp_path, monkeypatch):
    cfg = product_config(product_assets, tmp_path, maxGenerations=3)
    loaded, run, dataset = prepare_run(cfg, tmp_path, "cpu")
    seen = []

    def generate(model, tokenizer, rows, evaluation, chunk=16):
        seen.append(rows)
        return [{"output": row["label"]} for row in rows]

    monkeypatch.setattr("heteroes.v3.tracker.generate_rows", generate)
    tracker = Tracker(tmp_path, loaded, run, dataset, interval=2, model_path=cfg["modelPath"])
    weights = publish_weights(loaded.model, loaded.schema, tmp_path / "weights")
    tracker.observe(-1, weights)
    tracker.observe(0, weights)
    assert not (tmp_path / "validation-0.json").exists()
    tracker.observe(1, weights)
    tracker.observe(2, weights)  # the final generation always receives validation
    assert tracker.best["generation"] == -1  # ties preserve the earliest checkpoint
    assert tracker.best["validationReward"] == 1.0
    assert read_json(tmp_path / "study-metrics.json")["testLocked"] is True
    assert seen == [dataset["splits"]["validation"]] * 3
    assert read_json(tmp_path / "validation-2.json")["scorer"] == cfg["scorer"]
    repeated = Tracker(tmp_path, loaded, run, dataset, interval=2, model_path=cfg["modelPath"])
    assert repeated.best == tracker.best
    cfg["scorer"]["config"]["casefold"] = True
    loaded2, run2, _ = prepare_run(cfg, tmp_path / "different", "cpu")
    with pytest.raises(ValueError, match="selection"):
        Tracker(tmp_path, loaded2, run2, dataset)


@pytest.mark.parametrize(
    "space",
    [
        {"kind": "full"},
        {"kind": "subset", "include": [r"layers\.1\."]},
        {"kind": "lora", "rank": 2, "alpha": 4, "targetModules": ["q_proj"]},
    ],
)
def test_export_reloads_selected_space_and_repeats_test(product_assets, tmp_path, space):
    cfg = product_config(product_assets, tmp_path, weightSpace=space)
    loaded, run, dataset = prepare_run(cfg, tmp_path, "cpu")
    tracker = Tracker(tmp_path, loaded, run, dataset, model_path=cfg["modelPath"])
    from heteroes.es.perturb import perturb_model_

    perturb_model_(loaded.model, loaded.schema, 5, 0.05, run.chunk_elements)
    weights = publish_weights(loaded.model, loaded.schema, tmp_path / "weights")
    tracker.observe(-1, weights)
    receipt = tracker.export()
    assert receipt["weightsSha256"] == weights and receipt["independentReloadPassed"]
    assert receipt["test"]["split"] == "test" and receipt["test"]["scorer"] == cfg["scorer"]
    assert read_json(tmp_path / "study-metrics.json")["testLocked"] is False
    assert tracker.export() == receipt
    exported = tmp_path / "export" / next(iter(receipt["exportFiles"]))
    exported.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        tracker.export()


def test_a_better_validation_reward_replaces_the_selection(product_assets, tmp_path, monkeypatch):
    cfg = product_config(product_assets, tmp_path)
    loaded, run, dataset = prepare_run(cfg, tmp_path, "cpu")
    outputs = iter([False, True, True])

    def generate(model, tokenizer, rows, evaluation, chunk=16):
        correct = next(outputs)
        return [{"output": row["label"] if correct else "wrong"} for row in rows]

    monkeypatch.setattr("heteroes.v3.tracker.generate_rows", generate)
    tracker = Tracker(tmp_path, loaded, run, dataset)
    weights = publish_weights(loaded.model, loaded.schema, tmp_path / "weights")
    tracker.observe(-1, weights)
    tracker.observe(0, weights)
    tracker.observe(1, weights)
    assert tracker.best["generation"] == 0 and tracker.best["validationReward"] == 1


@pytest.mark.parametrize("failure", ["weights", "predictions"])
def test_independent_reload_mismatch_never_unlocks_test(product_assets, tmp_path, monkeypatch, failure):
    cfg = product_config(product_assets, tmp_path)
    loaded, run, dataset = prepare_run(cfg, tmp_path, "cpu")
    tracker = Tracker(tmp_path, loaded, run, dataset)
    weights = publish_weights(loaded.model, loaded.schema, tmp_path / "weights")
    tracker.observe(-1, weights)
    if failure == "weights":
        monkeypatch.setattr("heteroes.v3.tracker.model_weights_sha256", lambda *args: "0" * 64)
    else:
        outputs = iter(["first test output", "different after reload"])

        def generate(model, tokenizer, rows, evaluation, chunk=16):
            output = next(outputs)
            return [{"output": output} for row in rows]

        monkeypatch.setattr("heteroes.v3.tracker.generate_rows", generate)
    with pytest.raises(ValueError, match="reload"):
        tracker.export()
    assert not (tmp_path / "study-export.json").exists()
    assert read_json(tmp_path / "study-metrics.json")["testLocked"] is True
