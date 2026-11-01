"""Experiments HTTP adapters."""

from ..request_models import BackupPolicy, Configuration, MembershipRequest
from fastapi import Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from fastapi import APIRouter
from ..services.experiments import operations


def install_routes(app, store, runtime, scoped, visible, authorized, validate, *, service_scoped=None):
    service = operations(store, runtime, service_scoped or scoped, visible, authorized, validate)
    router = APIRouter()

    @router.get("/api/v1/experiments")
    def experiments(current=Depends(scoped)):
        return service.experiments(current=current)

    @router.post("/api/v1/experiments")
    def create(body: Configuration, current=Depends(scoped)):
        return service.create(body=body, current=current)

    @router.get("/api/v1/experiments/{run_id}")
    def experiment(run_id: str, current=Depends(scoped)):
        return service.experiment(run_id=run_id, current=current)

    @router.get("/api/v1/experiments/{run_id}/timeline")
    def run_timeline(run_id: str, current=Depends(scoped)):
        return service.run_timeline(run_id=run_id, current=current)

    @router.get("/api/v1/experiments/{run_id}/stream")
    def run_stream(run_id: str, current=Depends(scoped)):
        authorized(run_id, current)
        if not app.state.live.acquire():
            raise HTTPException(429, "Too many live views are open. Close one and try again.")
        return StreamingResponse(
            app.state.live.frames(store, run_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    @router.patch("/api/v1/experiments/{run_id}")
    def edit(run_id: str, request: dict, current=Depends(scoped)):
        return service.edit(run_id=run_id, request=request, current=current)

    @router.post("/api/v1/experiments/{run_id}/submit")
    def submit(run_id: str, current=Depends(scoped)):
        return service.submit(run_id=run_id, current=current)

    @router.post("/api/v1/experiments/{run_id}/cancel")
    def cancel(run_id: str, current=Depends(scoped)):
        return service.cancel(run_id=run_id, current=current)

    @router.delete("/api/v1/experiments/{run_id}", status_code=204)
    def archive(run_id: str, current=Depends(scoped)):
        service.archive(run_id=run_id, current=current)
        return Response(status_code=204)

    @router.post("/api/v1/experiments/{run_id}/pause")
    def pause(run_id: str, current=Depends(scoped)):
        return service.pause(run_id=run_id, current=current)

    @router.post("/api/v1/experiments/{run_id}/resume")
    def resume(run_id: str, current=Depends(scoped)):
        return service.resume(run_id=run_id, current=current)

    @router.patch("/api/v1/experiments/{run_id}/backup-policy")
    def backup_policy(run_id: str, policy: BackupPolicy, current=Depends(scoped)):
        return service.backup_policy(run_id=run_id, policy=policy, current=current)

    @router.post("/api/v1/experiments/{run_id}/workers")
    def members(run_id: str, request: MembershipRequest, current=Depends(scoped)):
        """Add or remove a worker while the experiment runs (ADR-009); it applies at the next generation boundary."""
        return service.members(run_id=run_id, request=request, current=current)

    @router.get("/api/v1/queue")
    def queue(current=Depends(scoped)):
        return service.queue(current=current)

    app.include_router(router)
