"""The researcher's notebook path to a shared lab: functions from a cell, frozen rows, a suggested batch and chunks."""

import json
import linecache

import pytest

from heteroes.sdk import ESConfig, ESTrainer
from heteroes.sdk_lab import Dataset, Device, Model, suggest


def cell(source, name):
    """A function defined the way a notebook defines it: its file name is not a file on disk."""
    filename = f"<ipython-input-{abs(hash(source))}>"
    linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)
    namespace = {"__name__": "__main__"}
    exec(compile(source, filename, "exec"), namespace)
    return namespace[name]


REWARD = """
def exact(completions, rows):
    import re
    found = [re.findall(r"-?[0-9]+", text) for text in completions]
    return [float(bool(f) and f[-1] == row["answer"]) for f, row in zip(found, rows)]
"""
LEAKY = """
import re
def leaky(completions, rows):
    return [float(bool(re.findall("1", t))) for t in completions]
"""


def rows(n, prefix="q"):
    return [{"prompt": f"{prefix}{i} what is {i}+1?", "answer": str(i + 1)} for i in range(n)]


def test_a_reward_written_in_a_notebook_cell_is_frozen_from_its_own_source(tmp_path):
    data = Dataset.from_rows(rows(20), directory=tmp_path / "data")
    args = ESConfig(model_path="m", model_id="x", dataset=data)
    trainer = ESTrainer(args, reward_func=cell(REWARD, "exact"), code_dir=tmp_path / "code")
    frozen = trainer.config()["scorer"]
    assert frozen["function"] == "exact" and open(frozen["path"]).read().strip() == REWARD.strip()
    # a name read from the notebook would not exist on the coordinator: said before anything is sent
    with pytest.raises(ValueError, match="reads 're' from the notebook"):
        ESTrainer(args, reward_func=cell(LEAKY, "leaky"), code_dir=tmp_path / "code")


def test_rows_from_any_loader_are_frozen_with_their_counts_and_a_content_hash(tmp_path):
    data = Dataset.from_rows(train=rows(8), validation=rows(2, "v"), test=rows(3, "t"), directory=tmp_path / "a")
    assert data.counts == {"train": 8, "validation": 2, "test": 3}
    assert [json.loads(line)["answer"] for line in open(data.files["test"])] == ["1", "2", "3"]
    again = Dataset.from_rows(train=rows(8), validation=rows(2, "v"), test=rows(3, "t"), directory=tmp_path / "b")
    assert again.sha256 == data.sha256
    assert Dataset.from_rows(rows(8), directory=tmp_path / "c").sha256 != data.sha256
    with pytest.raises(ValueError, match="non-empty text 'prompt'"):
        Dataset.from_rows([{"question": "no prompt"}], directory=tmp_path / "d")
    with pytest.raises(ValueError, match="give rows"):
        Dataset.from_rows(rows(3), train=rows(3), directory=tmp_path / "e")


def test_a_lab_spec_carries_the_pinned_hub_model_the_frozen_splits_and_the_chosen_chunks(tmp_path):
    model = Model("org/m", str(tmp_path), "c" * 40, "REFERENCE", {"files": {}})
    data = Dataset.from_rows(train=rows(8), validation=rows(2, "v"), test=rows(2, "t"), directory=tmp_path / "d")
    args = ESConfig(model=model, dataset=data, batch_size=4, eval_chunk=16, eval_chunks=[16, 32], validation_interval=5)
    spec = ESTrainer(args, scorer={"name": "answer-line-last-number"}).lab_spec("first")
    assert spec["model"] == {"path": str(tmp_path), "id": "org/m", "revision": "c" * 40, "source": "REFERENCE"}
    assert spec["data"]["splits"] == data.files and "path" not in spec["data"]
    assert (spec["evalChunk"], spec["evalChunks"], spec["validationInterval"], spec["name"]) == (
        16,
        [16, 32],
        5,
        "first",
    )
    with pytest.raises(ValueError, match="give a model"):
        ESConfig(dataset=data)


def device(worker, vram_gb):
    return Device(worker, worker, "d-" + worker, "GPU", vram_gb, True, True, False, True, False)


def measured(total_gb, peaks_gb, base_gb=2.0):
    chunks = [
        {"chunk": c, "ran": peak is not None, "peakBytes": None if peak is None else int(peak * 1e9), "seconds": 1.0}
        for c, peak in peaks_gb.items()
    ]
    return {"formatVersion": 1, "promptTokens": 200, "newTokens": 256, "baseBytes": int(base_gb * 1e9),
            "totalBytes": int(total_gb * 1e9), "chunks": chunks}  # fmt: skip


def test_each_gpu_gets_the_largest_exact_chunk_its_own_numbers_allow_scaled_to_the_recipe_length():
    exact = (16, 32, 64)
    devices = [device("big", 32), device("small", 6), device("new", 12)]
    measurements = {
        "big": measured(32, {16: 3, 32: 4, 64: 6, 128: 10}),  # 128 measured but not an exact chunk: never offered
        "small": measured(6, {16: 3.5, 32: 5.2, 64: None}),
    }
    at_measured = suggest(devices, measurements, exact, 456)
    assert at_measured.per_device == {"big": 64, "small": 32, "new": 32}
    assert at_measured.batch_size == 64 and at_measured.eval_chunks == [32, 64] and at_measured.eval_chunk == 32
    assert any("new: not measured" in n for n in at_measured.notes)
    # twice the tokens: the excess above the weights doubles (small: 2 + 2 * 3.2 > 0.9 * 6 at chunk 32)
    longer = suggest(devices, measurements, exact, 912)
    assert longer.per_device["small"] == 16 and longer.eval_chunks == [16, 32, 64]
    few = suggest(devices, measurements, exact, 456, train_rows=40)
    assert few.batch_size == 40 and few.eval_chunks == [32] and "batch limited" in few.notes[-1]


def test_small_gpus_alone_still_get_a_batch_of_64_questions_in_several_calls():
    # tier 3, 2026-10-22: 32 questions made the ranking of candidates mostly luck (learning audit)
    only_small = suggest([device("small", 6)], {"small": measured(6, {16: 3.5, 32: 5.2})}, (16, 32, 64), 456)
    assert (only_small.batch_size, only_small.eval_chunks) == (64, [32])


def test_a_reported_chunk_measurement_keeps_its_small_numeric_shape_only():
    from heteroes.product.chunk_memory import check

    good = measured(16, {16: 3, 32: 4, 64: None})
    assert check(good) == good
    for broken in (
        {**good, "extra": 1},
        {**good, "formatVersion": 2},
        {**good, "totalBytes": -1},
        {**good, "chunks": [{"chunk": 16, "ran": True, "peakBytes": "3GB", "seconds": 1.0}]},
        {**good, "chunks": [{"chunk": 16, "ran": True, "peakBytes": 3, "seconds": 1.0, "note": "x"}]},
    ):
        with pytest.raises(ValueError):
            check(broken)


def test_the_device_table_leaves_out_revoked_devices():
    from heteroes.sdk_lab import Lab

    lab = Lab.__new__(Lab)
    lab.request = lambda method, path, *a, **k: [
        {"workerId": "w-ok", "deviceId": "d-ok", "approvalStatus": "APPROVED"},
        {"workerId": "w-old", "deviceId": "d-old", "approvalStatus": "REVOKED"},
    ]
    assert [d.worker_id for d in lab.devices()] == ["w-ok"]


def test_notebook_qualification_never_reuses_v1_for_a_v2_run_and_deduplicates_devices():
    from types import SimpleNamespace
    from heteroes.noise.contracts import ENGINE_VERSION, ENGINE_V2
    from heteroes.sdk_lab import Lab, Device

    digest = "d" * 64
    model = SimpleNamespace(manifest_hash=digest, id="fixture/model")
    device = Device.of(
        {
            "workerId": "w",
            "deviceId": "a" * 32,
            "selfTest": {
                "noiseVersion": ENGINE_VERSION,
                "qualifiedModelHashes": [digest],
                "qualifiedModelsByNoiseEngine": {ENGINE_VERSION: [digest]},
            },
        }
    )
    lab = Lab("https://lab.example", "fixture", "lab")
    lab.model_asset = lambda model: {"id": "model"}
    requests = []

    def request(method, path, body=None):
        requests.append((method, body))
        return {"jobId": "job", "status": "COMPLETED"}

    lab.request = request
    lab.qualify(model, [device, device], log=lambda *_: None)
    assert requests == [("POST", {"deviceId": "a" * 32, "noiseEngineVersion": ENGINE_V2})]
    requests.clear()
    lab.qualify(model, [device], engine=ENGINE_VERSION, log=lambda *_: None)
    assert requests == []
