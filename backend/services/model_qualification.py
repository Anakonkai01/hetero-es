"""Model_Qualification business operations; HTTP responses stay in api/."""

from ..core.study_models import ProbeRequest
import json
import re
import time
import uuid
from heteroes.canonical import canonical_json_hash
from heteroes.product.model_qualification import STRICT_DECODER, check_reference, qualification_key, verify_observations
from ..policies import has_device_reservation, noise_qualification
from heteroes.noise.contracts import ENGINE_VERSION, CPU_NOISE_FINGERPRINTS
from heteroes.product.cpu_coordinator import coordinator_only
from types import SimpleNamespace
from ..core.errors import ServiceError
from ..repositories.model_qualification import ModelQualificationRepository as repository
from ..db.transactions import begin_write

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def restore_mismatch(report):
    if report.errorCode == "RESTORE_MISMATCH":
        return True
    observations = report.observations
    if not isinstance(observations, dict):
        return False
    return any(
        isinstance(row, dict)
        and isinstance(row.get("parentSha256"), str)
        and re.fullmatch("[a-f0-9]{64}", row["parentSha256"])
        and isinstance(row.get("restoredSha256"), str)
        and re.fullmatch("[a-f0-9]{64}", row["restoredSha256"])
        and row["parentSha256"] != row["restoredSha256"]
        for sign in ("1", "-1")
        for row in (observations.get(sign) if isinstance(observations.get(sign), list) else [])
    )


class ModelQualifications:
    def __init__(self, runtime):
        self.runtime = runtime

    @property
    def store(self):
        return self.runtime.store

    def save(self, db, job):
        repository.save_update_model_probe_jobs(db, (json.dumps(job, allow_nan=False), job["jobId"]))

    def reference(self, db, workspace, manifest_hash, engine=ENGINE_VERSION):
        if engine == ENGINE_VERSION:
            return repository.reference_select_model_references(db, (workspace, manifest_hash)).fetchone()
        return repository.reference_select_model_engine_references(db, (workspace, manifest_hash, engine)).fetchone()

    def effective_profile(self, db, device, profile, workspace):
        # Old immutable rows prove v1 only. New references have a separate engine key; neither rewrites the other.
        by_engine = {k: list(v) for k, v in (profile.get("qualifiedModelsByNoiseEngine") or {}).items()}
        baseline = by_engine.setdefault(profile.get("noiseVersion", ENGINE_VERSION), [])
        for digest in profile.get("qualifiedModelHashes", []):
            if digest not in baseline:
                baseline.append(digest)
        for table, engine_clause in (
            ("model_qualifications", ""),
            ("model_engine_qualifications", " AND r.engine=q.engine"),
        ):
            references = "model_references" if table == "model_qualifications" else "model_engine_references"
            engine_column = "'" + ENGINE_VERSION + "'" if not engine_clause else "q.engine"
            for row in repository.effective_profile_select_value(
                db,
                (device, workspace, canonical_json_hash(profile)),
                engine_clause=engine_clause,
                engine_column=engine_column,
                references=references,
                table=table,
            ):
                hashes = by_engine.setdefault(row[1], [])
                if row[0] not in hashes:
                    hashes.append(row[0])
        return {
            **profile,
            "qualifiedModelHashes": sorted({h for values in by_engine.values() for h in values}),
            "qualifiedModelsByNoiseEngine": by_engine,
        }

    def start(self, asset, device_id, current, engine=None, decoder=None):
        with self.store.db() as db:
            begin_write(db)
            device = repository.start_select_devices(db, (device_id,)).fetchone()
            allocation = (
                repository.start_select_worker_assignments(db, (device["worker_id"],)).fetchone() if device else None
            )
            if not device or not allocation or allocation[0] != current["workspaceId"]:
                raise ServiceError(404, "Device is not assigned to this workspace")
            profile = json.loads(device["self_test"])
            if (
                asset.get("recipeVersion") != 3
                or asset["status"] not in ("REGISTERED", "READY")
                or device["status"] != "APPROVED"
                or self.store.profile(device["owner"])["accountStatus"] != "ACTIVE"
                or not profile.get("passed")
                or profile.get("recipeVersions") != [3]
                or coordinator_only(profile)
            ):
                raise ServiceError(409, "A ready v3 model and an approved v3 device are required")
            if time.time() - device["seen"] >= 30 or not device["enabled"] or not device["desired"]:
                raise ServiceError(409, "Reconnect the device and turn contribution ON")
            engine = engine or profile.get("noiseVersion", ENGINE_VERSION)
            if engine not in CPU_NOISE_FINGERPRINTS or noise_qualification(profile, engine):
                raise ServiceError(409, "Update and self-test selected device for the run's noise engine")
            resource = profile.get("gpuUUID")
            if not resource or has_device_reservation(db, device_id, resource):
                raise ServiceError(409, "Wait for confirmed physical GPU release")
            # A legacy reservation without physical identity may be an alias of this device.
            if any(
                not json.loads(r[0]).get("gpuUUID") and not coordinator_only(json.loads(r[0]))
                for r in repository.start_select_device_reservations(db, ())
            ):
                raise ServiceError(409, "Wait for legacy GPU ownership release")
            self.runtime.require_command(db, device_id, "QUALIFY_MODEL")
            self.runtime.require_command(db, device_id, "CANCEL_MODEL_QUALIFICATION")
            # references and qualifications are keyed by engine, and by decoder for the strict identity only
            key = qualification_key(engine, decoder)
            reference = self.reference(db, current["workspaceId"], asset["manifestHash"], key)
            if not reference:
                for row in repository.start_select_model_probe_jobs(db, (current["workspaceId"],)):
                    other = json.loads(row[0])
                    if (
                        other["manifestHash"] == asset["manifestHash"]
                        and other["status"] not in TERMINAL
                        and qualification_key(other.get("noiseEngineVersion", ENGINE_VERSION), other.get("decoder"))
                        == key
                    ):
                        raise ServiceError(409, "Wait for the first device to establish the model reference")
            job = {
                "jobId": uuid.uuid4().hex,
                "deviceId": device_id,
                "assetId": asset["id"],
                "workspaceId": current["workspaceId"],
                "ownerUserId": current["userId"],
                "manifestHash": asset["manifestHash"],
                "noiseEngineVersion": engine,
                **({"decoder": STRICT_DECODER} if key != engine else {}),
                "manifest": asset["manifest"],
                "source": asset["source"],
                "profileHash": canonical_json_hash(profile),
                "resourceId": resource,
                "mode": "COMPARE_REFERENCE" if reference else "BUILD_REFERENCE",
                "reference": json.loads(reference["body"]) if reference else None,
                "status": "PREPARING",
                "cancelRequested": False,
                "errorCode": None,
                "createdAt": time.time(),
            }
            repository.start_insert_model_probe_jobs(
                db, (job["jobId"], job["workspaceId"], asset["id"], device_id, json.dumps(job))
            )
            repository.start_insert_model_probe_reservations(db, (job["jobId"], device_id, resource))
            self.runtime.enqueue(
                db,
                device_id,
                "QUALIFY_MODEL",
                {
                    k: job[k]
                    for k in ("jobId", "mode", "manifest", "source", "reference", "noiseEngineVersion", "decoder")
                    if k in job
                },
                "model-probe:" + job["jobId"],
            )
            self.store.audit(db, current["userId"], "MODEL_QUALIFICATION_REQUESTED", job["jobId"], job["workspaceId"])
        return self.public(job)

    @staticmethod
    def public(job):
        return {
            k: job[k]
            for k in ("jobId", "deviceId", "assetId", "ownerUserId", "mode", "status", "errorCode", "createdAt")
        } | {
            "chunkMemory": job.get("chunkMemory"),
            "noiseEngineVersion": job.get("noiseEngineVersion", ENGINE_VERSION),
            "decoder": job.get("decoder", "hf_generate"),
        }

    def cancel(self, db, job):
        if job["status"] in TERMINAL:
            return
        job.update(cancelRequested=True, status="CANCELLING")
        self.save(db, job)
        self.runtime.enqueue(
            db,
            job["deviceId"],
            "CANCEL_MODEL_QUALIFICATION",
            {"jobId": job["jobId"]},
            "cancel-model-probe:" + job["jobId"],
        )

    def accept(self, db, device, reports):
        # Approval, workspace and boot opt-in can change while a probe is running. Cancellation never releases ownership.
        current = repository.accept_select_devices(db, (device["id"],)).fetchone()
        allocation = repository.accept_select_worker_assignments(db, (current["worker_id"],)).fetchone()
        for row in repository.accept_select_model_probe_jobs(db, (device["id"],)).fetchall():
            job = json.loads(row[0])
            if (
                current["status"] != "APPROVED"
                or not current["desired"]
                or not current["enabled"]
                or not allocation
                or allocation[0] != job["workspaceId"]
                or self.store.profile(current["owner"])["accountStatus"] != "ACTIVE"
            ):
                self.cancel(db, job)
        accepted = []
        for report in reports:
            encoded = report.model_dump()
            if len(json.dumps(encoded, allow_nan=False).encode()) > 250_000:
                raise ServiceError(413, "Model qualification report is too large")
            row = repository.accept_select_model_probe_jobs_2(db, (report.jobId, device["id"])).fetchone()
            if not row:
                continue
            job = json.loads(row[0])
            accepted.append(report.jobId)
            if job["status"] in TERMINAL:
                continue
            restore_failed = restore_mismatch(report)
            if restore_failed:
                repository.accept_update_devices(db, (device["id"],))
                self.store.cancel_selected(db, current["worker_id"])
                self.store.audit(db, "system", "DEVICE_RESTORE_MISMATCH", device["id"], job["workspaceId"])
            if report.processAlive is not False:
                job["status"] = (
                    "CANCELLING"
                    if job["cancelRequested"]
                    else ("DRAINING" if report.status in TERMINAL else report.status)
                )
                self.save(db, job)
                continue
            if restore_failed:
                job.update(status="FAILED", errorCode="RESTORE_MISMATCH")
            elif job["cancelRequested"] or report.status == "CANCELLED":
                job.update(status="CANCELLED", errorCode=None)
            elif report.status != "COMPLETED":
                job.update(status="FAILED", errorCode=report.errorCode or "MODEL_PROBE_FAILED")
            else:
                try:
                    if canonical_json_hash(json.loads(current["self_test"])) != job["profileHash"]:
                        raise ValueError("Native profile changed")
                    reference = report.reference if job["mode"] == "BUILD_REFERENCE" else job["reference"]
                    check_reference(reference, job["manifest"])
                    engine = qualification_key(job.get("noiseEngineVersion", ENGINE_VERSION), job.get("decoder"))
                    recipe = reference["cell"]["recipe"]
                    if qualification_key(recipe["noise"]["engine"], recipe["evaluation"]["decoder"]) != engine:
                        raise ValueError("Model reference noise engine or decoder differs")
                    evidence = verify_observations(reference, report.observations)
                    reference_hash = canonical_json_hash(reference)
                    old = self.reference(db, job["workspaceId"], job["manifestHash"], engine)
                    if old and old["reference_hash"] != reference_hash:
                        raise ValueError("Frozen reference changed")
                    engine_args = () if engine == ENGINE_VERSION else (engine,)
                    repository.accept_insert_model_references(
                        db,
                        (job["workspaceId"], job["manifestHash"], reference_hash, json.dumps(reference), *engine_args),
                        engine_args=engine_args,
                    )
                    repository.accept_insert_model_qualifications(
                        db,
                        (
                            device["id"],
                            job["workspaceId"],
                            job["manifestHash"],
                            job["profileHash"],
                            reference_hash,
                            json.dumps(evidence),
                            *engine_args,
                        ),
                        engine_args=engine_args,
                    )
                    job.update(status="COMPLETED", errorCode=None, chunkMemory=checked_memory(report.chunkMemory))
                except (ValueError, TypeError, KeyError):
                    job.update(status="FAILED", errorCode="MODEL_QUALIFICATION_MISMATCH")
            repository.accept_delete_model_probe_reservations(db, (job["jobId"],))
            self.save(db, job)
            self.store.audit(db, "system", "MODEL_QUALIFICATION_" + job["status"], job["jobId"], job["workspaceId"])
        return accepted


def checked_memory(value):
    """A device's chunk measurement as the lab keeps it; anything else is dropped (the qualification stands)."""
    from heteroes.product.chunk_memory import check

    try:
        return None if value is None else check(value)
    except ValueError:
        return None


def operations(registry, runtime, scoped, device_auth):
    service = runtime.qualifications

    def start(asset_id: str, body: ProbeRequest, *, current):
        return service.start(
            registry.get(asset_id, current["workspaceId"], "model"),
            body.deviceId,
            current,
            body.noiseEngineVersion,
            body.decoder,
        )

    def status(asset_id: str, *, current):
        asset = registry.get(asset_id, current["workspaceId"], "model")
        with registry.store.db() as db:
            reference = service.reference(db, current["workspaceId"], asset["manifestHash"])
            return {
                "referenceHash": reference["reference_hash"] if reference else None,
                "referenceHashesByNoiseEngine": {
                    key: row["reference_hash"]
                    for engine in CPU_NOISE_FINGERPRINTS
                    for key in (engine, qualification_key(engine, STRICT_DECODER))
                    if (row := service.reference(db, current["workspaceId"], asset["manifestHash"], key))
                },
                "jobs": [
                    service.public(json.loads(r[0])) for r in repository.status_select_model_probe_jobs(db, (asset_id,))
                ],
            }

    def cancel(asset_id: str, job_id: str, *, current):
        registry.get(asset_id, current["workspaceId"], "model")
        with registry.store.db() as db:
            row = repository.cancel_select_model_probe_jobs(db, (job_id, asset_id)).fetchone()
            if not row:
                raise ServiceError(404, "Model qualification not found")
            job = json.loads(row[0])
            if current["workspaceRole"] != "ADMIN" and current["userId"] != job["ownerUserId"]:
                raise ServiceError(403, "Only the requester or workspace admin may cancel this probe")
            service.cancel(db, job)
            return service.public(job)

    def transfer(body: dict, *, current):
        with registry.store.db() as db:
            row = repository.transfer_select_model_probe_jobs(db, (body.get("jobId"), current["id"])).fetchone()
            if not row:
                raise ServiceError(403, "Model probe is stale or not owned by this device")
            job = json.loads(row[0])
            if (
                job["cancelRequested"]
                or job["source"] != "UPLOAD"
                or current["status"] != "APPROVED"
                or not current["desired"]
                or body.get("sha256") not in job["manifest"]["files"].values()
            ):
                raise ServiceError(403, "File is outside the active model probe")
            if runtime.storage_backend is None:
                raise ServiceError(409, "Configure local artifact storage first")
            sha = body["sha256"]
            return {"url": runtime.storage_backend.download_url("objects/" + sha), "sha256": sha}

    return SimpleNamespace(start=start, status=status, cancel=cancel, transfer=transfer)
