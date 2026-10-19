"""Workspace-scoped pinned models, immutable data and private transfer grants."""

from .migrations import initialize_study_schema
import hashlib
import json
import uuid
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from heteroes.study.data import dataset, canonical
from heteroes.study.models import validate as validate_model


class ImportData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    files: dict
    mapping: dict = Field(default_factory=lambda: {"prompt": "prompt", "answer": "answer"})
    adapter: str = "exact-number-v1"
    splitSeed: int = Field(default=42, ge=0, lt=2**53, strict=True)


class RegisterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
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
            value = dataset(body.files, seed=body.splitSeed, mapping=body.mapping, adapter=body.adapter)
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise HTTPException(422, "Invalid dataset format, mapping, exact answers or splits") from None
        payload = canonical(value)
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
            "adapter": value["adapter"],
        }
        result["datasetId"] = result["id"]
        return registry.save(result, current["workspaceId"], current["userId"], "dataset")

    @app.post("/api/v1/models/register", status_code=201)
    def register_model(body: RegisterModel, current=Depends(scoped)):
        try:
            validate_model(body.manifest)
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
            allowed = {config.get("datasetObjectSha256")}
            if config.get("modelSource") == "UPLOAD":
                allowed.update(config["modelManifest"]["files"].values())
            sha = body.get("sha256")
            if sha not in allowed or not isinstance(sha, str):
                raise HTTPException(403, "Object is outside the frozen assignment")
        return {"url": backend().download_url("objects/" + sha), "sha256": sha}
