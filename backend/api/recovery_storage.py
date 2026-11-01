"""Recovery_Storage HTTP adapters."""

from ..core.storage_models import Begin, Finish
from fastapi import Depends, Request, Response
from fastapi.responses import RedirectResponse
from fastapi import APIRouter
from ..services.recovery_storage import operations


def install_routes(app, store, storage, device_auth, user, scoped, authorized):
    service = operations(store, storage, device_auth, user, scoped, authorized)
    router = APIRouter()

    @app.post("/api/v1/device/recovery-points")
    def begin(body: Begin, current=Depends(device_auth)):
        return service.begin(body=body, current=current)

    @app.post("/api/v1/device/recovery-points/complete-object")
    def complete(body: Finish, current=Depends(device_auth)):
        return service.complete(body=body, current=current)

    @app.post("/api/v1/device/recovery-points/{point_id}/verify")
    def verify(point_id: str, body: dict, current=Depends(device_auth)):
        return service.verify(point_id=point_id, body=body, current=current)

    @app.get("/api/v1/device/recovery-points/{point_id}")
    def device_status(point_id: str, current=Depends(device_auth)):
        return service.device_status(point_id=point_id, current=current)

    @app.delete("/api/v1/device/recovery-points/{point_id}")
    def abandon(point_id: str, body: dict, current=Depends(device_auth)):
        return service.abandon(point_id=point_id, body=body, current=current)

    @app.post("/api/v1/experiments/{run_id}/recovery-import")
    def import_begin(run_id: str, body: dict, current=Depends(scoped)):
        return service.import_begin(run_id=run_id, body=body, current=current)

    @app.post("/api/v1/experiments/{run_id}/recovery-import/complete-object")
    def import_complete(run_id: str, body: dict, current=Depends(scoped)):
        return service.import_complete(run_id=run_id, body=body, current=current)

    @app.post("/api/v1/experiments/{run_id}/recovery-import/{point_id}/verify")
    def import_verify(run_id: str, point_id: str, current=Depends(scoped)):
        return service.import_verify(run_id=run_id, point_id=point_id, current=current)

    @app.get("/api/v1/experiments/{run_id}/recovery-points")
    def points(run_id: str, current=Depends(scoped)):
        return service.points(run_id=run_id, current=current)

    @app.post("/api/v1/recovery-points/{point_id}/download-plan")
    def download_plan(point_id: str, current=Depends(scoped)):
        return service.download_plan(point_id=point_id, current=current)

    @app.delete("/api/v1/recovery-points/{point_id}")
    def delete(point_id: str, current=Depends(scoped)):
        return service.delete(point_id=point_id, current=current)

    @app.post("/api/v1/artifacts/{artifact_id}/download-ticket")
    def ticket(artifact_id: str, response: Response, request: Request, current=Depends(scoped)):
        result = service.ticket(
            artifact_id=artifact_id, token=request.headers.get("Authorization", "")[7:], current=current
        )
        path = result["downloadUrl"]
        response.set_cookie(
            "heteroes-cloud-download",
            result["secret"],
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            path=path,
            max_age=60,
        )
        return {"downloadUrl": path}

    @app.get("/api/v1/cloud-downloads/{ticket_digest}")
    def consume(ticket_digest: str, request: Request):
        url = service.consume(ticket_digest=ticket_digest, secret=request.cookies.get("heteroes-cloud-download", ""))
        response = RedirectResponse(url, status_code=303)
        response.delete_cookie("heteroes-cloud-download", path="/api/v1/cloud-downloads/" + ticket_digest)
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.include_router(router)
