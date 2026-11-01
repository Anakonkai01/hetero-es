"""Fresh account/workspace authorization and application state views."""

from .policies import active_profile, platform_profile
from ..core.errors import ServiceError


class AccessService:
    def __init__(self, store, runtime):
        self.store, self.runtime = store, runtime

    def scope(self, current, workspace_id: str):
        profile = active_profile(self.store, current, "Your account must be active to access lab resources")
        membership = next(
            (w for w in self.store.workspaces(current["userId"]) if w["workspaceId"] == workspace_id), None
        )
        if not membership:
            raise ServiceError(403, "Select a workspace you belong to")
        return {**profile, "workspaceId": workspace_id, "workspaceRole": membership["role"]}

    def visible(self, current):
        return [
            body
            for body in self.store.list()
            if not body.get("archivedAt")
            and body["workspaceId"] == current["workspaceId"]
            and (current["workspaceRole"] == "ADMIN" or body["ownerUserId"] == current["userId"])
        ]

    def authorized(self, run_id, current):
        body = self.store.get(run_id)
        current = self.scope(current, current["workspaceId"])
        if (
            not body
            or body.get("archivedAt")
            or body["workspaceId"] != current["workspaceId"]
            or (current["workspaceRole"] != "ADMIN" and body["ownerUserId"] != current["userId"])
        ):
            raise ServiceError(404, "Experiment not found")
        return body

    def capabilities(self):
        try:
            value = self.runtime.capabilities()
            self.store.ensure_workers(value["workerIds"])
            return value
        except Exception:
            raise ServiceError(503, "Runtime control service unavailable") from None

    def active(self, current):
        return active_profile(self.store, current, "Your account is awaiting approval or is restricted")

    def platform(self, current):
        return platform_profile(current, "Platform administrator permission required")

    def workspace_admin(self, workspace_id, current):
        fresh = self.scope(current, workspace_id)
        if fresh["workspaceRole"] != "ADMIN":
            raise ServiceError(403, "Workspace administrator permission required")
        return fresh
