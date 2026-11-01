"""Actual MinIO bucket ownership through product dataset/model APIs and frozen device transfer grants."""

import hashlib
import json
import os
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import pytest

from backend.apps.factory import create_app
from backend.services.devices import AgentRuntime
from backend.storage.s3_backend import S3Backend
from labkit import login, pair
from test_study import manifest


if os.environ.get("HETEROES_TEST_MINIO_ENDPOINT"):
    from test_s3_backend import s3 as s3, put_url, read_url

    @pytest.fixture
    def cloud_lab(s3, tmp_path):
        _, config = s3
        # App owns its own clients; the fixture's separate administration clients clean its owned buckets afterwards.
        backend = S3Backend(config)
        runtime = AgentRuntime(backend)
        runtime.public_web_url = lambda: "https://cloud.example.test"
        app = create_app(tmp_path / "product.sqlite", {"admin": "test-admin-pass"}, runtime, dispatch=False)
        with TestClient(app) as client:
            yield client, app.state.store, backend, config, login(client, "admin")

    def imported(client, auth):
        response = client.post(
            "/api/v1/datasets/import",
            headers=auth,
            json={
                "name": "actual S3 dataset",
                "files": {
                    "all": {
                        "format": "json",
                        "content": json.dumps([{"prompt": f"Question {i}", "answer": i} for i in range(20)]),
                    }
                },
            },
        )
        assert response.status_code == 201
        return response.json()

    def published_model(client, auth):
        description, files = manifest()
        response = client.post(
            "/api/v1/models/register",
            headers=auth,
            json={"name": "S3 pinned model", "source": "UPLOAD", "manifest": description},
        )
        assert response.status_code == 201
        asset = response.json()
        base = "/api/v1/models/" + asset["id"]
        plans = client.post(base + "/upload-plan", headers=auth, json={name: len(data) for name, data in files.items()})
        assert plans.status_code == 200
        for name, data in files.items():
            assert "publicUrl" not in plans.json()[name]
            assert put_url(plans.json()[name]["url"], data, {"Content-Length": str(len(data))})[0] == 200
        ready = client.post(base + "/publish", headers=auth)
        assert ready.status_code == 200 and ready.json()["status"] == "READY"
        return ready.json(), files

    def test_inline_dataset_object_is_in_datasets_bucket_only(cloud_lab):
        client, _, backend, config, auth = cloud_lab
        data = imported(client, auth)
        key = "objects/" + data["objectSha256"]
        datasets = backend.for_purpose("datasets")
        payload = b"".join(datasets.get(key))
        assert hashlib.sha256(payload).hexdigest() == data["objectSha256"]
        assert urlsplit(datasets.download_url(key)).path.startswith("/" + config["buckets"]["datasets"] + "/")
        with pytest.raises(FileNotFoundError):
            b"".join(backend.get(key))

    def test_dataset_upload_build_and_split_publication_use_dataset_bucket(cloud_lab):
        client, _, backend, config, auth = cloud_lab
        payload = "".join(json.dumps({"question": f"Q{i}", "label": "A"}) + "\n" for i in range(20)).encode()
        result = client.post(
            "/api/v1/datasets/upload-plan",
            headers=auth,
            json={"name": "files", "files": {"all": {"format": "jsonl", "sizeBytes": len(payload)}}},
        )
        assert result.status_code == 201
        plan = result.json()
        target = plan["files"]["all"]
        assert "publicUrl" in target
        assert client.put(urlsplit(target["publicUrl"]).path, content=payload).status_code == 200
        built = client.post(
            "/api/v1/datasets/uploads/" + plan["uploadId"] + "/build",
            headers=auth,
            json={"mapping": {"prompt": "question"}},
        )
        assert built.status_code == 201
        data = built.json()
        datasets = backend.for_purpose("datasets")
        for sha in [data["objectSha256"], *data["splitObjects"]]:
            url = datasets.download_url("objects/" + sha)
            assert urlsplit(url).path.startswith("/" + config["buckets"]["datasets"] + "/")
            assert hashlib.sha256(read_url(url)).hexdigest() == sha
            with pytest.raises(FileNotFoundError):
                b"".join(backend.get("objects/" + sha))
        assert not list(backend.root.glob(".dataset-build-*"))

    def test_model_files_stay_in_recovery_bucket_with_private_uploads(cloud_lab):
        client, _, backend, config, auth = cloud_lab
        asset, files = published_model(client, auth)
        for name, data in files.items():
            key = "objects/" + asset["manifest"]["files"][name]
            assert urlsplit(backend.download_url(key)).path.startswith("/" + config["buckets"]["recovery"] + "/")
            assert read_url(backend.download_url(key)) == data
            with pytest.raises(FileNotFoundError):
                b"".join(backend.for_purpose("datasets").get(key))

    def test_frozen_device_transfer_selects_dataset_or_model_bucket_and_public_dataset_only(cloud_lab):
        client, store, backend, config, auth = cloud_lab
        data = imported(client, auth)
        model, files = published_model(client, auth)
        device, device_auth = pair((client, store, store.runtime, auth), "s3-test-device")
        run_id, assignment = "e" * 32, "f" * 32
        frozen = {
            "deviceIds": [device["deviceId"]],
            "config": {
                "datasetObjectSha256": data["objectSha256"],
                "datasetSplitObjects": [],
                "modelSource": "UPLOAD",
                "modelManifest": model["manifest"],
            },
        }
        with store.db() as db:
            db.execute(
                "INSERT INTO experiments(id,owner,body,snapshot) VALUES (:p0,:p1,:p2,NULL)",
                (
                    run_id,
                    "admin",
                    json.dumps(
                        {"experimentId": run_id, "workspaceId": "lab", "ownerUserId": "admin", "status": "RUNNING"}
                    ),
                ),
            )
            db.execute(
                "INSERT INTO assignments(id,run_id,epoch,coordinator,body,snapshot,released) VALUES (:p0,:p1,1,:p2,:p3,'{}',0)",
                (assignment, run_id, device["deviceId"], json.dumps(frozen)),
            )
        model_sha = next(iter(model["manifest"]["files"].values()))
        for sha, purpose in [(data["objectSha256"], "datasets"), (model_sha, "recovery")]:
            response = client.post(
                "/api/v1/device/study-transfer",
                headers=device_auth,
                json={"assignmentId": assignment, "epoch": 1, "sha256": sha},
            )
            assert response.status_code == 200
            grant = response.json()
            assert urlsplit(grant["url"]).path.startswith("/" + config["buckets"][purpose] + "/")
            assert hashlib.sha256(read_url(grant["url"])).hexdigest() == sha
            assert ("publicUrl" in grant) == (purpose == "datasets")
            if "publicUrl" in grant:
                assert hashlib.sha256(client.get(urlsplit(grant["publicUrl"]).path).content).hexdigest() == sha
        with store.db() as db:
            db.execute("UPDATE assignments SET released=1 WHERE id=:p0", (assignment,))
        assert (
            client.post(
                "/api/v1/device/study-transfer",
                headers=device_auth,
                json={"assignmentId": assignment, "epoch": 1, "sha256": model_sha},
            ).status_code
            == 403
        )
