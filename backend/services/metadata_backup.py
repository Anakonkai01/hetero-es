"""Hourly consistent product metadata backup; recovery storage failure leaves a local copy."""

from ..db.backups import backup_sqlite
from ..db.postgres_backup import snapshot_postgres
from ..repositories.metadata import MetadataRepository as repository
import logging
import hashlib
import json
import os
from pathlib import Path
import time
import uuid


def create_metadata_backup(store, storage):
    root = Path(store.path).parent / "metadata-backups"
    root.mkdir(mode=0o700, exist_ok=True, parents=True)
    point = root / uuid.uuid4().hex
    point.mkdir(mode=0o700)
    postgres = store.database.dialect == "postgresql"
    database = point / ("product.pgdump" if postgres else "product.sqlite")
    details = snapshot_postgres(store.database, database) if postgres else {}
    if not postgres:
        backup_sqlite(store, database)
    os.chmod(database, 0o600)
    with open(database, "rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    size_bytes = database.stat().st_size
    manifest = {
        "formatVersion": 1,
        "component": "heteroes-product-metadata",
        "createdAt": time.time(),
        "sha256": sha,
        "sizeBytes": size_bytes,
        "objectKey": "metadata/" + point.name + "/" + database.name,
        **details,
    }
    (point / "manifest.json").write_text(json.dumps(manifest))
    os.chmod(point / "manifest.json", 0o600)
    try:
        with storage.lock:
            usage = storage.usage()
            if usage["observedBytes"] + usage["reservedBytes"] + size_bytes + len(json.dumps(manifest)) > storage.quota:
                raise RuntimeError("Cloud quota reached")

            if hasattr(storage.backend, "put_file"):
                storage.backend.put_file(manifest["objectKey"], database)
            else:
                storage.backend.put(manifest["objectKey"], database.read_bytes())
            check = hashlib.sha256()
            size = 0
            for chunk in storage.backend.get(manifest["objectKey"]):
                check.update(chunk)
                size += len(chunk)
            if size != size_bytes or check.hexdigest() != sha:
                raise ValueError("Metadata checksum mismatch")
            storage.backend.put("metadata/" + point.name + "/manifest.json", json.dumps(manifest).encode())
        status = {"status": "READY", "pointId": point.name, "createdAt": manifest["createdAt"]}
    except Exception as error:
        status = {
            "status": "PENDING",
            "pointId": point.name,
            "errorType": type(error).__name__,
            "createdAt": manifest["createdAt"],
        }
    (point / "cloud-state.json").write_text(json.dumps(status))
    os.chmod(point / "cloud-state.json", 0o600)
    with store.db() as db:
        repository.set_backup_status(db, ("metadataBackupStatus", json.dumps(status)))
    points = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
    import shutil

    for old in points[24:]:
        if (old / "cloud-state.json").exists():
            storage.backend.delete("metadata/" + old.name + "/manifest.json")
            old_manifest = json.loads((old / "manifest.json").read_text())
            storage.backend.delete(old_manifest["objectKey"])
        shutil.rmtree(old)
    return status


def backup_loop(store, storage, stop):
    last = 0
    root = Path(store.path).parent / "metadata-backups"
    if root.exists():
        for point in root.glob("*/manifest.json"):
            last = max(last, json.loads(point.read_text())["createdAt"])
    while not stop.wait(60):
        if time.time() - last < 3600:
            continue
        try:
            create_metadata_backup(store, storage)
        except Exception as error:
            logging.getLogger(__name__).warning("Metadata backup failed: %s", type(error).__name__)
        last = time.time()
