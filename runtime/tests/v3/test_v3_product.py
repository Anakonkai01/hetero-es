"""Managed runner and the shipped worker CLI exchange texts over real HTTP on CPU."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from heteroes.canonical import canonical_json_hash
from heteroes.product.files import read_json, write_json
from heteroes.v3 import data
from heteroes.v3.model import file_manifest
from heteroes.v3.scoring import score
from heteroes.ledger import Ledger
from tinylm import build_tiny_lm


@pytest.fixture(scope="module")
def product_assets(tmp_path_factory):
    root = tmp_path_factory.mktemp("product-model")
    build_tiny_lm(root / "model")
    return root


def product_config(assets, root, **changes):
    rows = [{"prompt": f"What is {i} plus 2?", "label": str(i + 2)} for i in range(20)]
    dataset = data.build(rows)
    write_json(root / "dataset.json", dataset)
    files = file_manifest(assets / "model")
    manifest = {
        "formatVersion": 1,
        "modelId": "tiny/qwen2",
        "revision": canonical_json_hash(files)[:40],
        "tokenizerRevision": canonical_json_hash(files)[:40],
        "format": "safetensors",
        "files": files,
    }
    write_json(root / "model-manifest.json", manifest)
    return {
        "runId": "a" * 32,
        "recipeVersion": 3,
        "modelPath": str(assets / "model"),
        "modelManifest": manifest,
        "modelManifestPath": str(root / "model-manifest.json"),
        "datasetPath": str(root / "dataset.json"),
        "datasetIdentity": {k: dataset[k] for k in ("contentHash", "splitHashes")},
        "maxGenerations": 2,
        "candidatesPerGeneration": 4,
        "alpha": 0.5,
        "sigma": 0.5,
        "sigmaMinimum": 0.1,
        "sigmaSchedule": "cosine",
        "batchSize": 3,
        "batchSeed": 11,
        "maxNewTokens": 4,
        "systemPrompt": None,
        "antithetic": True,
        "coefficientRule": "zscore@1",
        "weightSpace": {"kind": "full"},
        "scorer": {
            "kind": "declarative",
            "name": "exact-string",
            "version": 1,
            "codeSha256": None,
            "config": {"answerField": "label", "strip": True, "casefold": False},
        },
        "decodeEngine": "hf_generate",
        "workerIds": ["fixture"],
        "host": "127.0.0.1",
        "port": 0,
        "schedulerPolicy": "greedy-tail",
        "syncMode": "synchronous",
        "validationInterval": 1,
        **changes,
    }


def wait_for(predicate, process, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        if process.poll() is not None:
            raise AssertionError(f"process exited early: {process.returncode}")
        time.sleep(0.1)
    raise AssertionError("managed process timed out")


@pytest.mark.parametrize(
    "space",
    [
        {"kind": "full"},
        {"kind": "subset", "include": [r"layers\.1\."]},
        {"kind": "lora", "rank": 2, "alpha": 4, "targetModules": ["q_proj", "v_proj"]},
    ],
)
@pytest.mark.parametrize("decoder", ["hf_generate", "hf_fp32_cpu_guard_v1"])
def test_managed_runner_and_worker_cli_commit_texts(product_assets, tmp_path, space, decoder):
    run_product(
        product_config(
            product_assets, tmp_path, weightSpace=space, candidateSeedNamespace="fixture-fixed", decodeEngine=decoder
        ),
        tmp_path,
    )


def run_product(cfg, tmp_path, python_scorer=None):
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    cfg = {**cfg, "port": port}
    space = cfg["weightSpace"]
    write_json(tmp_path / "config.json", cfg)
    # the lab sends a worker the configuration without researcher code
    write_json(tmp_path / "worker-config.json", {k: v for k, v in cfg.items() if k != "pythonCode"})
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "HETEROES_TOKEN": "fixture-secret"}
    runner_log = (tmp_path / "runner-output.txt").open("w")
    worker_log = (tmp_path / "worker-output.txt").open("w")
    runner = subprocess.Popen(
        [sys.executable, "-m", "heteroes.product.runner", str(tmp_path), "--device", "cpu"],
        env=env,
        stdout=runner_log,
        stderr=runner_log,
    )
    worker = None
    try:
        wait_for(lambda: read_json(tmp_path / "runner.json", {}).get("status") == "PREPARING", runner)
        worker = subprocess.Popen(
            [
                sys.executable,
                "scripts/run_worker.py",
                "--model-path",
                cfg["modelPath"],
                "--model-manifest",
                cfg["modelManifestPath"],
                "--dataset",
                cfg["datasetPath"],
                "--run-config",
                str(tmp_path / "worker-config.json"),
                "--coordinator-url",
                f"http://127.0.0.1:{port}",
                "--worker-id",
                "fixture",
                "--device",
                "cpu",
                "--log",
                str(tmp_path / "worker.jsonl"),
                "--cache-dir",
                str(tmp_path / "cache"),
                "--chunk",
                "2",
                "--poll-seconds",
                "0.05",
                "--replay",
                "always",
            ],
            env=env,
            stdout=worker_log,
            stderr=worker_log,
        )
        wait_for(
            lambda: (
                (tmp_path / "worker.jsonl").exists() and "executor_ready" in (tmp_path / "worker.jsonl").read_text()
            ),
            worker,
        )
        (tmp_path / "start.flag").touch()
        assert worker.wait(timeout=75) == 0, (tmp_path / "worker-output.txt").read_text()[-4000:]
        (tmp_path / "workers-stopped.flag").touch()
        assert runner.wait(timeout=30) == 0, (tmp_path / "runner-output.txt").read_text()[-4000:]
        assert read_json(tmp_path / "runner.json")["status"] == "COMPLETED"
        events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
        assert next(e for e in events if e.get("event") == "managed_start")["schedulerPolicy"] == "greedy-tail"
        recipe, plan = read_json(tmp_path / "recipe.json"), read_json(tmp_path / "plan.json")
        assert recipe["weightSpace"]["kind"] == space["kind"]
        assert plan["scorer"] == cfg["scorer"]
        dataset = data.open_dataset(cfg["datasetPath"])
        with Ledger(tmp_path / "ledger.sqlite") as ledger:
            for generation in range(2):
                candidates = ledger.list_candidates(cfg["runId"], generation)
                assert [c.descriptor.sign for c in candidates] == [1, -1, 1, -1]
                from heteroes.manifest import derive_seed

                namespace = cfg.get("candidateSeedNamespace", cfg["runId"])
                assert [c.descriptor.seed for c in candidates] == [
                    derive_seed(namespace, generation, i // 2) for i in range(4)
                ]
                rows = data.batch(dataset, generation, 3, 11)["rows"]
                for candidate in candidates:
                    _, texts = ledger.get_completions(candidate.descriptor.candidate_id)
                    assert candidate.result.reward == score(cfg["scorer"], texts, rows, python_scorer)[0]
                update = ledger.get_update(cfg["runId"], generation)
                assert update.applied_at and update.record.coefficient_rule == cfg["coefficientRule"]
        metrics = read_json(tmp_path / "study-metrics.json")
        assert metrics["testLocked"] is False and metrics["independentReloadPassed"]
        assert [item["generation"] for item in metrics["validation"]] == [-1, 0, 1]
        assert read_json(tmp_path / "study-export.json")["planHash"] == canonical_json_hash(plan)
        assert not (tmp_path / "study-export-error.json").exists()
        if space["kind"] == "lora":
            initial = tmp_path / "weights" / (recipe["weightSpace"]["initialAdapterSha256"] + ".bin")
            assert initial.exists()
    finally:
        (tmp_path / "workers-stopped.flag").touch()
        for process in (worker, runner):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        runner_log.close()
        worker_log.close()


REWARD = "def reward(texts, rows):\n    return [float(len(t) % 5) for t in texts]\n"
RULE = "def coefficients(rewards):\n    m = sum(rewards) / len(rewards)\n    return [r - m for r in rewards]\n"


def test_managed_run_with_a_file_backed_dataset_and_a_python_reward_and_rule(product_assets, tmp_path):
    from heteroes.v3.scoring import source_sha256

    source = tmp_path / "rows.jsonl"
    source.write_text(
        "".join(json.dumps({"prompt": f"What is {i} plus 2?", "label": str(i + 2)}) + "\n" for i in range(20))
    )
    document = data.build_file_dataset({"all": (source, "jsonl")}, tmp_path / "data")
    code = [
        {"role": "scorer", "name": "reward.py", "function": "reward", "source": REWARD},
        {"role": "coefficients", "name": "rule.py", "function": "coefficients", "source": RULE},
    ]
    for entry in code:
        entry["codeSha256"] = source_sha256(entry["name"], entry["source"].encode())
    cfg = product_config(product_assets, tmp_path, candidateSeedNamespace="fixture-fixed")
    cfg.update(
        datasetPath=str(tmp_path / "data" / "dataset.json"),
        datasetIdentity={k: document[k] for k in ("contentHash", "splitHashes")},
        scorer={"kind": "python", "name": "length", "version": 1, "codeSha256": code[0]["codeSha256"], "config": {}},
        coefficientRule="python@1:" + code[1]["codeSha256"],
        pythonCode=code,
    )

    run_product(cfg, tmp_path, python_scorer=lambda texts, rows: [float(len(t) % 5) for t in texts])


def test_product_refuses_a_python_scorer_without_its_frozen_code_before_loading(product_assets, tmp_path):
    from heteroes.product.v3 import prepare_run

    cfg = product_config(product_assets, tmp_path)
    cfg["modelPath"] = "/missing-model"
    cfg["scorer"] = {"kind": "python", "name": "user-code", "version": 1, "codeSha256": "a" * 64, "config": {}}
    # the web lab accepts Python scorers since 2026-10-20 (ADR-008), but only with the code the plan pins
    with pytest.raises(ValueError, match="pythonCode"):
        prepare_run(cfg, tmp_path, "cpu")


def test_product_checks_dataset_identity(product_assets, tmp_path):
    from heteroes.product.v3 import prepare_run

    cfg = product_config(product_assets, tmp_path)
    cfg["datasetIdentity"]["contentHash"] = "0" * 64
    with pytest.raises(ValueError, match="dataset identity"):
        prepare_run(cfg, tmp_path, "cpu")


def test_frozen_run_documents_and_adapter_survive_restart(product_assets, tmp_path):
    from heteroes.product.v3 import prepare_run

    space = {"kind": "lora", "rank": 2, "alpha": 4, "targetModules": ["q_proj"]}
    cfg = product_config(product_assets, tmp_path, weightSpace=space, antithetic=False)
    _, run, _ = prepare_run(cfg, tmp_path, "cpu")
    _, repeated, _ = prepare_run(cfg, tmp_path, "cpu")
    assert repeated.to_dict() == run.to_dict() and repeated.antithetic is False
    with pytest.raises(ValueError, match="documents changed"):
        prepare_run({**cfg, "alpha": 0.25}, tmp_path, "cpu")
    adapter = tmp_path / "initial-adapter.bin"
    raw = bytearray(adapter.read_bytes())
    raw[0] ^= 1
    adapter.write_bytes(raw)
    with pytest.raises(Exception, match="[Hh]ash|[Cc]hecksum"):
        prepare_run(cfg, tmp_path, "cpu")


def test_initial_adapter_remains_available_after_weight_pruning(tmp_path):
    from heteroes.coordinator import Coordinator

    coordinator = Coordinator.__new__(Coordinator)
    coordinator.models_dir = tmp_path
    coordinator._keep_published = 1
    coordinator._recent = []
    coordinator._pinned_weights = ("a" * 64,)
    coordinator._log = lambda event: None
    for prefix in ("a", "b", "c"):
        (tmp_path / (prefix * 64 + ".bin")).write_bytes(b"fixture")
    coordinator._prune("c" * 64)
    assert {p.name for p in tmp_path.iterdir()} == {"a" * 64 + ".bin", "c" * 64 + ".bin"}


def test_worker_rebuild_rejects_a_different_schema(product_assets, tmp_path):
    from copy import deepcopy
    from heteroes.product.v3 import prepare_run

    cfg = product_config(product_assets, tmp_path)
    _, run, _ = prepare_run(cfg, tmp_path, "cpu")
    declared = deepcopy(run.to_dict())
    declared["schemaHash"] = "0" * 64
    with pytest.raises(ValueError, match="differs from declared"):
        prepare_run(cfg, tmp_path, "cpu", declared=declared)


def test_agent_prepares_v3_columns_from_a_verified_transfer(product_assets, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from heteroes.study.data import sha
    from heteroes.study.prepare import prepare
    import heteroes.study.prepare as preparation

    cfg = product_config(product_assets, tmp_path)
    cfg["datasetObjectSha256"] = "d" * 64
    agent = SimpleNamespace(root=tmp_path, config={"modelPaths": {sha(cfg["modelManifest"]): cfg["modelPath"]}})
    requested = []

    def transfer(agent, assignment, digest, target, limit):
        requested.append(digest)
        return Path(cfg["datasetPath"])

    monkeypatch.setattr(preparation, "transfer", transfer)
    prepared = prepare(agent, {"assignmentId": "b" * 32, "epoch": 1}, cfg, tmp_path / "private")
    assert requested == [cfg["datasetObjectSha256"]]
    assert prepared["modelPath"] == cfg["modelPath"]
    assert data.verify(read_json(Path(prepared["datasetPath"]))) == read_json(tmp_path / "dataset.json")
    assert read_json(Path(prepared["modelManifestPath"])) == cfg["modelManifest"]


def test_the_default_study_cache_is_not_checked_against_the_model_volume(product_assets, tmp_path, monkeypatch):
    # Found on the packaged r11 candidate2 (2026-10-20): models on another disk (storageVolumeUUID set) and no
    # large-data directory made every v3 run fail with "Selected large-data volume is unavailable", because the private
    # default cache under the agent's state directory was checked against the models' disk.
    from types import SimpleNamespace
    from heteroes.study.data import sha
    from heteroes.study.prepare import prepare
    import heteroes.study.prepare as preparation

    cfg = product_config(product_assets, tmp_path)
    cfg["datasetObjectSha256"] = "d" * 64
    config = {"modelPaths": {sha(cfg["modelManifest"]): cfg["modelPath"]}, "storageVolumeUUID": "0" * 16}
    agent = SimpleNamespace(root=tmp_path / "state", config=config)
    targets = []

    def transfer(agent, assignment, digest, target, limit):
        targets.append(target)
        return Path(cfg["datasetPath"])

    monkeypatch.setattr(preparation, "transfer", transfer)
    prepare(agent, {"assignmentId": "b" * 32, "epoch": 1}, cfg, tmp_path / "private")
    assert targets[0].is_relative_to(tmp_path / "state" / "study-cache")
    # a large-data directory is still checked against its volume
    agent.config["largeDataDirectory"] = str(tmp_path / "large")
    with pytest.raises(ValueError, match="volume"):
        prepare(agent, {"assignmentId": "b" * 32, "epoch": 1}, cfg, tmp_path / "private")


def test_the_coordinator_agent_accepts_a_managed_python_scorer_only_with_its_frozen_code(product_assets, tmp_path):
    from heteroes.product.run_supervisor import validate
    from heteroes.v3.scoring import source_sha256

    entry = {"role": "scorer", "name": "reward.py", "function": "reward", "source": REWARD}
    entry["codeSha256"] = source_sha256(entry["name"], entry["source"].encode())
    cfg = product_config(product_assets, tmp_path, workload="text_v3")
    cfg.update(
        scorer={"kind": "python", "name": "length", "version": 1, "codeSha256": entry["codeSha256"], "config": {}},
        pythonCode=[entry],
    )
    # The COORDINATE command is checked before the run is prepared: a managed Python reward must get through.
    validate(cfg, {"fixture": {"id": "fixture"}})
    del cfg["pythonCode"]
    with pytest.raises(ValueError, match="pythonCode"):
        validate(cfg, {"fixture": {"id": "fixture"}})
