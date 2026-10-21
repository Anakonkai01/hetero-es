import json

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse


from fastapi import APIRouter

# What a device's agent says about a command it could not finish. Unlike the coordinator's events these never reach the
# run snapshot, and a run that is still STARTING has no snapshot at all.
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


def install_routes(app, store, runtime, scoped, visible, authorized):
    router = APIRouter()

    @router.get("/api/v1/experiments/{run_id}/generations")
    def generations(run_id: str, current=Depends(scoped)):
        authorized(run_id, current)
        return store.snapshot(run_id)["generations"]

    @router.get("/api/v1/experiments/{run_id}/generations/{generation_id}")
    def generation(run_id: str, generation_id: str, current=Depends(scoped)):
        value = next((value for value in generations(run_id, current) if value["generationId"] == generation_id), None)
        if not value:
            raise HTTPException(404, "Generation not found")
        return value

    def lookup(identifier, key, collection, current):
        run_id = identifier.split(".", 1)[0]
        authorized(run_id, current)
        value = next((item for item in store.snapshot(run_id)[collection] if item[key] == identifier), None)
        if not value:
            raise HTTPException(404, "Object not found")
        return value

    @router.get("/api/v1/generations/{generation_id}/candidates")
    def candidates(generation_id: str, current=Depends(scoped)):
        run_id = generation_id.split(".", 1)[0]
        authorized(run_id, current)
        return [item for item in store.snapshot(run_id)["candidates"] if item["generationId"] == generation_id]

    @router.get("/api/v1/candidates/{candidate_id}")
    def candidate(candidate_id: str, current=Depends(scoped)):
        return lookup(candidate_id, "candidateId", "candidates", current)

    @router.get("/api/v1/attempts/{attempt_id}")
    def attempt(attempt_id: str, current=Depends(scoped)):
        return lookup(attempt_id, "attemptId", "attempts", current)

    @router.get("/api/v1/events")
    def event_list(experimentId: str | None = None, limit: int = 2000, current=Depends(scoped)):
        """The newest events of the visible runs (or of one). Every read happens in ONE database session: the store
        serializes sessions, and during a busy run the agents' polls hold it; one session per run made this list wait
        behind them for minutes (HTTP 524 at the public edge, GSM8K demo tier 2)."""
        from datetime import datetime, timezone

        limit = max(1, min(limit, 2000))
        runs = [run["experimentId"] for run in visible(current) if experimentId in (None, run["experimentId"])]
        if experimentId and not runs:
            raise HTTPException(404, "Experiment not found")
        with store.db() as db:
            snapshots = {
                row["id"]: json.loads(row["snapshot"]) if row["snapshot"] else {"events": []}
                for row in db.execute(
                    f"SELECT id,snapshot FROM experiments WHERE id IN ({','.join('?' * len(runs))})", runs
                )
            }
            device = {}
            for row in db.execute(
                "SELECT a.run_id,m.sequence,m.body FROM monitoring_events m JOIN assignments a ON a.id=m.assignment_id "
                f"WHERE a.run_id IN ({','.join('?' * len(runs))}) AND json_extract(m.body,'$.event') IN (?,?) "
                "ORDER BY m.sequence",
                (*runs, *DEVICE_EVENTS),
            ):
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

    @router.get("/api/v1/artifacts")
    def artifact_list(current=Depends(scoped)):
        return [item for run in visible(current) for item in store.snapshot(run["experimentId"])["artifacts"]]

    @router.get("/api/v1/artifacts/{artifact_id}/download")
    def download(artifact_id: str, current=Depends(scoped)):
        artifact = lookup(artifact_id, "artifactId", "artifacts", current)
        return StreamingResponse(
            runtime.artifact(artifact["experimentId"], artifact["name"]),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{artifact["name"]}"'},
        )

    @router.get("/api/v1/audit")
    def audit(current=Depends(scoped)):
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
                for row in db.execute(
                    "SELECT * FROM audit WHERE workspace_id=? ORDER BY sequence DESC LIMIT 100",
                    (current["workspaceId"],),
                )
                if current["workspaceRole"] == "ADMIN" or row["actor"] == current["userId"]
            ]

    app.include_router(router)
