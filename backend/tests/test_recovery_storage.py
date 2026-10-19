"""Real manifest/quota logic against an in-memory object service, not cloud evidence."""

import hashlib
import json
import pytest
from backend.recovery_storage import RecoveryStorage, QuotaExceeded
from backend.devices import AgentRuntime
from backend.store import Store


class Objects:
    def __init__(self):
        self.data = {}

    def inventory(self):
        return sum(map(len, self.data.values()))

    def get(self, key):
        yield self.data[key]

    def put(self, key, data):
        self.data[key] = data

    def publish_upload(self, source, destination, etag):
        self.data[destination] = self.data.pop(source)

    def delete(self, key):
        self.data.pop(key, None)

    def upload_plan(self, key, size):
        return {"mode": "single", "key": key, "url": "https://private.invalid/secret", "headers": {}}

    def complete(self, key, upload_id, parts):
        pass

    def abort(self, key, upload_id):
        pass

    def download_url(self, key):
        return "https://private.invalid/secret"


@pytest.fixture
def storage(tmp_path):
    r = AgentRuntime()
    s = Store(tmp_path / "lab.sqlite", {"admin": "test-admin-pass"}, r)
    objects = Objects()
    return RecoveryStorage(s, objects, quota_bytes=10000), objects, s


def manifest(payload=b"weights", point="a" * 32):
    sha = hashlib.sha256(payload).hexdigest()
    return {
        "formatVersion": 1,
        "pointId": point,
        "runId": "b" * 32,
        "generation": 0,
        "final": False,
        "backupPolicy": {"interval": 1, "retain": 3},
        "childWeightsSha256": sha,
        "parentWeightsSha256": sha,
        "files": {
            "weights/" + sha + ".bin": {"sha256": sha, "sizeBytes": len(payload)},
            "ledger.sqlite": {"sha256": sha, "sizeBytes": len(payload)},
            "config.json": {"sha256": sha, "sizeBytes": len(payload)},
            "identity.json": {"sha256": sha, "sizeBytes": len(payload)},
        },
    }


def upload(storage, objects, m, payload=b"weights"):
    plan = storage.begin(m)
    for entry in plan["objects"]:
        objects.put(entry["key"], payload)
    storage.verify(m["pointId"])
    return plan


def test_manifest_published_last_and_contents_deduplicated(storage):
    st, obj, s = storage
    m = manifest()
    plan = st.begin(m)
    assert st.points(m["runId"])[0]["status"] == "PENDING"
    assert "manifests/" + m["pointId"] + ".json" not in obj.data
    assert len(plan["objects"]) == 1
    for entry in plan["objects"]:
        obj.put(entry["key"], b"weights")
    st.verify(m["pointId"])
    assert st.points(m["runId"])[0]["status"] == "READY"
    assert json.loads(obj.data["manifests/" + m["pointId"] + ".json"]) == m


def test_bad_content_never_becomes_ready(storage):
    st, obj, s = storage
    m = manifest()
    plan = st.begin(m)
    obj.put(plan["objects"][0]["key"], b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        st.verify(m["pointId"])
    assert st.points(m["runId"])[0]["status"] == "ERROR"
    assert "manifests/" + m["pointId"] + ".json" not in obj.data


def test_inflight_reservations_count_and_shared_objects_are_not_deleted(storage):
    st, obj, s = storage
    upload(st, obj, manifest())
    upload(st, obj, manifest(point="c" * 32))
    st.delete_point("a" * 32)
    assert any(k.startswith("objects/") for k in obj.data)
    assert st.points("b" * 32)[0]["status"] == "READY"
    st.quota = 500
    with pytest.raises(QuotaExceeded):
        st.begin(manifest(b"x" * 2000, point="d" * 32))
    assert len(st.points("b" * 32)) == 1


def test_unsafe_paths_and_changed_point_identity_are_rejected(storage):
    st, obj, s = storage
    m = manifest()
    m["files"]["../../secret"] = m["files"]["ledger.sqlite"]
    with pytest.raises(ValueError):
        st.begin(m)
    m = manifest()
    st.begin(m)
    with pytest.raises(ValueError):
        st.begin({**m, "generation": 1})


def test_metadata_backup_is_consistent_and_keeps_local_copy(storage):
    from backend.metadata_backup import create_metadata_backup
    from pathlib import Path
    import sqlite3

    st, obj, s = storage
    st.quota = 1_000_000
    result = create_metadata_backup(s, st)
    assert result["status"] == "READY"
    path = Path(s.path).parent / "metadata-backups" / result["pointId"] / "product.sqlite"
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    st.quota = 1
    result = create_metadata_backup(s, st)
    assert result["status"] == "PENDING"
    assert (Path(s.path).parent / "metadata-backups" / result["pointId"] / "product.sqlite").exists()


def test_uploaded_object_completion_is_idempotent_and_temp_keys_do_not_change_ready(storage):
    st, obj, s = storage
    m = manifest()
    plan = st.begin(m)
    entry = plan["objects"][0]
    assert entry["key"].startswith("uploads/")
    obj.put(entry["key"], b"weights")
    st.complete_object(m["pointId"], entry["sha256"], [])
    st.complete_object(m["pointId"], entry["sha256"], [])
    assert st.begin(m)["objects"] == []
    st.verify(m["pointId"])
    obj.put(entry["key"], b"changed-after-verify")
    assert obj.data["objects/" + entry["sha256"]] == b"weights"


def test_v3_manifest_objects_roundtrip_and_reject_unlisted_paths(storage):
    st, obj, _ = storage
    m = manifest()
    m["formatVersion"] = 2
    meta = m["files"]["ledger.sqlite"]
    m["files"].update(
        {"v3-state.json": meta, "initial-adapter.bin": meta, "selection/" + meta["sha256"] + ".bin": meta}
    )
    upload(st, obj, m)
    assert st.manifest(m["pointId"]) == m
    bad = json.loads(json.dumps(m))
    bad["files"]["selection/../config.json"] = meta
    with pytest.raises(ValueError, match="[Uu]nsafe"):
        st.validate_manifest(bad)
    bad = json.loads(json.dumps(m))
    del bad["files"]["v3-state.json"]
    with pytest.raises(ValueError, match="[Ii]ncomplete"):
        st.validate_manifest(bad)
    bad = json.loads(json.dumps(m))
    bad["files"]["selection/" + "f" * 64 + ".bin"] = bad["files"].pop("selection/" + meta["sha256"] + ".bin")
    with pytest.raises(ValueError, match="checksum"):
        st.validate_manifest(bad)
