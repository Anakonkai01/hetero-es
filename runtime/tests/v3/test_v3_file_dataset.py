"""File-backed Recipe v3 datasets (format 3): large files, rows read on demand, the same splits as the in-memory format."""

import json

import pytest

from heteroes.v3 import data as v3data


def rows(count, offset=0):
    return [{"prompt": f"What is {i} plus {i}?", "answer": str(2 * i), "n": i, "x": None} for i in range(offset, offset + count)]  # fmt: skip


def jsonl(path, values):
    path.write_text("".join(json.dumps(v) + "\n" for v in values))
    return path


def test_a_seeded_file_dataset_has_the_splits_of_the_in_memory_format_and_reads_rows_on_demand(tmp_path):
    source = jsonl(tmp_path / "all.jsonl", rows(50))

    document = v3data.build_file_dataset({"all": (source, "jsonl")}, tmp_path / "out", split_seed=7)
    dataset = v3data.open_dataset(tmp_path / "out" / "dataset.json")

    in_memory = v3data.build(rows(50), split_seed=7)
    assert {name: list(dataset["splits"][name]) for name in v3data.SPLITS} == in_memory["splits"]
    assert document["splitCounts"] == {"train": 40, "validation": 5, "test": 5}
    assert len(json.dumps(document)) < 1000  # the document stays small, whatever the size of the rows
    train = dataset["splits"]["train"]
    assert train[3] == in_memory["splits"]["train"][3] and train[1:3] == in_memory["splits"]["train"][1:3]
    selected = v3data.batch(dataset, 2, 4, 11)
    assert selected["rows"] == [train[i] for i in selected["indices"]] == v3data.batch(dataset, 2, 4, 11)["rows"]


def test_three_given_split_files_are_kept_as_given_and_csv_is_read(tmp_path):
    (tmp_path / "train.csv").write_text("prompt,answer\n" + "".join(f"q{i},{i}\n" for i in range(20)))
    validation, test = jsonl(tmp_path / "v.jsonl", rows(3, 100)), jsonl(tmp_path / "t.jsonl", rows(2, 200))

    v3data.build_file_dataset(
        {"train": (tmp_path / "train.csv", "csv"), "validation": (validation, "jsonl"), "test": (test, "jsonl")},
        tmp_path / "out",
    )
    dataset = v3data.open_dataset(tmp_path / "out" / "dataset.json")

    assert dataset["splitMode"] == "pre-split" and dataset["splits"]["train"][0] == {"prompt": "q0", "answer": "0"}
    assert list(dataset["splits"]["test"]) == rows(2, 200)


def test_an_epoch_of_a_file_dataset_visits_every_train_row_once(tmp_path):
    v3data.build_file_dataset({"all": (jsonl(tmp_path / "a.jsonl", rows(30)), "jsonl")}, tmp_path / "out")
    dataset = v3data.open_dataset(tmp_path / "out" / "dataset.json")
    indices = [i for g in range(5) for i in v3data.batch(dataset, g, 5, 3, "epoch-shuffle@1")["indices"]]
    assert sorted(indices) == list(range(24))


@pytest.mark.parametrize(
    "values, limits, message",
    [
        (rows(20) + [{"prompt": "What  is 3 plus\t3?"}], {}, "twice"),  # the same prompt up to whitespace
        (rows(20), {"max_rows": 19}, "rows"),
        (rows(20), {"max_bytes": 100}, "bytes"),
        (rows(20) + [{"answer": "no prompt"}], {}, "prompt"),
    ],
)
def test_duplicates_limits_and_bad_rows_are_refused(tmp_path, values, limits, message):
    with pytest.raises(ValueError, match=message):
        v3data.build_file_dataset({"all": (jsonl(tmp_path / "a.jsonl", values), "jsonl")}, tmp_path / "out", **limits)


def test_a_changed_split_file_or_document_is_refused(tmp_path):
    document = v3data.build_file_dataset({"all": (jsonl(tmp_path / "a.jsonl", rows(20)), "jsonl")}, tmp_path / "out")
    v3data.verify(document)  # a recovery point keeps only the document: it is checked on its own
    with pytest.raises(ValueError, match="content hash"):
        v3data.verify({**document, "splitSeed": 1})
    split = tmp_path / "out" / f"{document['splitHashes']['test']}.jsonl"
    split.write_bytes(split.read_bytes().replace(b"plus", b"PLUS", 1))
    with pytest.raises(ValueError, match="split file"):
        v3data.open_dataset(tmp_path / "out" / "dataset.json")


def test_the_in_memory_format_still_opens_from_its_document(tmp_path):
    (tmp_path / "dataset.json").write_text(json.dumps(v3data.build(rows(20))))
    assert v3data.open_dataset(tmp_path / "dataset.json")["splits"] == v3data.build(rows(20))["splits"]


def test_a_device_downloads_the_document_and_each_split_file_it_pins(tmp_path, monkeypatch):
    import hashlib
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from types import SimpleNamespace

    from heteroes.study import prepare as study_prepare

    v3data.build_file_dataset({"all": (jsonl(tmp_path / "a.jsonl", rows(30)), "jsonl")}, tmp_path / "lab")
    payloads = {hashlib.sha256(p.read_bytes()).hexdigest(): p.read_bytes() for p in (tmp_path / "lab").iterdir()}
    document = json.loads((tmp_path / "lab" / "dataset.json").read_text())
    doc_sha = hashlib.sha256((tmp_path / "lab" / "dataset.json").read_bytes()).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(payloads[self.path[1:]])

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    asked = []

    def grant(path, body):
        asked.append(body["sha256"])
        return {"url": f"http://127.0.0.1:{server.server_port}/{body['sha256']}", "sha256": body["sha256"]}

    monkeypatch.setattr(study_prepare, "prepare_model", lambda *a, **k: tmp_path / "model")
    agent = SimpleNamespace(root=tmp_path / "agent", config={}, call=grant)
    config = {
        "recipeVersion": 3,
        "datasetObjectSha256": doc_sha,
        "datasetIdentity": {k: document[k] for k in ("contentHash", "splitHashes")},
        "modelManifest": {},
    }
    try:
        prepared = study_prepare.prepare(agent, {"assignmentId": "a", "epoch": 1}, config, tmp_path / "run")
    finally:
        server.shutdown()
        server.server_close()
    assert asked[0] == doc_sha and sorted(asked[1:]) == sorted(document["splitHashes"].values())
    assert list(v3data.open_dataset(prepared["datasetPath"])["splits"]["test"]) == list(
        v3data.open_dataset(tmp_path / "lab" / "dataset.json")["splits"]["test"]
    )


def test_a_recovery_point_carries_the_split_files_and_refuses_one_without_them(tmp_path):
    from heteroes.product.files import write_json
    from heteroes.v3.recovery import capture_state, validate_state
    from heteroes.v3.run import RecipeV3Run, build_documents

    document = v3data.build_file_dataset({"all": (jsonl(tmp_path / "a.jsonl", rows(30)), "jsonl")}, tmp_path / "data")
    scorer = {"kind": "declarative", "name": "exact-string", "version": 1, "codeSha256": None,
              "config": {"answerField": "answer", "strip": True, "casefold": False}}  # fmt: skip
    recipe, plan = build_documents(
        {
            "model": {"id": "tiny"},
            "sigma": {"initial": 0.01},
            "population": 4,
            "generations": 3,
            "alpha": 0.1,
            "batchSize": 3,
            "scorerSpec": scorer,
        },  # fmt: skip
        model_files={"config.json": "a" * 64},
        revision="c" * 40,
        schema_hash="d" * 64,
        generation_config_sha256="e" * 64,
        dataset=document,
    )
    run = RecipeV3Run(recipe, plan)
    root = tmp_path / "run"
    (root / "selection").mkdir(parents=True)
    (root / "selection" / f"{'b' * 64}.bin").write_bytes(b"weights")
    row = {"recipeHash": run.hash, "planHash": run.plan_hash, "generation": -1, "weightsSha256": "b" * 64, "meanReward": 0.5}  # fmt: skip
    identity = {k: document[k] for k in ("contentHash", "splitHashes")}
    config = {"datasetPath": str(tmp_path / "data" / "dataset.json"), "datasetIdentity": identity}
    for name, value in (("config.json", config), ("recipe.json", recipe), ("plan.json", plan),
                        ("study-selection.json", {**row, "validationReward": 0.5}), ("validation--1.json", row)):  # fmt: skip
        write_json(root / name, value)
    point = tmp_path / "point"
    point.mkdir()

    names = capture_state(root, point, recipe, 0)

    files = {n: {"sha256": hashlib_sha(point / n), "sizeBytes": (point / n).stat().st_size} for n in names}
    assert {f"{sha}.jsonl" for sha in document["splitHashes"].values()} <= set(names)
    state = json.loads((point / "v3-state.json").read_text())
    validate_state(state, config, recipe, 0, files)
    missing = {n: f for n, f in files.items() if not n.endswith(".jsonl")}
    with pytest.raises(ValueError, match="split file"):
        validate_state(state, config, recipe, 0, missing)


def hashlib_sha(path):
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
