"""Inventory business operations; HTTP responses stay in api/."""

from .policies import storage_status
from ..core.config import load_config
import json
import os
from ..core.constants import ACTIVE
from types import SimpleNamespace
from ..core.errors import ServiceError
from ..repositories.inventory import InventoryRepository as repository


def _private_config():
    private_root = os.environ.get("HETEROES_PRIVATE_CONFIG")
    if not private_root:
        return {}
    try:
        return load_config(private_root)
    except (OSError, ValueError):
        return {}


def operations(store, runtime, scoped, visible, capabilities, registry):
    def health():
        # Quick URLs can rotate while this CPU service retains its identity.
        ui_url = _private_config().get("publicWebUrl") or os.environ.get("HETEROES_UI_URL")
        backend = getattr(runtime, "storage_backend", None)
        return {
            "ok": True,
            "dataSource": "real",
            "runtimeIssue": store.last_error,
            # Shipped r10 apps require these protocol capability fields.
            "agentMode": True,
            "deviceConfiguration": True,
            "recipeVersions": [1, 2, 3],
            **storage_status(runtime),
            "serverInstanceId": getattr(runtime, "server_instance_id", None),
            **({"uiUrl": ui_url} if ui_url else {}),
            # the private lab address is for signed-in members only: see /api/v1/capabilities (SECURITY-NOTES)
        }

    def get_capabilities(*, current):
        cap = capabilities()
        assigned = set(store.assignments(current["workspaceId"], include_disabled=True))
        coordinators = [
            {
                "deviceId": d["deviceId"],
                "workerId": d["workerId"],
                "displayName": d["displayName"],
                "platform": d["selfTest"].get("platform", "linux"),
                # measured by the device's self-test: the form shows seconds per generation from it
                "updateSecondsPerSeed": d["selfTest"].get("updateSecondsPerSeed"),
            }
            for d in runtime.devices()
            if d["workspaceId"] == current["workspaceId"]
            and d["approvalStatus"] == "APPROVED"
            and d["selfTest"]["coordinator"]
        ]
        with store.db() as db:
            row = repository.get_capabilities_select_workspace_settings(db, (current["workspaceId"],)).fetchone()
        default = row[0] if row else None
        private = _private_config()
        return {
            **cap,
            "workerIds": [w for w in store.assignments(current["workspaceId"]) if w in cap["workerIds"]],
            "coordinatorDevices": coordinators,
            # the lab's default, only while it is still an approved coordinator here
            "defaultCoordinatorDeviceId": default if any(d["deviceId"] == default for d in coordinators) else None,
            "quarantinedWorkerIds": [w for w in cap.get("quarantinedWorkerIds", []) if w in assigned],
            # the private lab address, for members (moved here from the public health check, SECURITY-NOTES)
            **({"privateLabUrl": private.get("bulkApiUrl", private["apiUrl"])} if private.get("apiUrl") else {}),
        }

    def resources(*, current):
        with store.db() as db:
            members = [
                {
                    "user": {
                        k: v
                        for k, v in json.loads(row["profile"]).items()
                        if k not in ("platformAdmin", "accountStatus")
                    },
                    "role": row["role"],
                }
                for row in repository.resources_select_memberships(db, (current["workspaceId"],))
            ]
        assigned = set(store.assignments(current["workspaceId"], include_disabled=True))
        busy = list(
            {worker for run in store.list() if run["status"] in ACTIVE for worker in run["workerIds"]} & assigned
        )
        return {"members": members, "busyWorkerIds": busy, "reservedWorkerIds": busy}

    def models(*, current):
        cap = capabilities()
        return [
            {
                "modelArtifactId": "qwen-pinned",
                "workspaceId": current["workspaceId"],
                "ownerUserId": "runtime",
                "name": cap["modelId"],
                "reference": cap["modelId"],
                "revision": cap["modelRevision"],
                "source": "REFERENCE",
                "status": "REGISTERED",
            }
        ] + registry.list(current["workspaceId"], "model")

    def workers(*, current):
        try:
            values = runtime.workers()
        except Exception:
            raise ServiceError(503, "Worker registry unavailable") from None
        # Shared GPU ownership is visible; another participant's experiment details are private.
        permitted = {body["experimentId"] for body in visible(current)}
        assigned = set(store.assignments(current["workspaceId"], include_disabled=True))
        enabled = set(store.assignments(current["workspaceId"]))
        return [
            {
                **value,
                "contributionEnabled": value["workerId"] in enabled and value.get("contributionEnabled", True),
                "allocatedTo": value.get("allocatedTo")
                if value.get("allocatedTo") in permitted
                else "Workspace pool busy"
                if value.get("allocatedTo")
                else None,
            }
            for value in values
            if value["workerId"] in assigned
        ]

    def worker(worker_id: str, *, current):
        value = next((value for value in workers(current=current) if value["workerId"] == worker_id), None)
        if not value:
            raise ServiceError(404, "Worker not found")
        return value

    def datasets(*, current):
        return registry.list(current["workspaceId"], "dataset")

    return SimpleNamespace(
        health=health,
        get_capabilities=get_capabilities,
        resources=resources,
        models=models,
        workers=workers,
        worker=worker,
        datasets=datasets,
    )
