"""History business operations; HTTP responses stay in api/."""

import json
from types import SimpleNamespace
from ..core.errors import ServiceError
from ..repositories.history import HistoryRepository as repository

DEVICE_EVENTS = ("agent_command_failed", "agent_command_deferred")


def severity(name):
    if "error" in name or "failed" in name:
        return "ERROR"
    if "unavailable" in name or "unknown" in name or "deferred" in name:
        return "WARNING"
    return "INFO"


def message(event):
    phrase = event["event"].replace("_", " ")
    if event["event"] in DEVICE_EVENTS:
        return event.get("reason", phrase)
    return event.get("error", phrase)


def operations(store, runtime, scoped, visible, authorized):
    def generations(run_id: str, *, current):
        authorized(run_id, current)
        return store.snapshot(run_id)["generations"]

    def generation(run_id: str, generation_id: str, *, current):
        value = next(
            (value for value in generations(run_id, current=current) if value["generationId"] == generation_id), None
        )
        if not value:
            raise ServiceError(404, "Generation not found")
        return value

    def lookup(identifier, key, collection, current):
        run_id = identifier.split(".", 1)[0]
        authorized(run_id, current)
        value = next((item for item in store.snapshot(run_id)[collection] if item[key] == identifier), None)
        if not value:
            raise ServiceError(404, "Object not found")
        return value

    def candidates(generation_id: str, *, current):
        run_id = generation_id.split(".", 1)[0]
        authorized(run_id, current)
        return [item for item in store.snapshot(run_id)["candidates"] if item["generationId"] == generation_id]

    def candidate(candidate_id: str, *, current):
        return lookup(candidate_id, "candidateId", "candidates", current)

    def attempt(attempt_id: str, *, current):
        return lookup(attempt_id, "attemptId", "attempts", current)

    def event_list(experimentId: str | None = None, limit: int = 2000, *, current):
        """The newest events of the visible runs (or of one). Every read happens in ONE database session: the store
        serializes sessions, and during a busy run the agents' polls hold it; one session per run made this list wait
        behind them for minutes (HTTP 524 at the public edge, GSM8K demo tier 2)."""
        from datetime import datetime, timezone

        limit = max(1, min(limit, 2000))
        runs = [run["experimentId"] for run in visible(current) if experimentId in (None, run["experimentId"])]
        if experimentId and not runs:
            raise ServiceError(404, "Experiment not found")
        with store.db() as db:
            snapshots = {
                row["id"]: json.loads(row["snapshot"]) if row["snapshot"] else {"events": []}
                for row in repository.event_list_select_experiments(db, runs, runs=runs)
            }
            device = {}
            for row in repository.event_list_select_monitoring_events(db, (*runs, *DEVICE_EVENTS), runs=runs):
                device.setdefault(row["run_id"], []).append((f"m{row['sequence']}", json.loads(row["body"])))
        result = []
        for run_id in runs:
            events = [(f"e{index}", event) for index, event in enumerate(snapshots.get(run_id, {}).get("events", []))]
            for key, event in events + device.get(run_id, []):
                result.append(
                    {
                        "eventId": f"{run_id}.{key}",
                        "experimentId": run_id,
                        "timestamp": datetime.fromtimestamp(event.get("t", 0), timezone.utc).isoformat(),
                        "eventType": event["event"],
                        "severity": severity(event["event"]),
                        "message": message(event),
                        "workerId": event.get("worker_id"),
                        "candidateId": event.get("uiCandidateId"),
                        "generationId": f"{run_id}.g{event['generation']}" if "generation" in event else None,
                        "details": event,
                    }
                )
        return sorted(result, key=lambda item: item["timestamp"])[-limit:]

    def artifact_list(*, current):
        return [item for run in visible(current) for item in store.snapshot(run["experimentId"])["artifacts"]]

    def audit(*, current):
        with store.db() as db:
            return [
                {
                    "auditId": str(row["sequence"]),
                    "workspaceId": row["workspace_id"],
                    "actorUserId": row["actor"],
                    "action": row["action"],
                    "targetId": row["target"],
                    "createdAt": row["created"],
                }
                for row in repository.audit_select_audit(db, (current["workspaceId"],))
                if current["workspaceRole"] == "ADMIN" or row["actor"] == current["userId"]
            ]

    return SimpleNamespace(
        generations=generations,
        generation=generation,
        lookup=lookup,
        candidates=candidates,
        candidate=candidate,
        attempt=attempt,
        event_list=event_list,
        artifact_list=artifact_list,
        audit=audit,
    )
