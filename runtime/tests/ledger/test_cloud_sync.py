"""Retention persists cleanup intents and outage errors never kill computation."""

from types import SimpleNamespace

import pytest

from heteroes.product.cloud_sync import CloudSync
from heteroes.product.files import write_json, read_json


def test_local_retention_remembers_remote_cleanup_across_outage(tmp_path, monkeypatch):
    root = tmp_path / "runs" / "run"
    root.mkdir(parents=True)
    write_json(
        root / "assignment.json", {"assignmentId": "a" * 32, "epoch": 1, "config": {"backupPolicy": {"retain": 1}}}
    )
    for generation in range(3):
        point = root / "recovery-points" / str(generation)
        write_json(point / "manifest.json", {"generation": generation, "final": False, "backupPolicy": {"retain": 1}})
        write_json(point / "cloud-state.json", {"status": "VERIFYING", "remoteCreated": True})

    def offline(*args, **kwargs):
        raise ConnectionError("CPU is offline")

    agent = SimpleNamespace(root=tmp_path, manager=SimpleNamespace(root=tmp_path / "runs"), call=offline)
    now = [0.0]
    sync = CloudSync(agent, clock=lambda: now[0])
    sync.cycle()
    assert [p.name for p in (root / "recovery-points").iterdir()] == ["2"]
    assert set(read_json(root / "cloud-cleanup.json")) == {"0", "1"}
    deleted = []

    def online(path, body, method=None):
        if method == "DELETE":
            deleted.append(path)
            return {"deleted": True}
        return {"status": "READY"}

    agent.call = online
    now[0] = read_json(root / "cloud-backoff.json")["retryAt"]  # the outage backoff has passed
    sync.cycle()
    assert len(deleted) == 2 and read_json(root / "cloud-cleanup.json") == []
    assert read_json(root / "cloud-sync.json")["lastCloudGeneration"] == 2


def test_bad_local_metadata_does_not_terminate_sync_thread(tmp_path, monkeypatch):
    agent = SimpleNamespace(root=tmp_path)
    sync = CloudSync(agent)

    def broken():
        sync.stop.set()
        raise ValueError("Broken private manifest")

    monkeypatch.setattr(sync, "cycle", broken)
    sync.run()
    assert read_json(tmp_path / "cloud-error.json")["errorType"] == "ValueError"


# ---- M3: retention dependencies, bounded streaming upload, stateful backoff, verification cache ---------------------


def points_of(root, statuses, retain=1, final=()):
    write_json(
        root / "assignment.json", {"assignmentId": "a" * 32, "epoch": 1, "config": {"backupPolicy": {"retain": retain}}}
    )
    for generation, status in enumerate(statuses):
        point = root / "recovery-points" / str(generation)
        manifest = {"generation": generation, "final": generation in final, "backupPolicy": {"retain": retain}}
        write_json(point / "manifest.json", manifest)
        if status:
            write_json(point / "cloud-state.json", {"status": status, "remoteCreated": True})


def agent_for(tmp_path, call):
    return SimpleNamespace(root=tmp_path, manager=SimpleNamespace(root=tmp_path / "runs"), call=call)


def offline(*args, **kwargs):
    raise ConnectionError("CPU is offline")


def test_retention_keeps_the_newest_cloud_copy_until_a_newer_one_is_ready(tmp_path):
    root = tmp_path / "runs" / "run"
    points_of(root, ["READY", "READY", "VERIFYING", "VERIFYING"])
    CloudSync(agent_for(tmp_path, offline)).cycle()
    # g1 is the only verified cloud copy: neither its local bytes nor its remote object are removed
    assert sorted(p.name for p in (root / "recovery-points").iterdir()) == ["1", "3"]
    assert set(read_json(root / "cloud-cleanup.json")) == {"0", "2"}


def test_retention_keeps_the_paused_checkpoint(tmp_path):
    root = tmp_path / "runs" / "run"
    points_of(root, [None, None, None])
    write_json(root / "pause-point.json", {"pointId": "0", "generation": 0})
    CloudSync(agent_for(tmp_path, offline)).cycle()
    assert sorted(p.name for p in (root / "recovery-points").iterdir()) == ["0", "2"]


def test_failures_back_off_and_the_state_survives_a_restart(tmp_path):
    root = tmp_path / "runs" / "run"
    points_of(root, ["VERIFYING"])
    calls, now = [], [1000.0]

    def failing(path, body, method=None):
        calls.append(path)
        raise ConnectionError("CPU is offline")

    sync = CloudSync(agent_for(tmp_path, failing), clock=lambda: now[0])
    sync.cycle()
    assert read_json(root / "cloud-backoff.json") == {"failures": 1, "retryAt": 1030.0}
    assert read_json(root / "cloud-sync.json")["status"] == "PENDING"
    assert read_json(root / "cloud-sync.json")["retryAt"] == 1030.0
    attempts = len(calls)
    now[0] = 1029.0
    CloudSync(agent_for(tmp_path, failing), clock=lambda: now[0]).cycle()  # a restarted thread keeps waiting
    assert len(calls) == attempts
    now[0] = 1030.0
    sync.cycle()
    assert len(calls) > attempts and read_json(root / "cloud-backoff.json") == {"failures": 2, "retryAt": 1090.0}
    for _ in range(10):
        now[0] = read_json(root / "cloud-backoff.json")["retryAt"]
        sync.cycle()
    assert read_json(root / "cloud-backoff.json")["retryAt"] - now[0] == 3600  # capped


def test_success_clears_the_backoff(tmp_path, monkeypatch):
    root = tmp_path / "runs" / "run"
    points_of(root, ["ERROR"])
    write_json(root / "cloud-backoff.json", {"failures": 3, "retryAt": 0})
    monkeypatch.setattr(CloudSync, "upload", lambda self, point, assignment: {})
    CloudSync(agent_for(tmp_path, offline), clock=lambda: 10.0).cycle()
    assert read_json(root / "recovery-points" / "0" / "cloud-state.json")["status"] == "VERIFYING"
    assert not (root / "cloud-backoff.json").exists()


class Response:
    def __init__(self, etag="etag"):
        self.headers = {"ETag": etag}

    def read(self):
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def upload_with(tmp_path, monkeypatch, content, objects, changed=None):
    """Upload one point whose single file is `content`; returns the bytes each PUT streamed and the API calls."""
    import hashlib

    from heteroes.product import cloud_sync

    point = tmp_path / "point"
    point.mkdir()
    (point / "weights.bin").write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    manifest = {"pointId": "p", "files": {"weights.bin": {"sha256": digest, "sizeBytes": len(content)}}}
    monkeypatch.setattr(cloud_sync, "verify_point", lambda path, cache=False: manifest)
    sent, calls = [], []

    def urlopen(request, timeout=None):
        assert not isinstance(request.data, (bytes, bytearray))  # streamed, never the whole object in memory
        assert int(request.headers["Content-length"]) == request.data.size
        pieces = []
        while piece := request.data.read():
            assert len(piece) <= cloud_sync.UPLOAD_BLOCK
            pieces.append(piece)
            if changed is not None and len(pieces) == 1:
                with open(point / "weights.bin", "r+b") as stream:
                    stream.seek(changed)
                    stream.write(b"!")
        sent.append(b"".join(pieces))
        return Response(f"e{len(sent)}")

    def call(path, body, method=None):
        calls.append((path, body))
        if path == "/api/v1/device/recovery-points":
            return {"status": "UPLOADING", "objects": [{"sha256": digest, "sizeBytes": len(content), **objects}]}
        return {}

    monkeypatch.setattr(cloud_sync.urllib.request, "urlopen", urlopen)
    sync = CloudSync(SimpleNamespace(call=call))
    return sync, point, sent, calls


def test_a_single_object_is_streamed_in_bounded_blocks(tmp_path, monkeypatch):
    from heteroes.product.cloud_sync import UPLOAD_BLOCK

    content = bytes(range(256)) * (3 * UPLOAD_BLOCK // 256 + 7)
    sync, point, sent, calls = upload_with(
        tmp_path, monkeypatch, content, {"mode": "single", "url": "http://store/o", "headers": {}}
    )
    sync.upload(point, {"assignmentId": "a", "epoch": 1})
    assert sent == [content]
    assert [path for path, _ in calls][-2:] == [
        "/api/v1/device/recovery-points/complete-object",
        "/api/v1/device/recovery-points/p/verify",
    ]


def test_multipart_parts_are_streamed_and_keep_their_etags(tmp_path, monkeypatch):
    content = b"abcdefghij" * 1000
    parts = [
        {"number": 1, "offset": 0, "sizeBytes": 4000, "url": "http://store/1"},
        {"number": 2, "offset": 4000, "sizeBytes": 6000, "url": "http://store/2"},
    ]
    sync, point, sent, calls = upload_with(tmp_path, monkeypatch, content, {"mode": "multipart", "parts": parts})
    sync.upload(point, {"assignmentId": "a", "epoch": 1})
    assert sent == [content[:4000], content[4000:]]
    complete = next(body for path, body in calls if path.endswith("complete-object"))
    assert complete["parts"] == [{"PartNumber": 1, "ETag": "e1"}, {"PartNumber": 2, "ETag": "e2"}]


@pytest.mark.parametrize("mode", ["single", "multipart"])
def test_a_point_that_changes_while_uploading_is_never_completed(tmp_path, monkeypatch, mode):
    from heteroes.product.cloud_sync import UPLOAD_BLOCK

    content = b"x" * (2 * UPLOAD_BLOCK + 5)
    objects = (
        {"mode": "single", "url": "http://store/o", "headers": {}}
        if mode == "single"
        else {
            "mode": "multipart",
            "parts": [{"number": 1, "offset": 0, "sizeBytes": len(content), "url": "http://store/1"}],
        }
    )
    sync, point, sent, calls = upload_with(tmp_path, monkeypatch, content, objects, changed=len(content) - 1)
    with pytest.raises(ValueError, match="changed"):
        sync.upload(point, {"assignmentId": "a", "epoch": 1})
    assert not any(path.endswith("complete-object") for path, _ in calls)


def test_a_superseded_verified_point_is_also_removed_remotely(tmp_path):
    root = tmp_path / "runs" / "run"
    points_of(root, ["VERIFYING", "VERIFYING"])
    sync = CloudSync(agent_for(tmp_path, lambda path, body, method=None: {"status": "READY"}))
    sync.cycle()
    assert sorted(p.name for p in (root / "recovery-points").iterdir()) == ["1"]
    assert read_json(root / "cloud-cleanup.json") == ["0"]  # its remote copy is deleted on the next cycle
