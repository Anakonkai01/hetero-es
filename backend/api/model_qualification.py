"""Model_Qualification HTTP adapters."""

from ..core.study_models import ProbeRequest
from fastapi import Depends
from fastapi import APIRouter
from ..services.model_qualification import operations


def install_routes(app, registry, runtime, scoped, device_auth):
    service = operations(registry, runtime, scoped, device_auth)
    router = APIRouter()

    @app.post("/api/v1/models/{asset_id}/qualifications", status_code=201)
    def start(asset_id: str, body: ProbeRequest, current=Depends(scoped)):
        return service.start(asset_id=asset_id, body=body, current=current)

    @app.get("/api/v1/models/{asset_id}/qualifications")
    def status(asset_id: str, current=Depends(scoped)):
        return service.status(asset_id=asset_id, current=current)

    @app.post("/api/v1/models/{asset_id}/qualifications/{job_id}/cancel")
    def cancel(asset_id: str, job_id: str, current=Depends(scoped)):
        return service.cancel(asset_id=asset_id, job_id=job_id, current=current)

    @app.post("/api/v1/device/model-transfer")
    def transfer(body: dict, current=Depends(device_auth)):
        return service.transfer(body=body, current=current)

    app.include_router(router)
