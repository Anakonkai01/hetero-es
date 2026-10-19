from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse


from fastapi import APIRouter


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
    def event_list(current=Depends(scoped)):
        from datetime import datetime, timezone

        result = []
        for run in visible(current):
            for index, event in enumerate(store.snapshot(run["experimentId"])["events"]):
                result.append(
                    {
                        "eventId": f"{run['experimentId']}.e{index}",
                        "experimentId": run["experimentId"],
                        "timestamp": datetime.fromtimestamp(event.get("t", 0), timezone.utc).isoformat(),
                        "eventType": event["event"],
                        "severity": "ERROR"
                        if "error" in event["event"]
                        else "WARNING"
                        if "unavailable" in event["event"] or "unknown" in event["event"]
                        else "INFO",
                        "message": event.get("error", event["event"].replace("_", " ")),
                        "workerId": event.get("worker_id"),
                        "candidateId": event.get("uiCandidateId"),
                        "generationId": f"{run['experimentId']}.g{event['generation']}"
                        if "generation" in event
                        else None,
                        "details": event,
                    }
                )
        return sorted(result, key=lambda item: item["timestamp"])[-2000:]

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
