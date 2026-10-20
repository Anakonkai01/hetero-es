"""Two independent worker processes consume pinned inputs; only their coordinator runs Python rewards."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from heteroes.product.files import read_json
from test_v3_local import assets, config_for


def test_inputs_are_authenticated_and_unconfigured_servers_do_not_expose_them(tmp_path):
    from heteroes.http_transport import CoordinatorServer, HttpClient, UnauthorizedError, TransportError

    class API:
        pass

    server = CoordinatorServer(API(), token="fixture-token")
    server.start()
    try:
        with pytest.raises(UnauthorizedError):
            HttpClient(server.url).get_json("/v1/inputs")
        client = HttpClient(server.url, token="fixture-token")
        assert client.get_json("/v1/inputs")["error"]["code"] == "unknown_operation"
        server.inputs = {"formatVersion": 1}
        assert client.get_json("/v1/inputs")["inputs"] == {"formatVersion": 1}
    finally:
        server.stop()


def test_unpinned_dataset_and_changed_recipe_are_refused(assets, tmp_path):
    import copy
    from heteroes.v3.local import prepare
    from heteroes.v3.distributed import validate_inputs

    ready = prepare(config_for(assets, generations=1), tmp_path, "cpu")
    inputs = {"formatVersion": 1, "recipe": ready["run"].recipe, "plan": ready["run"].plan, "dataset": ready["dataset"]}
    assert validate_inputs(inputs).hash == ready["run"].hash
    corrupted = copy.deepcopy(inputs)
    corrupted["dataset"]["splits"]["train"][0]["prompt"] += " changed"
    with pytest.raises(ValueError):
        validate_inputs(corrupted)
    with pytest.raises(ValueError):
        validate_inputs({**inputs, "pythonCode": "never sent to a worker"})
    with pytest.raises(ValueError, match="recipe"):
        validate_inputs(inputs, expected_recipe_hash="0" * 64)


@pytest.mark.parametrize("field", ["schemaHash", "generationConfigSha256"])
def test_worker_refuses_a_model_layout_or_generation_config_mismatch(assets, tmp_path, monkeypatch, field):
    import copy
    from heteroes.canonical import canonical_json_hash
    from heteroes.v3.local import prepare
    from heteroes.v3.distributed import worker
    import heteroes.http_transport as transport

    ready = prepare(config_for(assets, generations=1), tmp_path / "source", "cpu")
    recipe = copy.deepcopy(ready["run"].recipe)
    target = recipe if field == "schemaHash" else recipe["evaluation"]
    target[field] = "0" * 64
    plan = {**ready["run"].plan, "recipeHash": canonical_json_hash(recipe)}
    inputs = {"formatVersion": 1, "recipe": recipe, "plan": plan, "dataset": ready["dataset"]}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def get_json(self, path):
            return {"ok": True, "inputs": inputs}

    monkeypatch.setattr(transport, "HttpClient", Client)
    monkeypatch.setenv("HETEROES_TOKEN", "fixture-token")
    with pytest.raises(ValueError, match="schema|Generation configuration"):
        worker("http://127.0.0.1:1", assets / "model", tmp_path / "worker", "fixture")


def test_serve_requires_an_environment_secret_before_creating_the_run(assets, tmp_path, monkeypatch):
    from heteroes.v3.distributed import serve

    monkeypatch.delenv("HETEROES_TOKEN", raising=False)
    with pytest.raises(ValueError, match="HETEROES_TOKEN"):
        serve(config_for(assets, generations=1), tmp_path / "run", host="127.0.0.1", port=0, timeout_seconds=0.1)
    assert not (tmp_path / "run").exists()


def test_windows_coordinator_never_initializes_an_adapter(assets, tmp_path, monkeypatch):
    import types
    import heteroes.v3.distributed as distributed

    monkeypatch.setenv("HETEROES_TOKEN", "fixture-token")
    monkeypatch.setattr(distributed, "sys", types.SimpleNamespace(platform="win32"))
    config = config_for(assets, generations=1)
    config["weightSpace"] = {"kind": "lora", "rank": 2, "alpha": 4, "targetModules": ["q_proj", "v_proj"]}
    with pytest.raises(ValueError, match="initial-adapter"):
        distributed.serve(config, tmp_path / "run", timeout_seconds=0.1)
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("lora", [False, True])
def test_two_worker_processes_match_the_local_run_with_python_scoring(assets, tmp_path, lora):
    from heteroes.v3.local import run_local

    config = config_for(assets, generations=2, candidateSeedNamespace="distributed-fixture")
    private_scorer = tmp_path / "server-only-scorer.py"
    private_scorer.write_text(
        'import os\nif os.environ.get("HETEROES_TEST_FORBID_SCORER"):\n'
        '    raise RuntimeError("A worker imported researcher code")\n' + Path(config["scorer"]["path"]).read_text()
    )
    config["scorer"]["path"] = str(private_scorer)
    if lora:
        config["weightSpace"] = {"kind": "lora", "rank": 2, "alpha": 4, "targetModules": ["q_proj", "v_proj"]}
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(config))
    baseline = run_local(config, tmp_path / "baseline", workers=1, timeout_seconds=30)
    root = tmp_path / "distributed"
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "HETEROES_TOKEN": "fixture-distributed-token"}
    server_output = (tmp_path / "serve.log").open("w")
    command = [
        sys.executable,
        "-m",
        "heteroes.v3",
        "serve",
        str(spec),
        "--out",
        str(root),
        "--host",
        "127.0.0.1",
        "--port",
        "0",
        "--device",
        "cpu",
        "--timeout-seconds",
        "40",
        "--worker-ids",
        "worker-a,worker-b",
        "--audit-rate",
        "1",
    ]
    coordinator = subprocess.Popen(command, env=env, stdout=server_output, stderr=server_output)
    workers, outputs = [], []
    try:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and not (root / "server.json").exists() and coordinator.poll() is None:
            time.sleep(0.05)
        ready = read_json(root / "server.json")
        assert ready, (tmp_path / "serve.log").read_text()
        # Only copy the MODEL to worker processes: they fetch data/recipe/plan and never load the Python scorer file.
        for name in ("worker-a", "worker-b"):
            output = (tmp_path / f"{name}.log").open("w")
            outputs.append(output)
            worker = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "heteroes.v3",
                    "worker",
                    "--coordinator",
                    ready["url"],
                    "--model-path",
                    str(assets / "model"),
                    "--worker-id",
                    name,
                    "--out",
                    str(tmp_path / name),
                    "--device",
                    "cpu",
                    "--recipe-hash",
                    ready["recipeHash"],
                ],
                env={**env, "HETEROES_TEST_FORBID_SCORER": "1"},
                stdout=output,
                stderr=output,
            )
            workers.append(worker)
        assert coordinator.wait(timeout=60) == 0, (tmp_path / "serve.log").read_text()
        for worker, name in zip(workers, ("worker-a", "worker-b")):
            assert worker.wait(timeout=15) == 0, (tmp_path / f"{name}.log").read_text()
        results = json.loads((root / "summaries.json").read_text())
        assert [r["child_sha256"] for r in results] == [r["child_sha256"] for r in baseline]
        for name in ("worker-a", "worker-b"):
            events = [json.loads(line) for line in (tmp_path / name / "events.jsonl").read_text().splitlines()]
            assert any(event["event"] == "exit" and event["reason"] == "finished" for event in events)
            assert not (tmp_path / name / "scorer.py").exists()
        assert "pythonCode" not in json.loads((root / "inputs.json").read_text())
    finally:
        for process in [*workers, coordinator]:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=20)
        server_output.close()
        for output in outputs:
            output.close()
