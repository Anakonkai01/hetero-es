"""A replacement installation retains frozen inputs, earlier selection and audit faults."""

import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from heteroes.canonical import canonical_json_hash
from heteroes.product.files import read_json, write_json
from heteroes.product.recovery import capture_point, restore_point, verify_point
from heteroes.product.v3 import prepare_run
from test_v3_product import product_assets, product_config, run_product  # noqa: F401


def completed_run(assets, root):
    root.mkdir()
    cfg = product_config(assets, root, weightSpace={"kind": "lora", "rank": 2, "alpha": 4, "targetModules": ["q_proj"]})
    write_json(root / "config.json", cfg)
    _, run, _ = prepare_run(cfg, root, "cpu")
    hashes = []
    for label in (b"parent", b"child", b"earlier best"):
        sha = hashlib.sha256(label).hexdigest()
        directory = root / ("selection" if label == b"earlier best" else "weights")
        directory.mkdir(exist_ok=True)
        (directory / f"{sha}.bin").write_bytes(label)
        hashes.append(sha)
    parent, child, best = hashes
    with sqlite3.connect(root / "ledger.sqlite") as db:
        db.execute("CREATE TABLE generation_update(generation INTEGER,child_weights_sha256 TEXT,applied_at REAL)")
        db.execute("INSERT INTO generation_update VALUES(0,?,1)", (child,))
    selection = {
        "generation": -1,
        "weightsSha256": best,
        "validationReward": 1.0,
        "recipeHash": run.hash,
        "planHash": run.plan_hash,
    }
    write_json(root / "study-selection.json", selection)
    for gen in (-1, 0):
        write_json(
            root / f"validation-{gen}.json",
            {
                "generation": gen,
                "recipeHash": run.hash,
                "planHash": run.plan_hash,
                "weightsSha256": best if gen == -1 else child,
                "meanReward": 1.0 if gen == -1 else 0.0,
            },
        )
    write_json(root / "study-metrics.json", {"best": selection, "testLocked": True})
    write_json(root / "audit-faults.json", {"bad-worker": {"reason": "RESTORE_MISMATCH", "candidateId": "a" * 64}})
    return cfg, run, {"generation": 0, "parent_sha256": parent, "child_sha256": child}


def test_replacement_preserves_v3_inputs_selection_and_faults(product_assets, tmp_path):
    root = tmp_path / "source"
    cfg, run, summary = completed_run(product_assets, root)
    point = capture_point(root, summary, run.to_dict(), {"interval": 1, "retain": 3})
    retained = tmp_path / "point"
    shutil.copytree(point, retained)
    old_selection = read_json(root / "study-selection.json")
    adapter_bytes = (root / "initial-adapter.bin").read_bytes()
    shutil.rmtree(root)
    restored = restore_point(retained, tmp_path / "replacement")
    assert read_json(retained / "manifest.json")["formatVersion"] == 2
    assert read_json(restored / "study-selection.json") == old_selection
    assert (restored / "selection" / f"{old_selection['weightsSha256']}.bin").read_bytes() == b"earlier best"
    assert [read_json(restored / f"validation-{g}.json")["generation"] for g in (-1, 0)] == [-1, 0]
    assert read_json(restored / "audit-faults.json")["bad-worker"]["reason"] == "RESTORE_MISMATCH"
    assert (restored / "initial-adapter.bin").read_bytes() == adapter_bytes
    restored_cfg = read_json(restored / "config.json")
    assert Path(restored_cfg["datasetPath"]) == restored / "dataset.json"
    assert read_json(restored / "study-metrics.json")["testLocked"]
    _, rebuilt, _ = prepare_run(restored_cfg, restored, "cpu")
    assert rebuilt.hash == run.hash and rebuilt.plan_hash == run.plan_hash
    assert (restored / "dispatch-held.flag").exists()
    assert not (restored / "study-export.json").exists()


def test_capture_refuses_missing_selection_instead_of_resetting(product_assets, tmp_path):
    root = tmp_path / "source"
    _, run, summary = completed_run(product_assets, root)
    (root / "study-selection.json").unlink()
    with pytest.raises(ValueError, match="selection"):
        capture_point(root, summary, run.to_dict(), {"interval": 1, "retain": 3})


def test_recovery_rejects_state_from_a_different_plan(product_assets, tmp_path):
    root = tmp_path / "source"
    _, run, summary = completed_run(product_assets, root)
    point = capture_point(root, summary, run.to_dict(), {"interval": 1, "retain": 3})
    state = read_json(point / "v3-state.json")
    state["plan"]["alpha"] = 0.25
    write_json(point / "v3-state.json", state)
    m = read_json(point / "manifest.json")
    raw = (point / "v3-state.json").read_bytes()
    m["files"]["v3-state.json"] = {"sha256": hashlib.sha256(raw).hexdigest(), "sizeBytes": len(raw)}
    write_json(point / "manifest.json", m)
    with pytest.raises(ValueError, match="plan|Plan"):
        verify_point(point)
    assert canonical_json_hash(state["plan"]) != run.plan_hash


@pytest.mark.parametrize(
    "space", [{"kind": "full"}, {"kind": "lora", "rank": 2, "alpha": 4, "targetModules": ["q_proj", "v_proj"]}]
)
def test_real_runner_resumes_a_v3_point_on_a_replacement_installation(product_assets, tmp_path, space):
    root = tmp_path / "source"
    root.mkdir()
    cfg = product_config(product_assets, root, weightSpace=space, backupPolicy={"interval": 1, "retain": 3})
    run_product(cfg, root)
    point = next(p for p in (root / "recovery-points").iterdir() if read_json(p / "manifest.json")["generation"] == 0)
    saved = tmp_path / "saved-point"
    shutil.copytree(point, saved)
    with sqlite3.connect(root / "ledger.sqlite") as db:
        expected = db.execute("SELECT child_weights_sha256 FROM generation_update ORDER BY generation").fetchall()
    selected = read_json(root / "study-selection.json")
    shutil.rmtree(root)
    restored = restore_point(saved, tmp_path / "replacement")
    # Operator maps the same pinned model onto a different installation's private path.
    new_model = tmp_path / "new-model"
    shutil.copytree(product_assets / "model", new_model)
    config = read_json(restored / "config.json")
    config["modelPath"] = str(new_model)
    run_product(config, restored)
    with sqlite3.connect(restored / "ledger.sqlite") as db:
        actual = db.execute("SELECT child_weights_sha256 FROM generation_update ORDER BY generation").fetchall()
    assert actual == expected
    assert read_json(restored / "study-selection.json") == selected
    assert read_json(restored / "study-export.json")["independentReloadPassed"]
