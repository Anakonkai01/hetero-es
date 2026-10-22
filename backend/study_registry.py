"""Workspace-scoped pinned models, immutable data and private transfer grants."""

from .migrations import initialize_study_schema
import hashlib
import json
from pathlib import Path
import uuid
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from heteroes.study.data import dataset, canonical
from heteroes.study.models import validate as validate_model
from heteroes.v3 import data as v3data
from .policies import platform_profile


class ImportData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipeVersion: int = Field(default=2, ge=2, le=3, strict=True)
    name: str = Field(min_length=1, max_length=100)
    files: dict
    mapping: dict | None = None
    adapter: str = "exact-number-v1"
    splitSeed: int = Field(default=42, ge=0, lt=2**53, strict=True)


class DatasetUpload(BaseModel):
    """A large Recipe v3 dataset: one file or three named splits, uploaded with signed requests, then built."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    files: dict


class DatasetBuild(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mapping: dict | None = None
    splitSeed: int = Field(default=42, ge=0, lt=2**53, strict=True)


class DatasetLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maxBytes: int = Field(ge=1_000_000, le=50_000_000_000, strict=True)
    maxRows: int = Field(ge=1_000, le=1_000_000_000, strict=True)


def dataset_limits(store):
    """The platform's limits for one dataset file (owner default 2026-10-20: 1 GB and 10 million rows)."""
    with store.db() as db:
        row = db.execute("SELECT value FROM settings WHERE key='datasetLimits'").fetchone()
    return (
        json.loads(row[0]) if row else {"maxBytes": v3data.DEFAULT_MAX_BYTES, "maxRows": v3data.DEFAULT_MAX_FILE_ROWS}
    )


class RegisterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipeVersion: int = Field(default=2, ge=2, le=3, strict=True)
    name: str = Field(min_length=1, max_length=100)
    manifest: dict
    source: str = "REFERENCE"


class Registry:
    def __init__(self, store):
        self.store = store
        with store.db() as db:
            initialize_study_schema(db)

    def list(self, workspace, kind):
        with self.store.db() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT body FROM study_assets WHERE workspace_id=? AND kind=? ORDER BY rowid", (workspace, kind)
                )
            ]

    def get(self, asset_id, workspace, kind):
        with self.store.db() as db:
            row = db.execute(
                "SELECT body FROM study_assets WHERE id=? AND workspace_id=? AND kind=?", (asset_id, workspace, kind)
            ).fetchone()
        if not row:
            raise HTTPException(404, "Workspace asset not found")
        return json.loads(row[0])

    def save(self, body, workspace, owner, kind):
        with self.store.db() as db:
            db.execute(
                "INSERT INTO study_assets VALUES (?,?,?,?,?)", (body["id"], workspace, owner, kind, json.dumps(body))
            )
            self.store.audit(db, owner, "REGISTER_" + kind.upper(), body["id"], workspace)
        return body


def install_routes(app, registry, runtime, scoped, device_auth):
    def backend():
        if runtime.storage_backend is None:
            raise HTTPException(409, "Configure local artifact storage first")
        return runtime.storage_backend

    @app.post("/api/v1/datasets/import", status_code=201)
    def import_data(body: ImportData, current=Depends(scoped)):
        try:
            value = (
                v3data.dataset(body.files, seed=body.splitSeed, mapping=body.mapping)
                if body.recipeVersion == 3
                else dataset(body.files, seed=body.splitSeed, mapping=body.mapping, adapter=body.adapter)
            )
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise HTTPException(422, "Invalid dataset format, mapping, exact answers or splits") from None
        payload = canonical(value)
        if len(payload) > 10_000_000:
            raise HTTPException(422, "Dataset document exceeds 10 MB")
        digest = hashlib.sha256(payload).hexdigest()
        store_backend = backend()
        if hasattr(store_backend, "inventory") and store_backend.inventory() + len(payload) > getattr(
            store_backend, "quota_bytes", 200_000_000_000
        ):
            raise HTTPException(507, "Artifact quota exceeded")
        store_backend.put("objects/" + digest, payload)
        result = {
            "id": uuid.uuid4().hex,
            "datasetId": None,
            "name": body.name,
            "workspaceId": current["workspaceId"],
            "ownerUserId": current["userId"],
            "status": "READY",
            "objectSha256": digest,
            "identity": {k: value[k] for k in ("contentHash", "splitHashes")},
            "counts": {k: len(v) for k, v in value["splits"].items()},
            "splitSeed": value["splitSeed"],
            "splitMode": value["splitMode"],
            "adapter": value.get("adapter"),
            "recipeVersion": body.recipeVersion,
            "columns": sorted(set.intersection(*(set(row) for rows in value["splits"].values() for row in rows))),
        }
        result["datasetId"] = result["id"]
        return registry.save(result, current["workspaceId"], current["userId"], "dataset")

    @app.get("/api/v1/platform/dataset-limits")
    def get_dataset_limits(current=Depends(scoped)):
        return dataset_limits(registry.store)

    @app.put("/api/v1/platform/dataset-limits")
    def set_dataset_limits(body: DatasetLimits, current=Depends(scoped)):
        platform_profile(current)
        with registry.store.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES ('datasetLimits', ?)", (json.dumps(body.model_dump()),))
            registry.store.audit(db, current["userId"], "DATASET_LIMITS_CHANGED", json.dumps(body.model_dump()))
        return body.model_dump()

    @app.post("/api/v1/datasets/upload-plan", status_code=201)
    def dataset_upload_plan(body: DatasetUpload, current=Depends(scoped)):
        limits = dataset_limits(registry.store)
        names = set(body.files)
        if names not in ({"all"}, set(v3data.SPLITS)) or any(
            not isinstance(f, dict)
            or set(f) != {"format", "sizeBytes"}
            or f["format"] not in ("jsonl", "csv", "json")
            or type(f["sizeBytes"]) is not int
            or not 1 <= f["sizeBytes"] <= limits["maxBytes"]
            for f in body.files.values()
        ):
            raise HTTPException(
                422, f"Give one file or three splits (.jsonl, .csv or .json) of at most {limits['maxBytes']} bytes"
            )
        b = backend()
        if hasattr(b, "inventory") and b.inventory() + 3 * sum(f["sizeBytes"] for f in body.files.values()) > getattr(
            b, "quota_bytes", 200_000_000_000
        ):
            raise HTTPException(507, "Artifact quota exceeded")
        upload_id = uuid.uuid4().hex
        files, plans = {}, {}
        for name, f in sorted(body.files.items()):
            key = "uploads/" + hashlib.sha256(f"{upload_id}:{name}".encode()).hexdigest() + "/" + upload_id
            files[name] = {**f, "key": key}
            plans[name] = b.upload_plan(key, f["sizeBytes"], public_base=runtime.public_web_url())
        record = {"id": upload_id, "name": body.name, "ownerUserId": current["userId"], "files": files}
        registry.save(record, current["workspaceId"], current["userId"], "dataset-upload")
        return {"uploadId": upload_id, "files": plans}

    @app.post("/api/v1/datasets/uploads/{upload_id}/build", status_code=201)
    def build_uploaded_dataset(upload_id: str, body: DatasetBuild, current=Depends(scoped)):
        import shutil
        import tempfile

        upload = registry.get(upload_id, current["workspaceId"], "dataset-upload")
        if upload["ownerUserId"] != current["userId"]:
            raise HTTPException(403, "Only the uploader may build this dataset")
        mapping = body.mapping or {"prompt": "prompt"}
        if set(mapping) != {"prompt"} or not isinstance(mapping["prompt"], str) or not mapping["prompt"]:
            raise HTTPException(422, "Map the prompt field; the scorer selects its other columns")
        limits, b = dataset_limits(registry.store), backend()
        work = Path(tempfile.mkdtemp(prefix=".dataset-build-", dir=b.root))
        try:
            sources = {}
            for name, f in upload["files"].items():
                source = work / f"source-{name}.{f['format']}"
                try:
                    with source.open("wb") as stream:
                        for chunk in b.get(f["key"]):
                            stream.write(chunk)
                except FileNotFoundError:
                    raise HTTPException(409, "Upload every file before building the dataset") from None
                if source.stat().st_size != f["sizeBytes"]:
                    raise HTTPException(409, "An uploaded file is incomplete")
                sources[name] = (source, f["format"])
            try:
                document = v3data.build_file_dataset(
                    sources,
                    work / "out",
                    split_seed=body.splitSeed,
                    prompt_field=mapping["prompt"],
                    max_bytes=limits["maxBytes"],
                    max_rows=limits["maxRows"],
                )
                columns = v3data.common_columns(v3data.open_dataset(work / "out" / "dataset.json"))
            except (ValueError, KeyError, TypeError, UnicodeError) as error:
                raise HTTPException(422, f"Invalid dataset: {error}") from None
            for sha in v3data.split_files(document):
                b.put_file("objects/" + sha, work / "out" / f"{sha}.jsonl", sha)
            payload = canonical(document)
            digest = hashlib.sha256(payload).hexdigest()
            b.put("objects/" + digest, payload)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        for f in upload["files"].values():
            b.delete(f["key"])
        result = {
            "id": uuid.uuid4().hex,
            "datasetId": None,
            "name": upload["name"],
            "workspaceId": current["workspaceId"],
            "ownerUserId": current["userId"],
            "status": "READY",
            "objectSha256": digest,
            "identity": {k: document[k] for k in ("contentHash", "splitHashes")},
            "counts": document["splitCounts"],
            "splitSeed": document["splitSeed"],
            "splitMode": document["splitMode"],
            "adapter": None,
            "recipeVersion": 3,
            "formatVersion": v3data.FILE_FORMAT_VERSION,
            "splitObjects": sorted(v3data.split_files(document)),
            "sizeBytes": sum(document["splitBytes"].values()),
            "columns": columns,
        }
        result["datasetId"] = result["id"]
        return registry.save(result, current["workspaceId"], current["userId"], "dataset")

    @app.post("/api/v1/models/register", status_code=201)
    def register_model(body: RegisterModel, current=Depends(scoped)):
        try:
            validate_model(body.manifest, allow_any=body.recipeVersion == 3)
        except (ValueError, TypeError, KeyError):
            raise HTTPException(422, "Use a supported text model with pinned safetensors files") from None
        if body.source not in ("REFERENCE", "UPLOAD"):
            raise HTTPException(422, "Use REFERENCE or UPLOAD")
        model_id = uuid.uuid4().hex
        result = {
            "id": model_id,
            "modelArtifactId": model_id,
            "name": body.name,
            "workspaceId": current["workspaceId"],
            "ownerUserId": current["userId"],
            "reference": body.manifest["modelId"],
            "recipeVersion": body.recipeVersion,
            "revision": body.manifest["revision"],
            "manifest": body.manifest,
            "source": body.source,
            "status": "REGISTERED" if body.source == "REFERENCE" else "AWAITING_FILES",
            "manifestHash": hashlib.sha256(canonical(body.manifest)).hexdigest(),
        }
        return registry.save(result, current["workspaceId"], current["userId"], "model")

    @app.post("/api/v1/models/{asset_id}/upload-plan")
    def upload_plan(asset_id: str, sizes: dict, current=Depends(scoped)):
        asset = registry.get(asset_id, current["workspaceId"], "model")
        if asset["ownerUserId"] != current["userId"] or asset["source"] != "UPLOAD":
            raise HTTPException(403, "Only the uploader may publish this model")
        expected = asset["manifest"]["files"]
        if set(sizes) != set(expected) or any(
            type(n) is not int or not 1 <= n <= 5_000_000_000 for n in sizes.values()
        ):
            raise HTTPException(422, "Provide the exact pinned file sizes")
        b = backend()
        if hasattr(b, "inventory") and b.inventory() + sum(sizes.values()) > getattr(b, "quota_bytes", 200_000_000_000):
            raise HTTPException(507, "Artifact quota exceeded")
        result = {}
        with registry.store.db() as db:
            for name, size in sizes.items():
                identity = uuid.uuid4().hex
                key = "uploads/" + expected[name] + "/" + identity
                db.execute(
                    "INSERT INTO study_uploads VALUES (?,?,?,?,?,?)",
                    (identity, asset_id, name, expected[name], key, size),
                )
                result[name] = {"uploadId": identity, **b.upload_plan(key, size)}
        return result

    @app.post("/api/v1/models/{asset_id}/publish")
    def publish(asset_id: str, current=Depends(scoped)):
        asset = registry.get(asset_id, current["workspaceId"], "model")
        if asset["ownerUserId"] != current["userId"] or asset["source"] != "UPLOAD":
            raise HTTPException(403, "Only the uploader may publish this model")
        b = backend()
        with registry.store.db() as db:
            for name, sha in asset["manifest"]["files"].items():
                try:
                    hasher = hashlib.sha256()
                    for chunk in b.get("objects/" + sha):
                        hasher.update(chunk)
                    if hasher.hexdigest() == sha:
                        continue
                except FileNotFoundError:
                    pass
                uploaded = False
                for row in db.execute(
                    "SELECT * FROM study_uploads WHERE asset_id=? AND name=? ORDER BY rowid DESC", (asset_id, name)
                ):
                    try:
                        etag, chunks = b.read_version(row["upload_key"])
                        hasher = hashlib.sha256()
                        length = 0
                        for chunk in chunks:
                            hasher.update(chunk)
                            length += len(chunk)
                        if hasher.hexdigest() != sha or length != row["size"]:
                            continue
                        b.publish_upload(row["upload_key"], "objects/" + sha, etag)
                        uploaded = True
                        break
                    except (FileNotFoundError, ValueError):
                        continue
                if not uploaded:
                    raise HTTPException(409, "A pinned file is missing, incomplete or has the wrong checksum")
            asset["status"] = "READY"
            db.execute("UPDATE study_assets SET body=? WHERE id=?", (json.dumps(asset), asset_id))
        return asset

    @app.post("/api/v1/device/study-transfer")
    def transfer(body: dict, current=Depends(device_auth)):
        # Fresh grants are issued only to an active member of this frozen epoch.
        with registry.store.db() as db:
            row = db.execute(
                "SELECT * FROM assignments WHERE id=? AND epoch=? AND released=0",
                (body.get("assignmentId"), body.get("epoch")),
            ).fetchone()
            if not row:
                raise HTTPException(403, "Assignment is stale or released")
            ar = json.loads(row["body"])
            if current["id"] not in ar["deviceIds"]:
                raise HTTPException(403, "Device is not selected")
            config = ar["config"]
            datasets = {config.get("datasetObjectSha256"), *config.get("datasetSplitObjects", [])}
            allowed = set(datasets)
            if config.get("modelSource") == "UPLOAD":
                allowed.update(config["modelManifest"]["files"].values())
            sha = body.get("sha256")
            if sha not in allowed or not isinstance(sha, str):
                raise HTTPException(403, "Object is outside the frozen assignment")
        grant = {"url": backend().download_url("objects/" + sha), "sha256": sha}
        public = runtime.public_web_url()
        if public and sha in datasets:
            # for a device that cannot reach the private route (no Tailscale): small dataset files only
            if url := backend().public_study_url(public, "objects/" + sha):
                grant["publicUrl"] = url
        return grant
