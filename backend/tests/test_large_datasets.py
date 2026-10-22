"""Large Recipe v3 datasets: signed uploads, a file-backed build on the lab, limits the administrator sets."""

import hashlib
import json
from urllib.parse import urlsplit

import pytest

from test_devices import enable, pair
from test_study import study as study_fixture
from test_v3_study import assets, configuration, qualify_v3


@pytest.fixture
def v3_study(tmp_path):
    yield from study_fixture.__wrapped__(tmp_path)


def upload(c, headers, files, name="Big data"):
    """Ask for a plan and PUT every file through its signed URL; returns the upload id."""
    sizes = {k: {"format": fmt, "sizeBytes": len(data)} for k, (fmt, data) in files.items()}
    plan = c.post("/api/v1/datasets/upload-plan", headers=headers, json={"name": name, "files": sizes})
    assert plan.status_code == 201, plan.text
    for key, (fmt, data) in files.items():
        target = plan.json()["files"][key]
        assert c.put(urlsplit(target["url"]).path, content=data, headers=target["headers"]).status_code in (
            200,
            201,
            204,
        )
    return plan.json()["uploadId"]


def lines(count):
    return "".join(json.dumps({"question": f"Q{i}", "label": "A", "level": i}) + "\n" for i in range(count)).encode()


def test_a_large_dataset_is_uploaded_built_from_files_and_reaches_the_devices(v3_study):
    c, admin, _ = v3_study
    store = c.app.state.store
    lab = (c, store, store.runtime, admin)
    upload_id = upload(c, admin, {"all": ("jsonl", lines(400))})

    built = c.post(
        f"/api/v1/datasets/uploads/{upload_id}/build", headers=admin, json={"mapping": {"prompt": "question"}}
    )

    assert built.status_code == 201, built.text
    data = built.json()
    assert (data["formatVersion"], data["counts"], data["columns"]) == (3, {"train": 320, "validation": 40, "test": 40}, ["label", "level", "prompt", "question"])  # fmt: skip
    assert data["id"] in [d["id"] for d in c.get("/api/v1/datasets", headers=admin).json()]
    d, device_auth = pair(lab)
    model, _ = assets(v3_study)
    qualify_v3(c, device_auth, c.get("/api/v1/devices", headers=admin).json()[0]["selfTest"], model)
    body = {**configuration(d, model, data), "datasetIds": [data["datasetId"]]}
    run = c.post("/api/v1/experiments", headers=admin, json=body)
    assert run.status_code == 200, run.text
    enable(lab, d, device_auth)
    assert c.post(f"/api/v1/experiments/{run.json()['experimentId']}/submit", headers=admin).status_code == 200
    store.dispatch_once()
    ar = store.runtime.runs()[0]
    for sha in [data["objectSha256"], *data["splitObjects"]]:
        grant = c.post(
            "/api/v1/device/study-transfer",
            headers=device_auth,
            json={"assignmentId": ar["assignmentId"], "epoch": ar["epoch"], "sha256": sha},
        )
        assert grant.status_code == 200, grant.text
    outside = {"assignmentId": ar["assignmentId"], "epoch": ar["epoch"], "sha256": "f" * 64}
    assert c.post("/api/v1/device/study-transfer", headers=device_auth, json=outside).status_code == 403


def test_the_administrator_sets_the_limits_and_bad_files_are_refused(v3_study):
    c, admin, _ = v3_study
    assert c.get("/api/v1/platform/dataset-limits", headers=admin).json() == {"maxBytes": 1_000_000_000, "maxRows": 10_000_000}  # fmt: skip
    assert c.put("/api/v1/platform/dataset-limits", headers=admin, json={"maxBytes": 2_000_000, "maxRows": 1_000}).status_code == 200  # fmt: skip
    too_big = {"name": "x", "files": {"all": {"format": "jsonl", "sizeBytes": 2_000_001}}}
    assert c.post("/api/v1/datasets/upload-plan", headers=admin, json=too_big).status_code == 422
    rows = c.post(
        f"/api/v1/datasets/uploads/{upload(c, admin, {'all': ('jsonl', lines(1001))})}/build",
        headers=admin,
        json={"mapping": {"prompt": "question"}},
    )
    assert rows.status_code == 422 and "rows" in rows.text
    twice = c.post(
        f"/api/v1/datasets/uploads/{upload(c, admin, {'all': ('jsonl', lines(20) + lines(1))})}/build",
        headers=admin,
        json={"mapping": {"prompt": "question"}},
    )
    assert twice.status_code == 422 and "twice" in twice.text


def test_only_a_platform_administrator_changes_the_dataset_limits(setup):
    from labkit import login

    client, _, _ = setup
    member = login(client, "participant")
    assert client.get("/api/v1/platform/dataset-limits", headers=member).status_code == 200
    refused = client.put(
        "/api/v1/platform/dataset-limits", headers=member, json={"maxBytes": 2_000_000, "maxRows": 1_000}
    )
    assert refused.status_code == 403 and "Platform administrator" in refused.text


def test_a_device_without_the_private_route_gets_small_dataset_files_over_the_public_address(
    v3_study, tmp_path, monkeypatch
):
    # GSM8K demo tier 1, 2026-10-21: with Tailscale off, 3060-thao could never fetch the dataset (private grant only)
    from backend import local_storage

    c, admin, _ = v3_study
    store = c.app.state.store
    lab = (c, store, store.runtime, admin)
    (tmp_path / "private").mkdir()
    (tmp_path / "private/config.json").write_text(json.dumps({"publicWebUrl": "https://lab.example"}))
    monkeypatch.setenv("HETEROES_PRIVATE_CONFIG", str(tmp_path / "private"))
    upload_id = upload(c, admin, {"all": ("jsonl", lines(400))})
    data = c.post(
        f"/api/v1/datasets/uploads/{upload_id}/build", headers=admin, json={"mapping": {"prompt": "question"}}
    ).json()
    d, device_auth = pair(lab)
    model, _ = assets(v3_study)
    qualify_v3(c, device_auth, c.get("/api/v1/devices", headers=admin).json()[0]["selfTest"], model)
    run = c.post("/api/v1/experiments", headers=admin, json={**configuration(d, model, data), "datasetIds": [data["datasetId"]]})  # fmt: skip
    enable(lab, d, device_auth)
    assert c.post(f"/api/v1/experiments/{run.json()['experimentId']}/submit", headers=admin).status_code == 200
    store.dispatch_once()
    ar = store.runtime.runs()[0]
    query = {"assignmentId": ar["assignmentId"], "epoch": ar["epoch"], "sha256": data["objectSha256"]}
    grant = c.post("/api/v1/device/study-transfer", headers=device_auth, json=query).json()
    public = urlsplit(grant["publicUrl"])
    assert (public.scheme, public.netloc) == ("https", "lab.example") and public.path.startswith(
        "/api/v1/public-study/"
    )
    served = c.get(public.path)
    assert served.status_code == 200
    assert hashlib.sha256(served.content).hexdigest() == data["objectSha256"]
    # each link works only on its own route: the private one is not a public one, and the reverse
    assert c.get("/api/v1/public-study/" + urlsplit(grant["url"]).path.rsplit("/", 1)[1]).status_code == 403
    assert c.get("/api/v1/local-storage/" + public.path.rsplit("/", 1)[1]).status_code == 403
    # a file above the bound (never weights) only goes over the private route
    monkeypatch.setattr(local_storage, "PUBLIC_STUDY_MAX_BYTES", 10)
    assert "publicUrl" not in c.post("/api/v1/device/study-transfer", headers=device_auth, json=query).json()


def test_a_researcher_without_the_private_route_uploads_a_small_dataset_over_the_public_address(
    v3_study, tmp_path, monkeypatch
):
    # owner 2026-10-22: no Tailscale by default; a notebook far from the lab must still be able to send its dataset
    from backend import local_storage

    c, admin, _ = v3_study
    (tmp_path / "private").mkdir()
    (tmp_path / "private/config.json").write_text(json.dumps({"publicWebUrl": "https://lab.example"}))
    monkeypatch.setenv("HETEROES_PRIVATE_CONFIG", str(tmp_path / "private"))
    data = lines(400)
    sizes = {"all": {"format": "jsonl", "sizeBytes": len(data)}}
    plan = c.post("/api/v1/datasets/upload-plan", headers=admin, json={"name": "far", "files": sizes}).json()
    target = plan["files"]["all"]
    public = urlsplit(target["publicUrl"])
    assert (public.scheme, public.netloc) == ("https", "lab.example") and public.path.startswith(
        "/api/v1/public-upload/"
    )
    # each link works only on its own route
    assert c.put("/api/v1/local-storage/" + public.path.rsplit("/", 1)[1], content=data, headers=target["headers"]).status_code == 403  # fmt: skip
    assert c.put(public.path, content=data, headers=target["headers"]).status_code in (200, 201, 204)
    built = c.post(f"/api/v1/datasets/uploads/{plan['uploadId']}/build", headers=admin, json={"mapping": {"prompt": "question"}})  # fmt: skip
    assert built.status_code == 201, built.text
    # a file above the bound only goes over the private route
    monkeypatch.setattr(local_storage, "PUBLIC_STUDY_MAX_BYTES", 10)
    plan = c.post("/api/v1/datasets/upload-plan", headers=admin, json={"name": "far", "files": sizes}).json()
    assert "publicUrl" not in plan["files"]["all"]
