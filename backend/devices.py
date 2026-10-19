"""CPU-only device control. Connectivity is never evidence of process death."""

from .constants import CORE_COMMAND_KINDS, COMMAND_KINDS

from .device_models import (
    command_capabilities,
    re_checkpoint,
    digest,
    SelfTest,
    EndpointUpdate,
    DeviceConfigurationUpdate,
    QualificationUpdate,
    Enrollment,
    Approval,
    Contribution,
    ProcessReport,
    Report,
    MonitoringEvent,
    GPUObservation,
    HostObservation,
    DiskObservation,
    TransportObservation,
    Telemetry,
    Poll,
    WorkerCommand,
)
from .agent_scheduling import AgentScheduling
from .agent_commands import AgentCommands
from .agent_polling import AgentPolling
from .migrations import initialize_agent_schema
from .policies import has_device_reservation, processes_drained
from .policies import set_disabled_workers, active_profile, platform_profile
from .config import load_config
import hashlib
import json
import os
import secrets
import time
import uuid

from fastapi import Depends, Header, HTTPException, Request
from .addresses import endpoint, is_private

from .constants import MODEL, REVISION, QUIESCENT
from heteroes.catalog import WORKLOAD_NAMES


class AgentRuntime(AgentScheduling, AgentCommands, AgentPolling):
    """Adapter for the existing product dispatcher; shared runtime imports stay CPU-only."""

    def __init__(self, storage_backend=None):
        self.store = None
        self.storage_backend = storage_backend

    def attach_store(self, store):
        self.store = store
        initialize_agent_schema(store)

    def devices(self, db=None):
        if self.store is None:
            return []
        if db is None:
            with self.store.db() as connection:
                return self.devices(connection)
        result = []
        for row in db.execute("SELECT * FROM devices ORDER BY rowid"):
            profile = json.loads(row["self_test"])
            reservation = db.execute(
                "SELECT a.run_id FROM device_reservations r JOIN assignments a ON a.id=r.assignment_id WHERE r.device_id=?",
                (row["id"],),
            ).fetchone()
            if not reservation and profile.get("gpuUUID"):
                reservation = db.execute(
                    "SELECT a.run_id FROM physical_reservations r JOIN assignments a ON a.id=r.assignment_id WHERE r.resource_id=?",
                    (profile["gpuUUID"],),
                ).fetchone()
            allocation = db.execute(
                "SELECT workspace_id FROM worker_assignments WHERE worker_id=?", (row["worker_id"],)
            ).fetchone()
            result.append(
                {
                    "deviceId": row["id"],
                    "workerId": row["worker_id"],
                    "ownerUserId": row["owner"],
                    "displayName": row["name"],
                    "approvalStatus": row["status"],
                    "bootId": row["boot_id"],
                    "lastSeen": row["seen"],
                    "connectionStatus": "ONLINE" if time.time() - row["seen"] < 30 else "OFFLINE",
                    "contributionEnabled": bool(row["enabled"] and row["desired"]),
                    "workspaceId": allocation[0] if allocation else None,
                    "computeUrl": row["compute_url"],
                    "bulkUrl": row["bulk_url"] or row["compute_url"],
                    "selfTest": profile,
                    "allocatedTo": reservation[0] if reservation else None,
                    "physicalResourceId": profile.get("gpuUUID"),
                    "telemetry": json.loads(row["telemetry"]) if row["telemetry"] else None,
                    "telemetryHistory": [
                        json.loads(h[0])
                        for h in db.execute(
                            "SELECT body FROM device_telemetry_history WHERE device_id=? ORDER BY received_at DESC LIMIT 60",
                            (row["id"],),
                        ).fetchall()
                    ][::-1],
                }
            )
        return result

    def capabilities(self):
        return {
            "controlApiVersion": 2,
            "recipeVersions": [1, 2],
            "physicalGpuIdentity": True,
            "parallelJobs": True,
            "modelId": MODEL,
            "modelRevision": REVISION,
            "workerIds": [d["workerId"] for d in self.devices() if d["approvalStatus"] == "APPROVED"],
            "workloads": list(WORKLOAD_NAMES),
            "schedulerPolicies": ["greedy"],
            "syncModes": ["synchronous"],
            "quarantinedWorkerIds": [d["workerId"] for d in self.devices() if d["approvalStatus"] == "QUARANTINED"],
            "maxRunSeconds": None,
            "telemetry": True,
            "pauseResume": True,
            "unsupported": ["change-workers", "model-upload", "dataset-upload", "asynchronous"],
        }

    def public_compute_url(self):
        """The lab's public compute address, read per command so a new Quick URL is used at once.
        Only a public HTTPS host name is passed on; anything else is ignored."""
        root = os.environ.get("HETEROES_PRIVATE_CONFIG")
        if not root:
            return None
        try:
            value = load_config(root).get("publicComputeUrl")
            return endpoint(value) if value and not is_private(value) else None
        except (OSError, ValueError, TypeError):
            return None

    def workers(self):
        return [
            {
                **d,
                "status": d["connectionStatus"],
                "host": d["computeUrl"],
                "profile": {
                    **d["selfTest"],
                    **(
                        {
                            "vramFreeMb": max(
                                0, d["telemetry"]["gpu"]["vramTotalMb"] - d["telemetry"]["gpu"]["vramUsedMb"]
                            )
                        }
                        if d.get("telemetry")
                        and d["telemetry"].get("gpu")
                        and d["telemetry"]["gpu"].get("vramTotalMb") is not None
                        and d["telemetry"]["gpu"].get("vramUsedMb") is not None
                        else {}
                    ),
                },
                "temperatureC": (d.get("telemetry") or {}).get("gpu", {}).get("temperatureC")
                if (d.get("telemetry") or {}).get("gpu")
                else None,
                "utilizationPercent": (d.get("telemetry") or {}).get("gpu", {}).get("utilizationPercent")
                if (d.get("telemetry") or {}).get("gpu")
                else None,
                "admissionStatus": "APPROVED" if d["approvalStatus"] == "APPROVED" else "PENDING_VERIFICATION",
            }
            for d in self.devices()
        ]

    def snapshot(self, run_id):
        with self.store.db() as db:
            row = db.execute(
                "SELECT snapshot,released FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", (run_id,)
            ).fetchone()
            if not row:
                raise FileNotFoundError(run_id)
            snap = json.loads(row[0])
            if not row[1] and snap["state"]["status"] in QUIESCENT:
                snap["state"] = {
                    **snap["state"],
                    "status": "PAUSING" if snap["state"]["status"] == "PAUSED" else "DRAINING",
                }
            return snap

    def runs(self):
        if not self.store:
            return []
        with self.store.db() as db:
            return [
                {
                    "runId": r["run_id"],
                    "assignmentId": r["id"],
                    "epoch": r["epoch"],
                    "status": json.loads(r["snapshot"])["state"]["status"]
                    if r["released"]
                    else self.snapshot(r["run_id"])["state"]["status"],
                }
                for r in db.execute("SELECT * FROM assignments ORDER BY rowid")
            ]

    def artifact(self, run_id, name):
        import base64

        snapshot = self.store.snapshot(run_id)
        content = snapshot.get("artifactContents", {}).get(name)
        if content:
            data = base64.b64decode(content["base64"], validate=True)
            if hashlib.sha256(data).hexdigest() != content["sha256"]:
                raise HTTPException(409, "Cached artifact checksum mismatch")
            return iter([data])
        storage = getattr(self, "storage", None)
        if storage and re_checkpoint(name):
            for point in storage.points(run_id):
                if point["status"] == "READY" and any(
                    v["sha256"] == name[:-4] for v in storage.manifest(point["pointId"])["files"].values()
                ):
                    return storage.backend.get("objects/" + name[:-4])
        raise HTTPException(409, "Artifact cloud sync is pending or the local source is unavailable")


def install_device_routes(app, store, user, runtime):
    def active(current):
        return active_profile(store, current)

    def admin(current=Depends(user)):
        p = active(current)
        return platform_profile(p)

    def device_auth(request: Request, authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Device authentication required")
        with store.db() as db:
            row = db.execute("SELECT * FROM devices WHERE token_digest=?", (digest(authorization[7:]),)).fetchone()
            if not row:
                raise HTTPException(401, "Device revoked or unknown")
            if row["status"] in ("REVOKED", "QUARANTINED") or store.profile(row["owner"])["accountStatus"] != "ACTIVE":
                drain = request.url.path == "/api/v1/device/poll"
                if request.url.path == "/api/v1/device/worker-command":
                    drain = bool(
                        db.execute(
                            "SELECT 1 FROM assignments WHERE coordinator=? AND released=0", (row["id"],)
                        ).fetchone()
                    )
                if not drain:
                    raise HTTPException(401, "Device revoked or unknown")
            return dict(row)

    @app.post("/api/v1/devices/pairing-codes")
    def pairing(current=Depends(user)):
        active(current)
        code = secrets.token_urlsafe(24)
        with store.db() as db:
            db.execute(
                "INSERT INTO pairing_codes VALUES (?,?,?,0)", (digest(code), current["userId"], time.time() + 600)
            )
        return {"code": code, "expiresInSeconds": 600}

    @app.post("/api/v1/device/enroll", status_code=201)
    def enroll(body: Enrollment):
        with store.db() as db:
            code = db.execute("SELECT * FROM pairing_codes WHERE digest=?", (digest(body.code),)).fetchone()
            if not code or code["used"] or code["expires"] <= time.time():
                raise HTTPException(409, "Pairing code used or expired")
            if store.profile(code["owner"])["accountStatus"] != "ACTIVE":
                raise HTTPException(403, "Owner access revoked")
            if db.execute("SELECT 1 FROM devices WHERE worker_id=?", (body.workerId,)).fetchone():
                raise HTTPException(409, "Worker alias already enrolled")
            legacy = db.execute("SELECT owner FROM worker_assignments WHERE worker_id=?", (body.workerId,)).fetchone()
            if legacy and legacy[0] != code["owner"]:
                raise HTTPException(403, "Worker alias belongs to another owner")
            did = uuid.uuid4().hex
            token = secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO devices(id,worker_id,owner,name,token_digest,status,compute_url,bulk_url,self_test) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    did,
                    body.workerId,
                    code["owner"],
                    body.displayName,
                    digest(token),
                    "PENDING",
                    body.computeUrl,
                    body.bulkUrl,
                    json.dumps(body.selfTest.model_dump()),
                ),
            )
            db.execute("UPDATE pairing_codes SET used=1 WHERE digest=?", (digest(body.code),))
            db.execute("INSERT OR IGNORE INTO worker_assignments VALUES (?,?,NULL)", (body.workerId, code["owner"]))
            store.audit(db, code["owner"], "DEVICE_ENROLLED", did)
            return {"deviceId": did, "workerId": body.workerId, "deviceToken": token, "approvalStatus": "PENDING"}

    @app.get("/api/v1/devices")
    def own_devices(current=Depends(user)):
        active(current)
        return [d for d in runtime.devices() if d["ownerUserId"] == current["userId"]]

    def update_endpoints(device_id, body, owner, boot_id=None, self_test=None):
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            d = db.execute("SELECT * FROM devices WHERE id=? AND owner=?", (device_id, owner)).fetchone()
            if not d:
                raise HTTPException(404, "Owned device not found")
            if boot_id is not None and d["boot_id"] != boot_id:
                raise HTTPException(409, "Current boot required")
            resource = json.loads(d["self_test"]).get("gpuUUID")
            reserved = has_device_reservation(db, device_id, resource)
            processes = json.loads(d["processes"])
            if d["enabled"] or d["desired"] or reserved or not processes_drained(processes):
                raise HTTPException(
                    409, "Turn contribution OFF and confirm all processes drained before changing endpoints"
                )
            if self_test is not None:
                old = json.loads(d["self_test"])
                if (
                    not self_test.passed
                    or self_test.gpuUUID != old.get("gpuUUID")
                    or self_test.platform != old.get("platform", "linux")
                    or (self_test.coordinator and (self_test.platform != "linux" or self_test.vramTotalMb < 11000))
                ):
                    raise HTTPException(
                        422, "Role change requires a qualified Linux coordinator and the same physical GPU"
                    )
                db.execute("UPDATE devices SET self_test=? WHERE id=?", (json.dumps(self_test.model_dump()), device_id))
            db.execute(
                "UPDATE devices SET compute_url=?,bulk_url=? WHERE id=?", (body.computeUrl, body.bulkUrl, device_id)
            )
            store.audit(db, owner, "DEVICE_ENDPOINTS_CHANGED", device_id)
        return next(d for d in runtime.devices() if d["deviceId"] == device_id)

    @app.patch("/api/v1/devices/{device_id}/endpoints")
    def owned_endpoints(device_id: str, body: EndpointUpdate, current=Depends(user)):
        return update_endpoints(device_id, body, active(current)["userId"])

    @app.patch("/api/v1/devices/{device_id}/configuration")
    def owned_configuration(device_id: str, body: DeviceConfigurationUpdate, current=Depends(user)):
        return update_endpoints(device_id, body, active(current)["userId"], self_test=body.selfTest)

    @app.patch("/api/v1/device/qualification")
    def qualification(body: QualificationUpdate, current=Depends(device_auth)):
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            d = db.execute("SELECT * FROM devices WHERE id=?", (current["id"],)).fetchone()
            old = json.loads(d["self_test"])
            if (
                d["boot_id"] != body.bootId
                or d["enabled"]
                or d["desired"]
                or has_device_reservation(db, d["id"], old.get("gpuUUID"))
            ):
                raise HTTPException(409, "Current boot, OFF and confirmed drain required")
            if (
                not body.selfTest.passed
                or body.selfTest.gpuUUID != old.get("gpuUUID")
                or body.selfTest.platform != old.get("platform", "linux")
            ):
                raise HTTPException(422, "Qualification cannot replace physical identity or platform")
            db.execute("UPDATE devices SET self_test=? WHERE id=?", (json.dumps(body.selfTest.model_dump()), d["id"]))
            store.audit(db, d["owner"], "DEVICE_QUALIFICATION_UPDATED", d["id"])
        return {"updated": True}

    @app.get("/api/v1/platform/devices")
    def devices(current=Depends(admin)):
        return runtime.devices()

    @app.patch("/api/v1/platform/devices/{device_id}")
    def approve(device_id: str, body: Approval, current=Depends(admin)):
        with store.db() as db:
            d = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
            if not d:
                raise HTTPException(404, "Device not found")
            if body.approved:
                if d["status"] == "QUARANTINED":
                    raise HTTPException(
                        409, "Restore mismatch quarantine requires investigation and fresh compatibility evidence"
                    )
                if d["status"] == "REVOKED":
                    raise HTTPException(409, "Re-enroll with a new device alias after revocation")
                if not json.loads(d["self_test"])["passed"]:
                    raise HTTPException(409, "Self-test must pass")
                if (
                    not body.workspaceId
                    or not db.execute(
                        "SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?", (body.workspaceId, d["owner"])
                    ).fetchone()
                ):
                    raise HTTPException(422, "Owner must belong to target workspace")
                if has_device_reservation(db, device_id):
                    raise HTTPException(409, "Device is reserved")
                db.execute('UPDATE devices SET status="APPROVED" WHERE id=?', (device_id,))
                db.execute(
                    "UPDATE worker_assignments SET workspace_id=? WHERE worker_id=?", (body.workspaceId, d["worker_id"])
                )
                disabled = store.disabled_workers(db)
                disabled.discard(d["worker_id"])
                set_disabled_workers(db, disabled)
            else:
                store.cancel_selected(db, d["worker_id"])
                for row in db.execute(
                    "SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=?",
                    (device_id,),
                ).fetchall():
                    runtime.cancel(row[0], db=db)
                db.execute('UPDATE devices SET status="REVOKED",enabled=0,desired=0 WHERE id=?', (device_id,))
            store.audit(
                db,
                current["userId"],
                "DEVICE_APPROVAL" if body.approved else "DEVICE_REVOKED",
                device_id,
                body.workspaceId,
            )
        return next(d for d in runtime.devices() if d["deviceId"] == device_id)

    @app.delete("/api/v1/platform/devices/{device_id}", status_code=204)
    def remove_device(device_id: str, current=Depends(admin)):
        # A revoked (or never approved) device stays listed forever otherwise. Approved devices must be revoked first, and a
        # device that still holds a reservation or is under restore quarantine is never removed. The audit log keeps the history.
        with store.db() as db:
            d = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
            if not d:
                raise HTTPException(404, "Device not found")
            if d["status"] == "QUARANTINED":
                raise HTTPException(409, "Restore mismatch quarantine requires investigation before removal")
            if d["status"] not in ("REVOKED", "PENDING"):
                raise HTTPException(409, "Revoke the device before removing it")
            if has_device_reservation(db, device_id):
                raise HTTPException(409, "Device is reserved")
            for table in ("device_commands", "device_telemetry_history", "device_reports"):
                db.execute(f"DELETE FROM {table} WHERE device_id=?", (device_id,))
            db.execute("DELETE FROM devices WHERE id=?", (device_id,))
            if not db.execute("SELECT 1 FROM devices WHERE worker_id=?", (d["worker_id"],)).fetchone():
                db.execute("DELETE FROM worker_assignments WHERE worker_id=?", (d["worker_id"],))
            store.audit(db, current["userId"], "DEVICE_REMOVED", device_id)

    @app.post("/api/v1/devices/{device_id}/contribution")
    def contribution(device_id: str, body: Contribution, current=Depends(user)):
        p = active(current)
        with store.db() as db:
            d = db.execute("SELECT * FROM devices WHERE id=? AND owner=?", (device_id, p["userId"])).fetchone()
            if not d:
                raise HTTPException(404, "Owned device not found")
            if d["status"] != "APPROVED" or d["boot_id"] != body.bootId:
                raise HTTPException(409, "Approval and current boot identity required")
            db.execute("UPDATE devices SET desired=? WHERE id=?", (body.enabled, device_id))
            runtime.enqueue(
                db,
                device_id,
                "SET_CONTRIBUTION",
                {"enabled": body.enabled, "bootId": body.bootId},
                "contribution:" + uuid.uuid4().hex,
            )
            if not body.enabled:
                store.cancel_selected(db, d["worker_id"])
                for row in db.execute(
                    "SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=?",
                    (device_id,),
                ).fetchall():
                    runtime.cancel(row[0], db=db)
            store.audit(db, p["userId"], "DEVICE_ON" if body.enabled else "DEVICE_OFF", device_id)
        return {"deviceId": device_id, "enabled": body.enabled, "pending": True}

    @app.post("/api/v1/device/poll")
    def poll(
        body: Poll,
        current=Depends(device_auth),
        capabilities: str | None = Header(default=None, alias="X-HeteroES-Agent-Commands"),
    ):
        return runtime.poll(current, body, command_kinds=command_capabilities(capabilities))

    @app.post("/api/v1/device/worker-command")
    def worker(body: WorkerCommand, current=Depends(device_auth)):
        if (
            current["status"] in ("REVOKED", "QUARANTINED")
            or store.profile(current["owner"])["accountStatus"] != "ACTIVE"
        ) and body.action not in ("poll", "stop"):
            raise HTTPException(401, "Revoked coordinators may only confirm or stop their existing workers")
        return runtime.worker_command(current, body)

    return device_auth


__all__ = [
    "AgentRuntime",
    "command_capabilities",
    "re_checkpoint",
    "digest",
    "SelfTest",
    "EndpointUpdate",
    "DeviceConfigurationUpdate",
    "QualificationUpdate",
    "Enrollment",
    "Approval",
    "Contribution",
    "ProcessReport",
    "Report",
    "MonitoringEvent",
    "GPUObservation",
    "HostObservation",
    "DiskObservation",
    "TransportObservation",
    "Telemetry",
    "Poll",
    "WorkerCommand",
]
