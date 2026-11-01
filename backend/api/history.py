"""History HTTP adapters."""

from fastapi import Depends
from fastapi.responses import StreamingResponse
from fastapi import APIRouter
from ..services.history import operations


def install_routes(app, store, runtime, scoped, visible, authorized):
    service = operations(store, runtime, scoped, visible, authorized)
    router = APIRouter()
    lookup = service.lookup

    @router.get("/api/v1/experiments/{run_id}/generations")
    def generations(run_id: str, current=Depends(scoped)):
        return service.generations(run_id=run_id, current=current)

    @router.get("/api/v1/experiments/{run_id}/generations/{generation_id}")
    def generation(run_id: str, generation_id: str, current=Depends(scoped)):
        return service.generation(run_id=run_id, generation_id=generation_id, current=current)

    @router.get("/api/v1/generations/{generation_id}/candidates")
    def candidates(generation_id: str, current=Depends(scoped)):
        return service.candidates(generation_id=generation_id, current=current)

    @router.get("/api/v1/candidates/{candidate_id}")
    def candidate(candidate_id: str, current=Depends(scoped)):
        return service.candidate(candidate_id=candidate_id, current=current)

    @router.get("/api/v1/attempts/{attempt_id}")
    def attempt(attempt_id: str, current=Depends(scoped)):
        return service.attempt(attempt_id=attempt_id, current=current)

    @router.get("/api/v1/events")
    def event_list(experimentId: str | None = None, limit: int = 2000, current=Depends(scoped)):
        """The newest events of the visible runs (or of one). Every read happens in ONE database session: the store
        serializes sessions, and during a busy run the agents' polls hold it; one session per run made this list wait
        behind them for minutes (HTTP 524 at the public edge, GSM8K demo tier 2)."""
        return service.event_list(experimentId=experimentId, limit=limit, current=current)

    @router.get("/api/v1/artifacts")
    def artifact_list(current=Depends(scoped)):
        return service.artifact_list(current=current)

    @router.get("/api/v1/artifacts/{artifact_id}/download")
    def download(artifact_id: str, current=Depends(scoped)):
        artifact = lookup(artifact_id, "artifactId", "artifacts", current)
        return StreamingResponse(
            runtime.artifact(artifact["experimentId"], artifact["name"]),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'''attachment; filename="{artifact["name"]}"'''},
        )

    @router.get("/api/v1/audit")
    def audit(current=Depends(scoped)):
        return service.audit(current=current)

    app.include_router(router)
