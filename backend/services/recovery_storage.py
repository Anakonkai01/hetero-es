"""Recovery_Storage business operations; HTTP responses stay in api/."""

from ..core.storage_models import Begin, Finish
import secrets
import logging
from ..db.migrations import initialize_recovery_schema, initialize_recovery_downloads_schema
from .policies import backup_policy
import hashlib
import json
import re
import threading
import time
import uuid
from types import SimpleNamespace
from ..core.errors import ServiceError
from ..repositories.recovery_storage import RecoveryStorageRepository as repository
from .scheduling import cloud_sync_projection

HEX = re.compile("[a-f0-9]{64}")

UUID = re.compile("[a-f0-9]{32}")


class QuotaExceeded(RuntimeError):
    pass


class RecoveryStorage:
    # Legacy cloud_* table names preserve compatibility with existing lab databases.

    def __init__(self, store, backend, quota_bytes=8000000000):
        self.store = store
        self.backend = backend
        self.quota = quota_bytes
        self.lock = threading.RLock()
        with store.db() as db:
            initialize_recovery_downloads_schema(db)
        self.pending = set()

    def validate_manifest(self, m):
        from heteroes.recovery_manifest import validate_manifest

        validate_manifest(m)
        backup_policy(m.get("backupPolicy", {}))

    def usage(self):
        observed = self.backend.inventory()
        with self.store.db() as db:
            reserved = 2 * repository.usage_select_cloud_objects(db, ()).fetchone()[0]
        return {
            "quotaBytes": self.quota,
            "observedBytes": observed,
            "reservedBytes": reserved,
            "storageMode": getattr(self.backend, "mode", "local"),
            "warning": observed + reserved >= self.quota * 0.8,
        }

    def begin(self, m):
        self.validate_manifest(m)
        with self.lock:
            with self.store.db() as db:
                old = repository.begin_select_recovery_points(db, (m["pointId"],)).fetchone()
                if old and json.loads(old[0]) != m:
                    raise ValueError("Frozen recovery manifest changed")
                if old and old["status"] == "READY":
                    return {"pointId": m["pointId"], "status": "READY", "objects": []}
                unique = {}
                for meta in m["files"].values():
                    if meta["sha256"] in unique and unique[meta["sha256"]] != meta["sizeBytes"]:
                        raise ValueError("Hash/size mismatch")
                    unique[meta["sha256"]] = meta["sizeBytes"]
                existing = {r["sha"]: dict(r) for r in repository.begin_select_cloud_objects(db, ())}
                if any((sha in existing and existing[sha]["size"] != size for sha, size in unique.items())):
                    raise ValueError("Stored hash/size mismatch")
            usage = self.usage()
            new_bytes = 2 * sum((size for sha, size in unique.items() if sha not in existing))
            if usage["observedBytes"] + usage["reservedBytes"] + new_bytes + len(json.dumps(m)) > self.quota:
                raise QuotaExceeded("Recovery storage quota reached; compute continues with local recovery points")
            plans = []
            with self.store.db() as db:
                repository.begin_insert_recovery_points(
                    db, (m["pointId"], m["runId"], m["generation"], m["final"], "PENDING", json.dumps(m), time.time())
                )
                for sha, size in unique.items():
                    repository.begin_insert_cloud_objects(db, (sha, size))
                    repository.begin_insert_cloud_refs(db, (m["pointId"], sha))
            for sha, size in unique.items():
                entry = existing.get(sha)
                if entry and entry["status"] in ("READY", "UPLOADED"):
                    continue
                with self.store.db() as db:
                    row = repository.begin_select_cloud_objects_2(db, (sha,)).fetchone()
                if row["upload_plan"] and (row["expires"] or 0) > time.time() + 30:
                    plan = json.loads(row["upload_plan"])
                else:
                    if row["upload_plan"]:
                        previous = json.loads(row["upload_plan"])
                        if previous.get("uploadId"):
                            self.backend.abort(previous["key"], previous["uploadId"])
                    plan = self.backend.upload_plan("uploads/" + sha + "/" + uuid.uuid4().hex, size)
                    with self.store.db() as db:
                        repository.begin_update_cloud_objects(db, (json.dumps(plan), time.time() + 900, sha))
                plans.append({"sha256": sha, "sizeBytes": size, **plan})
            return {"pointId": m["pointId"], "status": "PENDING", "objects": plans}

    def complete_object(self, point_id, sha, parts):
        with self.lock:
            with self.store.db() as db:
                row = repository.complete_object_select_cloud_objects(db, (point_id, sha)).fetchone()
                if not row:
                    raise ValueError("Object is not referenced by this point")
                if row["status"] in ("READY", "UPLOADED"):
                    return
                plan = json.loads(row["upload_plan"])
            if plan["mode"] == "multipart":
                if len(parts) != len(plan["parts"]) or [p["PartNumber"] for p in parts] != list(
                    range(1, len(parts) + 1)
                ):
                    raise ValueError("Incomplete multipart upload")
                self.backend.complete(plan["key"], plan["uploadId"], parts)
            with self.store.db() as db:
                repository.complete_object_update_cloud_objects(db, (sha,))

    def verify(self, point_id):
        with self.lock:
            with self.store.db() as db:
                row = repository.verify_select_recovery_points(db, (point_id,)).fetchone()
                if not row:
                    raise ValueError("Point not found")
                m = json.loads(row["manifest"])
            try:
                for sha in {meta["sha256"] for meta in m["files"].values()}:
                    with self.store.db() as db:
                        obj = repository.verify_select_cloud_objects(db, (sha,)).fetchone()
                    if obj["status"] == "READY":
                        continue
                    hasher = hashlib.sha256()
                    size = 0
                    plan = json.loads(obj["upload_plan"])
                    upload_key = plan["key"]
                    if hasattr(self.backend, "read_version"):
                        etag, chunks = self.backend.read_version(upload_key)
                    else:
                        etag = None
                        chunks = self.backend.get(upload_key)
                    for chunk in chunks:
                        hasher.update(chunk)
                        size += len(chunk)
                        if size > obj["size"]:
                            raise ValueError("Object checksum/size mismatch")
                    if size != obj["size"] or hasher.hexdigest() != sha:
                        raise ValueError("Object checksum/size mismatch")
                    self.backend.publish_upload(upload_key, "objects/" + sha, etag)
                    with self.store.db() as db:
                        repository.verify_update_cloud_objects(db, (sha,))
                self.backend.put("manifests/" + point_id + ".json", json.dumps(m, sort_keys=True).encode())
                with self.store.db() as db:
                    repository.verify_update_recovery_points(db, (point_id,))
                self.retain(m["runId"], m["backupPolicy"]["retain"])
                with self.store.db() as db:
                    body = self.store.get(m["runId"])
                    if body:
                        old = body.get("cloudSync", {})
                        if old.get("lastCloudGeneration", -1) <= m["generation"]:
                            # The same rule as the coordinator-snapshot path: once a completed run has a verified
                            # final point, a periodic twin of that generation verified later never replaces it (B-022).
                            body["cloudSync"] = cloud_sync_projection(
                                db,
                                body,
                                {"status": "READY", "lastCloudGeneration": m["generation"], "pointId": point_id},
                            )
                            self.store.save(db, body)
            except Exception as error:
                if isinstance(error, ValueError):
                    with self.store.db() as db:
                        repository.verify_update_cloud_objects_2(db, (sha,))
                with self.store.db() as db:
                    repository.verify_update_recovery_points_2(db, ("ERROR", type(error).__name__, point_id))
                raise

    def verify_background(self, point_id):
        with self.lock:
            if point_id in self.pending:
                return
            self.pending.add(point_id)

        def work():
            try:
                self.verify(point_id)
            except Exception as error:
                logging.getLogger(__name__).warning("Recovery verification failed: %s", type(error).__name__)
            finally:
                with self.lock:
                    self.pending.discard(point_id)

        threading.Thread(target=work, daemon=True).start()

    def points(self, run_id):
        with self.store.db() as db:
            return [
                {
                    "pointId": r["id"],
                    "generation": r["generation"],
                    "final": bool(r["final"]),
                    "status": r["status"],
                    "errorType": r["error"],
                }
                for r in repository.points_select_recovery_points(db, (run_id,))
            ]

    def manifest(self, point_id):
        with self.store.db() as db:
            row = repository.manifest_select_recovery_points(db, (point_id,)).fetchone()
            if not row or row["status"] != "READY":
                raise ValueError("Verified recovery point unavailable")
            return json.loads(row["manifest"])

    def retain(self, run_id, count):
        points = [p for p in self.points(run_id) if p["status"] == "READY" and (not p["final"])]
        for point in points[count:]:
            self.delete_point(point["pointId"])

    def delete_point(self, point_id):
        with self.lock:
            self.backend.delete("manifests/" + point_id + ".json")
            with self.store.db() as db:
                repository.delete_point_delete_cloud_refs(db, (point_id,))
                repository.delete_point_delete_recovery_points(db, (point_id,))
                orphaned = [dict(r) for r in repository.delete_point_select_cloud_objects(db, ())]
            for obj in orphaned:
                plan = json.loads(obj["upload_plan"]) if obj["upload_plan"] else {}
                if plan.get("uploadId"):
                    self.backend.abort(plan["key"], plan["uploadId"])
                if plan.get("key"):
                    self.backend.delete(plan["key"])
                self.backend.delete("objects/" + obj["sha"])
                with self.store.db() as db:
                    repository.delete_point_delete_cloud_objects(db, (obj["sha"],))


def operations(store, storage, device_auth, user, scoped, authorized):
    with store.db() as db:
        initialize_recovery_schema(db)

    def grant(device, assignment_id, epoch, run_id):
        with store.db() as db:
            row = repository.grant_select_assignments(db, (assignment_id,)).fetchone()
            if not row or (row["coordinator"], row["epoch"], row["run_id"]) != (device["id"], epoch, run_id):
                raise ServiceError(403, "Recovery upload is outside this assignment")

    def point_run(point_id):
        with store.db() as db:
            row = repository.point_run_select_recovery_points(db, (point_id,)).fetchone()
            if not row:
                raise ServiceError(404, "Recovery point not found")
            return row[0]

    def storage_error(error):
        raise ServiceError(
            409 if isinstance(error, QuotaExceeded) else 422,
            "Recovery quota reached; local computation continues"
            if isinstance(error, QuotaExceeded)
            else "Recovery storage operation failed",
        ) from None

    def begin(body: Begin, *, current):
        grant(current, body.assignmentId, body.epoch, body.manifest.get("runId"))
        try:
            return storage.begin(body.manifest)
        except (ValueError, QuotaExceeded) as error:
            storage_error(error)

    def complete(body: Finish, *, current):
        grant(current, body.assignmentId, body.epoch, point_run(body.pointId))
        try:
            storage.complete_object(body.pointId, body.sha256, body.parts)
        except (ValueError, QuotaExceeded) as error:
            storage_error(error)
        return {"ok": True}

    def verify(point_id: str, body: dict, *, current):
        grant(current, body.get("assignmentId"), body.get("epoch"), point_run(point_id))
        storage.verify_background(point_id)
        return {"status": "VERIFYING"}

    def device_status(point_id: str, *, current):
        run_id = point_run(point_id)
        with store.db() as db:
            row = repository.device_status_select_assignments(db, (run_id,)).fetchone()
            if not row or row[0] != current["id"]:
                raise ServiceError(403, "Coordinator identity required")
        return next((p for p in storage.points(run_id) if p["pointId"] == point_id))

    def abandon(point_id: str, body: dict, *, current):
        grant(current, body.get("assignmentId"), body.get("epoch"), point_run(point_id))
        with storage.lock:
            point = next((p for p in storage.points(point_run(point_id)) if p["pointId"] == point_id))
            if point["status"] == "READY":
                return {"deleted": False, "retained": True}
            storage.delete_point(point_id)
        return {"deleted": True}

    def historical(run_id, current):
        body = authorized(run_id, current)
        if not current.get("platformAdmin") or body["status"] != "COMPLETED":
            raise ServiceError(403, "Completed experiment and platform administrator required")
        with store.db() as db:
            if repository.historical_select_assignments(db, (run_id,)).fetchone():
                raise ServiceError(409, "Use the assigned coordinator for this experiment")
        return body

    def import_begin(run_id: str, body: dict, *, current):
        experiment = historical(run_id, current)
        if (
            body.get("runId") != run_id
            or body.get("final") is not True
            or body.get("childWeightsSha256") != experiment.get("modelVersion")
        ):
            raise ServiceError(422, "Imported point disagrees with the historical final checkpoint")
        try:
            result = storage.begin(body)
        except (ValueError, QuotaExceeded) as error:
            storage_error(error)
        with store.db() as db:
            store.audit(db, current["userId"], "HISTORICAL_RECOVERY_IMPORT", body["pointId"], experiment["workspaceId"])
        return result

    def import_complete(run_id: str, body: dict, *, current):
        historical(run_id, current)
        if point_run(body.get("pointId")) != run_id:
            raise ServiceError(403, "Recovery point belongs to another experiment")
        try:
            storage.complete_object(body["pointId"], body["sha256"], body.get("parts", []))
        except (ValueError, QuotaExceeded) as error:
            storage_error(error)
        return {"ok": True}

    def import_verify(run_id: str, point_id: str, *, current):
        historical(run_id, current)
        if point_run(point_id) != run_id:
            raise ServiceError(403, "Recovery point belongs to another experiment")
        storage.verify_background(point_id)
        return {"status": "VERIFYING"}

    def points(run_id: str, *, current):
        authorized(run_id, current)
        return storage.points(run_id)

    def download_plan(point_id: str, *, current):
        authorized(point_run(point_id), current)
        try:
            m = storage.manifest(point_id)
        except ValueError:
            raise ServiceError(409, "Recovery point is not verified") from None
        return {
            "manifest": m,
            "objects": {
                name: storage.backend.download_url("objects/" + meta["sha256"]) for name, meta in m["files"].items()
            },
        }

    def delete(point_id: str, *, current):
        body = authorized(point_run(point_id), current)
        storage.delete_point(point_id)
        with store.db() as db:
            store.audit(db, current["userId"], "CLOUD_COPY_DELETED", point_id, body["workspaceId"])
        return {"deleted": True}

    def ticket(artifact_id: str, token: str, *, current):
        run_id, _, name = artifact_id.partition(".")
        authorized(run_id, current)
        if not re.fullmatch("[a-f0-9]{64}\\.bin", name):
            raise ServiceError(404, "Cloud checkpoint not found")
        sha = name[:-4]
        found = False
        for point in storage.points(run_id):
            if point["status"] == "READY" and any(
                (v["sha256"] == sha for v in storage.manifest(point["pointId"])["files"].values())
            ):
                found = True
                break
        if not found:
            raise ServiceError(404, "Cloud checkpoint not ready")
        secret = secrets.token_urlsafe(32)
        td = hashlib.sha256(secret.encode()).hexdigest()
        session_digest, ticket_expiry = store.authentication.download_session(token, current["userId"])
        path = "/api/v1/cloud-downloads/" + td
        with store.db() as db:
            repository.ticket_insert_cloud_downloads(
                db, (td, current["userId"], session_digest, run_id, sha, ticket_expiry)
            )
        return {"downloadUrl": path, "secret": secret}

    def consume(ticket_digest: str, secret: str):
        if hashlib.sha256(secret.encode()).hexdigest() != ticket_digest:
            raise ServiceError(401, "Download ticket required")
        with store.db() as db:
            row = repository.consume_select_cloud_downloads(db, (ticket_digest, time.time())).fetchone()
            if not row:
                raise ServiceError(401, "Download ticket expired")
            if (
                not store.authentication.external_download_session(row["session_digest"])
                and not repository.consume_select_sessions(
                    db, (row["session_digest"], row["user_id"], time.time())
                ).fetchone()
            ):
                raise ServiceError(401, "Session revoked")
            body = store.get(row["run_id"])
            profile = store.profile(row["user_id"])
            membership = repository.consume_select_memberships(db, (body["workspaceId"], row["user_id"])).fetchone()
            if (
                profile["accountStatus"] != "ACTIVE"
                or not membership
                or (membership[0] != "ADMIN" and body["ownerUserId"] != row["user_id"])
            ):
                raise ServiceError(403, "Experiment access revoked")
            repository.consume_delete_cloud_downloads(db, (ticket_digest,))
        return storage.backend.download_url("objects/" + row["sha"])

    return SimpleNamespace(
        grant=grant,
        point_run=point_run,
        storage_error=storage_error,
        begin=begin,
        complete=complete,
        verify=verify,
        device_status=device_status,
        abandon=abandon,
        historical=historical,
        import_begin=import_begin,
        import_complete=import_complete,
        import_verify=import_verify,
        points=points,
        download_plan=download_plan,
        delete=delete,
        ticket=ticket,
        consume=consume,
    )
