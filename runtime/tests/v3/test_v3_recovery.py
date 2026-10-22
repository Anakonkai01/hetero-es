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


def completed_run(assets, root, *, file_dataset=False):
    root.mkdir()
    cfg = product_config(assets, root, weightSpace={"kind": "lora", "rank": 2, "alpha": 4, "targetModules": ["q_proj"]})
    if file_dataset:
        from heteroes.v3.data import build_file_dataset

        original = read_json(root / "dataset.json")
        sources = {}
        for name, rows in original["splits"].items():
            path = root / (name + "-source.jsonl")
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            sources[name] = path, "jsonl"
        dataset = build_file_dataset(sources, root / "file-dataset")
        cfg["datasetPath"] = str(root / "file-dataset/dataset.json")
        cfg["datasetIdentity"] = {key: dataset[key] for key in ("contentHash", "splitHashes")}
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


def test_recovery_preserves_file_backed_splits_lora_and_optional_usage(product_assets, tmp_path):
    from heteroes.manifest import CandidateDescriptor
    from heteroes.v3.usage import UsageStore

    root = tmp_path / "source"
    cfg, run, summary = completed_run(product_assets, root, file_dataset=True)
    usage = UsageStore(root / "usage.sqlite")
    usage.record(
        CandidateDescriptor(run.hash, summary["parent_sha256"], cfg["runId"], 0, 0, 5),
        1,
        "worker",
        {"formatVersion": 1, "device": "cuda", "generatedTokens": [3, 4], "wallSeconds": 2.5},
    )
    usage.record_update(0, 0.5)
    point = capture_point(root, summary, run.to_dict(), {"interval": 1, "retain": 3})
    assert len(read_json(point / "manifest.json")["files"]) == 12
    retained = tmp_path / "retained"
    shutil.copytree(point, retained)
    shutil.rmtree(root)
    restored = restore_point(retained, tmp_path / "replacement")
    actual = UsageStore(restored / "usage.sqlite", create=False).summary(
        0, expected_candidates=1, expected_audits=0, expected_updates=1
    )
    assert actual["generatedTokens"] == 7 and actual["gpuSeconds"] == 3 and not actual["partial"]
    _, rebuilt, data = prepare_run(read_json(restored / "config.json"), restored, "cpu")
    assert rebuilt.hash == run.hash and len(data["splits"]["train"]) > 0


def test_file_backed_recovery_also_works_without_usage_receipts(product_assets, tmp_path):
    root = tmp_path / "source"
    _, run, summary = completed_run(product_assets, root, file_dataset=True)
    point = capture_point(root, summary, run.to_dict(), {"interval": 1, "retain": 3})
    assert verify_point(point)["formatVersion"] == 2


def test_recovery_preserves_terminal_worker_blocks(product_assets, tmp_path):
    root = tmp_path / "source"
    _, run, summary = completed_run(product_assets, root)
    blocks = {"fixture": {"reason": "needs_private_route", "blockedAt": 123.0}}
    write_json(root / "worker-blocks.json", blocks)
    point = capture_point(root, summary, run.to_dict(), {"interval": 1, "retain": 3})
    restored = restore_point(point, tmp_path / "replacement")
    assert read_json(restored / "worker-blocks.json") == blocks


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


def test_download_restore_cli_accepts_v3_objects(product_assets, tmp_path, monkeypatch):
    import importlib.util
    import io
    import sys
    import urllib.request

    root = tmp_path / "source"
    _, run, summary = completed_run(product_assets, root)
    point = capture_point(root, summary, run.to_dict(), {"interval": 1, "retain": 3})
    manifest = read_json(point / "manifest.json")
    script = Path(__file__).resolve().parents[3] / "scripts/recovery.py"
    spec = importlib.util.spec_from_file_location("recovery_cli", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    credentials = tmp_path / "private.json"
    write_json(credentials, {"users": {"admin": "fixture-only"}})
    destination = tmp_path / "downloaded"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            "restore",
            "--url",
            "https://fixture.invalid",
            "--runtime-root",
            str(script.parent.parent / "runtime"),
            "--point-id",
            manifest["pointId"],
            "--destination",
            str(destination),
            "--credentials-file",
            str(credentials),
        ],
    )

    def request(url, **kwargs):
        url = url.full_url if isinstance(url, urllib.request.Request) else url
        if url.endswith("/auth/login"):
            payload = json.dumps({"accessToken": "fixture-only"}).encode()
        elif url.endswith("/download-plan"):
            payload = json.dumps(
                {
                    "manifest": manifest,
                    "objects": {name: "https://fixture.invalid/files/" + name for name in manifest["files"]},
                }
            ).encode()
        elif "/files/" in url:
            payload = (point / url.split("/files/", 1)[1]).read_bytes()
        elif url.endswith("/auth/logout"):
            payload = b"{}"
        else:
            raise AssertionError("Unexpected fixture request")
        return io.BytesIO(payload)

    monkeypatch.setattr(urllib.request, "urlopen", request)
    assert module.main() == 0
    assert read_json(destination / "study-selection.json") == read_json(root / "study-selection.json")
