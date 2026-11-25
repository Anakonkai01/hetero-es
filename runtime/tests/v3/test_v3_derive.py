"""
Continuing an earlier run (`heteroes.v3.derive`): the derived model directory reproduces the source weights bit for bit,
names its source in a pinned lineage file, and a new run on it starts from exactly those weights with other settings.
"""

import json
import shutil
import sqlite3

import pytest

from heteroes.model.weights_io import WeightsFileError
from heteroes.v3 import derive
from heteroes.v3.__main__ import main
from heteroes.v3.local import run_local
from heteroes.v3.model import file_manifest

from test_v3_local import assets, config_for  # noqa: F401  (assets is a fixture)


def ledger_rows(run_dir, query):
    with sqlite3.connect(f"file:{run_dir / 'ledger.sqlite'}?mode=ro", uri=True) as db:
        return db.execute(query).fetchall()


def parent_of_generation_zero(run_dir):
    return ledger_rows(run_dir, "SELECT parent_weights_sha256 FROM generation WHERE generation=0")[0][0]


def final_child(run_dir):
    return ledger_rows(
        run_dir, "SELECT child_weights_sha256 FROM generation_update WHERE applied_at IS NOT NULL ORDER BY generation"
    )[-1][0]


@pytest.fixture(scope="module")
def first_run(assets, tmp_path_factory):  # noqa: F811
    out = tmp_path_factory.mktemp("first") / "run"
    run_local(config_for(assets), out, workers=1, timeout_seconds=30)
    return out


def test_a_continued_run_starts_from_the_source_weights_with_new_settings(assets, first_run, tmp_path):  # noqa: F811
    source = derive.local_source(first_run)
    assert source["sha256"] == final_child(first_run)
    assert source["source"] == {"kind": "local", "runDirectory": "run", "generation": 1}
    assert source["sha256"] != parent_of_generation_zero(first_run)  # the first run moved the weights

    result = derive.derive_model(assets / "model", source, tmp_path / "derived")
    lineage = json.loads((tmp_path / "derived" / derive.LINEAGE_FILE).read_text())
    assert lineage == result["lineage"] and derive.read_lineage(tmp_path / "derived") == lineage
    assert lineage["weightsSha256"] == source["sha256"]
    assert lineage["base"]["modelId"] == "tiny/qwen2" and lineage["parent"] is None
    assert lineage["source"] == source["source"]
    files = file_manifest(tmp_path / "derived")
    assert derive.LINEAGE_FILE in files and "model.safetensors" in files and files == result["files"]
    base = file_manifest(assets / "model")
    assert {n: h for n, h in files.items() if not n.endswith(".safetensors") and n != derive.LINEAGE_FILE} == {
        n: h for n, h in base.items() if not n.endswith(".safetensors")
    }  # configuration and tokenizer are the base's bytes

    changed = config_for(assets, alpha=0.25, sigma={"initial": 0.25}, generations=1)
    changed["model"] = {"path": str(tmp_path / "derived"), "id": "tiny/qwen2+continued"}
    second = tmp_path / "second"
    run_local(changed, second, workers=1, timeout_seconds=30)
    assert parent_of_generation_zero(second) == source["sha256"]
    recipe = json.loads((second / "recipe.json").read_text())
    assert recipe["model"]["files"][derive.LINEAGE_FILE] == files[derive.LINEAGE_FILE]  # the lineage is pinned

    chained = derive.derive_model(tmp_path / "derived", derive.local_source(second), tmp_path / "derived-2")
    assert chained["lineage"]["parent"] == lineage
    assert chained["lineage"]["weightsSha256"] == final_child(second)


def test_derivation_refuses_another_base_model(assets, first_run, tmp_path):  # noqa: F811
    other = tmp_path / "other"
    shutil.copytree(assets / "model", other)
    config = json.loads((other / "config.json").read_text())
    config["rms_norm_eps"] = 1e-5
    (other / "config.json").write_text(json.dumps(config))
    with pytest.raises(ValueError, match="not the model the source run pinned"):
        derive.derive_model(other, derive.local_source(first_run), tmp_path / "derived")
    assert not (tmp_path / "derived").exists()


def test_derivation_refuses_weights_that_are_not_the_named_hash(assets, first_run, tmp_path):  # noqa: F811
    source = derive.local_source(first_run)
    tampered = tmp_path / "tampered.bin"
    data = bytearray(source["weights"].read_bytes())
    data[0] ^= 1
    tampered.write_bytes(bytes(data))
    with pytest.raises(WeightsFileError, match="wrong hash"):
        derive.derive_model(assets / "model", {**source, "weights": tampered}, tmp_path / "derived")
    assert list(tmp_path.iterdir()) == [tampered]  # nothing half-written is left behind


def test_derivation_refuses_an_existing_output_lora_and_old_recipes(assets, first_run, tmp_path):  # noqa: F811
    source = derive.local_source(first_run)
    (tmp_path / "taken").mkdir()
    with pytest.raises(FileExistsError):
        derive.derive_model(assets / "model", source, tmp_path / "taken")
    space = {"kind": "lora", "rank": 2, "alpha": 4, "targetModules": ["q_proj"]}
    lora = {**source, "recipe": {**source["recipe"], "weightSpace": space}}
    with pytest.raises(ValueError, match="keeps only its adapters"):
        derive.derive_model(assets / "model", lora, tmp_path / "lora")
    with pytest.raises(ValueError, match="Recipe v3"):
        derive.derive_model(assets / "model", {**source, "recipe": {"formatVersion": 2}}, tmp_path / "v2")


def test_derivation_refuses_a_recipe_with_another_trainable_schema(assets, first_run, tmp_path):  # noqa: F811
    source = derive.local_source(first_run)
    other = {**source, "recipe": {**source["recipe"], "schemaHash": "0" * 64}}
    with pytest.raises(ValueError, match="trainable schema differs"):
        derive.derive_model(assets / "model", other, tmp_path / "derived")


def test_a_derived_model_that_does_not_reproduce_the_weights_is_not_published(
    assets,
    first_run,
    tmp_path,
    monkeypatch,  # noqa: F811
):
    import heteroes.eval.candidate

    monkeypatch.setattr(heteroes.eval.candidate, "model_weights_sha256", lambda model, schema: "0" * 64)
    with pytest.raises(ValueError, match="does not reproduce"):
        derive.derive_model(assets / "model", derive.local_source(first_run), tmp_path / "derived")
    assert list(tmp_path.iterdir()) == []  # the staging directory is removed


def test_a_sharded_base_model_becomes_one_safetensors_file(assets, first_run, tmp_path):  # noqa: F811
    from safetensors import safe_open

    sharded = tmp_path / "sharded"
    shutil.copytree(assets / "model", sharded)
    shard = "model-00001-of-00001.safetensors"
    (sharded / "model.safetensors").rename(sharded / shard)
    with safe_open(str(sharded / shard), "pt") as handle:
        index = {"metadata": {}, "weight_map": {key: shard for key in handle.keys()}}
    (sharded / "model.safetensors.index.json").write_text(json.dumps(index))
    source = derive.local_source(first_run)
    recipe = {**source["recipe"], "model": {**source["recipe"]["model"], "files": file_manifest(sharded)}}
    result = derive.derive_model(sharded, {**source, "recipe": recipe}, tmp_path / "derived")
    assert shard not in result["files"] and "model.safetensors.index.json" not in result["files"]
    assert "model.safetensors" in result["files"]


def test_a_run_without_an_applied_generation_cannot_be_continued(first_run, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    shutil.copyfile(first_run / "recipe.json", empty / "recipe.json")
    with sqlite3.connect(empty / "ledger.sqlite") as db:
        db.execute("CREATE TABLE generation_update (generation INTEGER, child_weights_sha256 TEXT, applied_at REAL)")
    with pytest.raises(ValueError, match="no applied generation"):
        derive.local_source(empty)
    with sqlite3.connect(empty / "ledger.sqlite") as db:
        db.execute("INSERT INTO generation_update VALUES (0, ?, 1.0)", ("a" * 64,))
    with pytest.raises(ValueError, match="are missing"):
        derive.local_source(empty)


POINTS = [
    {"pointId": "p0", "generation": 0, "final": False, "status": "READY"},
    {"pointId": "p3", "generation": 3, "final": False, "status": "READY"},
    {"pointId": "p4", "generation": 4, "final": False, "status": "VERIFYING"},
    {"pointId": "pf", "generation": 2, "final": True, "status": "READY"},
]


def test_point_choice_takes_the_newest_verified_point_and_only_verified_ones():
    # pf is final but older than p3 (a paused run marked its point final before 25/11): the newer weights win
    assert derive.choose_point(POINTS)["pointId"] == "p3"
    assert derive.choose_point([p for p in POINTS if not p["final"]])["pointId"] == "p3"
    ending = [
        *POINTS,
        {"pointId": "p9", "generation": 9, "final": False, "status": "READY"},
        {"pointId": "pe", "generation": 9, "final": True, "status": "READY"},
    ]
    assert derive.choose_point(ending)["pointId"] == "pe"  # the final point breaks a tie with its periodic twin
    ending[-1] = {**ending[-1], "status": "PENDING"}
    with pytest.raises(ValueError, match="final point .generation 9. is PENDING"):
        derive.choose_point(ending)  # never an older point while the run's last weights are still being verified
    assert derive.choose_point(POINTS, "p0")["pointId"] == "p0"
    with pytest.raises(ValueError, match="VERIFYING, not READY"):
        derive.choose_point(POINTS, "p4")
    with pytest.raises(ValueError, match="does not belong"):
        derive.choose_point(POINTS, "elsewhere")
    with pytest.raises(ValueError, match="no verified"):
        derive.choose_point([POINTS[2]])


class FakeLab:
    """The two lab routes a derivation reads, serving a local run as if it were a verified recovery point."""

    def __init__(self, run_dir, run_id="run-1", answer_run=None):
        self.source = derive.local_source(run_dir)
        sha = self.source["sha256"]
        self.identity = json.dumps({"recipe": self.source["recipe"]}).encode()
        self.run_id, self.answer_run, self.calls = run_id, answer_run or run_id, []
        self.blobs = {"identity.json": self.identity, f"weights/{sha}.bin": self.source["weights"].read_bytes()}

    def request(self, method, path, body=None):
        self.calls.append((method, path))
        if path == f"/api/v1/experiments/{self.run_id}/recovery-points":
            return [{"pointId": "pf", "generation": 1, "final": True, "status": "READY"}]
        assert (method, path) == ("POST", "/api/v1/recovery-points/pf/download-plan")
        import hashlib

        files = {n: {"sha256": hashlib.sha256(b).hexdigest(), "sizeBytes": len(b)} for n, b in self.blobs.items()}
        return {
            "manifest": {
                "runId": self.answer_run,
                "pointId": "pf",
                "generation": 1,
                "final": True,
                "childWeightsSha256": self.source["sha256"],
                "files": files,
            },
            "objects": {name: "signed://" + name for name in self.blobs},
        }

    def download(self, url, target, sha256, size):
        data = self.blobs[url.removeprefix("signed://")]
        assert len(data) == size
        target.write_bytes(data)
        self.downloads = getattr(self, "downloads", 0) + 1
        return target


def test_a_lab_point_is_fetched_checked_and_cached(assets, first_run, tmp_path):  # noqa: F811
    lab = FakeLab(first_run)
    source = derive.lab_source(lab, "run-1", tmp_path / "cache", download=lab.download)
    assert lab.downloads == 2
    assert source["sha256"] == lab.source["sha256"] and source["recipe"] == lab.source["recipe"]
    assert source["source"] == {"kind": "lab", "runId": "run-1", "pointId": "pf", "generation": 1, "final": True}
    derive.lab_source(lab, "run-1", tmp_path / "cache", download=lab.download)
    assert lab.downloads == 2  # verified cached files are not fetched again
    result = derive.derive_model(assets / "model", source, tmp_path / "derived")
    assert result["lineage"]["source"]["pointId"] == "pf"


def test_a_lab_answer_for_another_run_is_refused(first_run, tmp_path):
    lab = FakeLab(first_run, answer_run="run-2")
    with pytest.raises(ValueError, match="another recovery point"):
        derive.lab_source(lab, "run-1", tmp_path / "cache", download=lab.download)


def test_the_command_line_derives_from_a_local_run(assets, first_run, tmp_path, capsys):  # noqa: F811
    assert (
        main(
            ["derive", "--base-model", str(assets / "model"), "--run-dir", str(first_run), "--out", str(tmp_path / "d")]
        )
        == 0
    )
    printed = json.loads(capsys.readouterr().out)
    assert printed["path"] == str(tmp_path / "d") and printed["lineage"]["weightsSha256"] == final_child(first_run)
    with pytest.raises(SystemExit):
        main(["derive", "--base-model", str(assets / "model"), "--out", str(tmp_path / "e")])


def test_the_sdk_continues_local_and_lab_runs(assets, first_run, tmp_path):  # noqa: F811
    from heteroes.sdk import continue_from
    from heteroes.sdk_lab import Run

    local = continue_from(first_run, assets / "model", tmp_path / "local")
    assert derive.read_lineage(local)["source"]["kind"] == "local"
    lab = FakeLab(first_run)
    path = Run(lab, "run-1").derive_model(assets / "model", tmp_path / "lab", download=lab.download)
    assert derive.read_lineage(path)["source"]["runId"] == "run-1"
    assert (tmp_path / "lab.source" / "identity.json").is_file()
