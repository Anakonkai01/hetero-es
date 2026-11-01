"""Devices business operations; HTTP responses stay in api/."""

from ..core.device_models import (
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
    DeviceContribution,
    ContributionPreference,
    DeviceName,
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
from ..agent_scheduling import AgentScheduling
from ..agent_commands import AgentCommands
from ..agent_polling import AgentPolling
from ..model_qualification import ModelQualifications
from ..db.migrations import initialize_agent_schema
from ..policies import has_device_reservation, processes_drained
from ..policies import set_disabled_workers, active_profile, platform_profile
from ..config import load_config
import hashlib
import json
import os
import secrets
import time
import uuid
from ..addresses import endpoint, is_private
from ..core.constants import MODEL, REVISION, QUIESCENT
from heteroes.product.cpu_coordinator import coordinator_only
from heteroes.catalog import SCHEDULER_POLICIES, SYNC_MODES, WORKLOAD_NAMES
from types import SimpleNamespace
from ..core.errors import ServiceError
from ..repositories.devices import DevicesRepository as repository
from ..db.transactions import begin_write


class AgentRuntime(AgentScheduling, AgentCommands, AgentPolling):
    """Adapter for the existing product dispatcher; shared runtime imports stay CPU-only."""

    def __init__(self, storage_backend=None):
        self.store = None
        self.storage_backend = storage_backend
        self.qualifications = ModelQualifications(self)

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
        for row in repository.devices_select_devices(db, ()):
            profile = json.loads(row["self_test"])
            reservation = repository.devices_select_device_reservations(db, (row["id"],)).fetchone()
            if not reservation and profile.get("gpuUUID"):
                reservation = repository.devices_select_physical_reservations(db, (profile["gpuUUID"],)).fetchone()
            allocation = repository.devices_select_worker_assignments(db, (row["worker_id"],)).fetchone()
            probe = repository.devices_select_model_probe_reservations(
                db, (row["id"], profile.get("gpuUUID"))
            ).fetchone()
            profile = self.qualifications.effective_profile(
                db, row["id"], profile, allocation[0] if allocation else None
            )
            block = {}
            if reservation:
                snapshot = repository.devices_select_experiments(db, (reservation[0],)).fetchone()
                if snapshot and snapshot[0]:
                    states = (json.loads(snapshot[0]).get("state") or {}).get("workerStates", {})
                    block = states.get(row["worker_id"], {})
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
                    "contributionDesired": bool(row["desired"]),
                    "keepContributionAfterReboot": bool(row["keep_on"]),
                    "workspaceId": allocation[0] if allocation else None,
                    "computeUrl": row["compute_url"],
                    "bulkUrl": row["bulk_url"] or row["compute_url"],
                    "selfTest": profile,
                    "allocatedTo": reservation[0] if reservation else ("qualification:" + probe[0] if probe else None),
                    "physicalResourceId": profile.get("gpuUUID"),
                    "stopReason": block.get("stopReason"),
                    "blockedRunId": reservation[0] if reservation and block.get("stopReason") else None,
                    "telemetry": json.loads(row["telemetry"]) if row["telemetry"] else None,
                    "telemetryHistory": [
                        json.loads(h[0])
                        for h in repository.devices_select_device_telemetry_history(db, (row["id"],)).fetchall()
                    ][::-1],
                }
            )
        return result

    def capabilities(self):
        return {
            "controlApiVersion": 2,
            "recipeVersions": [1, 2, 3],
            "physicalGpuIdentity": True,
            "parallelJobs": True,
            "modelId": MODEL,
            "modelRevision": REVISION,
            "workerIds": [
                d["workerId"]
                for d in self.devices()
                if d["approvalStatus"] == "APPROVED" and not coordinator_only(d["selfTest"])
            ],
            "workloads": list(WORKLOAD_NAMES),
            "schedulerPolicies": list(SCHEDULER_POLICIES),
            "syncModes": list(SYNC_MODES),
            "quarantinedWorkerIds": [d["workerId"] for d in self.devices() if d["approvalStatus"] == "QUARANTINED"],
            "maxRunSeconds": None,
            "telemetry": True,
            "pauseResume": True,
            "unsupported": ["model-upload", "dataset-upload"],
        }

    def public_web_url(self):
        """The lab's public HTTPS address (it carries small dataset files to devices without the private route)."""
        root = os.environ.get("HETEROES_PRIVATE_CONFIG")
        if not root:
            return None
        try:
            value = load_config(root).get("publicWebUrl")
            return endpoint(value) if value and not is_private(value) else None
        except (OSError, ValueError, TypeError):
            return None

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
            if not coordinator_only(d["selfTest"])
        ]

    def snapshot(self, run_id):
        with self.store.db() as db:
            row = repository.snapshot_select_assignments(db, (run_id,)).fetchone()
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
                for r in repository.runs_select_assignments(db, ())
            ]

    def artifact(self, run_id, name):
        import base64

        snapshot = self.store.snapshot(run_id)
        content = snapshot.get("artifactContents", {}).get(name)
        if content:
            data = base64.b64decode(content["base64"], validate=True)
            if hashlib.sha256(data).hexdigest() != content["sha256"]:
                raise ServiceError(409, "Cached artifact checksum mismatch")
            return iter([data])
        storage = getattr(self, "storage", None)
        if storage and re_checkpoint(name):
            for point in storage.points(run_id):
                if point["status"] == "READY" and any(
                    v["sha256"] == name[:-4] for v in storage.manifest(point["pointId"])["files"].values()
                ):
                    return storage.backend.get("objects/" + name[:-4])
        raise ServiceError(409, "Artifact cloud sync is pending or the local source is unavailable")


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


def operations(store, user, runtime):
    def active(current):
        return active_profile(store, current)

    def admin(*, current):
        p = active(current)
        return platform_profile(p)

    def authenticate_device(token, purpose):
        with store.db() as db:
            row = repository.authenticate_device_select_devices(db, (digest(token),)).fetchone()
            if not row:
                raise ServiceError(401, "Device revoked or unknown")
            if row["status"] in ("REVOKED", "QUARANTINED") or store.profile(row["owner"])["accountStatus"] != "ACTIVE":
                drain = purpose == "poll"
                if purpose == "worker-command":
                    drain = bool(repository.authenticate_device_select_assignments(db, (row["id"],)).fetchone())
                if not drain:
                    raise ServiceError(401, "Device revoked or unknown")
            return dict(row)

    def pairing(*, current):
        active(current)
        code = secrets.token_urlsafe(24)
        with store.db() as db:
            repository.pairing_insert_pairing_codes(db, (digest(code), current["userId"], time.time() + 600))
        return {"code": code, "expiresInSeconds": 600}

    def enroll(body: Enrollment):
        with store.db() as db:
            code = repository.enroll_select_pairing_codes(db, (digest(body.code),)).fetchone()
            if not code or code["used"] or code["expires"] <= time.time():
                raise ServiceError(409, "Pairing code used or expired")
            if store.profile(code["owner"])["accountStatus"] != "ACTIVE":
                raise ServiceError(403, "Owner access revoked")
            if repository.enroll_select_devices(db, (body.workerId,)).fetchone():
                raise ServiceError(409, "Worker alias already enrolled")
            legacy = repository.enroll_select_worker_assignments(db, (body.workerId,)).fetchone()
            if legacy and legacy[0] != code["owner"]:
                raise ServiceError(403, "Worker alias belongs to another owner")
            did = uuid.uuid4().hex
            token = secrets.token_urlsafe(32)
            repository.enroll_insert_devices(
                db,
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
            repository.enroll_update_pairing_codes(db, (digest(body.code),))
            repository.enroll_insert_worker_assignments(db, (body.workerId, code["owner"]))
            store.audit(db, code["owner"], "DEVICE_ENROLLED", did)
            return {"deviceId": did, "workerId": body.workerId, "deviceToken": token, "approvalStatus": "PENDING"}

    def own_devices(*, current):
        active(current)
        return [d for d in runtime.devices() if d["ownerUserId"] == current["userId"]]

    def update_endpoints(device_id, body, owner, boot_id=None, self_test=None):
        with store.db() as db:
            begin_write(db)
            d = repository.update_endpoints_select_devices(db, (device_id, owner)).fetchone()
            if not d:
                raise ServiceError(404, "Owned device not found")
            if boot_id is not None and d["boot_id"] != boot_id:
                raise ServiceError(409, "Current boot required")
            resource = json.loads(d["self_test"]).get("gpuUUID")
            reserved = has_device_reservation(db, device_id, resource)
            processes = json.loads(d["processes"])
            if d["enabled"] or d["desired"] or reserved or not processes_drained(processes):
                raise ServiceError(
                    409, "Turn contribution OFF and confirm all processes drained before changing endpoints"
                )
            if self_test is not None:
                old = json.loads(d["self_test"])
                if (
                    not self_test.passed
                    or self_test.gpuUUID != old.get("gpuUUID")
                    or self_test.platform != old.get("platform", "linux")
                ):
                    raise ServiceError(
                        422, "Role change requires a passed self-test and the same physical GPU and platform"
                    )
                repository.update_endpoints_update_devices_2(db, (json.dumps(self_test.model_dump()), device_id))
            repository.update_endpoints_update_devices(db, (body.computeUrl, body.bulkUrl, device_id))
            store.audit(db, owner, "DEVICE_ENDPOINTS_CHANGED", device_id)
        return next(d for d in runtime.devices() if d["deviceId"] == device_id)

    def owned_endpoints(device_id: str, body: EndpointUpdate, *, current):
        return update_endpoints(device_id, body, active(current)["userId"])

    def owned_configuration(device_id: str, body: DeviceConfigurationUpdate, *, current):
        return update_endpoints(device_id, body, active(current)["userId"], self_test=body.selfTest)

    def qualification(body: QualificationUpdate, *, current):
        with store.db() as db:
            begin_write(db)
            d = repository.qualification_select_devices(db, (current["id"],)).fetchone()
            old = json.loads(d["self_test"])
            if d["boot_id"] == body.bootId and body.selfTest.model_dump() == old:
                # an app started again sends the evidence the lab already holds: nothing changes, even while reserved
                return {"updated": False}
            if (
                d["boot_id"] != body.bootId
                or d["enabled"]
                or d["desired"]
                or has_device_reservation(db, d["id"], old.get("gpuUUID"))
            ):
                raise ServiceError(409, "Current boot, OFF and confirmed drain required")
            if (
                not body.selfTest.passed
                or body.selfTest.gpuUUID != old.get("gpuUUID")
                or body.selfTest.platform != old.get("platform", "linux")
            ):
                raise ServiceError(422, "Qualification cannot replace physical identity or platform")
            repository.qualification_update_devices(db, (json.dumps(body.selfTest.model_dump()), d["id"]))
            store.audit(db, d["owner"], "DEVICE_QUALIFICATION_UPDATED", d["id"])
        return {"updated": True}

    def devices(*, current):
        # approval puts a device into a workspace of its OWNER (approve() checks the membership): list them
        with store.db() as db:
            owned = {}
            for row in repository.devices_select_memberships(db, ()):
                owned.setdefault(row[0], []).append({"workspaceId": row[1], "name": row[2]})
        return [{**d, "ownerWorkspaces": owned.get(d["ownerUserId"], [])} for d in runtime.devices()]

    def approve(device_id: str, body: Approval, *, current):
        with store.db() as db:
            d = repository.approve_select_devices(db, (device_id,)).fetchone()
            if not d:
                raise ServiceError(404, "Device not found")
            if body.approved:
                if d["status"] == "QUARANTINED":
                    raise ServiceError(
                        409, "Restore mismatch quarantine requires investigation and fresh compatibility evidence"
                    )
                if d["status"] == "REVOKED":
                    raise ServiceError(409, "Re-enroll with a new device alias after revocation")
                if not json.loads(d["self_test"])["passed"]:
                    raise ServiceError(409, "Self-test must pass")
                if (
                    not body.workspaceId
                    or not repository.approve_select_memberships(db, (body.workspaceId, d["owner"])).fetchone()
                ):
                    raise ServiceError(422, "Owner must belong to target workspace")
                if has_device_reservation(db, device_id):
                    raise ServiceError(409, "Device is reserved")
                repository.approve_update_devices(db, (device_id,))
                repository.approve_update_worker_assignments(db, (body.workspaceId, d["worker_id"]))
                disabled = store.disabled_workers(db)
                disabled.discard(d["worker_id"])
                set_disabled_workers(db, disabled)
            else:
                store.cancel_selected(db, d["worker_id"])
                for row in repository.approve_select_assignments(db, (device_id,)).fetchall():
                    runtime.cancel(row[0], db=db)
                repository.approve_update_devices_2(db, (device_id,))
            store.audit(
                db,
                current["userId"],
                "DEVICE_APPROVAL" if body.approved else "DEVICE_REVOKED",
                device_id,
                body.workspaceId,
            )
        return next(d for d in runtime.devices() if d["deviceId"] == device_id)

    def remove(db, d, actor):
        # A device that still holds a reservation or is under restore quarantine is never removed. The audit log keeps
        # the history.
        if d["status"] == "QUARANTINED":
            raise ServiceError(409, "Restore mismatch quarantine requires investigation before removal")
        if has_device_reservation(db, d["id"]):
            raise ServiceError(409, "Device is reserved")
        for table in ("device_commands", "device_telemetry_history", "device_reports"):
            repository.remove_delete_value(db, (d["id"],), table=table)
        repository.remove_delete_devices(db, (d["id"],))
        if not repository.remove_select_devices(db, (d["worker_id"],)).fetchone():
            repository.remove_delete_worker_assignments(db, (d["worker_id"],))
        store.audit(db, actor, "DEVICE_REMOVED", d["id"])

    def remove_device(device_id: str, *, current):
        # A revoked (or never approved) device stays listed forever otherwise. Approved devices must be revoked first.
        with store.db() as db:
            d = repository.remove_device_select_devices(db, (device_id,)).fetchone()
            if not d:
                raise ServiceError(404, "Device not found")
            if d["status"] not in ("REVOKED", "PENDING", "QUARANTINED"):
                raise ServiceError(409, "Revoke the device before removing it")
            remove(db, d, current["userId"])

    def managed(db, device_id, current):
        """A device its owner or a platform administrator may rename or delete; to anyone else it does not exist."""
        p = active(current)
        d = repository.managed_select_devices(db, (device_id,)).fetchone()
        if not d or (d["owner"] != p["userId"] and not p.get("platformAdmin")):
            raise ServiceError(404, "Device not found")
        return d, p

    def rename(device_id: str, body: DeviceName, *, current):
        with store.db() as db:
            d, p = managed(db, device_id, current)
            name = body.displayName.strip() or d["name"]
            repository.rename_update_devices(db, (name, device_id))
            store.audit(db, p["userId"], "DEVICE_RENAMED", device_id)
        return {"deviceId": device_id, "displayName": name}

    def delete_device(device_id: str, *, current):
        """Revoke and remove in one step (owner 2026-10-22): its credential stops working and it leaves every list.
        Never while a run holds it, which would cancel that run: it is turned OFF or the run ends first."""
        with store.db() as db:
            d, p = managed(db, device_id, current)
            if has_device_reservation(db, device_id):
                raise ServiceError(409, "Device is in a run: turn it OFF or wait for the run to end, then delete it")
            if d["status"] == "APPROVED":
                store.cancel_selected(db, d["worker_id"])
                repository.delete_device_update_devices(db, (device_id,))
                store.audit(db, p["userId"], "DEVICE_REVOKED", device_id)
            remove(db, d, p["userId"])

    def set_contribution(db, d, enabled, boot_id, keep, actor):
        repository.set_contribution_update_devices(db, (enabled, d["id"]))
        if keep is not None:
            repository.set_contribution_update_devices_2(db, (keep, d["id"]))
        runtime.enqueue(
            db,
            d["id"],
            "SET_CONTRIBUTION",
            {"enabled": enabled, "bootId": boot_id},
            "contribution:" + uuid.uuid4().hex,
        )
        if not enabled:
            left = runtime.leave_on_disable(db, d)  # a worker of a run with others leaves it (ADR-009)
            store.cancel_selected(db, d["worker_id"], include_queued=False, keep=left)
            for row in repository.set_contribution_select_assignments(db, (d["id"],)).fetchall():
                if row[0] not in left:
                    runtime.cancel(row[0], db=db)
        store.audit(db, actor, "DEVICE_ON" if enabled else "DEVICE_OFF", d["id"])
        return {"deviceId": d["id"], "enabled": enabled, "pending": True}

    def contribution(device_id: str, body: Contribution, *, current):
        p = active(current)
        with store.db() as db:
            d = repository.contribution_select_devices(db, (device_id, p["userId"])).fetchone()
            if not d:
                raise ServiceError(404, "Owned device not found")
            if d["status"] != "APPROVED" or d["boot_id"] != body.bootId:
                raise ServiceError(409, "Approval and current boot identity required")
            return set_contribution(db, d, body.enabled, body.bootId, body.keepAfterReboot, p["userId"])

    def contribution_preference(device_id: str, body: ContributionPreference, *, current):
        # only the choice for future restarts: the current boot's ON/OFF and its runs are untouched
        p = active(current)
        with store.db() as db:
            d = repository.contribution_preference_select_devices(db, (device_id, p["userId"])).fetchone()
            if not d:
                raise ServiceError(404, "Owned device not found")
            repository.contribution_preference_update_devices(db, (body.keepAfterReboot, device_id))
            store.audit(db, p["userId"], "DEVICE_KEEP_ON" if body.keepAfterReboot else "DEVICE_KEEP_OFF", device_id)
        return {"deviceId": device_id, "keepAfterReboot": body.keepAfterReboot}

    def own_contribution(body: DeviceContribution, *, current):
        # the machine's own command line: an approved device turns itself ON or OFF; the audit names the device
        with store.db() as db:
            d = repository.own_contribution_select_devices(db, (current["id"],)).fetchone()
            if d["status"] != "APPROVED" or not d["boot_id"]:
                raise ServiceError(409, "Approval and a running agent required")
            return set_contribution(db, d, body.enabled, d["boot_id"], body.keepAfterReboot, "device:" + d["id"])

    def own_name(body: DeviceName, *, current):
        with store.db() as db:
            repository.own_name_update_devices(db, (body.displayName.strip() or current["name"], current["id"]))
            store.audit(db, "device:" + current["id"], "DEVICE_RENAMED", current["id"])
        return {"deviceId": current["id"], "displayName": body.displayName.strip() or current["name"]}

    def forget_self(*, current):
        """The machine leaves the lab (`heteroes-worker forget`): its token stops working. Never while it holds work."""
        with store.db() as db:
            d = repository.forget_self_select_devices(db, (current["id"],)).fetchone()
            if has_device_reservation(db, d["id"]) or d["enabled"] or not processes_drained(json.loads(d["processes"])):
                raise ServiceError(409, "Turn contribution OFF and wait for its work to stop first")
            repository.forget_self_update_devices(db, (d["id"],))
            store.audit(db, "device:" + d["id"], "DEVICE_LEFT_LAB", d["id"])

    def own_summary(*, current):
        """What the machine's command line shows: its name, approval, contribution and the run it takes part in."""
        with store.db() as db:
            d = repository.own_summary_select_devices(db, (current["id"],)).fetchone()
            runs = []
            for row in repository.own_summary_select_assignments(db, (d["id"],)):
                body = store.get(row["run_id"]) or {}
                snapshot = json.loads(row["snapshot"])
                runs.append(
                    {
                        "experimentId": row["run_id"],
                        "name": body.get("name"),
                        "status": body.get("status"),
                        "role": "coordinator" if row["coordinator"] == d["id"] else "worker",
                        "completedGenerations": snapshot.get("completedGenerationCount"),
                        "maxGenerations": body.get("maxGenerations"),
                    }
                )
        return {
            "deviceId": d["id"],
            "workerId": d["worker_id"],
            "displayName": d["name"],
            "approvalStatus": d["status"],
            "contributionDesired": bool(d["desired"]),
            "contributionEnabled": bool(d["enabled"] and d["desired"]),
            "keepContributionAfterReboot": bool(d["keep_on"]),
            "runs": runs,
        }

    def poll(body: Poll, *, current, capabilities: str | None):
        return runtime.poll(current, body, command_kinds=command_capabilities(capabilities))

    def worker(body: WorkerCommand, *, current):
        if (
            current["status"] in ("REVOKED", "QUARANTINED")
            or store.profile(current["owner"])["accountStatus"] != "ACTIVE"
        ) and body.action not in ("poll", "stop"):
            raise ServiceError(401, "Revoked coordinators may only confirm or stop their existing workers")
        return runtime.worker_command(current, body)

    return SimpleNamespace(
        active=active,
        admin=admin,
        authenticate_device=authenticate_device,
        pairing=pairing,
        enroll=enroll,
        own_devices=own_devices,
        update_endpoints=update_endpoints,
        owned_endpoints=owned_endpoints,
        owned_configuration=owned_configuration,
        qualification=qualification,
        devices=devices,
        approve=approve,
        remove=remove,
        remove_device=remove_device,
        managed=managed,
        rename=rename,
        delete_device=delete_device,
        set_contribution=set_contribution,
        contribution=contribution,
        contribution_preference=contribution_preference,
        own_contribution=own_contribution,
        own_name=own_name,
        forget_self=forget_self,
        own_summary=own_summary,
        poll=poll,
        worker=worker,
    )
