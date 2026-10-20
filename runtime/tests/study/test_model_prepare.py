"""A qualification downloads pinned model files without a dataset or an experiment grant."""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from heteroes.study.prepare import prepare_model, transfer


@pytest.fixture
def pinned():
    files = {"config.json": b"{}", "model.safetensors": b"fixture-only", "tokenizer.json": b"{}"}
    manifest = {
        "formatVersion": 1,
        "modelId": "research/new-model",
        "revision": "e" * 40,
        "tokenizerRevision": "e" * 40,
        "format": "safetensors",
        "files": {k: hashlib.sha256(v).hexdigest() for k, v in files.items()},
    }
    return manifest, files


def test_reference_downloads_the_exact_revision_and_refuses_a_changed_cached_file(tmp_path, pinned, monkeypatch):
    manifest, files = pinned
    calls = []

    def download(model_id, name, revision, local_dir):
        assert model_id == manifest["modelId"] and revision == manifest["revision"]
        calls.append(name)
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        (Path(local_dir) / name).write_bytes(files[name])

    monkeypatch.setattr("huggingface_hub.hf_hub_download", download)
    agent = SimpleNamespace(root=tmp_path, config={})
    config = {"recipeVersion": 3, "modelManifest": manifest, "modelSource": "REFERENCE"}
    model = prepare_model(agent, {"jobId": "a" * 32}, config)
    assert set(calls) == set(files)
    assert not list(tmp_path.rglob("datasets"))
    agent.config["modelPaths"] = {__import__("heteroes.study.data", fromlist=["sha"]).sha(manifest): str(model)}
    (model / "model.safetensors").write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        prepare_model(agent, {"jobId": "a" * 32}, config)


def test_uploaded_model_uses_only_the_job_grant_and_verifies_streamed_bytes(tmp_path, pinned):
    manifest, files = pinned
    payloads = {hashlib.sha256(v).hexdigest(): v for v in files.values()}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = payloads[self.path[1:]]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    grants = []

    def grant(path, body):
        assert path == "/api/v1/device/model-transfer" and set(body) == {"jobId", "sha256"}
        assert body["jobId"] == "a" * 32
        grants.append(body["sha256"])
        return {"url": f"http://127.0.0.1:{server.server_port}/{body['sha256']}", "sha256": body["sha256"]}

    agent = SimpleNamespace(root=tmp_path, config={}, call=grant)
    try:
        model = prepare_model(
            agent, {"jobId": "a" * 32}, {"recipeVersion": 3, "modelManifest": manifest, "modelSource": "UPLOAD"}
        )
        assert all((model / name).read_bytes() == value for name, value in files.items())
        assert set(grants) == set(manifest["files"].values())
        target = tmp_path / "bad-download"
        digest = manifest["files"]["model.safetensors"]
        payloads[digest] = b"wrong"
        with pytest.raises(ValueError, match="checksum"):
            transfer(agent, {"jobId": "a" * 32}, digest, target, 1000)
        assert not target.exists() and not list(tmp_path.glob(".pending-*"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
